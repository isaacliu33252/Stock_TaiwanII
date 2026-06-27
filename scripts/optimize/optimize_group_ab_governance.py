#!/usr/bin/env python3
"""Grid-optimize Group A/B governance parameters without retraining."""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_ab_hold10_research import _load_hold10_ab
from finrl_meta_strategy_governance import (
    ABGovernanceParams,
    StressGateParams,
    metrics,
    resolve_project_path,
    simulate_ab_governed,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GROUP_A_SWEEP = PROJECT_ROOT / "results" / "group_a_00632r_dca_sweep_20240102_20260604_curve.csv"
DEFAULT_BASE_AB = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_governance_optimization_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-a-sweep-csv", default=str(DEFAULT_GROUP_A_SWEEP))
    parser.add_argument("--base-ab-curve-csv", default=str(DEFAULT_BASE_AB))
    parser.add_argument("--group-a-variant", default="hold_limit_00632r_10d_to_0050")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-mdd-floor", type=float, default=-0.20)
    return parser.parse_args()


def _candidate_params() -> list[ABGovernanceParams]:
    params: list[ABGovernanceParams] = []

    # Practical grid: search around the current live candidate instead of
    # brute-forcing every combination. This keeps one optimization run short
    # enough to repeat after strategy changes.
    for lookback, band, base_weight, upper, lower, min_transfer, cooldown in itertools.product(
        [84, 126, 168],
        [0.05, 0.08, 0.12],
        [0.60, 0.625, 0.65],
        [0.70, 0.75],
        [0.55, 0.60],
        [50_000.0, 100_000.0],
        [10, 20, 30],
    ):
        if not lower <= base_weight <= upper:
            continue
        midpoint_up = round((base_weight + upper) / 2.0, 4)
        midpoint_down = round((base_weight + lower) / 2.0, 4)
        params.append(
            ABGovernanceParams(
                strategy_name=(
                    f"opt_lb{lookback}_b{band:.3f}_base{base_weight:.3f}_"
                    f"lo{lower:.2f}_hi{upper:.2f}_min{int(min_transfer)}_cd{cooldown}_nostress"
                ),
                base_a_weight=base_weight,
                dynamic_lookback=lookback,
                dynamic_band=band,
                upper_a_weight=upper,
                upper_mid_a_weight=midpoint_up,
                lower_mid_a_weight=midpoint_down,
                lower_a_weight=lower,
                min_transfer_notional=min_transfer,
                cooldown_days=cooldown,
                stress_gate=StressGateParams(enabled=False),
            )
        )

    # A smaller aggressive sleeve checks whether heavier Group A exposure is
    # worth the extra drawdown. These variants are reviewed separately by the
    # feasible/MDD rankings in the report.
    for lookback, band, base_weight, upper, lower, min_transfer, cooldown in itertools.product(
        [84, 126, 168],
        [0.05, 0.08],
        [0.675, 0.70],
        [0.80, 0.85],
        [0.55, 0.60],
        [50_000.0],
        [20],
    ):
        if not lower <= base_weight <= upper:
            continue
        midpoint_up = round((base_weight + upper) / 2.0, 4)
        midpoint_down = round((base_weight + lower) / 2.0, 4)
        params.append(
            ABGovernanceParams(
                strategy_name=(
                    f"opt_aggr_lb{lookback}_b{band:.3f}_base{base_weight:.3f}_"
                    f"lo{lower:.2f}_hi{upper:.2f}_min{int(min_transfer)}_cd{cooldown}_nostress"
                ),
                base_a_weight=base_weight,
                dynamic_lookback=lookback,
                dynamic_band=band,
                upper_a_weight=upper,
                upper_mid_a_weight=midpoint_up,
                lower_mid_a_weight=midpoint_down,
                lower_a_weight=lower,
                min_transfer_notional=min_transfer,
                cooldown_days=cooldown,
                stress_gate=StressGateParams(enabled=False),
            )
        )

    for lookback, band, risk_cap, caution_cap in itertools.product(
        [84, 126, 168],
        [0.05, 0.08],
        [0.55, 0.60],
        [0.60, 0.625, 0.65],
    ):
        params.append(
            ABGovernanceParams(
                strategy_name=f"opt_lb{lookback}_b{band:.3f}_stress_c{caution_cap:.3f}_r{risk_cap:.2f}",
                dynamic_lookback=lookback,
                dynamic_band=band,
                min_transfer_notional=50_000.0,
                cooldown_days=20,
                stress_gate=StressGateParams(
                    enabled=True,
                    caution_a_weight_cap=caution_cap,
                    risk_off_a_weight_cap=risk_cap,
                ),
            )
        )
        params.append(
            ABGovernanceParams(
                strategy_name=f"opt_lb{lookback}_b{band:.3f}_qstress_c{caution_cap:.3f}_r{risk_cap:.2f}",
                dynamic_lookback=lookback,
                dynamic_band=band,
                min_transfer_notional=50_000.0,
                cooldown_days=20,
                stress_gate=StressGateParams(
                    enabled=True,
                    use_quantile_thresholds=True,
                    quantile_window=252,
                    quantile_min_periods=126,
                    caution_quantile=0.25,
                    risk_off_quantile=0.10,
                    caution_a_weight_cap=caution_cap,
                    risk_off_a_weight_cap=risk_cap,
                ),
            )
        )
    return params


def _score(row: dict[str, Any]) -> float:
    mdd_penalty = max(0.0, abs(min(float(row["max_drawdown"]) + 0.20, 0.0))) * 4.0
    cost_penalty = float(row["total_cost"]) / 1_000_000.0
    return float(row["sharpe_ratio"]) + 0.20 * float(row["annual_return"]) - mdd_penalty - cost_penalty


def main() -> None:
    args = _parse_args()
    output = resolve_project_path(PROJECT_ROOT, args.output)
    ab = _load_hold10_ab(
        resolve_project_path(PROJECT_ROOT, args.group_a_sweep_csv),
        resolve_project_path(PROJECT_ROOT, args.base_ab_curve_csv),
        str(args.group_a_variant),
    )
    rows: list[dict[str, Any]] = []
    curves: dict[str, pd.Series] = {}
    details: dict[str, Any] = {}
    params_list = _candidate_params()
    for i, params in enumerate(params_list, start=1):
        curve, events, diagnostic = simulate_ab_governed(ab, params)
        row = {
            "variant": params.strategy_name,
            "config_id": params.deterministic_id,
            **metrics(curve, events=len(events), total_cost=sum(float(e["total_cost"]) for e in events)),
        }
        row["objective_score"] = _score(row)
        rows.append(row)
        if i % 200 == 0:
            print(f"evaluated {i}/{len(params_list)}", flush=True)
        details[params.strategy_name] = {
            "params": asdict(params),
            "target_counts": {str(k): int(v) for k, v in diagnostic["target_a_weight"].value_counts().sort_index().to_dict().items()},
            "events": events,
        }
        # Keep only useful curves to avoid huge files.
        if row["max_drawdown"] >= float(args.max_mdd_floor):
            curves[params.strategy_name] = curve

    rows_sorted = sorted(rows, key=lambda row: (row["objective_score"], row["sharpe_ratio"], row["final_value"]), reverse=True)
    feasible = [row for row in rows if row["max_drawdown"] >= float(args.max_mdd_floor)]
    best = {
        "objective": rows_sorted[0],
        "sharpe": max(rows, key=lambda row: (row["sharpe_ratio"], row["final_value"])),
        "final": max(rows, key=lambda row: row["final_value"]),
        "feasible_objective": max(feasible, key=lambda row: (row["objective_score"], row["sharpe_ratio"], row["final_value"])) if feasible else None,
        "feasible_final": max(feasible, key=lambda row: row["final_value"]) if feasible else None,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    pd.DataFrame(rows).sort_values(["objective_score", "sharpe_ratio", "final_value"], ascending=False).to_csv(csv_path, index=False, encoding="utf-8-sig")
    if curves:
        frame = pd.DataFrame(curves)
        frame.index.name = "date"
        frame.to_csv(curve_path, encoding="utf-8-sig")
    report = {
        "experiment": "group_ab_governance_optimization",
        "method_note": "Grid search over A/B governance parameters. No retraining. Ranking uses objective_score plus separate best Sharpe/final views.",
        "window": {"start": str(ab.index[0].date()), "end": str(ab.index[-1].date()), "rows": int(len(ab))},
        "settings": {"max_mdd_floor": float(args.max_mdd_floor), "num_candidates": len(params_list)},
        "best": best,
        "top20": rows_sorted[:20],
        "details_for_top20": {row["variant"]: details[row["variant"]] for row in rows_sorted[:20]},
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV: {csv_path}")
    print(f"Curve CSV: {curve_path}")
    for label, row in best.items():
        if row:
            print(
                f"Best {label}: {row['variant']} final={row['final_value']:.2f}, "
                f"sharpe={row['sharpe_ratio']:.4f}, sortino={row['sortino_ratio']:.4f}, "
                f"mdd={row['max_drawdown']:.4%}, score={row['objective_score']:.4f}"
            )


if __name__ == "__main__":
    main()
