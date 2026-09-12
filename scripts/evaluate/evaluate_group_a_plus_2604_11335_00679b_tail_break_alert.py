#!/usr/bin/env python3
"""00679B tail-dependence break alert inspired by arXiv:2604.11335."""

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
    _rolling_snapshots,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_00679b_tail_break_alert.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_00679b_tail_break_alert.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_11335_00679b_tail_break_alert/history"


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _extract_asset_series(snapshots: list[dict[str, Any]], asset: str) -> list[tuple[str, float]]:
    series: list[tuple[str, float]] = []
    for snapshot in snapshots:
        date = str(snapshot.get("date"))
        for row in snapshot.get("pairs", []):
            if row.get("asset") != asset:
                continue
            value = row.get("lower_tail_dependence_proxy")
            if isinstance(value, (int, float)) and np.isfinite(float(value)):
                series.append((date, float(value)))
    return series


def _summarize_break(
    series: list[tuple[str, float]],
    *,
    recent_snapshots: int,
    elevated_threshold: float,
    break_delta_threshold: float,
) -> dict[str, Any]:
    if not series:
        return {"status": "insufficient_data", "observations": 0}
    values = [value for _date, value in series]
    latest_date, latest = series[-1]
    recent = values[-recent_snapshots:] if len(values) > recent_snapshots else values[max(0, len(values) // 2) :]
    baseline = values[:-recent_snapshots] if len(values) > recent_snapshots else values[: max(1, len(values) // 2)]
    recent_mean = float(np.mean(recent)) if recent else float(np.mean(values))
    baseline_mean = float(np.mean(baseline)) if baseline else float(np.mean(values))
    latest_minus_baseline = latest - baseline_mean
    recent_minus_baseline = recent_mean - baseline_mean
    latest_break = latest >= elevated_threshold and latest_minus_baseline >= break_delta_threshold
    recent_break = recent_mean >= elevated_threshold and recent_minus_baseline >= break_delta_threshold
    return {
        "status": "available",
        "observations": len(series),
        "latest_date": latest_date,
        "latest_lower_tail_dependence_proxy": _float(latest),
        "baseline_mean": _float(baseline_mean),
        "recent_mean": _float(recent_mean),
        "latest_minus_baseline": _float(latest_minus_baseline),
        "recent_minus_baseline": _float(recent_minus_baseline),
        "min": _float(np.min(values)),
        "max": _float(np.max(values)),
        "latest_break": latest_break,
        "recent_mean_break": recent_break,
        "break_alert": bool(latest_break or recent_break),
    }


def build_alert(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    asset: str = "00679B.TWO",
    alpha: float = 0.10,
    window: int = 252,
    recent_snapshots: int = 126,
    elevated_threshold: float = 0.35,
    break_delta_threshold: float = 0.15,
) -> dict[str, Any]:
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    blockers: list[str] = []
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, end_resolved)
    if close.empty or base not in close.columns or asset not in close.columns:
        blockers.append("price_panel_missing_or_asset_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    available = tuple(col for col in tickers if col in returns.columns and returns[col].notna().sum() >= window)
    snapshots = _rolling_snapshots(
        returns[list(available)] if available else returns,
        base=base,
        assets=(asset,) if asset in available and base in available else (),
        alpha=alpha,
        window=window,
    )
    series = _extract_asset_series(snapshots, asset)
    summary = _summarize_break(
        series,
        recent_snapshots=recent_snapshots,
        elevated_threshold=elevated_threshold,
        break_delta_threshold=break_delta_threshold,
    )
    break_alert = bool(summary.get("break_alert"))
    warnings = ["00679b_tail_dependence_break_alert"] if break_alert else []

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_11335_00679b_tail_break_alert",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "policy": "research_shadow_only_no_live_weight_change",
        "source_paper": "2604.11335v1",
        "parameters": {
            "start": start,
            "end": end_resolved,
            "tickers": list(tickers),
            "available_tickers": list(available),
            "base": base,
            "asset": asset,
            "alpha": alpha,
            "window": window,
            "recent_snapshots": recent_snapshots,
            "elevated_threshold": elevated_threshold,
            "break_delta_threshold": break_delta_threshold,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "snapshot_count": int(len(snapshots)),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "summary": summary,
        "decision": {
            "break_alert_complete": True,
            "tail_break_alert_active": break_alert,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_tail_dependence": False,
            "allow_00632r_open_from_tail_dependence": False,
            "allow_00679b_add_from_tail_dependence": False,
            "downgrade_00679b_hedge_value_from_this_alert": break_alert,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": warnings,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# 2604.11335 00679B Tail-Dependence Break Alert",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Summary",
        "",
        f"- Asset: `{payload['parameters']['asset']}` versus `{payload['parameters']['base']}`",
        f"- Latest proxy: `{summary.get('latest_lower_tail_dependence_proxy')}`",
        f"- Baseline mean: `{summary.get('baseline_mean')}`",
        f"- Recent mean: `{summary.get('recent_mean')}`",
        f"- Latest-baseline: `{summary.get('latest_minus_baseline')}`",
        f"- Recent-baseline: `{summary.get('recent_minus_baseline')}`",
        f"- Break alert active: `{payload['decision']['tail_break_alert_active']}`",
        "",
        "## Decision",
        "",
        "- Shadow diagnostic only.",
        "- Do not change target weights.",
        "- Do not add `00679B.TWO` from low tail co-exceedance alone.",
        "- If active, use only as a warning to downgrade bond-hedge confidence.",
        "- Keep `Golden1_0531` unchanged.",
        "",
    ]
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2604_11335_00679b_tail_break_alert_{as_of.replace('-', '')}.json"


def write_outputs(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = str(payload.get("parameters", {}).get("end") or datetime.now().strftime("%Y-%m-%d"))
        _history_path(history_dir, as_of).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--alpha", type=float, default=0.10)
    parser.add_argument("--window", type=int, default=252)
    parser.add_argument("--recent-snapshots", type=int, default=126)
    parser.add_argument("--elevated-threshold", type=float, default=0.35)
    parser.add_argument("--break-delta-threshold", type=float, default=0.15)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_alert(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        alpha=args.alpha,
        window=args.window,
        recent_snapshots=args.recent_snapshots,
        elevated_threshold=args.elevated_threshold,
        break_delta_threshold=args.break_delta_threshold,
    )
    write_outputs(payload, Path(args.output), Path(args.output_md), None if args.no_history else Path(args.history_dir))
    print(f"2604.11335 00679B tail break alert: {Path(args.output).resolve()}")
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "decision": payload["decision"]}, indent=2))


if __name__ == "__main__":
    main()
