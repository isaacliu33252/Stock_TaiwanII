#!/usr/bin/env python3
"""Direction #6, production-gate correction (2026-09-08, deeper analysis).

Both test_no_trade_band_20260908.py (the original proxy) and
test_no_trade_band_a2118_faithful_20260908.py modeled PVA-driven 00631L
rebalancing as if production applies the PVA leverage_scale continuously,
every single day it changes at all (their "band=0.0" baseline). That is
NOT what production's actual golden1 generation does.

Verified in train_dual_group_2024_2026.py (the environment that trains/
generates the golden1_0531 signal) lines ~2785-2795: the PVA-rescaled
candidate weights are only actually applied when
`pva_drift = sum(abs(candidate_target_weights - self.weights))` (the FULL
portfolio L1 weight distance between the PVA candidate and the currently
held weights) is >= `self.pva_drift_threshold`. GROUP_A_GOLDEN1_0531_RELEASE.md
section 4 documents the live value: `pva_drift_threshold = 0.05` (5% L1).
Below that threshold, the PVA adjustment is skipped entirely for that step.

This IS a no-trade band -- production already has one, at 5% L1 drift,
built directly into golden1 generation. Direction 6's original "89% of
days trigger rebalancing, 85% noise-sized" finding was computed against a
proxy with NO such gate, and its "optimal band ~=2-3%" conclusion was found
relative to that wrong (ungated) baseline.

This rebuilds the proxy with the real 5% L1-drift gate applied exactly as
production does, and sweeps additional threshold levels around and beyond
it, to see what (if anything) is actually left to gain once the
already-existing gate is modeled correctly.

Caveat (unchanged from the original proxy, not introduced by this
correction): build_pva_leverage_scale is a from-scratch reconstruction of
the vol_scale/regime_scale/blend_weight formula in
train_dual_group_2024_2026.py's _pva_risk_scaled_weights, not the literal
production code path -- structurally matched (same vol_scale/regime_scale/
min(...)  formula, same clip bounds) but not byte-for-byte verified against
a live run. Also, in real production, when the gate blocks the PVA
adjustment, target_weights falls back to `base_target_weights` (the raw PPO
policy action for that step), NOT necessarily "hold the currently-held
weight" -- this proxy (like the original) has no PPO base-action model at
all, so it approximates "gate blocked" as "hold previous weight," which is
the same simplification the original proxy already made for its band
mechanism. Both caveats bias in the same direction as before, so the
before/after comparison in this script is still apples-to-apples.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "misc"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json
import pandas as pd

from test_pva_00713_and_gate_20260908 import build_pva_leverage_scale
from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from backtest_group_a_plus_policy_signal import _normalize

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "2026-09-04"),
    ("active_2025_2026", "2025-01-02", "2026-09-04"),
]
COMMISSION = 0.001425
SLIPPAGE = 0.0005
SELL_TAX = 0.001
INITIAL = 1_000_000.0
PRODUCTION_PVA_DRIFT_THRESHOLD = 0.05  # GROUP_A_GOLDEN1_0531_RELEASE.md section 4


def simulate(scale: pd.Series, prices: pd.DataFrame, l1_drift_threshold: float) -> dict:
    """l1_drift_threshold matches production's pva_drift semantics: the sum
    of absolute weight changes across the moved tickers (0050 + 00631L),
    NOT the single-ticker 00631L delta the original proxy's `band` used."""
    tickers = ["0050.TW", "00631L.TW"]
    shares = {t: 0.0 for t in tickers}
    cash = INITIAL
    held_w631l = None
    values = []
    total_cost = 0.0
    n_rebal = 0
    n_days_checked = 0
    n_days_gate_would_fire = 0
    for dt, price_row in prices.iterrows():
        gross = cash + sum(shares[t] * float(price_row[t]) for t in tickers)
        target_w631l = 0.20 * float(scale.get(dt, scale.iloc[scale.index.get_indexer([dt], method="nearest")[0]]))
        if held_w631l is not None:
            n_days_checked += 1
            l1_drift = 2.0 * abs(target_w631l - held_w631l)  # 0050 moves opposite 00631L, cash fixed
            if l1_drift >= l1_drift_threshold:
                n_days_gate_would_fire += 1
        do_trade = held_w631l is None or 2.0 * abs(target_w631l - held_w631l) >= l1_drift_threshold
        if do_trade:
            w631l = target_w631l
            weights = _normalize({"0050.TW": 0.50 - w631l, "00631L.TW": w631l, "cash": 0.30})
            current_values = {t: shares[t] * float(price_row[t]) for t in tickers}
            net_value = gross
            cost = 0.0
            for _ in range(3):
                target_values = {t: net_value * weights.get(t, 0.0) for t in tickers}
                cost, _turnover = _trade_cost(current_values, target_values, COMMISSION, SLIPPAGE, SELL_TAX)
                net_value = max(gross - cost, 0.0)
            shares = {t: net_value * weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in tickers}
            cash = net_value * weights.get("cash", 0.0)
            gross = net_value
            total_cost += cost
            n_rebal += 1
            held_w631l = w631l
        values.append(gross)
    curve = pd.Series(values, index=prices.index, dtype=float)
    m = _metrics(curve, INITIAL)
    trigger_rate = n_days_gate_would_fire / n_days_checked if n_days_checked else 0.0
    return {**m, "total_cost": total_cost, "n_rebal": n_rebal, "trigger_rate": trigger_rate}


def main() -> None:
    scale_full = build_pva_leverage_scale(DB_PATH, "2020-01-02", "2026-09-04")
    prices_full, _ = _load_total_return_prices(DB_PATH, scale_full.index)

    # 0.0 = original proxy's "no gate at all" baseline (kept for direct
    # comparison). PRODUCTION_PVA_DRIFT_THRESHOLD (0.05) = what production
    # actually runs today. The rest sweep around it to see if there's still
    # room to improve once the real baseline is modeled.
    l1_thresholds = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15, 0.20]

    all_results = {}
    print(f"{'window':20s} {'l1_thr':>7s} {'final':>12s} {'sharpe':>8s} {'mdd':>8s} {'cost':>9s} {'n_rebal':>8s} {'trig%':>7s}")
    for label, start, end in WINDOWS:
        mask = (scale_full.index >= start) & (scale_full.index <= end)
        scale_w = scale_full[mask]
        prices_w = prices_full.loc[scale_w.index]
        all_results[label] = {}
        base = None
        for thr in l1_thresholds:
            r = simulate(scale_w, prices_w, thr)
            if thr == 0.0:
                base = r
            r["delta_final_value_vs_no_gate"] = r["final_value"] - base["final_value"]
            r["delta_max_drawdown_pp_vs_no_gate"] = (r["max_drawdown"] - base["max_drawdown"]) * 100
            all_results[label][str(thr)] = r
            flag = "  <-- production" if thr == PRODUCTION_PVA_DRIFT_THRESHOLD else ("  <-- no gate (old baseline)" if thr == 0.0 else "")
            print(
                f"{label:20s} {thr*100:6.1f}% {r['final_value']:12,.0f} {r['sharpe_ratio']:8.4f} "
                f"{r['max_drawdown']*100:8.2f} {r['total_cost']:9,.0f} {r['n_rebal']:8d} {r['trigger_rate']*100:6.1f}%{flag}"
            )
        print()

    out_path = Path(__file__).resolve().parents[2] / "results" / "no_trade_band_production_gate_corrected_20260908.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
