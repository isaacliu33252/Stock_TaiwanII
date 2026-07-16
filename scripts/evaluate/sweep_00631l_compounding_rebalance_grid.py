#!/usr/bin/env python3
"""Sweep A21.20 staged 00631L add-speed parameters.

Research-only wrapper around evaluate_00631l_compounding_regime_no_add_shadow.
This checks whether the staged trend-reentry result is robust across
base/mean-reversion/trend add-fraction settings.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import build_report


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_compounding_rebalance_grid_20260715.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "00631l_compounding_rebalance_grid_20260715.csv"


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _args_from(base: argparse.Namespace, *, base_add: float, mean_reversion: float, trend: float) -> SimpleNamespace:
    return SimpleNamespace(
        db=base.db,
        windows=base.windows,
        initial_value=base.initial_value,
        ar1_trend_min=base.ar1_trend_min,
        ar1_revert_max=base.ar1_revert_max,
        variance_ratio_trend_min=base.variance_ratio_trend_min,
        variance_ratio_revert_max=base.variance_ratio_revert_max,
        trend_persistence_min=base.trend_persistence_min,
        trend_persistence_revert_max=base.trend_persistence_revert_max,
        reversal_speed_revert_min=base.reversal_speed_revert_min,
        reversal_speed_trend_max=base.reversal_speed_trend_max,
        drawdown_recovery_revert_min=base.drawdown_recovery_revert_min,
        trend_score_min=base.trend_score_min,
        mean_reversion_score_min=base.mean_reversion_score_min,
        baseline_add_fraction=base_add,
        mean_reversion_add_fraction=mean_reversion,
        trend_persistent_add_fraction=trend,
        ce_filter=base.ce_filter,
    )


def _row(report: dict[str, Any]) -> dict[str, Any]:
    totals = report["totals"]
    windows = report["windows"]
    return {
        "baseline_add_fraction": report["baseline_add_fraction"],
        "mean_reversion_add_fraction": report["mean_reversion_add_fraction"],
        "trend_persistent_add_fraction": report["trend_persistent_add_fraction"],
        "ce_filter": report["ce_filter"],
        "blocked_days": totals["blocked_days"],
        "accelerated_days": totals.get("accelerated_days", 0),
        "event_days": totals.get("event_days", 0),
        "delta_final_value_sum": totals["delta_final_value_sum"],
        "delta_sharpe_sum": totals["delta_sharpe_sum"],
        "delta_max_drawdown_sum": totals["delta_max_drawdown_sum"],
        "positive_final_value_windows": totals["positive_final_value_windows"],
        "window_count": len(windows),
        "active_2025_2026_delta_final_value": next(
            (
                window["delta_vs_baseline"]["final_value"]
                for window in windows
                if window["label"] == "active_2025_2026"
            ),
            None,
        ),
        "live_2024_2026_delta_final_value": next(
            (
                window["delta_vs_baseline"]["final_value"]
                for window in windows
                if window["label"] == "live_2024_2026"
            ),
            None,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"))
    parser.add_argument("--windows", default="default")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--base-add-fractions", default="0.20,0.40,0.60")
    parser.add_argument("--mean-reversion-add-fractions", default="0.00,0.25,0.50")
    parser.add_argument("--trend-add-fractions", default="0.80,1.00")
    parser.add_argument("--ce-filter", choices=("none", "ce20_negative", "ce20_or_60_negative", "ce20_and_60_negative"), default="none")
    parser.add_argument("--ar1-trend-min", type=float, default=0.05)
    parser.add_argument("--ar1-revert-max", type=float, default=-0.15)
    parser.add_argument("--variance-ratio-trend-min", type=float, default=1.02)
    parser.add_argument("--variance-ratio-revert-max", type=float, default=0.98)
    parser.add_argument("--trend-persistence-min", type=float, default=0.60)
    parser.add_argument("--trend-persistence-revert-max", type=float, default=0.55)
    parser.add_argument("--reversal-speed-revert-min", type=float, default=0.55)
    parser.add_argument("--reversal-speed-trend-max", type=float, default=0.45)
    parser.add_argument("--drawdown-recovery-revert-min", type=float, default=0.50)
    parser.add_argument("--trend-score-min", type=int, default=4)
    parser.add_argument("--mean-reversion-score-min", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    reports: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for base_add in _parse_floats(args.base_add_fractions):
        for mean_reversion in _parse_floats(args.mean_reversion_add_fractions):
            for trend in _parse_floats(args.trend_add_fractions):
                print(f"Evaluating base={base_add:.2f} mr={mean_reversion:.2f} trend={trend:.2f}")
                report = build_report(_args_from(args, base_add=base_add, mean_reversion=mean_reversion, trend=trend))
                reports.append(report)
                rows.append(_row(report))

    rows_sorted = sorted(
        rows,
        key=lambda row: (
            row["positive_final_value_windows"],
            row["active_2025_2026_delta_final_value"],
            row["delta_final_value_sum"],
            row["delta_sharpe_sum"],
        ),
        reverse=True,
    )
    payload = {
        "schema_version": 1,
        "experiment": "00631l_compounding_rebalance_grid",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "ranking": "positive_windows_then_active_delta_then_total_delta_then_sharpe",
        "rows": rows_sorted,
        "best": rows_sorted[0] if rows_sorted else None,
        "reports": reports,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if rows_sorted:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows_sorted[0].keys()))
            writer.writeheader()
            writer.writerows(rows_sorted)
    print(f"Saved: {output}")
    print(f"CSV: {csv_path}")
    print(json.dumps(payload["best"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
