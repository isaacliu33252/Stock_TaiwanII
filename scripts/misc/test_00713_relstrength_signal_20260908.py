#!/usr/bin/env python3
"""Test Fable direction #3: 00713.TW vs 0050.TW relative-strength z-score as
an early regime/de-risk signal for 00631L.TW weight, standalone (not stacked
on PVA, to isolate this signal's own effect first).

IC screen already passed (see fork report 2026-09-08): 20d-lookback z-score
vs 0050 forward-15d return/max-drawdown gives IC=-0.113 / -0.082 respectively
(p<0.001, n=2146), direction consistent with the hypothesis (00713 relative
outperformance -> subsequent 0050 weakness).

Design: golden1-style base split 0050=50%/00631L=20%/cash=30%. 00631L weight
is scaled by scale(z) = clip(1 - k*max(0, z), min_scale, 1.0), same bound
style as production PVA (min_scale=0.35). Difference shifted to 0050 (cash
held fixed at 30%, mirroring how PVA itself only trades off 0050<->00631L).
Daily rebalance (z changes daily). Research-only, does not touch production.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_switch_policy import DB_PATH

WINDOWS = {
    "covid_2020": ("2020-01-02", "2020-12-31"),
    "inflation_2022": ("2022-01-03", "2022-12-30"),
    "live_2024_2026": ("2024-01-02", "2026-09-07"),
    "active_2025_2026": ("2025-01-02", "2026-09-07"),
}

LOOKBACK = 20
K = 0.10
MIN_SCALE = 0.35
BASE_0050, BASE_631L, BASE_CASH = 0.50, 0.20, 0.30
INITIAL_VALUE = 1_000_000.0
COMMISSION_RATE, SLIPPAGE_RATE, SELL_TAX = 0.001425, 0.0005, 0.001


def build_z(tr: pd.DataFrame) -> pd.Series:
    rel = tr["00713.TW"] / tr["0050.TW"]
    return (rel - rel.rolling(LOOKBACK).mean()) / rel.rolling(LOOKBACK).std()


def simulate(tr: pd.DataFrame, z: pd.Series, start: str, end: str, use_signal: bool) -> dict:
    window = tr.loc[start:end]
    z_window = z.reindex(window.index)
    tickers = ["0050.TW", "00631L.TW", "cash"]
    shares = {"0050.TW": 0.0, "00631L.TW": 0.0}
    cash = INITIAL_VALUE
    values = []
    prev_w631l = None
    for dt, row in window.iterrows():
        gross = cash + shares["0050.TW"] * row["0050.TW"] + shares["00631L.TW"] * row["00631L.TW"]
        zt = z_window.loc[dt]
        if use_signal and pd.notna(zt):
            scale = min(1.0, max(MIN_SCALE, 1.0 - K * max(0.0, zt)))
        else:
            scale = 1.0
        w631l = BASE_631L * scale
        w0050 = BASE_0050 + (BASE_631L - w631l)
        wcash = BASE_CASH
        if prev_w631l is None or abs(w631l - prev_w631l) > 1e-9:
            current_values = {"0050.TW": shares["0050.TW"] * row["0050.TW"], "00631L.TW": shares["00631L.TW"] * row["00631L.TW"]}
            net_value = gross
            for _ in range(3):
                target_values = {"0050.TW": net_value * w0050, "00631L.TW": net_value * w631l}
                cost, _turnover = _trade_cost(current_values, target_values, COMMISSION_RATE, SLIPPAGE_RATE, SELL_TAX)
                net_value = max(gross - cost, 0.0)
            shares["0050.TW"] = net_value * w0050 / max(row["0050.TW"], 1e-12)
            shares["00631L.TW"] = net_value * w631l / max(row["00631L.TW"], 1e-12)
            cash = net_value * wcash
            gross = net_value
            prev_w631l = w631l
        values.append(gross)
    curve = pd.Series(values, index=window.index, dtype=float)
    ret = curve.pct_change().dropna()
    sharpe = (ret.mean() / ret.std()) * np.sqrt(252) if ret.std() > 0 else float("nan")
    peak = curve.cummax()
    mdd = ((curve - peak) / peak).min()
    return {"final_value": float(curve.iloc[-1]), "sharpe_ratio": float(sharpe), "max_drawdown": float(mdd)}


def main() -> None:
    import duckdb

    con = duckdb.connect(str(DB_PATH), read_only=True)
    dates = con.execute(
        "SELECT dt FROM ohlcv WHERE ticker='0050.TW' AND dt>='2017-09-19' AND dt<='2026-09-07' ORDER BY dt"
    ).fetchdf()
    con.close()
    close_index = pd.DatetimeIndex(pd.to_datetime(dates["dt"]))
    tr, cov = _load_total_return_prices(DB_PATH, close_index)
    tr = tr.dropna()
    z = build_z(tr)

    print(f"z-score coverage: {z.notna().sum()} / {len(z)} days")
    print()
    print(f"{'window':20s} {'base_final':>13s} {'sig_final':>13s} {'d_final':>11s} {'base_sh':>8s} {'sig_sh':>8s} {'d_sh':>7s} {'base_mdd':>9s} {'sig_mdd':>9s} {'d_mdd':>7s}")
    for label, (start, end) in WINDOWS.items():
        base = simulate(tr, z, start, end, use_signal=False)
        sig = simulate(tr, z, start, end, use_signal=True)
        print(
            f"{label:20s} {base['final_value']:13,.0f} {sig['final_value']:13,.0f} {sig['final_value']-base['final_value']:+11,.0f} "
            f"{base['sharpe_ratio']:8.4f} {sig['sharpe_ratio']:8.4f} {sig['sharpe_ratio']-base['sharpe_ratio']:+7.4f} "
            f"{base['max_drawdown']*100:9.2f} {sig['max_drawdown']*100:9.2f} {(sig['max_drawdown']-base['max_drawdown'])*100:+7.2f}"
        )


if __name__ == "__main__":
    main()
