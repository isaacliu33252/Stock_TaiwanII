#!/usr/bin/env python3
"""Fable direction #3 follow-up: find a deployable rule for the 00713-vs-0050
relative-strength signal (IC already confirmed real at lookback=20 in
test_00713_relstrength_signal_20260908.py). The tested linear-scaling rule
failed (worsened MDD in real crisis windows). This script:

1. Re-verifies IC at shorter lookbacks (5, 10 days) before building rules on
   them -- do not assume the 20d IC transfers.
2. Tests non-linear scaling and pure-threshold rule variants at whichever
   lookback(s) pass the IC screen, across the 4 standard windows.

Research-only, does not touch production/live files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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

BASE_0050, BASE_631L, BASE_CASH = 0.50, 0.20, 0.30
INITIAL_VALUE = 1_000_000.0
COMMISSION_RATE, SLIPPAGE_RATE, SELL_TAX = 0.001425, 0.0005, 0.001
MIN_SCALE = 0.35


def build_z(tr: pd.DataFrame, lookback: int) -> pd.Series:
    rel = tr["00713.TW"] / tr["0050.TW"]
    return (rel - rel.rolling(lookback).mean()) / rel.rolling(lookback).std()


def ic_screen(tr: pd.DataFrame, z: pd.Series, horizon: int = 15) -> dict:
    fwd_ret = tr["0050.TW"].pct_change(horizon).shift(-horizon)
    fwd_dd = (
        tr["0050.TW"].rolling(horizon).apply(lambda s: (s.iloc[-1] / s.max()) - 1.0, raw=False).shift(-horizon)
    )
    df = pd.DataFrame({"z": z, "fwd_ret": fwd_ret, "fwd_dd": fwd_dd}).dropna()
    ic_ret, p_ret = stats.spearmanr(df["z"], df["fwd_ret"])
    ic_dd, p_dd = stats.spearmanr(df["z"], df["fwd_dd"])
    return {"n": len(df), "ic_fwd_ret": ic_ret, "p_fwd_ret": p_ret, "ic_fwd_dd": ic_dd, "p_fwd_dd": p_dd}


def simulate(tr: pd.DataFrame, scale_series: pd.Series, start: str, end: str) -> dict:
    window = tr.loc[start:end]
    scale_w = scale_series.reindex(window.index)
    shares = {"0050.TW": 0.0, "00631L.TW": 0.0}
    cash = INITIAL_VALUE
    values = []
    prev_w631l = None
    for dt, row in window.iterrows():
        gross = cash + shares["0050.TW"] * row["0050.TW"] + shares["00631L.TW"] * row["00631L.TW"]
        s = scale_w.loc[dt]
        s = 1.0 if pd.isna(s) else float(s)
        w631l = BASE_631L * s
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


def scale_linear(z: pd.Series, k: float) -> pd.Series:
    return z.apply(lambda zt: min(1.0, max(MIN_SCALE, 1.0 - k * max(0.0, zt))) if pd.notna(zt) else 1.0)


def scale_convex(z: pd.Series, k: float, power: float, thresh: float) -> pd.Series:
    def f(zt):
        if pd.isna(zt) or zt <= thresh:
            return 1.0
        excess = zt - thresh
        return min(1.0, max(MIN_SCALE, 1.0 - k * (excess ** power)))
    return z.apply(f)


def scale_threshold(z: pd.Series, thresh: float, low_scale: float) -> pd.Series:
    return z.apply(lambda zt: low_scale if (pd.notna(zt) and zt > thresh) else 1.0)


def main() -> None:
    import duckdb

    con = duckdb.connect(str(DB_PATH), read_only=True)
    dates = con.execute(
        "SELECT dt FROM ohlcv WHERE ticker='0050.TW' AND dt>='2017-09-19' AND dt<='2026-09-07' ORDER BY dt"
    ).fetchdf()
    con.close()
    close_index = pd.DatetimeIndex(pd.to_datetime(dates["dt"]))
    tr, _cov = _load_total_return_prices(DB_PATH, close_index)
    tr = tr.dropna()

    print("=== Step 1: IC re-verification at shorter lookbacks ===")
    z_by_lb = {}
    for lb in (5, 10, 20):
        z_lb = build_z(tr, lb)
        z_by_lb[lb] = z_lb
        ic = ic_screen(tr, z_lb)
        print(f"lookback={lb:2d}d  n={ic['n']:5d}  IC(fwd_ret)={ic['ic_fwd_ret']:+.4f} (p={ic['p_fwd_ret']:.2e})  "
              f"IC(fwd_dd)={ic['ic_fwd_dd']:+.4f} (p={ic['p_fwd_dd']:.2e})")
    print()

    print("=== Step 2: rule variants across 4 windows ===")
    z20 = z_by_lb[20]
    z10 = z_by_lb[10]
    baseline_cache = {}
    for label, (start, end) in WINDOWS.items():
        baseline_cache[label] = simulate(tr, pd.Series(1.0, index=tr.index), start, end)

    variants = {
        "linear_k0.10_lb20 (original)": scale_linear(z20, 0.10),
        "linear_k0.30_lb20 (original)": scale_linear(z20, 0.30),
        "convex_p2_k0.15_th1.0_lb20": scale_convex(z20, 0.15, 2.0, 1.0),
        "convex_p3_k0.08_th1.0_lb20": scale_convex(z20, 0.08, 3.0, 1.0),
        "threshold_th1.5_scale0.35_lb20": scale_threshold(z20, 1.5, 0.35),
        "threshold_th2.0_scale0.35_lb20": scale_threshold(z20, 2.0, 0.35),
        "threshold_th1.5_scale0.60_lb20": scale_threshold(z20, 1.5, 0.60),
        "linear_k0.10_lb10": scale_linear(z10, 0.10),
        "threshold_th1.5_scale0.35_lb10": scale_threshold(z10, 1.5, 0.35),
    }

    header = f"{'window':18s} {'variant':32s} {'d_final':>11s} {'d_sharpe':>9s} {'d_mdd_pp':>9s}"
    print(header)
    results = {}
    for label, (start, end) in WINDOWS.items():
        base = baseline_cache[label]
        results[label] = {"baseline": base, "variants": {}}
        for name, scale_series in variants.items():
            sig = simulate(tr, scale_series, start, end)
            d_final = sig["final_value"] - base["final_value"]
            d_sharpe = sig["sharpe_ratio"] - base["sharpe_ratio"]
            d_mdd = (sig["max_drawdown"] - base["max_drawdown"]) * 100
            results[label]["variants"][name] = {**sig, "d_final": d_final, "d_sharpe": d_sharpe, "d_mdd_pp": d_mdd}
            print(f"{label:18s} {name:32s} {d_final:+11,.0f} {d_sharpe:+9.4f} {d_mdd:+9.2f}")
        print()

    import json
    out_path = PROJECT_ROOT / "results" / "fable_direction3_rule_variants_20260909.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    print(f"Saved: {out_path}")

    run_and_gate_test(tr, z20)


def scale_and_gate(z: pd.Series, dd_from_high: pd.Series, z_thresh: float, dd_thresh: float, low_scale: float) -> pd.Series:
    def f(dt, zt):
        ddv = dd_from_high.get(dt, 0.0)
        if pd.notna(zt) and zt > z_thresh and ddv <= dd_thresh:
            return low_scale
        return 1.0
    return pd.Series({dt: f(dt, zt) for dt, zt in z.items()})


def run_and_gate_test(tr: pd.DataFrame, z20: pd.Series) -> None:
    px = tr["0050.TW"]
    dd_from_high = (px / px.cummax()) - 1.0  # simplified proxy for "already-stressed" market state
    print("=== Step 3: AND-gate (relstrength z + simplified drawdown-stress proxy) ===")
    variants = {
        "and_z1.5_dd-0.05_scale0.35": scale_and_gate(z20, dd_from_high, 1.5, -0.05, 0.35),
        "and_z1.0_dd-0.05_scale0.35": scale_and_gate(z20, dd_from_high, 1.0, -0.05, 0.35),
        "and_z1.5_dd-0.08_scale0.35": scale_and_gate(z20, dd_from_high, 1.5, -0.08, 0.35),
        "and_z1.0_dd-0.08_scale0.50": scale_and_gate(z20, dd_from_high, 1.0, -0.08, 0.50),
    }
    header = f"{'window':18s} {'variant':32s} {'d_final':>11s} {'d_sharpe':>9s} {'d_mdd_pp':>9s} {'trig_days':>9s}"
    print(header)
    results = {}
    for label, (start, end) in WINDOWS.items():
        base = simulate(tr, pd.Series(1.0, index=tr.index), start, end)
        results[label] = {}
        for name, scale_series in variants.items():
            sig = simulate(tr, scale_series, start, end)
            d_final = sig["final_value"] - base["final_value"]
            d_sharpe = sig["sharpe_ratio"] - base["sharpe_ratio"]
            d_mdd = (sig["max_drawdown"] - base["max_drawdown"]) * 100
            trig = int((scale_series.reindex(tr.loc[start:end].index) < 1.0).sum())
            results[label][name] = {"d_final": d_final, "d_sharpe": d_sharpe, "d_mdd_pp": d_mdd, "trig_days": trig}
            print(f"{label:18s} {name:32s} {d_final:+11,.0f} {d_sharpe:+9.4f} {d_mdd:+9.2f} {trig:9d}")
        print()
    import json
    out_path = PROJECT_ROOT / "results" / "fable_direction3_and_gate_variants_20260909.json"
    out_path.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
