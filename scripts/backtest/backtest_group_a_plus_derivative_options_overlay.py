#!/usr/bin/env python3
"""Derivative/options risk overlay tests for GroupA+ inspired by Fincept options analytics."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    SwitchRule,
    _load_chip_features,
    _load_prices,
    _metrics,
    _regime_features,
    _simulate_regime_curve,
    _switch_returns,
)
from tw_output_standard import OutputStandardizer, write_standard_output


PROJECT_ROOT = Path(__file__).resolve().parent
A207_RULE = SwitchRule(
    "risk_ma75_dd11_total6_hold5_eg0175_xg020",
    75,
    -0.0175,
    0.02,
    75,
    -0.11,
    5,
    5,
    0,
    None,
    0,
    None,
    6,
    6,
)
MA20_RULE = SwitchRule("ma20_dd7_hold5", 20, -0.03, 0.01, 20, -0.07, 5, 5)


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _derivative_features(prices: pd.DataFrame, chip_features: pd.DataFrame) -> pd.DataFrame:
    frame = _regime_features(prices, A207_RULE, chip_features)
    close = prices["0050.TW"].astype(float)
    frame["return_0050_5d"] = close.pct_change(5).fillna(0.0)
    pcr = frame["txo_foreign_put_call_net_oi"].astype(float)
    pcr_mean = pcr.rolling(60, min_periods=20).mean()
    pcr_std = pcr.rolling(60, min_periods=20).std().replace(0.0, math.nan)
    frame["txo_pcr_z"] = ((pcr - pcr_mean) / pcr_std).replace([math.inf, -math.inf], math.nan).fillna(0.0)
    dealer = frame["dealer_txo_volume_5d"].astype(float)
    dealer_mean = dealer.rolling(60, min_periods=20).mean()
    dealer_std = dealer.rolling(60, min_periods=20).std().replace(0.0, math.nan)
    frame["dealer_txo_volume_z"] = ((dealer - dealer_mean) / dealer_std).replace([math.inf, -math.inf], math.nan).fillna(0.0)
    frame["option_stress_score"] = (
        (frame["txo_pcr_z"] >= 1.0).astype(int)
        + ((frame["txo_foreign_put_call_net_oi"] > 0.0) & (frame["txo_foreign_put_call_net_oi_chg_5d"] > 0.0)).astype(int)
        + ((frame["dealer_txo_volume_z"] >= 1.0) & (frame["return_0050_5d"] < 0.0)).astype(int)
        + (frame["derivative_score"] >= 1).astype(int)
    )
    return frame


def _selector_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    min_score: int,
    min_pcr_z: float,
    min_dealer_z: float,
    max_return_5d: float,
) -> pd.DataFrame:
    trigger = (
        (features["option_stress_score"] >= min_score)
        & ((features["txo_pcr_z"] >= min_pcr_z) | (features["dealer_txo_volume_z"] >= min_dealer_z))
        & (features["return_0050_5d"] <= max_return_5d)
    )
    frame = features.copy()
    frame["options_trigger"] = trigger.astype(int)
    frame["regime"] = a207_regime.copy()
    frame.loc[trigger, "regime"] = ma20_regime.loc[trigger]
    return frame


def _guard_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    min_score: int,
    min_pcr_z: float,
    min_dealer_z: float,
    max_return_5d: float,
    min_hold_days: int,
) -> pd.DataFrame:
    in_guard = False
    hold = 0
    regimes = []
    trigger_days = []
    for dt, row in features.iterrows():
        trigger = (
            int(row["option_stress_score"]) >= min_score
            and (float(row["txo_pcr_z"]) >= min_pcr_z or float(row["dealer_txo_volume_z"]) >= min_dealer_z)
            and float(row["return_0050_5d"]) <= max_return_5d
        )
        exit_ = int(row["option_stress_score"]) <= 1 and float(row["return_0050_5d"]) >= 0.0
        if in_guard:
            hold += 1
            if hold >= min_hold_days and exit_:
                in_guard = False
                hold = 0
        elif trigger:
            in_guard = True
            hold = 1
            trigger_days.append(dt)
        regimes.append("group_a_plus_defensive" if in_guard else str(a207_regime.loc[dt]))
    frame = features.copy()
    frame["options_trigger"] = 0
    if trigger_days:
        frame.loc[trigger_days, "options_trigger"] = 1
    frame["regime"] = regimes
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--min-scores", default="2,3,4")
    parser.add_argument("--min-pcr-z", default="0.5,1.0,1.5")
    parser.add_argument("--min-dealer-z", default="0.5,1.0,1.5")
    parser.add_argument("--max-return-5d", default="0.0,-0.02,-0.04")
    parser.add_argument("--min-hold-days", default="3,5,10")
    parser.add_argument("--output-prefix", default="results/group_a_plus_derivative_options_overlay_20260619")
    args = parser.parse_args()
    std = OutputStandardizer("backtest_group_a_plus_derivative_options_overlay.py")

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}
    a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)
    base_curves = {
        "a207": _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value),
        "ma20": _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, args.initial_value),
    }
    features = _derivative_features(prices, chip_features)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for min_score in _parse_int_list(args.min_scores):
        for min_pcr_z in _parse_float_list(args.min_pcr_z):
            for min_dealer_z in _parse_float_list(args.min_dealer_z):
                for max_ret in _parse_float_list(args.max_return_5d):
                    label = f"opts_selector_s{min_score}_p{int(min_pcr_z*10):02d}_d{int(min_dealer_z*10):02d}_r{int(abs(max_ret)*100):02d}"
                    frame = _selector_regime(features, a207_frame["regime"], ma20_frame["regime"], min_score, min_pcr_z, min_dealer_z, max_ret)
                    curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                    rows.append(
                        {
                            "variant": label,
                            "mode": "selector",
                            **_metrics(curve, args.initial_value),
                            "min_score": min_score,
                            "min_pcr_z": min_pcr_z,
                            "min_dealer_z": min_dealer_z,
                            "max_return_5d": max_ret,
                            "min_hold_days": 0,
                            "trigger_days": int(frame["options_trigger"].sum()),
                            "override_days": int((frame["regime"] != a207_frame["regime"]).sum()),
                            "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                        }
                    )
                    frames[label] = frame
                    for hold in _parse_int_list(args.min_hold_days):
                        guard_label = f"opts_guard_s{min_score}_p{int(min_pcr_z*10):02d}_d{int(min_dealer_z*10):02d}_r{int(abs(max_ret)*100):02d}_h{hold}"
                        guard = _guard_regime(features, a207_frame["regime"], min_score, min_pcr_z, min_dealer_z, max_ret, hold)
                        curve = _simulate_regime_curve(prices, guard["regime"], weights_by_regime, args.initial_value)
                        rows.append(
                            {
                                "variant": guard_label,
                                "mode": "guard",
                                **_metrics(curve, args.initial_value),
                                "min_score": min_score,
                                "min_pcr_z": min_pcr_z,
                                "min_dealer_z": min_dealer_z,
                                "max_return_5d": max_ret,
                                "min_hold_days": hold,
                                "trigger_days": int(guard["options_trigger"].sum()),
                                "override_days": int((guard["regime"] != a207_frame["regime"]).sum()),
                                "defense_days": int((guard["regime"] == "group_a_plus_defensive").sum()),
                            }
                        )
                        frames[guard_label] = guard

    summary = {name: _metrics(curve, args.initial_value) for name, curve in base_curves.items()}
    ranked = sorted(rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_derivative_options_overlay",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "inputs": {"policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)), "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT))},
        "rules": {"a207": asdict(A207_RULE), "ma20": asdict(MA20_RULE)},
        "summary": summary,
        "rows": rows,
        "best_by_sharpe": ranked[:10],
        "best": best,
        "feature_summary": {
            "max_txo_pcr_z": float(features["txo_pcr_z"].max()),
            "max_dealer_txo_volume_z": float(features["dealer_txo_volume_z"].max()),
            "max_option_stress_score": int(features["option_stress_score"].max()),
        },
    }
    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    best_frame_path = prefix.with_name(prefix.name + "_best_frame.csv")
    write_standard_output(std.success(report), str(json_path))
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(base_curves).to_csv(curve_path, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(best_frame_path, encoding="utf-8-sig")
    print(f"JSON: {json_path}")
    print(f"Best: {best['variant']} final={best['final_value']:,.0f}, sharpe={best['sharpe_ratio']:.3f}, mdd={best['max_drawdown']:.2%}")


if __name__ == "__main__":
    main()
