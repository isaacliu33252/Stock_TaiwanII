#!/usr/bin/env python3
"""Direction #5 follow-up, full threshold sweep (2026-09-08).

test_reentry_earlier_exit_forward_test_basket_correction_20260908.py only
tested two momentum_fast_exit_min values (0.05, 0.07) and found 0.07 has
zero MDD/final-value cost in inflation_2022 while 0.05 has a large one. That
is exactly the shape of result feedback_overfitting_fixed_window_tuning
warns about: two hand-picked points, one of which happens to land just
above a single historical false-signal's exact momentum value. This sweeps
a fine grid to see whether 0.07 sits in a wide, robust "safe" plateau or
right at a fragile cliff edge -- and to find where that cliff actually is,
rather than treating a single historical value as ground truth.

Same tooling and windows as the basket-correction script: real production
switch rule (a2111._build_switch_rule()), real current defensive basket
(bond0_cash60, corrected as of the 2026-09-08 audit), same 4 windows.
momentum_fast_exit_ma_gap_min and risk_score_lookback_days held fixed at
production values (-0.08, 5) -- only momentum_fast_exit_min varies.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

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
DEFENSIVE = dict(DEFENSIVE_BASKETS["bond0_cash60"])  # production basket since 2026-08-18
INITIAL_VALUE = 1_000_000.0
WARMUP_DAYS = 200

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "2026-09-04"),
    ("active_2025_2026", "2025-01-02", "2026-09-04"),
]

BASELINE_THRESHOLD = 0.10  # production
FIXED_KW = dict(risk_score_lookback_days=5, momentum_fast_exit_ma_gap_min=-0.08)

# Fine grid, denser around the 0.05-0.10 region where the cliff was found.
THRESHOLDS = [0.02, 0.03, 0.04, 0.045, 0.05, 0.055, 0.06, 0.065, 0.07,
              0.075, 0.08, 0.085, 0.09, 0.095, 0.10, 0.11, 0.12, 0.13, 0.15]


def run(prices, chip_features, threshold):
    kwargs = {**FIXED_KW, "momentum_fast_exit_min": threshold}
    events, frame = _switch_returns(prices, chip_features, RULE, **kwargs)
    regimes = frame["regime"].astype(str)
    weights_by_regime = {"golden1": GOLDEN1, "group_a_plus_defensive": DEFENSIVE}
    curve = _simulate_regime_curve(prices[TICKERS], regimes, weights_by_regime, INITIAL_VALUE)
    return events, regimes, curve


def trim(curve, regimes, start, end):
    return curve.loc[start:end], regimes.loc[start:end]


def count_events(regimes: pd.Series) -> tuple[int, int]:
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


def main() -> None:
    all_results = {}
    for label, start, end in WINDOWS:
        load_start = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
        prices = _load_prices(DB_PATH, TICKERS, load_start, end)
        chip_features = _load_chip_features(DB_PATH, prices.index, load_start, end)

        _, reg_base, curve_base = run(prices, chip_features, BASELINE_THRESHOLD)
        curve_base_w, reg_base_w = trim(curve_base, reg_base, start, end)
        base_metrics = _metrics(curve_base_w / curve_base_w.iloc[0] * INITIAL_VALUE, INITIAL_VALUE)
        base_enters, base_exits = count_events(reg_base_w)

        window_rows = []
        for threshold in THRESHOLDS:
            _, reg_v, curve_v = run(prices, chip_features, threshold)
            curve_v_w, reg_v_w = trim(curve_v, reg_v, start, end)
            v_metrics = _metrics(curve_v_w / curve_v_w.iloc[0] * INITIAL_VALUE, INITIAL_VALUE)
            v_enters, v_exits = count_events(reg_v_w)
            window_rows.append(
                {
                    "threshold": threshold,
                    "final_value": v_metrics["final_value"],
                    "sharpe_ratio": v_metrics["sharpe_ratio"],
                    "max_drawdown": v_metrics["max_drawdown"],
                    "exits": v_exits,
                    "delta_final_value": v_metrics["final_value"] - base_metrics["final_value"],
                    "delta_sharpe": v_metrics["sharpe_ratio"] - base_metrics["sharpe_ratio"],
                    "delta_max_drawdown_pp": (v_metrics["max_drawdown"] - base_metrics["max_drawdown"]) * 100,
                    "delta_exits": v_exits - base_exits,
                }
            )

        all_results[label] = {
            "baseline_production": {**base_metrics, "enters": base_enters, "exits": base_exits},
            "sweep": window_rows,
        }

        print(f"=== {label} ({start}..{end}) === baseline(0.10): final={base_metrics['final_value']:,.0f} "
              f"sharpe={base_metrics['sharpe_ratio']:.4f} mdd={base_metrics['max_drawdown']*100:.2f}% exits={base_exits}")
        for row in window_rows:
            flag = "  <-- baseline" if row["threshold"] == BASELINE_THRESHOLD else ""
            print(f"  thr={row['threshold']:.3f}  final={row['final_value']:>12,.0f} (Δ{row['delta_final_value']:+9,.0f})  "
                  f"sharpe={row['sharpe_ratio']:7.4f} (Δ{row['delta_sharpe']:+.4f})  "
                  f"mdd={row['max_drawdown']*100:7.2f}% (Δ{row['delta_max_drawdown_pp']:+.2f}pp)  "
                  f"exits={row['exits']} (Δ{row['delta_exits']:+d}){flag}")
        print()

    out_path = PROJECT_ROOT / "results" / "reentry_momentum_threshold_sweep_20260908.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
