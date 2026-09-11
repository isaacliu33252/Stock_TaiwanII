#!/usr/bin/env python3
"""Build same-window GroupA+ candidate reports for promotion-gate validation."""

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

from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS, _resolve_end_date, run_a2118  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/golden2_same_window_candidate_backtests.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/golden2_same_window_candidate_backtests.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/golden2_same_window_candidate_backtests/history"
DEFAULT_WINDOWS = (
    "2020_covid:2020-01-02:2020-12-31:results/ncf_00631l_panel_backfill_2020_20260716.csv:out_of_sample,"
    "2022_rate_hike:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:out_of_sample,"
    "live_2024_2026:2024-01-02:latest:results/ncf_00631l_panel_latest_20260831.csv:tuning_window,"
    "active_2025_2026:2025-01-02:latest:results/ncf_00631l_panel_latest_20260831.csv:tuning_window"
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_windows(raw: str) -> list[dict[str, str]]:
    windows: list[dict[str, str]] = []
    for item in raw.split(","):
        if not item.strip():
            continue
        parts = item.split(":")
        if len(parts) != 5:
            raise ValueError("windows must use label:start:end:panel:bucket")
        label, start, end, panel, bucket = parts
        windows.append({"label": label, "start": start, "end": end, "panel": panel, "bucket": bucket})
    return windows


def _metric_subset(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    execution = report.get("execution") if isinstance(report.get("execution"), dict) else {}
    out = dict(metrics)
    if "rebalance_count" in execution:
        out["rebalance_count"] = execution.get("rebalance_count")
    if "transaction_cost" in execution:
        out["transaction_cost"] = execution.get("transaction_cost")
    return out


def _window_from_report(report: dict[str, Any], fallback: dict[str, str]) -> dict[str, Any]:
    window = report.get("window")
    if isinstance(window, dict):
        return window
    return {"start": fallback["start"], "end": fallback["end"]}


def _run_window(window: dict[str, str], *, db: Path, initial_value: float) -> dict[str, Any]:
    end = _resolve_end_date(db, window["end"])
    common = {
        "start": window["start"],
        "end": end,
        "initial_value": float(initial_value),
        "db": db,
        "chip_data_fallback_max_stale_days": CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    }
    baseline_report, _baseline_frame = run_a2118(ncf_panel_631l_path=None, **common)
    candidate_report, _candidate_frame = run_a2118(ncf_panel_631l_path=str(_resolve(window["panel"])), **common)
    return {
        "label": window["label"],
        "bucket": window["bucket"],
        "experiment": "group_a_plus_golden2_same_window_candidate_backtest",
        "window": _window_from_report(candidate_report, window),
        "baseline": {
            "name": "a2118_without_ncf_panel",
            "metrics": _metric_subset(baseline_report),
        },
        "rows": [
            {
                "name": "golden2_latest_ncf_panel",
                "panel": str(_resolve(window["panel"])),
                "bucket": window["bucket"],
                "metrics": _metric_subset(candidate_report),
                "trigger_days": (candidate_report.get("execution") or {}).get("late_bull_trigger_days", 0),
                "override_days": (candidate_report.get("execution") or {}).get("late_bull_trigger_days", 0),
            }
        ],
        "baseline_report_summary": {
            "backtest_mode": baseline_report.get("backtest_mode"),
            "strategy": baseline_report.get("strategy"),
        },
        "candidate_report_summary": {
            "backtest_mode": candidate_report.get("backtest_mode"),
            "strategy": candidate_report.get("strategy"),
        },
    }


def build_report(*, windows: list[dict[str, str]], db: Path, initial_value: float) -> dict[str, Any]:
    reports = [_run_window(window, db=db, initial_value=initial_value) for window in windows]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_golden2_same_window_candidate_backtests",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_strategy_change_no_weight_change_no_orders",
        "candidate_name": "golden2_latest_ncf_panel",
        "window_count": len(reports),
        "reports": reports,
        "decision": {
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "creates_orders": False,
            "recommended_next_step": "run evaluate_group_a_plus_multi_window_gate.py on exported window reports",
        },
    }


def write_outputs(report: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> list[Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    written = [output, output_md]
    window_dir = output.parent / "golden2_same_window_candidate_backtests"
    window_dir.mkdir(parents=True, exist_ok=True)
    for item in report["reports"]:
        window_output = window_dir / f"{item['label']}.json"
        window_output.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(window_output)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        history = history_dir / "golden2_same_window_candidate_backtests_20260831.json"
        history.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(history)
    return written


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Golden2 Same-Window Candidate Backtests",
        "",
        f"- Policy: `{report.get('policy')}`",
        f"- Candidate: `{report.get('candidate_name')}`",
        f"- Window count: `{report.get('window_count')}`",
        "",
        "| window | baseline final | candidate final | delta final pct | baseline Sharpe | candidate Sharpe | baseline MDD | candidate MDD | triggers |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report.get("reports") or []:
        baseline = item["baseline"]["metrics"]
        row = item["rows"][0]
        metrics = row["metrics"]
        base_final = float(baseline.get("final_value", 0.0) or 0.0)
        cand_final = float(metrics.get("final_value", 0.0) or 0.0)
        delta = cand_final / base_final - 1.0 if base_final else 0.0
        lines.append(
            f"| `{item['label']}` | {_fmt(base_final, 2)} | {_fmt(cand_final, 2)} | {_fmt(delta)} | "
            f"{_fmt(baseline.get('sharpe_ratio'))} | {_fmt(metrics.get('sharpe_ratio'))} | "
            f"{_fmt(baseline.get('max_drawdown'))} | {_fmt(metrics.get('max_drawdown'))} | "
            f"{row.get('trigger_days', 0)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(windows=_parse_windows(args.windows), db=_resolve(args.db), initial_value=args.initial_value)
    written = write_outputs(
        report,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Golden2 same-window candidate backtests: {_resolve(args.output)}")
    print(f"Window files: {len([path for path in written if path.name.endswith('.json')]) - 2}")


if __name__ == "__main__":
    main()
