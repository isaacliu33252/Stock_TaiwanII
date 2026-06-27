#!/usr/bin/env python3
"""Backtest FinRL-Meta-inspired governance on Group A hold10 + Group B no-2884."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_ab_hold10_research import _load_hold10_ab
from finrl_meta_strategy_governance import (
    ABGovernanceParams,
    StressGateParams,
    TradeCostParams,
    metrics,
    resolve_project_path,
    simulate_ab_governed,
    simulate_ab_validation_selector,
    write_epoch_oos_scaffold,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GROUP_A_SWEEP = PROJECT_ROOT / "results" / "group_a_00632r_dca_sweep_20240102_20260604_curve.csv"
DEFAULT_BASE_AB = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_meta_governed_hold10_no2884_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-a-sweep-csv", default=str(DEFAULT_GROUP_A_SWEEP))
    parser.add_argument("--base-ab-curve-csv", default=str(DEFAULT_BASE_AB))
    parser.add_argument("--group-a-variant", default="hold_limit_00632r_10d_to_0050")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _variant_params() -> list[ABGovernanceParams]:
    base = ABGovernanceParams()
    return [
        replace(
            base,
            strategy_name="dynamic_lb126_band012_base060_hold10_no2884_optimized",
            base_a_weight=0.60,
            dynamic_lookback=126,
            dynamic_band=0.12,
            upper_a_weight=0.70,
            upper_mid_a_weight=0.65,
            lower_mid_a_weight=0.575,
            lower_a_weight=0.55,
            min_transfer_notional=50_000.0,
            cooldown_days=20,
            stress_gate=StressGateParams(enabled=False),
        ),
        replace(
            base,
            strategy_name="dynamic_lb126_band008_hold10_no2884_governed",
            dynamic_band=0.08,
            min_transfer_notional=50_000.0,
            cooldown_days=20,
            stress_gate=StressGateParams(enabled=True, caution_a_weight_cap=0.625, risk_off_a_weight_cap=0.55),
        ),
        replace(
            base,
            strategy_name="dynamic_lb126_band008_hold10_no2884_no_stress",
            dynamic_band=0.08,
            min_transfer_notional=50_000.0,
            cooldown_days=20,
            stress_gate=StressGateParams(enabled=False),
        ),
        replace(
            base,
            strategy_name="dynamic_lb126_band008_hold10_no2884_strict_cost",
            dynamic_band=0.08,
            min_transfer_notional=100_000.0,
            cooldown_days=30,
            cost=TradeCostParams(commission_rate=0.001425, sell_tax_rate=0.001, slippage_rate=0.001),
            stress_gate=StressGateParams(enabled=True, caution_a_weight_cap=0.60, risk_off_a_weight_cap=0.50),
        ),
        replace(
            base,
            strategy_name="dynamic_lb126_band003_hold10_no2884_governed",
            dynamic_band=0.03,
            min_transfer_notional=50_000.0,
            cooldown_days=20,
            stress_gate=StressGateParams(enabled=True, caution_a_weight_cap=0.625, risk_off_a_weight_cap=0.55),
        ),
        replace(
            base,
            strategy_name="dynamic_lb126_band008_hold10_no2884_quantile_stress",
            dynamic_band=0.08,
            min_transfer_notional=50_000.0,
            cooldown_days=20,
            stress_gate=StressGateParams(
                enabled=True,
                use_quantile_thresholds=True,
                quantile_window=252,
                quantile_min_periods=126,
                caution_quantile=0.25,
                risk_off_quantile=0.10,
                caution_a_weight_cap=0.625,
                risk_off_a_weight_cap=0.55,
            ),
        ),
    ]


def main() -> None:
    args = _parse_args()
    group_a_path = resolve_project_path(PROJECT_ROOT, args.group_a_sweep_csv)
    base_ab_path = resolve_project_path(PROJECT_ROOT, args.base_ab_curve_csv)
    output = resolve_project_path(PROJECT_ROOT, args.output)
    ab = _load_hold10_ab(group_a_path, base_ab_path, str(args.group_a_variant))

    rows: list[dict[str, Any]] = []
    all_curves = pd.DataFrame(index=ab.index)
    all_curves["group_a_hold10"] = ab["group_a_value"]
    all_curves["group_b_no2884"] = ab["group_b_value"]
    detailed: dict[str, Any] = {}
    best_key = ""
    best_row: dict[str, Any] | None = None

    variant_params = _variant_params()
    for params in variant_params:
        curve, events, diagnostic = simulate_ab_governed(ab, params)
        row = {
            "variant": params.strategy_name,
            "config_id": params.deterministic_id,
            **metrics(curve, events=len(events), total_cost=sum(float(e["total_cost"]) for e in events)),
        }
        rows.append(row)
        all_curves[params.strategy_name] = curve
        if best_row is None or (row["sharpe_ratio"], row["final_value"]) > (best_row["sharpe_ratio"], best_row["final_value"]):
            best_row = row
            best_key = params.strategy_name
        detailed[params.strategy_name] = {
            "params": asdict(params),
            "metrics": row,
            "target_counts": {str(k): int(v) for k, v in diagnostic["target_a_weight"].value_counts().sort_index().to_dict().items()},
            "stress_counts": {str(k): int(v) for k, v in diagnostic["stress_state"].value_counts().to_dict().items()},
            "events": events,
        }
        print(
            f"{params.strategy_name}: final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"events={row['num_events']}, cost={row['total_cost']:.2f}",
            flush=True,
        )

    selector_candidates = [
        params
        for params in variant_params
        if params.strategy_name
        in {
            "dynamic_lb126_band012_base060_hold10_no2884_optimized",
            "dynamic_lb126_band008_hold10_no2884_no_stress",
            "dynamic_lb126_band008_hold10_no2884_governed",
            "dynamic_lb126_band008_hold10_no2884_quantile_stress",
            "dynamic_lb126_band003_hold10_no2884_governed",
        }
    ]
    selector_params = replace(
        ABGovernanceParams(),
        strategy_name="validation_selector_126d_quarterly_hold10_no2884",
        dynamic_band=0.08,
        min_transfer_notional=50_000.0,
        cooldown_days=20,
        stress_gate=StressGateParams(enabled=False),
    )
    selector_curve, selector_events, selector_diagnostic, selector_choices = simulate_ab_validation_selector(
        ab,
        selector_candidates,
        selector_params,
        validation_days=126,
        metric="sharpe_ratio",
    )
    selector_row = {
        "variant": selector_params.strategy_name,
        "config_id": selector_params.deterministic_id,
        **metrics(selector_curve, events=len(selector_events), total_cost=sum(float(e["total_cost"]) for e in selector_events)),
    }
    rows.append(selector_row)
    all_curves[selector_params.strategy_name] = selector_curve
    if best_row is None or (selector_row["sharpe_ratio"], selector_row["final_value"]) > (best_row["sharpe_ratio"], best_row["final_value"]):
        best_row = selector_row
        best_key = selector_params.strategy_name
    detailed[selector_params.strategy_name] = {
        "params": asdict(selector_params),
        "selector_candidates": [asdict(params) for params in selector_candidates],
        "selector_choices": selector_choices,
        "metrics": selector_row,
        "target_counts": {str(k): int(v) for k, v in selector_diagnostic["target_a_weight"].value_counts().sort_index().to_dict().items()},
        "chosen_variant_counts": {str(k): int(v) for k, v in selector_diagnostic["chosen_variant"].value_counts().to_dict().items()},
        "events": selector_events,
    }
    print(
        f"{selector_params.strategy_name}: final={selector_row['final_value']:.2f}, "
        f"sharpe={selector_row['sharpe_ratio']:.4f}, mdd={selector_row['max_drawdown']:.4%}, "
        f"events={selector_row['num_events']}, cost={selector_row['total_cost']:.2f}",
        flush=True,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    trade_log_path = output.with_name(output.stem + "_trade_log.csv")
    diagnostic_path = output.with_name(output.stem + "_diagnostic.csv")
    selector_choice_path = output.with_name(output.stem + "_selector_choices.csv")
    scaffold_path = output.with_name(output.stem + "_epoch_oos_scaffold.json")

    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    all_curves.index.name = "date"
    all_curves.to_csv(curve_path, encoding="utf-8-sig")
    trade_rows = []
    for variant, detail in detailed.items():
        for event in detail["events"]:
            trade_rows.append({"variant": variant, **event})
    pd.DataFrame(trade_rows).to_csv(trade_log_path, index=False, encoding="utf-8-sig")

    pd.DataFrame(selector_choices).to_csv(selector_choice_path, index=False, encoding="utf-8-sig")
    if best_key == selector_params.strategy_name:
        best_diagnostic = selector_diagnostic
        best_params = selector_params
    else:
        best_params = next(params for params in variant_params if params.strategy_name == best_key)
        _, _, best_diagnostic = simulate_ab_governed(ab, best_params)
    best_diagnostic.index.name = "date"
    best_diagnostic.to_csv(diagnostic_path, encoding="utf-8-sig")
    write_epoch_oos_scaffold(
        scaffold_path,
        strategy_name=best_key,
        train_windows=[("2020-01-01", "2023-12-31")],
        test_windows=[("2024-01-02", "2026-06-04"), ("2007-07-01", "2010-12-31")],
        params=asdict(best_params),
    )

    report = {
        "experiment": "group_ab_meta_governed_hold10_no2884",
        "method_note": (
            "Imports FinRL-Meta-style governance: last target weight in state/diagnostics, "
            "cooldown, min transfer threshold, stress gate, full trade cost log, dataclass params, "
            "and epoch OOS scaffold. No model retraining."
        ),
        "sources": {
            "group_a_sweep_csv": str(group_a_path.resolve()),
            "base_ab_curve_csv": str(base_ab_path.resolve()),
            "group_a_variant": str(args.group_a_variant),
        },
        "window": {"start": str(ab.index[0].date()), "end": str(ab.index[-1].date()), "rows": int(len(ab))},
        "best": best_row,
        "results": rows,
        "details": detailed,
        "outputs": {
            "json": str(output),
            "csv": str(csv_path),
            "curve_csv": str(curve_path),
            "trade_log_csv": str(trade_log_path),
            "diagnostic_csv": str(diagnostic_path),
            "selector_choices_csv": str(selector_choice_path),
            "epoch_oos_scaffold_json": str(scaffold_path),
        },
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV: {csv_path}")
    print(f"Trade log: {trade_log_path}")
    print(f"Diagnostic: {diagnostic_path}")
    print(f"Selector choices: {selector_choice_path}")
    print(f"Epoch OOS scaffold: {scaffold_path}")
    if best_row:
        print(
            f"Best: {best_row['variant']} final={best_row['final_value']:.2f}, "
            f"sharpe={best_row['sharpe_ratio']:.4f}, mdd={best_row['max_drawdown']:.4%}"
        )


if __name__ == "__main__":
    main()
