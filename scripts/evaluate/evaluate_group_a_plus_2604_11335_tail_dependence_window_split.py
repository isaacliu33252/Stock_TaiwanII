#!/usr/bin/env python3
"""Window-split tail-dependence diagnostics for arXiv:2604.11335."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.build_group_a_plus_2607_16450_tail_dependence_monitor import (
    DEFAULT_TICKERS,
    _load_close,
    _tail_metrics,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_tail_dependence_window_split.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_tail_dependence_window_split.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_11335_tail_dependence_window_split/history"

WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("full_available", "2018-01-02", "2026-08-28"),
    ("trade_war_2018", "2018-01-02", "2018-12-28"),
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("rate_hike_2022", "2022-01-03", "2022-12-30"),
    ("recent_2024_2026", "2024-01-02", "2026-08-28"),
)


def build_window_split(
    *,
    db_path: Path = DB_PATH,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    alpha: float = 0.10,
    windows: tuple[tuple[str, str, str], ...] = WINDOWS,
    high_tail_dependence_threshold: float = 0.65,
) -> dict[str, Any]:
    blockers: list[str] = []
    rows: list[dict[str, Any]] = []
    if not db_path.exists():
        blockers.append("stock_database_missing")
    for label, start, end in windows:
        if blockers:
            rows.append({"label": label, "start": start, "end": end, "status": "blocked", "pairs": []})
            continue
        close = _load_close(db_path, tickers, start, end)
        if close.empty or base not in close.columns:
            rows.append({"label": label, "start": start, "end": end, "status": "missing_prices", "pairs": []})
            continue
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
        available = tuple(col for col in tickers if col in returns.columns and returns[col].notna().sum() >= 30)
        pairs = [
            _tail_metrics(returns[list(available)], base=base, asset=asset, alpha=alpha)
            for asset in available
            if asset != base
        ]
        rows.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "status": "available",
                "observations": int(len(returns)),
                "available_tickers": list(available),
                "pairs": pairs,
            }
        )

    high_00631l_windows = []
    high_00679b_windows = []
    positive_00632r_lower_tail_windows = []
    for row in rows:
        for pair in row.get("pairs", []):
            value = pair.get("lower_tail_dependence_proxy")
            if not isinstance(value, (int, float)):
                continue
            if pair.get("asset") == "00631L.TW" and value >= high_tail_dependence_threshold:
                high_00631l_windows.append(row["label"])
            if pair.get("asset") == "00679B.TWO" and value >= high_tail_dependence_threshold:
                high_00679b_windows.append(row["label"])
            if pair.get("asset") == "00632R.TW" and value > 0.0:
                positive_00632r_lower_tail_windows.append(row["label"])

    valid_rows = [row for row in rows if row.get("status") == "available"]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_11335_tail_dependence_window_split",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "policy": "research_shadow_only_no_live_weight_change",
        "source_paper": "2604.11335v1",
        "parameters": {
            "tickers": list(tickers),
            "base": base,
            "alpha": alpha,
            "high_tail_dependence_threshold": high_tail_dependence_threshold,
        },
        "rows": rows,
        "summary": {
            "valid_windows": len(valid_rows),
            "high_00631l_windows": high_00631l_windows,
            "high_00679b_windows": high_00679b_windows,
            "positive_00632r_lower_tail_windows": sorted(set(positive_00632r_lower_tail_windows)),
            "00631l_high_tail_dependence_all_windows": bool(valid_rows)
            and len(set(high_00631l_windows)) == len(valid_rows),
            "00679b_high_tail_dependence_any_window": bool(high_00679b_windows),
        },
        "decision": {
            "window_split_complete": True,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_tail_dependence": False,
            "allow_00632r_open_from_tail_dependence": False,
            "allow_00679b_add_from_tail_dependence": False,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": blockers,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 2604.11335 Tail Dependence Window Split",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Summary",
        "",
        f"- Valid windows: `{payload['summary']['valid_windows']}`",
        f"- High `00631L.TW` windows: `{payload['summary']['high_00631l_windows']}`",
        f"- High `00679B.TWO` windows: `{payload['summary']['high_00679b_windows']}`",
        f"- Positive `00632R.TW` lower-lower windows: `{payload['summary']['positive_00632r_lower_tail_windows']}`",
        f"- Promote to live: `{payload['decision']['promote_to_live']}`",
        "",
        "## Rows",
        "",
        "| Window | Asset | Lower-tail proxy | Co-exceedance days | Correlation |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in payload["rows"]:
        for pair in row.get("pairs", []):
            lines.append(
                "| {window} | {asset} | {tail} | {co} | {corr} |".format(
                    window=row["label"],
                    asset=pair.get("asset"),
                    tail=pair.get("lower_tail_dependence_proxy"),
                    co=pair.get("co_exceedance_days"),
                    corr=pair.get("linear_correlation"),
                )
            )
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path) -> Path:
    return history_dir / "2604_11335_tail_dependence_window_split_20260828.json"


def write_outputs(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    payload = build_window_split(db_path=Path(args.db))
    write_outputs(payload, Path(args.output), Path(args.output_md), None if args.no_history else Path(args.history_dir))
    print(f"2604.11335 tail-dependence window split: {Path(args.output).resolve()}")
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "decision": payload["decision"]}, indent=2))


if __name__ == "__main__":
    main()
