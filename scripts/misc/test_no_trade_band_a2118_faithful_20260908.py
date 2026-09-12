#!/usr/bin/env python3
"""Fable direction #6, a2118-faithful re-test (2026-09-08).

The original direction-6 script (test_no_trade_band_20260908.py) used a
simplified proxy: a static golden1 basket (50/20/30) with a continuous
PVA leverage_scale applied directly to 00631L's weight every day. That
mechanism does NOT exist inside group_a_plus.runners.a2118.run_a2118()'s
own historical backtest -- run_a2118 uses a SINGLE STATIC golden1 weight
vector (whichever signal_group_a_*.json is newest at run time, per the
documented H3 limitation) combined with a categorical regime label
(golden1 / group_a_plus_defensive / group_a_plus_recovery / ncf late-bull
hedge / etc.) that only changes at discrete switch-rule/NCF-overlay
events. There is no day-to-day continuous PVA-driven weight drift inside
a2118's own backtest replay at all.

Reuses `_simulate_costed_curve_with_no_trade_band` from
scripts/evaluate/evaluate_group_a_plus_volatility_gate_shadow.py (an
existing, already-tested no-trade-band-aware simulator built for this
exact regime/weights_by_regime shape) rather than hand-rolling a new one.

Read-only research. Does not modify group_a_plus/runners/a2118.py,
strategy.json, execution_plan.json, or any other production/live file.
Uses the LIVE production runner_params (report/group_a_plus/latest/
strategy.json's active_strategy.runner_params) -- the same config
actually running in production today, not defaults.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "evaluate"))

import pandas as pd

from group_a_plus.runners.a2118 import (
    run_a2118,
    _add_00713_cash_sleeve,
    _recovery_boost_weights,
    _late_bull_hedge_weights,
    _golden_tail_trim_weights,
    RECOVERY_00631L_BOOST_REGIME,
    NCF_LB_REGIME,
    NCF_LB_SOFT_REGIME,
    GOLDEN_TAIL_TRIM_REGIME,
    GOLDEN_FOLLOW_THROUGH_TRIM_REGIME,
    GOLDEN_REBOUND_RECAPTURE_REGIME,
    GOLDEN_LEVERAGE_CAP_REGIME,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
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
from backtest_group_a_plus_defensive_basket import _load_total_return_prices, DEFENSIVE_BASKETS
from evaluate_group_a_plus_volatility_gate_shadow import _simulate_costed_curve_with_no_trade_band

STRATEGY_JSON = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
RUNNER_PARAMS = json.loads(STRATEGY_JSON.read_text(encoding="utf-8"))["active_strategy"]["runner_params"]

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "2026-09-04"),
    ("active_2025_2026", "2025-01-02", "2026-09-04"),
]
INITIAL_VALUE = 1_000_000.0
COMMISSION = 0.001425
SLIPPAGE = 0.0005
SELL_TAX = 0.001
BANDS = [0.0, 0.005, 0.01, 0.02, 0.03]


def build_weights_by_regime(cash_sleeve_weight: float) -> dict[str, dict[str, float]]:
    """Reconstruct a2118's own weights_by_regime dict (mirrors run_a2118
    lines ~823-915) so a daily regime-label series can be mapped to actual
    weight vectors without touching a2118.py."""
    policy_signal, _ = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal = _load(_resolve(DEFAULT_GOLDEN_SIGNAL))
    current_defensive = _add_00713_cash_sleeve(_weights_from_group_a_plus(policy_signal), cash_sleeve_weight)
    basket = _add_00713_cash_sleeve(DEFENSIVE_BASKETS["bond0_cash60"], cash_sleeve_weight)
    golden_weights = _add_00713_cash_sleeve(_weights_from_group_a(golden_signal), cash_sleeve_weight)
    return {
        "golden1": _normalize(golden_weights),
        "group_a_plus_defensive": _normalize(basket),
        "group_a_plus_recovery": _normalize(_recovery_boost_weights(current_defensive, 0.0)),
        RECOVERY_00631L_BOOST_REGIME: _normalize(_recovery_boost_weights(current_defensive, 0.0)),
        NCF_LB_REGIME: _normalize(_late_bull_hedge_weights(golden_weights)),
        NCF_LB_SOFT_REGIME: _normalize(_late_bull_hedge_weights(golden_weights, intensity=0.5)),
        GOLDEN_TAIL_TRIM_REGIME: _normalize(_golden_tail_trim_weights(golden_weights, 0.5)),
        GOLDEN_FOLLOW_THROUGH_TRIM_REGIME: _normalize(_golden_tail_trim_weights(golden_weights, 0.5)),
        GOLDEN_REBOUND_RECAPTURE_REGIME: _normalize(golden_weights),
        GOLDEN_LEVERAGE_CAP_REGIME: _normalize(golden_weights),
    }


def main():
    results = {}
    for label, start, end in WINDOWS:
        report, frame = run_a2118(start, end, INITIAL_VALUE, DB_PATH, **RUNNER_PARAMS)
        regime = frame["execution_regime"].astype(str)
        cash_sleeve_weight = float(RUNNER_PARAMS.get("group_a_plusplus_00713_cash_sleeve_weight", 0.0))
        weights_by_regime = build_weights_by_regime(cash_sleeve_weight)

        # Diagnostic: how much does a2118's REAL regime series move total
        # portfolio weight day to day, at the label-change level (band=0)?
        prev = None
        switch_days = 0
        turnovers = []
        for r in regime:
            if prev is not None and r != prev:
                switch_days += 1
                w_prev = weights_by_regime.get(prev, {})
                w_new = weights_by_regime.get(r, {})
                turnovers.append(sum(abs(float(w_new.get(t, 0.0)) - float(w_prev.get(t, 0.0))) for t in TICKERS))
            prev = r

        total_return_prices, _ = _load_total_return_prices(DB_PATH, frame.index)

        window_result = {
            "diagnostic": {
                "total_days": len(regime),
                "regime_switch_days": switch_days,
                "switch_turnovers": turnovers,
                "min_switch_turnover": min(turnovers) if turnovers else None,
                "max_switch_turnover": max(turnovers) if turnovers else None,
            },
            "bands": {},
        }

        for band in BANDS:
            curve, sim_result = _simulate_costed_curve_with_no_trade_band(
                total_return_prices, regime, weights_by_regime, INITIAL_VALUE,
                COMMISSION, SLIPPAGE, SELL_TAX, band,
            )
            m = _metrics(curve, INITIAL_VALUE)
            window_result["bands"][f"{band}"] = {**m, **sim_result}

        results[label] = window_result
        print(f"=== {label} ({start}..{end}) ===")
        print(f"  regime_switch_days={switch_days}/{len(regime)}  "
              f"switch_turnover_range=[{window_result['diagnostic']['min_switch_turnover']}, "
              f"{window_result['diagnostic']['max_switch_turnover']}]")
        for band in BANDS:
            r = window_result["bands"][f"{band}"]
            print(f"  band={band*100:4.1f}%  final={r['final_value']:>12,.0f}  sharpe={r['sharpe_ratio']:7.4f}  "
                  f"mdd={r['max_drawdown']*100:7.2f}%  rebal={r.get('rebalance_count')}  skipped={r.get('skipped_rebalance_count')}")
        print()

        out_path = PROJECT_ROOT / f"results/no_trade_band_a2118_faithful_{label}_20260908.json"
        base = window_result["bands"]["0.0"]
        payload = {
            "experiment": "no_trade_band_a2118_faithful",
            "window": {"start": start, "end": end},
            "diagnostic": window_result["diagnostic"],
            "baseline": {"metrics": {k: base[k] for k in ("final_value", "sharpe_ratio", "max_drawdown")}},
            "rows": [
                {
                    "name": f"band_{band}",
                    "metrics": {k: window_result["bands"][f"{band}"][k] for k in ("final_value", "sharpe_ratio", "max_drawdown")},
                }
                for band in BANDS
            ],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return results


if __name__ == "__main__":
    main()
