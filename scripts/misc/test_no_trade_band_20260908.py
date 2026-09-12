#!/usr/bin/env python3
"""Fable direction #6 (2026-09-08): does a no-trade band on PVA-driven
00631L/0050 rebalancing reduce transaction cost drag without hurting
crisis-window risk? Reuses build_pva_leverage_scale from
test_pva_00713_and_gate_20260908.py (already-verified PVA formula
reconstruction). Research-only, does not touch production/live files.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "misc"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
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


def simulate(scale: pd.Series, prices: pd.DataFrame, band: float) -> dict:
    tickers = ["0050.TW", "00631L.TW"]
    shares = {t: 0.0 for t in tickers}
    cash = INITIAL
    held_w631l = None
    values = []
    total_cost = 0.0
    n_rebal = 0
    for dt, price_row in prices.iterrows():
        gross = cash + sum(shares[t] * float(price_row[t]) for t in tickers)
        target_w631l = 0.20 * float(scale.get(dt, scale.iloc[scale.index.get_indexer([dt], method="nearest")[0]]))
        do_trade = held_w631l is None or abs(target_w631l - held_w631l) > band
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
    return {**m, "total_cost": total_cost, "n_rebal": n_rebal}


def main() -> None:
    scale_full = build_pva_leverage_scale(DB_PATH, "2020-01-02", "2026-09-04")
    prices_full, _ = _load_total_return_prices(DB_PATH, scale_full.index)
    bands = [0.0, 0.005, 0.01, 0.02, 0.03]
    print(f"{'window':20s} {'band':>6s} {'final':>12s} {'sharpe':>8s} {'mdd':>8s} {'cost':>10s} {'n_rebal':>8s}")
    results = {}
    for label, start, end in WINDOWS:
        mask = (scale_full.index >= start) & (scale_full.index <= end)
        scale_w = scale_full[mask]
        prices_w = prices_full.loc[scale_w.index]
        results[label] = {}
        for band in bands:
            r = simulate(scale_w, prices_w, band)
            results[label][band] = r
            print(f"{label:20s} {band*100:5.1f}% {r['final_value']:12,.0f} {r['sharpe_ratio']:8.4f} {r['max_drawdown']*100:8.2f} {r['total_cost']:10,.0f} {r['n_rebal']:8d}")
        print()


if __name__ == "__main__":
    main()
