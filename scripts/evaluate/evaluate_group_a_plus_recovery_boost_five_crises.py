#!/usr/bin/env python3
"""Validate recovery 00631L boost across five historical crisis folds.

This reuses the prepared 2008/2011/2015/2018/2020 crisis folds from
scripts/misc/backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706.py.
Most folds are close-only TWII proxies, so this script tests fixed recovery
boost sizes only, not the OHLC-based foundation-volatility quality gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _recovery_ramp_regime
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _metrics, _simulate_regime_curve, _switch_returns
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path
from group_a_plus.runners.a2118 import _recovery_boost_weights
from scripts.misc.backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    FOLDS,
    INITIAL_VALUE,
    _load_fold_data,
    _trim,
)


BOOSTS = {
    "baseline": 0.0,
    "recovery_boost_010": 0.10,
    "recovery_boost_015": 0.15,
}

BOOSTED_RECOVERY_REGIME = "group_a_plus_recovery_boost"

CONDITIONAL_POLICIES: dict[str, dict[str, Any]] = {
    "recovery_boost_010_age10": {"boost": 0.10, "max_recovery_age": 10},
    "recovery_boost_010_age20": {"boost": 0.10, "max_recovery_age": 20},
    "recovery_boost_010_age30": {"boost": 0.10, "max_recovery_age": 30},
    "recovery_boost_010_ma_gap_ge_0": {"boost": 0.10, "min_ma_gap": 0.0},
    "recovery_boost_010_ma_gap_ge_minus_002": {"boost": 0.10, "min_ma_gap": -0.02},
    "recovery_boost_010_vol_ratio_le_120": {"boost": 0.10, "max_vol_ratio": 1.20},
    "recovery_boost_010_age10_ma_gap_ge_minus_002": {
        "boost": 0.10,
        "max_recovery_age": 10,
        "min_ma_gap": -0.02,
    },
    "recovery_boost_010_age10_vol_ratio_le_120": {
        "boost": 0.10,
        "max_recovery_age": 10,
        "max_vol_ratio": 1.20,
    },
    "recovery_boost_010_quality_guard": {
        "boost": 0.10,
        "max_recovery_age": 10,
        "min_ma_gap": -0.02,
        "max_vol_ratio": 1.20,
        "max_tail_risk_score": 0,
    },
    "recovery_boost_015_age10": {"boost": 0.15, "max_recovery_age": 10},
    "recovery_boost_015_age20": {"boost": 0.15, "max_recovery_age": 20},
    "recovery_boost_015_age30": {"boost": 0.15, "max_recovery_age": 30},
    "recovery_boost_015_quality_guard": {
        "boost": 0.15,
        "max_recovery_age": 10,
        "min_ma_gap": -0.02,
        "max_vol_ratio": 1.20,
        "max_tail_risk_score": 0,
    },
}


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = ("final_value", "total_return", "annual_return", "sharpe_ratio", "max_drawdown")
    return {f"delta_{key}": float(candidate[key]) - float(baseline[key]) for key in keys}


def _rebase_curve(curve: pd.Series, initial_value: float = INITIAL_VALUE) -> pd.Series:
    return curve / float(curve.iloc[0]) * float(initial_value)


def _recovery_age(regime: pd.Series) -> pd.Series:
    ages: list[int] = []
    age = 0
    previous_recovery = False
    for state in regime.astype(str):
        is_recovery = state == "group_a_plus_recovery"
        if is_recovery:
            age = age + 1 if previous_recovery else 1
        else:
            age = 0
        ages.append(age)
        previous_recovery = is_recovery
    return pd.Series(ages, index=regime.index, dtype=int)


def _boost_allow_mask(regime: pd.Series, frame: pd.DataFrame, policy: dict[str, Any]) -> pd.Series:
    allow = regime.astype(str) == "group_a_plus_recovery"
    age = _recovery_age(regime)
    if policy.get("max_recovery_age") is not None:
        allow &= age <= int(policy["max_recovery_age"])
    if policy.get("min_ma_gap") is not None:
        allow &= frame["ma_gap"].astype(float) >= float(policy["min_ma_gap"])
    if policy.get("max_vol_ratio") is not None:
        allow &= frame["realized_vol_ratio_20_60"].astype(float) <= float(policy["max_vol_ratio"])
    if policy.get("max_tail_risk_score") is not None:
        allow &= frame["tail_risk_score"].astype(float) <= float(policy["max_tail_risk_score"])
    return allow.fillna(False)


def main() -> None:
    db_path = _resolve(str(DB_PATH))
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    latest_golden_signal_path = _resolve_golden_signal_path()
    latest_golden_signal = _load(latest_golden_signal_path)
    latest_golden_weights = _normalize(_weights_from_group_a(latest_golden_signal))
    switch_rule = _build_switch_rule()

    folds: dict[str, Any] = {}
    for name, spec in FOLDS.items():
        prices, chip_features = _load_fold_data(name, spec, db_path)
        events, frame = _switch_returns(
            prices,
            chip_features,
            switch_rule,
            chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        )
        execution_regime = _recovery_ramp_regime(frame["regime"], frame)
        report_start = spec["report_start"]
        report_end = spec["report_end"]
        report_index = _trim(pd.Series(index=prices.index, dtype=float), report_start, report_end).index
        fold_variants: dict[str, Any] = {}

        variant_specs: dict[str, dict[str, Any]] = {
            **{variant: {"boost": boost, "allow_mask": None, "policy": "unconditional"} for variant, boost in BOOSTS.items()},
        }
        for variant, policy in CONDITIONAL_POLICIES.items():
            variant_specs[variant] = {
                "boost": float(policy["boost"]),
                "allow_mask": _boost_allow_mask(execution_regime, frame, policy),
                "policy": policy,
            }

        for variant, variant_spec in variant_specs.items():
            boost = float(variant_spec["boost"])
            variant_regime = execution_regime.copy()
            allow_mask = variant_spec["allow_mask"]
            if allow_mask is not None:
                variant_regime.loc[allow_mask] = BOOSTED_RECOVERY_REGIME
            weights_by_regime = {
                "golden1": latest_golden_weights,
                "group_a_plus_defensive": basket,
                "group_a_plus_recovery": current_defensive,
                BOOSTED_RECOVERY_REGIME: _recovery_boost_weights(current_defensive, boost),
            }
            if allow_mask is None and boost > 0.0:
                weights_by_regime["group_a_plus_recovery"] = _recovery_boost_weights(current_defensive, boost)
            curve = _simulate_regime_curve(prices, variant_regime, weights_by_regime, INITIAL_VALUE)
            report_curve = _trim(curve, report_start, report_end)
            rebased_report_curve = _rebase_curve(report_curve)
            metrics = _metrics(report_curve, float(report_curve.iloc[0]))
            rebased_metrics = _metrics(rebased_report_curve, INITIAL_VALUE)
            full_recovery_days = int((execution_regime == "group_a_plus_recovery").sum())
            report_recovery_days = int((execution_regime.loc[report_index] == "group_a_plus_recovery").sum())
            full_boosted_days = int((variant_regime == BOOSTED_RECOVERY_REGIME).sum())
            report_boosted_days = int((variant_regime.loc[report_index] == BOOSTED_RECOVERY_REGIME).sum())
            if allow_mask is None and boost > 0.0:
                full_boosted_days = full_recovery_days
                report_boosted_days = report_recovery_days
            fold_variants[variant] = {
                "metrics": metrics,
                "rebased_report_metrics": rebased_metrics,
                "recovery_boost_fraction": boost,
                "boost_policy": variant_spec["policy"],
                "recovery_days": report_recovery_days,
                "boosted_recovery_days": report_boosted_days,
                "full_window_recovery_days": full_recovery_days,
                "full_window_boosted_recovery_days": full_boosted_days,
                "pre_report_recovery_days": full_recovery_days - report_recovery_days,
                "pre_report_boosted_recovery_days": full_boosted_days - report_boosted_days,
            }

        baseline_metrics = fold_variants["baseline"]["metrics"]
        baseline_rebased_metrics = fold_variants["baseline"]["rebased_report_metrics"]
        for variant, payload in fold_variants.items():
            payload["delta_vs_baseline"] = {} if variant == "baseline" else _metric_delta(payload["metrics"], baseline_metrics)
            payload["rebased_delta_vs_baseline"] = (
                {} if variant == "baseline" else _metric_delta(payload["rebased_report_metrics"], baseline_rebased_metrics)
            )

        folds[name] = {
            "label": spec["label"],
            "data_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
            "report_window": {
                "start": str(report_index[0].date()),
                "end": str(report_index[-1].date()),
            },
            "variants": fold_variants,
        }

    summary: dict[str, dict[str, float]] = {}
    candidate_variants = [variant for variant in variant_specs if variant != "baseline"]
    for variant in candidate_variants:
        deltas = [fold["variants"][variant]["delta_vs_baseline"] for fold in folds.values()]
        rebased_deltas = [fold["variants"][variant]["rebased_delta_vs_baseline"] for fold in folds.values()]
        summary[variant] = {
            "sum_delta_final_value": sum(d["delta_final_value"] for d in deltas),
            "sum_delta_sharpe_ratio": sum(d["delta_sharpe_ratio"] for d in deltas),
            "min_delta_final_value": min(d["delta_final_value"] for d in deltas),
            "positive_final_value_folds": sum(1 for d in deltas if d["delta_final_value"] > 0),
            "rebased_sum_delta_final_value": sum(d["delta_final_value"] for d in rebased_deltas),
            "rebased_sum_delta_sharpe_ratio": sum(d["delta_sharpe_ratio"] for d in rebased_deltas),
            "rebased_min_delta_final_value": min(d["delta_final_value"] for d in rebased_deltas),
            "rebased_positive_final_value_folds": sum(1 for d in rebased_deltas if d["delta_final_value"] > 0),
            "total_folds": len(deltas),
            "total_recovery_days": sum(fold["variants"][variant]["recovery_days"] for fold in folds.values()),
            "total_boosted_recovery_days": sum(fold["variants"][variant]["boosted_recovery_days"] for fold in folds.values()),
            "total_pre_report_recovery_days": sum(fold["variants"][variant]["pre_report_recovery_days"] for fold in folds.values()),
            "total_pre_report_boosted_recovery_days": sum(
                fold["variants"][variant]["pre_report_boosted_recovery_days"] for fold in folds.values()
            ),
        }

    payload = {
        "strategy": "group_a_plus_recovery_boost_five_crises",
        "research_only": True,
        "inputs": {
            "policy_signal_path": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "latest_golden_signal_path": str(latest_golden_signal_path.relative_to(PROJECT_ROOT)),
            "current_defensive_weights": current_defensive,
            "latest_golden_weights": latest_golden_weights,
            "note": "close-only crisis folds; foundation-vol quality gate intentionally not applied",
            "metric_note": "metrics are measured on the trimmed report window; rebased_report_metrics reset each report window to 1,000,000 to isolate in-window effects from pre-report capital carry-in.",
        },
        "summary": summary,
        "folds": folds,
        "promotion_review": {
            "decision": "do_not_promote_keep_shadow",
            "reason": "Crisis folds are proxy/close-only and recovery events remain sparse.",
        },
    }
    output = PROJECT_ROOT / "results" / "group_a_plus_recovery_boost_five_crises_20260710.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    for variant, row in summary.items():
        print(
            f"{variant}: sum_delta_fv={row['sum_delta_final_value']:.1f} "
            f"rebased_sum_delta_fv={row['rebased_sum_delta_final_value']:.1f} "
            f"sum_delta_sharpe={row['sum_delta_sharpe_ratio']:.4f} "
            f"positive_folds={row['positive_final_value_folds']}/{row['total_folds']} "
            f"rebased_positive_folds={row['rebased_positive_final_value_folds']}/{row['total_folds']} "
            f"min_delta_fv={row['min_delta_final_value']:.1f} "
            f"boosted_days={row['total_boosted_recovery_days']}"
        )
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
