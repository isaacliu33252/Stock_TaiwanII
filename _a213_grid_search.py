#!/usr/bin/env python3
"""Grid search A213 improvement: vol_override threshold + switch rule tuning"""
import sys, json, itertools
sys.path.insert(0, '.')

from pathlib import Path
from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_switch_policy import DB_PATH, SwitchRule, _load_chip_features, _load_prices, _switch_returns
from backtest_group_a_plus_policy_signal import DEFAULT_DECISION_POINTER, DEFAULT_GOLDEN_SIGNAL, TICKERS, _load, _load_policy_signal, _normalize, _resolve, _weights_from_group_a, _weights_from_group_a_plus
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from backtest_group_a_plus_defensive_basket import _simulate_costed_curve, _recovery_ramp_regime, DEFENSIVE_BASKETS
from backtest_group_a_plus_policy_signal import _metrics

START = "2025-01-02"
END = "2026-06-22"
INITIAL_VALUE = 1_000_000.0

def run_variant(
    ma_window, dd_threshold, entry_gap, exit_gap,
    vol_enter_threshold, warmup_days=180,
    basket_name="cash30"
):
    switch_rule = SwitchRule(
        f"search_ma{ma_window}_dd{abs(int(dd_threshold*100))}_tot{int(entry_gap*1000)}_x{int(exit_gap*1000)}",
        ma_window, entry_gap, exit_gap,
        ma_window, dd_threshold,
        5, 5, 0, None, 0, None, 6, 6
    )

    policy_signal = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))[0]
    golden_signal = _load(_resolve(DEFAULT_GOLDEN_SIGNAL))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS[basket_name])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(START, warmup_days)
    full_prices = _load_prices(_resolve(DB_PATH), list(TICKERS), load_start, END)
    full_chip = _load_chip_features(_resolve(DB_PATH), full_prices.index, load_start, END)
    full_events, full_frame = _switch_returns(full_prices, full_chip, switch_rule)
    close_prices, frame, events = _trim_window(full_prices, full_frame, full_events, START, END)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(DB_PATH), close_prices.index)

    if vol_enter_threshold is not None:
        vol_col = "realized_vol_0050_20d"
        if vol_col in frame.columns:
            frame["vol_override"] = frame[vol_col] > vol_enter_threshold
        else:
            frame["vol_override"] = False
    else:
        frame["vol_override"] = False

    execution_regime = _recovery_ramp_regime(
        frame["regime"], frame,
        vol_enter_threshold=vol_enter_threshold,
    )

    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
    }
    curve, _ = _simulate_costed_curve(
        total_return_prices, execution_regime, weights_by_regime,
        INITIAL_VALUE, 0.001425, 0.0005, 0.001,
    )
    m = _metrics(curve, INITIAL_VALUE)
    return {
        "final_value": m["final_value"],
        "total_return": m["total_return"],
        "annual_return": m["annual_return"],
        "sharpe": m["sharpe_ratio"],
        "sortino": m.get("sortino_ratio", None),
        "mdd": m["max_drawdown"],
        "turnover": m.get("turnover_value", 0),
        "params": {
            "ma_window": ma_window, "dd_threshold": dd_threshold,
            "entry_gap": entry_gap, "exit_gap": exit_gap,
            "vol_enter_threshold": vol_enter_threshold,
        }
    }

# Grid search
base_params = dict(ma_window=75, dd_threshold=-0.11, entry_gap=0.0175, exit_gap=0.020)
best = None
results = []

# 1. vol_enter_threshold sweep (with base switch params)
print("=== vol_enter_threshold sweep ===")
for vol_thresh in [None, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040]:
    r = run_variant(**{**base_params, "vol_enter_threshold": vol_thresh})
    r["variant"] = f"vol_thresh={vol_thresh}"
    results.append(r)
    print(f"  vol={vol_thresh}: Sharpe={r['sharpe']:.3f}  MDD={r['mdd']:.2%}  Annual={r['annual_return']:+.2%}  Final={r['final_value']:,.0f}")

print()
# 2. DD threshold sweep
print("=== DD threshold sweep ===")
for dd in [-0.06, -0.08, -0.10, -0.11, -0.13, -0.15]:
    r = run_variant(**{**base_params, "dd_threshold": dd, "vol_enter_threshold": None})
    r["variant"] = f"dd={dd}"
    results.append(r)
    print(f"  dd={dd}: Sharpe={r['sharpe']:.3f}  MDD={r['mdd']:.2%}  Annual={r['annual_return']:+.2%}  Final={r['final_value']:,.0f}")

print()
# 3. Entry/Exit gap sweep
print("=== Entry/Exit gap sweep ===")
for eg, xg in [(0.010, 0.015), (0.015, 0.020), (0.0175, 0.020), (0.020, 0.025), (0.025, 0.030)]:
    r = run_variant(**{**base_params, "entry_gap": eg, "exit_gap": xg, "vol_enter_threshold": None})
    r["variant"] = f"eg={eg}_xg={xg}"
    results.append(r)
    print(f"  eg={eg} xg={xg}: Sharpe={r['sharpe']:.3f}  MDD={r['mdd']:.2%}  Annual={r['annual_return']:+.2%}")

print()
# 4. Combined: best vol + tighter DD
print("=== Combined: vol + tighter DD ===")
for vol_thresh in [0.020, 0.025]:
    for dd in [-0.07, -0.08, -0.09, -0.10]:
        r = run_variant(**{**base_params, "dd_threshold": dd, "vol_enter_threshold": vol_thresh})
        r["variant"] = f"vol={vol_thresh}_dd={dd}"
        results.append(r)
        print(f"  vol={vol_thresh} dd={dd}: Sharpe={r['sharpe']:.3f}  MDD={r['mdd']:.2%}  Annual={r['annual_return']:+.2%}  Final={r['final_value']:,.0f}")

# Find best by Sharpe
best = max(results, key=lambda x: x["sharpe"])
print(f"\n=== BEST by Sharpe ===")
print(f"  {best['variant']}: Sharpe={best['sharpe']:.3f}  MDD={best['mdd']:.2%}  Annual={best['annual_return']:+.2%}  Final={best['final_value']:,.0f}")
print(f"  params: {best['params']}")

# Find best by MDD
best_mdd = min(results, key=lambda x: x["mdd"])
print(f"\n=== BEST by MDD ===")
print(f"  {best_mdd['variant']}: Sharpe={best_mdd['sharpe']:.3f}  MDD={best_mdd['mdd']:.2%}  Annual={best_mdd['annual_return']:+.2%}  Final={best_mdd['final_value']:,.0f}")
print(f"  params: {best_mdd['params']}")

# Save all
with open("results/a213_grid_search.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nSaved: results/a213_grid_search.json")
