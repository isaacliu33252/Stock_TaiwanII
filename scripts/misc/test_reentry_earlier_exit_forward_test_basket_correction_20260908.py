#!/usr/bin/env python3
"""Direction #5 follow-up, basket correction (2026-09-08 audit follow-up).

The committed 2026-09-09 script (test_reentry_earlier_exit_forward_test_20260909.py,
the basis for direction 5's "closed_negative" verdict -- inflation_2022 MDD
worsening from -24.33% to -30.53% when the fast-exit threshold is loosened)
used DEFENSIVE_BASKETS["bond30_cash30"] (0050 40% / 00679B.TWO 30% / cash
30%). That basket has NOT been in production since the 2026-08-18 promotion
(see group_a_plus/runners/a2118.py line ~838): production's actual
defensive basket is bond0_cash60 (0050 40% / cash 60%), because 00679B only
genuinely hedged in 1 of 7 major defensive episodes and actively hurt in
2022 and 2025-03. So the committed direction-5 follow-up quantified its
"whipsaw cost" against a basket production has not run for three weeks.

This is an exact copy of the 2026-09-09 script's logic with only the
DEFENSIVE basket corrected to bond0_cash60, to check whether the
closed_negative verdict survives using the actual current production
basket.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS
from group_a_plus.runners.a2111 import _build_switch_rule
from backtest_group_a_plus_policy_signal import TICKERS as ALL_TICKERS

RULE = _build_switch_rule()
TICKERS = list(ALL_TICKERS)
GOLDEN1 = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}
DEFENSIVE = dict(DEFENSIVE_BASKETS["bond0_cash60"])  # CORRECTED: actual production basket since 2026-08-18
INITIAL_VALUE = 1_000_000.0
WARMUP_DAYS = 200

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "2026-09-04"),
    ("active_2025_2026", "2025-01-02", "2026-09-04"),
]

# Production baseline (current live values from report/group_a_plus/latest/strategy.json)
BASELINE_KW = dict(
    risk_score_lookback_days=5,
    momentum_fast_exit_min=0.10,
    momentum_fast_exit_ma_gap_min=-0.08,
)

# Candidate variants: each loosens exactly one lever vs. baseline so the
# effect of that lever alone is visible.
VARIANTS = {
    "lower_momentum_threshold_0.05": dict(
        rule=RULE,
        kwargs=dict(risk_score_lookback_days=5, momentum_fast_exit_min=0.05, momentum_fast_exit_ma_gap_min=-0.08),
    ),
    "lower_momentum_threshold_0.07": dict(
        rule=RULE,
        kwargs=dict(risk_score_lookback_days=5, momentum_fast_exit_min=0.07, momentum_fast_exit_ma_gap_min=-0.08),
    ),
    "looser_ma_gap_guard_-0.15": dict(
        rule=RULE,
        kwargs=dict(risk_score_lookback_days=5, momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.15),
    ),
    "shorter_momentum_lookback_3d": dict(
        rule=dataclasses.replace(RULE, exit_momentum_days=3),
        kwargs=dict(risk_score_lookback_days=5, momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.08),
    ),
}


def run(prices, chip_features, rule, kwargs):
    events, frame = _switch_returns(prices, chip_features, rule, **kwargs)
    regimes = frame["regime"].astype(str)
    weights_by_regime = {"golden1": GOLDEN1, "group_a_plus_defensive": DEFENSIVE}
    curve = _simulate_regime_curve(prices[TICKERS], regimes, weights_by_regime, INITIAL_VALUE)
    return events, regimes, curve


def trim(curve, regimes, start, end):
    return curve.loc[start:end], regimes.loc[start:end]


def count_events(regimes: pd.Series) -> tuple[int, int]:
    """Return (enter_defense_count, exit_defense_count) transition counts."""
    prev = None
    enters = 0
    exits = 0
    for val in regimes:
        is_def = val == "group_a_plus_defensive"
        if prev is not None:
            if is_def and not prev:
                enters += 1
            if not is_def and prev:
                exits += 1
        prev = is_def
    return enters, exits


def main():
    all_results = {}
    for label, start, end in WINDOWS:
        load_start = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
        prices = _load_prices(DB_PATH, TICKERS, load_start, end)
        chip_features = _load_chip_features(DB_PATH, prices.index, load_start, end)

        window_result = {}

        _, reg_base, curve_base = run(prices, chip_features, RULE, BASELINE_KW)
        curve_base_w, reg_base_w = trim(curve_base, reg_base, start, end)
        base_metrics = _metrics(curve_base_w / curve_base_w.iloc[0] * INITIAL_VALUE, INITIAL_VALUE)
        base_enters, base_exits = count_events(reg_base_w)
        window_result["baseline_production"] = {**base_metrics, "enters": base_enters, "exits": base_exits}

        for variant_name, spec in VARIANTS.items():
            _, reg_v, curve_v = run(prices, chip_features, spec["rule"], spec["kwargs"])
            curve_v_w, reg_v_w = trim(curve_v, reg_v, start, end)
            v_metrics = _metrics(curve_v_w / curve_v_w.iloc[0] * INITIAL_VALUE, INITIAL_VALUE)
            v_enters, v_exits = count_events(reg_v_w)
            window_result[variant_name] = {
                **v_metrics,
                "enters": v_enters,
                "exits": v_exits,
                "delta_final_value": v_metrics["final_value"] - base_metrics["final_value"],
                "delta_sharpe": v_metrics["sharpe_ratio"] - base_metrics["sharpe_ratio"],
                "delta_max_drawdown_pp": (v_metrics["max_drawdown"] - base_metrics["max_drawdown"]) * 100,
                "delta_exits": v_exits - base_exits,
            }

        all_results[label] = window_result

        print(f"=== {label} ({start}..{end}) ===")
        b = window_result["baseline_production"]
        print(f"  baseline_production: final={b['final_value']:,.0f} sharpe={b['sharpe_ratio']:.4f} "
              f"mdd={b['max_drawdown']*100:.2f}% enters={b['enters']} exits={b['exits']}")
        for variant_name in VARIANTS:
            v = window_result[variant_name]
            print(f"  {variant_name:32s}: final={v['final_value']:,.0f} (Δ{v['delta_final_value']:+,.0f}) "
                  f"sharpe={v['sharpe_ratio']:.4f} (Δ{v['delta_sharpe']:+.4f}) "
                  f"mdd={v['max_drawdown']*100:.2f}% (Δ{v['delta_max_drawdown_pp']:+.2f}pp) "
                  f"exits={v['exits']} (Δ{v['delta_exits']:+d})")
        print()

    out_path = PROJECT_ROOT / "results" / "reentry_earlier_exit_forward_test_basket_correction_20260908.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
