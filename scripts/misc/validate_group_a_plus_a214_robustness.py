#!/usr/bin/env python3
"""Matched walk-forward, latency, and cost robustness checks for A21.4."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    _asymmetric_delayed_regime,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.a213 import _run_recovery_strategy
from tw_output_standard import OutputStandardizer, write_standard_output


SPECS = {
    "a213": {"ma_window": 75, "basket_name": "cash30"},
    "a214": {"ma_window": 60, "basket_name": "bond30_cash30"},
}
ROBUSTNESS_WINDOWS = {
    "train_2020_2024": ("2020-01-02", "2024-12-31"),
    "validation_2025_2026": ("2025-01-02", "2026-06-18"),
    "long_2020_2026": ("2020-01-02", "2026-06-18"),
}
WALK_FORWARD_FOLDS = {
    "2020": ("2020-01-02", "2020-12-31"),
    "2021": ("2021-01-04", "2021-12-30"),
    "2022": ("2022-01-03", "2022-12-30"),
    "2023": ("2023-01-03", "2023-12-29"),
    "2024": ("2024-01-02", "2024-12-31"),
    "2025": ("2025-01-02", "2025-12-31"),
    "2026_ytd": ("2026-01-02", "2026-06-18"),
}
COST_MULTIPLIERS = (0.5, 1.0, 2.0, 3.0)


def _run_spec(
    name: str,
    start: str,
    end: str,
    db: Path,
    initial_value: float,
    cost_multiplier: float = 1.0,
) -> tuple[dict[str, Any], pd.DataFrame]:
    spec = SPECS[name]
    return _run_recovery_strategy(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db,
        commission_rate=0.001425 * cost_multiplier,
        slippage_rate=0.0005 * cost_multiplier,
        equity_etf_sell_tax=0.001,
        basket_name=str(spec["basket_name"]),
        ma_window=int(spec["ma_window"]),
        strategy_id=name,
        experiment="group_a_plus_a214_robustness",
        status="research",
    )


def _comparison_row(label: str, scenario: Any, a213: dict[str, Any], a214: dict[str, Any]) -> dict[str, Any]:
    base = a213["metrics"] if "metrics" in a213 else a213
    candidate = a214["metrics"] if "metrics" in a214 else a214
    delta_final = float(candidate["final_value"]) - float(base["final_value"])
    delta_sharpe = float(candidate["sharpe_ratio"]) - float(base["sharpe_ratio"])
    delta_mdd = float(candidate["max_drawdown"]) - float(base["max_drawdown"])
    return {
        "test": label,
        "scenario": scenario,
        "a213_final": float(base["final_value"]),
        "a214_final": float(candidate["final_value"]),
        "delta_final": delta_final,
        "delta_sharpe": delta_sharpe,
        "delta_mdd": delta_mdd,
        "final_pass": delta_final >= -1e-9,
        "sharpe_pass": delta_sharpe >= -1e-12,
        "mdd_pass": delta_mdd >= -1e-12,
        "joint_pass": delta_final >= -1e-9 and delta_sharpe >= -1e-12 and delta_mdd >= -1e-12,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scenario_count": len(rows),
        "joint_pass_count": sum(bool(row["joint_pass"]) for row in rows),
        "final_pass_count": sum(bool(row["final_pass"]) for row in rows),
        "sharpe_pass_count": sum(bool(row["sharpe_pass"]) for row in rows),
        "mdd_pass_count": sum(bool(row["mdd_pass"]) for row in rows),
        "worst_delta_final": min(float(row["delta_final"]) for row in rows),
        "median_delta_final": float(pd.Series([row["delta_final"] for row in rows]).median()),
    }


def _walk_forward(db: Path, initial_value: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for fold, (start, end) in WALK_FORWARD_FOLDS.items():
        reports = {name: _run_spec(name, start, end, db, initial_value)[0] for name in SPECS}
        row = _comparison_row("walk_forward", fold, reports["a213"], reports["a214"])
        row.update({"start": start, "end": end})
        rows.append(row)
    return rows, _summary(rows)


def _cost_stress(db: Path, initial_value: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for window, (start, end) in ROBUSTNESS_WINDOWS.items():
        for multiplier in COST_MULTIPLIERS:
            reports = {
                name: _run_spec(name, start, end, db, initial_value, multiplier)[0]
                for name in SPECS
            }
            row = _comparison_row("cost_stress", f"{window}_cost{multiplier:g}x", reports["a213"], reports["a214"])
            row.update({"window": window, "cost_multiplier": multiplier})
            rows.append(row)
    return rows, _summary(rows)


def _latency_metrics(
    report: dict[str, Any],
    frame: pd.DataFrame,
    prices: pd.DataFrame,
    initial_value: float,
    enter_delay: int,
    exit_delay: int,
) -> dict[str, Any]:
    delayed = _asymmetric_delayed_regime(frame["base_regime"], enter_delay, exit_delay)
    execution_regime = _recovery_ramp_regime(delayed, frame)
    curve, _ = _simulate_costed_curve(
        prices,
        execution_regime,
        report["weights"],
        initial_value,
        0.001425,
        0.0005,
        0.001,
    )
    return _metrics(curve, initial_value)


def _latency_stress(db: Path, initial_value: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for window, (start, end) in ROBUSTNESS_WINDOWS.items():
        contexts = {name: _run_spec(name, start, end, db, initial_value) for name in SPECS}
        prices = {
            name: _load_total_return_prices(db, context[1].index)[0]
            for name, context in contexts.items()
        }
        for enter_delay in range(4):
            for exit_delay in range(4):
                metrics = {
                    name: _latency_metrics(
                        contexts[name][0], contexts[name][1], prices[name], initial_value, enter_delay, exit_delay
                    )
                    for name in SPECS
                }
                row = _comparison_row(
                    "latency",
                    f"{window}_enter{enter_delay}_exit{exit_delay}",
                    metrics["a213"],
                    metrics["a214"],
                )
                row.update({"window": window, "enter_delay": enter_delay, "exit_delay": exit_delay})
                rows.append(row)
    by_window = {
        window: _summary([row for row in rows if row["window"] == window])
        for window in ROBUSTNESS_WINDOWS
    }
    return rows, {"overall": _summary(rows), "by_window": by_window}


def run_robustness(db: Path, initial_value: float = 1_000_000.0) -> dict[str, Any]:
    walk_rows, walk_summary = _walk_forward(db, initial_value)
    latency_rows, latency_summary = _latency_stress(db, initial_value)
    cost_rows, cost_summary = _cost_stress(db, initial_value)
    return {
        "experiment": "group_a_plus_a214_matched_robustness",
        "candidate": SPECS["a214"],
        "baseline": SPECS["a213"],
        "selection_policy": "A21.4 parameters fixed before all checks; no scenario-specific tuning.",
        "walk_forward": {"summary": walk_summary, "rows": walk_rows},
        "latency": {"summary": latency_summary, "rows": latency_rows},
        "cost_stress": {"summary": cost_summary, "rows": cost_rows},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output-prefix", default="results/group_a_plus_a214_robustness_20260621")
    args = parser.parse_args()
    prefix = Path(args.output_prefix)
    std = OutputStandardizer("validate_group_a_plus_a214_robustness.py")
    try:
        report = run_robustness(Path(args.db), args.initial_value)
        pd.DataFrame(report["walk_forward"]["rows"]).to_csv(
            prefix.parent / f"{prefix.name}_walk_forward.csv", index=False, encoding="utf-8-sig"
        )
        pd.DataFrame(report["latency"]["rows"]).to_csv(
            prefix.parent / f"{prefix.name}_latency.csv", index=False, encoding="utf-8-sig"
        )
        pd.DataFrame(report["cost_stress"]["rows"]).to_csv(
            prefix.parent / f"{prefix.name}_cost.csv", index=False, encoding="utf-8-sig"
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, str(prefix.with_suffix(".json")))
    print(f"Robustness JSON: {prefix.with_suffix('.json').resolve()}")


if __name__ == "__main__":
    main()
