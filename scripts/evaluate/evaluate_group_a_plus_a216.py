#!/usr/bin/env python3
"""Matched three-window evaluation for the pre-specified A21.6 rule."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a213 import run_a213
from group_a_plus.runners.a216 import run_a216
from tw_output_standard import OutputStandardizer, write_standard_output


WINDOWS = {
    "train_2020_2024": ("2020-01-02", "2024-12-31"),
    "validation_2025_2026": ("2025-01-02", "2026-06-18"),
    "long_2020_2026": ("2020-01-02", "2026-06-18"),
}


def evaluate(db: Path, initial_value: float) -> dict:
    rows = []
    for window, (start, end) in WINDOWS.items():
        base = run_a213(start, end, initial_value, db)[0]
        candidate = run_a216(start, end, initial_value, db)[0]
        bm, cm = base["metrics"], candidate["metrics"]
        row = {
            "window": window,
            "severe_day_count": candidate["severe_day_count"],
            "delta_final": cm["final_value"] - bm["final_value"],
            "delta_sharpe": cm["sharpe_ratio"] - bm["sharpe_ratio"],
            "delta_sortino": cm["sortino_ratio"] - bm["sortino_ratio"],
            "delta_mdd": cm["max_drawdown"] - bm["max_drawdown"],
            "delta_etl": cm["expected_tail_loss_5pct"] - bm["expected_tail_loss_5pct"],
            "a213_final": bm["final_value"],
            "a216_final": cm["final_value"],
        }
        row["formal_pass"] = row["delta_final"] >= -1e-9 and row["delta_sharpe"] >= 0 and row["delta_mdd"] >= 0
        rows.append(row)
    formal = all(row["formal_pass"] for row in rows)
    return {
        "experiment": "group_a_plus_a216_predefined_severity_validation",
        "parameter_selection": "Rule thresholds were fixed before running any A21.6 backtest.",
        "rows": rows,
        "decision": {
            "formal_promotion_pass": formal,
            "status": "promotion_ready" if formal else "research_only",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output-prefix", default="results/group_a_plus_a216_evaluation_20260621")
    args = parser.parse_args()
    prefix = Path(args.output_prefix)
    std = OutputStandardizer("evaluate_group_a_plus_a216.py")
    try:
        report = evaluate(Path(args.db), args.initial_value)
        pd.DataFrame(report["rows"]).to_csv(
            prefix.parent / f"{prefix.name}_windows.csv", index=False, encoding="utf-8-sig"
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, str(prefix.with_suffix(".json")))


if __name__ == "__main__":
    main()
