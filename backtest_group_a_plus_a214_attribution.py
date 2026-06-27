#!/usr/bin/env python3
"""Run the matched 2x2 attribution test for the A21.4 candidate."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a213 import _run_recovery_strategy
from tw_output_standard import OutputStandardizer, write_standard_output


WINDOWS = {
    "train_2020_2024": ("2020-01-02", "2024-12-31"),
    "validation_2025_2026": ("2025-01-02", "2026-06-18"),
    "long_2020_2026": ("2020-01-02", "2026-06-18"),
}
COMBINATIONS = (
    (75, "cash30"),
    (60, "cash30"),
    (75, "bond30_cash30"),
    (60, "bond30_cash30"),
)
ATTRIBUTION_METRICS = (
    "final_value",
    "annual_return",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "expected_tail_loss_5pct",
    "worst_20d_return",
)


def _variant(ma_window: int, basket_name: str) -> str:
    return f"ma{ma_window}_{basket_name}"


def _attribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decompose A21.4 minus A21.3 into MA, basket, and interaction effects."""
    output: list[dict[str, Any]] = []
    for window in WINDOWS:
        by_variant = {row["variant"]: row for row in rows if row["window"] == window}
        base = by_variant["ma75_cash30"]
        ma_only = by_variant["ma60_cash30"]
        basket_only = by_variant["ma75_bond30_cash30"]
        combined = by_variant["ma60_bond30_cash30"]
        for metric in ATTRIBUTION_METRICS:
            base_value = float(base[metric])
            ma_effect = float(ma_only[metric]) - base_value
            basket_effect = float(basket_only[metric]) - base_value
            combined_effect = float(combined[metric]) - base_value
            output.append(
                {
                    "window": window,
                    "metric": metric,
                    "a213_base": base_value,
                    "ma60_effect_at_cash30": ma_effect,
                    "bond_basket_effect_at_ma75": basket_effect,
                    "interaction_effect": combined_effect - ma_effect - basket_effect,
                    "a214_combined_effect": combined_effect,
                    "a214_value": float(combined[metric]),
                }
            )
    return output


def run_attribution(db: Path, initial_value: float = 1_000_000.0) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for window, (start, end) in WINDOWS.items():
        for ma_window, basket_name in COMBINATIONS:
            report, _ = _run_recovery_strategy(
                start=start,
                end=end,
                initial_value=initial_value,
                db=db,
                basket_name=basket_name,
                ma_window=ma_window,
                strategy_id=_variant(ma_window, basket_name),
                experiment="group_a_plus_a214_2x2_attribution",
                status="research",
            )
            metrics = report["metrics"]
            rows.append(
                {
                    "window": window,
                    "start": start,
                    "end": end,
                    "variant": _variant(ma_window, basket_name),
                    "ma_window": ma_window,
                    "basket_name": basket_name,
                    "recovery_count": len(report["recovery_ramp_dates"]),
                    **metrics,
                }
            )
    return {
        "experiment": "group_a_plus_a214_2x2_attribution",
        "design": {
            "factors": {"ma_window": [75, 60], "defensive_basket": ["cash30", "bond30_cash30"]},
            "fixed_parameters": {
                "entry_gap": -0.0175,
                "exit_gap": 0.02,
                "drawdown": -0.11,
                "total_risk_score": 6,
                "minimum_hold_days": 5,
                "warmup_calendar_days": 180,
                "recovery_trigger": "ma_gap >= 0 and exit_momentum > 0",
            },
            "baseline": "ma75_cash30",
            "candidate": "ma60_bond30_cash30",
        },
        "rows": rows,
        "attribution": _attribution(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output-prefix", default="results/group_a_plus_a214_attribution_20260621")
    args = parser.parse_args()
    prefix = Path(args.output_prefix)
    std = OutputStandardizer("backtest_group_a_plus_a214_attribution.py")
    try:
        report = run_attribution(Path(args.db), args.initial_value)
        pd.DataFrame(report["rows"]).to_csv(prefix.with_suffix(".csv"), index=False, encoding="utf-8-sig")
        pd.DataFrame(report["attribution"]).to_csv(
            prefix.parent / f"{prefix.name}_effects.csv", index=False, encoding="utf-8-sig"
        )
        payload = std.success(
            report,
            rows_csv=str(prefix.with_suffix(".csv")),
            effects_csv=str(prefix.parent / f"{prefix.name}_effects.csv"),
        )
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, str(prefix.with_suffix(".json")))
    print(f"Attribution JSON: {prefix.with_suffix('.json').resolve()}")


if __name__ == "__main__":
    main()
