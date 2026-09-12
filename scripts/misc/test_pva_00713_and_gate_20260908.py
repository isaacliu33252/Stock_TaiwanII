#!/usr/bin/env python3
"""Test Fable direction #4: AND-gate combination of PVA leverage_scale
(already-proven production signal) and the 00713-vs-0050 relative-strength
z-score (direction #3: real IC but standalone rule failed in crisis windows).

Hypothesis: requiring the 00713 signal to be confirmed by PVA before applying
EXTRA de-risking (beyond what PVA alone already gives) reduces the
false-positive/mistimed-whipsaw problem that made direction #3's standalone
rule worsen MDD in covid_2020/inflation_2022.

Rule definitions:
- PVA elevated: leverage_scale < PVA_ELEVATED_THRESHOLD (0.85; PVA's own
  long-run mean leverage_scale is ~0.817 per the 2026-09-08 direction-1 fork
  report, so 0.85 flags a meaningful minority of days without being extreme).
- 00713 elevated: relative-strength z-score > Z_ELEVATED_THRESHOLD (1.0,
  matching direction #3's own script spirit).
- AND-gate combined scale: leverage_scale * EXTRA_CUT (0.80) only when BOTH
  conditions hold; otherwise combined scale == plain leverage_scale (i.e. the
  AND-gate rule is never LESS protective than plain PVA, only sometimes MORE
  protective, and only when both signals agree).

Compares three variants on the same golden1-style 50/20/30 base split,
00631L weight scaled by each variant's scale series, difference shifted to
0050, cash fixed at 30% (mirrors PVA's own 0050<->00631L-only tradeoff):
  (a) PVA baseline (scale = leverage_scale alone)
  (b) 00713 standalone (scale = clip(1 - K*max(0,z), MIN_SCALE, 1.0), K=0.10,
      no PVA at all -- reproduces direction #3's own baseline for reference)
  (c) AND-gate combined (scale = leverage_scale * extra_cut as above)

Research-only, does not touch production/live files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
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

# -- PVA reconstruction constants (matches train_dual_group_2024_2026.py, verified 2026-09-08) --
PVA_TARGET_VOL = 0.012
PVA_MIN_LEVERAGE_SCALE = 0.35
PVA_WEIGHT_S = 0.30
PVA_WEIGHT_J = 0.0
PVA_WEIGHT_M = 1.0

# -- 00713 relative-strength constants (matches test_00713_relstrength_signal_20260908.py) --
Z_LOOKBACK = 20
Z_K = 0.10

# -- AND-gate constants --
PVA_ELEVATED_THRESHOLD = 0.85
Z_ELEVATED_THRESHOLD = 1.0
EXTRA_CUT = 0.80
MIN_SCALE = 0.35

BASE_0050, BASE_631L, BASE_CASH = 0.50, 0.20, 0.30
INITIAL_VALUE = 1_000_000.0
COMMISSION_RATE, SLIPPAGE_RATE, SELL_TAX = 0.001425, 0.0005, 0.001


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _rolling_zscore(series: pd.Series, window: int = 252, min_periods: int = 63) -> pd.Series:
    values = series.astype(float)
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std(ddof=1)
    return ((values - mean) / std.replace(0.0, np.nan)).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def build_pva_leverage_scale(db_path: Path, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker='0050.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    df = rows.set_index("dt")
    close = df["close"].astype(float)

    ma120 = close.rolling(120).mean()
    close_ma120_ratio = close / ma120
    p = close_ma120_ratio.fillna(1.0) - 1.0
    v = close.pct_change(63).fillna(0.0)
    a = v - v.shift(20).fillna(v)
    p_z = _rolling_zscore(p)
    v_z = _rolling_zscore(v)
    a_z = _rolling_zscore(a)

    panic = (a_z < -2.0) | (v_z < -2.0)
    greed = (v_z > 1.0) & (a_z > 0.0)
    state_code = pd.Series(0.0, index=df.index)
    state_code[greed] = 1.0
    state_code[panic] = -1.0
    sjm_state = pd.Series("S", index=df.index)
    sjm_state[state_code < 0] = "M"
    sjm_state[state_code > 0] = "J"

    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    downside_returns = returns.where(returns < 0.0, 0.0)
    rolling_peak_20 = close.rolling(20, min_periods=1).max()
    realized_vol_20 = returns.rolling(20, min_periods=5).std(ddof=1).fillna(0.0)
    downside_vol_20 = downside_returns.rolling(20, min_periods=5).std(ddof=1).fillna(0.0)
    drawdown_20 = (close / (rolling_peak_20 + 1e-10) - 1.0).fillna(0.0)
    drawdown_20_abs = drawdown_20.clip(upper=0.0).abs()

    blend_weight = sjm_state.map({"S": PVA_WEIGHT_S, "J": PVA_WEIGHT_J, "M": PVA_WEIGHT_M}).astype(float)
    state_pressure = sjm_state.map({"M": 1.0, "S": 0.35, "J": 0.10}).astype(float)

    regime_pressure = (
        0.40 * _sigmoid(-p_z.to_numpy())
        + 0.35 * _sigmoid(-v_z.to_numpy())
        + 0.25 * _sigmoid(-a_z.to_numpy())
    )
    vol_pressure = np.maximum(realized_vol_20.to_numpy() / PVA_TARGET_VOL - 1.0, 0.0)
    downside_pressure = np.maximum(downside_vol_20.to_numpy() / PVA_TARGET_VOL - 0.5, 0.0)
    drawdown_pressure = np.minimum(drawdown_20_abs.to_numpy() / 0.08, 1.0)

    risk_score = np.clip(
        0.40 * regime_pressure
        + 0.25 * _sigmoid(2.0 * vol_pressure)
        + 0.20 * _sigmoid(2.0 * downside_pressure)
        + 0.10 * drawdown_pressure
        + 0.05 * state_pressure.to_numpy(),
        0.0, 1.0,
    )
    vol_scale = np.clip(PVA_TARGET_VOL / np.maximum(realized_vol_20.to_numpy(), 1e-6), PVA_MIN_LEVERAGE_SCALE, 1.0)
    regime_scale = np.clip(1.0 - 0.85 * blend_weight.to_numpy() * risk_score, PVA_MIN_LEVERAGE_SCALE, 1.0)
    leverage_scale = np.minimum(vol_scale, regime_scale)
    return pd.Series(leverage_scale, index=df.index, name="leverage_scale")


def build_00713_z(tr: pd.DataFrame) -> pd.Series:
    rel = tr["00713.TW"] / tr["0050.TW"]
    return (rel - rel.rolling(Z_LOOKBACK).mean()) / rel.rolling(Z_LOOKBACK).std()


def simulate(tr: pd.DataFrame, scale: pd.Series, start: str, end: str) -> dict:
    window = tr.loc[start:end]
    scale_w = scale.reindex(window.index).fillna(1.0)
    shares = {"0050.TW": 0.0, "00631L.TW": 0.0}
    cash = INITIAL_VALUE
    values = []
    prev_w631l = None
    for dt, row in window.iterrows():
        gross = cash + shares["0050.TW"] * row["0050.TW"] + shares["00631L.TW"] * row["00631L.TW"]
        s = float(scale_w.loc[dt])
        w631l = BASE_631L * min(1.0, max(MIN_SCALE, s))
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
    con = duckdb.connect(str(DB_PATH), read_only=True)
    dates = con.execute(
        "SELECT dt FROM ohlcv WHERE ticker='0050.TW' AND dt>='2017-09-19' AND dt<='2026-09-07' ORDER BY dt"
    ).fetchdf()
    con.close()
    close_index = pd.DatetimeIndex(pd.to_datetime(dates["dt"]))
    tr, _cov = _load_total_return_prices(DB_PATH, close_index)
    tr = tr.dropna()

    pva_scale = build_pva_leverage_scale(DB_PATH, "2017-07-01", "2026-09-07")
    z = build_00713_z(tr)

    pva_elevated = pva_scale < PVA_ELEVATED_THRESHOLD
    z_elevated = (z > Z_ELEVATED_THRESHOLD).reindex(pva_scale.index).fillna(False)
    both = pva_elevated & z_elevated
    print(f"PVA elevated days: {int(pva_elevated.sum())}/{len(pva_scale)} "
          f"({pva_elevated.mean()*100:.1f}%), PVA mean={pva_scale.mean():.4f}")
    print(f"00713-z elevated days: {int(z_elevated.sum())}/{z_elevated.notna().sum()} "
          f"({z_elevated.mean()*100:.1f}%)")
    print(f"BOTH elevated (AND-gate fires) days: {int(both.sum())} ({both.mean()*100:.2f}%)")
    print()

    scale_a = pva_scale  # (a) PVA baseline
    scale_b = (1.0 - Z_K * z.clip(lower=0.0)).clip(lower=MIN_SCALE, upper=1.0)  # (b) 00713 standalone
    scale_c = pva_scale * np.where(both.reindex(pva_scale.index).fillna(False), EXTRA_CUT, 1.0)  # (c) AND-gate

    header = (f"{'window':18s} {'variant':10s} {'final_value':>13s} {'d_final':>11s} "
              f"{'sharpe':>8s} {'d_sh':>7s} {'mdd':>8s} {'d_mdd':>7s}")
    print(header)
    for label, (start, end) in WINDOWS.items():
        res_a = simulate(tr, scale_a, start, end)
        res_b = simulate(tr, scale_b, start, end)
        res_c = simulate(tr, scale_c, start, end)
        for name, res in (("(a)PVA", res_a), ("(b)00713", res_b), ("(c)AND", res_c)):
            d_final = res["final_value"] - res_a["final_value"]
            d_sh = res["sharpe_ratio"] - res_a["sharpe_ratio"]
            d_mdd = (res["max_drawdown"] - res_a["max_drawdown"]) * 100
            print(f"{label:18s} {name:10s} {res['final_value']:13,.0f} {d_final:+11,.0f} "
                  f"{res['sharpe_ratio']:8.4f} {d_sh:+7.4f} {res['max_drawdown']*100:8.2f} {d_mdd:+7.2f}")


if __name__ == "__main__":
    main()
