#!/usr/bin/env python3
"""Robustness sweep for the 2604.11335 tail-dependence trend review."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.build_group_a_plus_2604_11335_tail_dependence_trend_review import (
    DEFAULT_PDF,
    build_review,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_tail_dependence_trend_robustness.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_tail_dependence_trend_robustness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_11335_tail_dependence_trend_robustness/history"
ALPHAS = (0.05, 0.10, 0.15)
WINDOWS = (126, 252, 504)


def _pair_value(review: dict[str, Any], asset: str, key: str) -> float | None:
    for row in review.get("latest", {}).get("pairs", []):
        if row.get("asset") == asset:
            value = row.get(key)
            return float(value) if isinstance(value, (int, float)) else None
    return None


def _trend_value(review: dict[str, Any], asset: str, key: str) -> float | None:
    row = review.get("trend_summary", {}).get(asset, {})
    value = row.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def build_sweep(
    *,
    pdf_path: Path = DEFAULT_PDF,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    alphas: tuple[float, ...] = ALPHAS,
    windows: tuple[int, ...] = WINDOWS,
    high_tail_dependence_threshold: float = 0.65,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for alpha in alphas:
        for window in windows:
            review = build_review(
                pdf_path=pdf_path,
                db_path=db_path,
                start=start,
                end=end,
                alpha=alpha,
                window=window,
                high_tail_dependence_threshold=high_tail_dependence_threshold,
            )
            rows.append(
                {
                    "alpha": alpha,
                    "window": window,
                    "status": review["status"],
                    "as_of": review.get("parameters", {}).get("end"),
                    "snapshot_count": review.get("coverage", {}).get("snapshot_count"),
                    "00631l_latest_lower_tail_dependence": _pair_value(
                        review, "00631L.TW", "lower_tail_dependence_proxy"
                    ),
                    "00631l_recent_minus_prior": _trend_value(
                        review, "00631L.TW", "recent_minus_prior"
                    ),
                    "00632r_latest_lower_tail_dependence": _pair_value(
                        review, "00632R.TW", "lower_tail_dependence_proxy"
                    ),
                    "00679b_latest_lower_tail_dependence": _pair_value(
                        review, "00679B.TWO", "lower_tail_dependence_proxy"
                    ),
                    "high_latest_assets": review.get("alerts", {}).get("high_latest_assets", []),
                    "warning_reasons": review.get("warning_reasons", []),
                    "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                }
            )

    valid = [row for row in rows if row["status"] != "blocked"]
    high_631 = [
        row for row in valid
        if isinstance(row["00631l_latest_lower_tail_dependence"], (int, float))
        and row["00631l_latest_lower_tail_dependence"] >= high_tail_dependence_threshold
    ]
    rising_631 = [
        row for row in valid
        if isinstance(row["00631l_recent_minus_prior"], (int, float))
        and row["00631l_recent_minus_prior"] >= 0.10
    ]
    promote = False
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_11335_tail_dependence_trend_robustness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "available_for_shadow_monitoring" if valid else "blocked",
        "policy": "research_shadow_only_no_live_weight_change",
        "source_paper": "2604.11335v1",
        "parameters": {
            "start": start,
            "end": rows[0]["as_of"] if rows else end,
            "alphas": list(alphas),
            "windows": list(windows),
            "high_tail_dependence_threshold": high_tail_dependence_threshold,
        },
        "rows": rows,
        "summary": {
            "valid_runs": len(valid),
            "high_00631l_runs": len(high_631),
            "rising_00631l_runs": len(rising_631),
            "00631l_high_tail_dependence_robust": bool(valid) and len(high_631) == len(valid),
            "00631l_recent_rising_robust": bool(valid) and len(rising_631) == len(valid),
        },
        "decision": {
            "robustness_complete": True,
            "promote_to_live": promote,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_tail_dependence": False,
            "allow_00632r_open_from_tail_dependence": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 2604.11335 Tail Dependence Trend Robustness",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Summary",
        "",
        f"- Valid runs: `{payload['summary']['valid_runs']}`",
        f"- High `00631L.TW` runs: `{payload['summary']['high_00631l_runs']}`",
        f"- Robust high `00631L.TW` tail dependence: `{payload['summary']['00631l_high_tail_dependence_robust']}`",
        f"- Robust recent rising `00631L.TW`: `{payload['summary']['00631l_recent_rising_robust']}`",
        f"- Promote to live: `{payload['decision']['promote_to_live']}`",
        "",
        "## Rows",
        "",
        "| Alpha | Window | 00631L latest | 00631L recent-prior | 00632R latest | 00679B latest | High assets |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {alpha:.2f} | {window} | {l631} | {r631} | {r632} | {b679} | `{assets}` |".format(
                alpha=row["alpha"],
                window=row["window"],
                l631=row["00631l_latest_lower_tail_dependence"],
                r631=row["00631l_recent_minus_prior"],
                r632=row["00632r_latest_lower_tail_dependence"],
                b679=row["00679b_latest_lower_tail_dependence"],
                assets=row["high_latest_assets"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2604_11335_tail_dependence_trend_robustness_{as_of.replace('-', '')}.json"


def write_sweep(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
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
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    payload = build_sweep(
        pdf_path=Path(args.pdf),
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
    )
    write_sweep(
        payload,
        Path(args.output),
        Path(args.output_md),
        None if args.no_history else Path(args.history_dir),
    )
    print(f"2604.11335 tail-dependence robustness: {Path(args.output).resolve()}")
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "decision": payload["decision"]}, indent=2))


if __name__ == "__main__":
    main()
