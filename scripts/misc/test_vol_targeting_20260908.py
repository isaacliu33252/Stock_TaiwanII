#!/usr/bin/env python3
"""Test Fable direction #10: classic symmetric volatility-targeting overlay
for 00631L position sizing, vs. the existing PVA leverage_scale mechanism.

Step 1 (already answered by inspecting scripts/misc/test_pva_00713_and_gate_20260908.py,
build_pva_leverage_scale()): PVA's vol_scale component is

    vol_scale = clip(PVA_TARGET_VOL / realized_vol_20, PVA_MIN_LEVERAGE_SCALE, 1.0)

This is clipped with an UPPER bound of 1.0 -- it can only ever cap/reduce
00631L's weight when realized_vol_20 > PVA_TARGET_VOL, and never scales above
the 1.0x (20% base) weight even when realized_vol_20 is far below target.
Genuine symmetric vol-targeting is therefore NOT present in production; this
confirms direction #10 is not moot and the standalone overlay below is a novel
test, not a duplicate of existing PVA behavior.

Step 2: build a standalone symmetric vol-targeting overlay:

    vol_target_scale = clip(PVA_TARGET_VOL / realized_vol_20, FLOOR, CEILING)

with FLOOR=0.5, CEILING=1.5 (symmetric log-distance around 1.0x; caps 00631L
weight in [10%, 30%] against a 20% base -- deliberately conservative vs. a
wider band, since the whole point of this test is to check the blow-up risk
of the CEILING side, not to find the most aggressive parameterization).
Applied to 00631L weight (base 20% * vol_target_scale), difference shifted to
0050, cash fixed at 30% -- same mechanic as the PVA/00713 scripts this session.

Step 3: compare final_value/Sharpe/MDD against the PVA-only baseline across
the 4 standard windows.

Step 4: explicit blow-up check -- does realized_vol_20 dip low enough in
Dec 2019/Jan 2020 (right before the COVID crash) to push vol_target_scale
toward the 1.5x ceiling, and does that hurt covid_2020 performance?

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

# -- symmetric vol-targeting constants --
VT_FLOOR = 0.5
VT_CEILING = 1.5

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


def build_0050_series(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker='0050.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def build_pva_leverage_scale(close: pd.Series) -> pd.Series:
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
    state_code = pd.Series(0.0, index=close.index)
    state_code[greed] = 1.0
    state_code[panic] = -1.0
    sjm_state = pd.Series("S", index=close.index)
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
    return pd.Series(leverage_scale, index=close.index, name="leverage_scale"), realized_vol_20


def simulate(tr: pd.DataFrame, scale: pd.Series, start: str, end: str, min_scale: float, max_scale: float) -> dict:
    window = tr.loc[start:end]
    scale_w = scale.reindex(window.index).fillna(1.0)
    shares = {"0050.TW": 0.0, "00631L.TW": 0.0}
    cash = INITIAL_VALUE
    values = []
    prev_w631l = None
    for dt, row in window.iterrows():
        gross = cash + shares["0050.TW"] * row["0050.TW"] + shares["00631L.TW"] * row["00631L.TW"]
        s = float(scale_w.loc[dt])
        w631l = BASE_631L * min(max_scale, max(min_scale, s))
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

    px = build_0050_series(DB_PATH, "2017-07-01", "2026-09-07")
    close = px["close"].astype(float)
    pva_scale, realized_vol_20 = build_pva_leverage_scale(close)

    vol_target_scale = pd.Series(
        np.clip(PVA_TARGET_VOL / np.maximum(realized_vol_20.to_numpy(), 1e-6), VT_FLOOR, VT_CEILING),
        index=close.index, name="vol_target_scale",
    )

    print(f"vol_target_scale stats: mean={vol_target_scale.mean():.4f} "
          f"min={vol_target_scale.min():.4f} max={vol_target_scale.max():.4f} "
          f"pct_above_1.0={(vol_target_scale > 1.0).mean()*100:.1f}%")
    print()

    # -- Step 4: blow-up check, Dec 2019 / Jan 2020 --
    pre_covid = vol_target_scale.loc["2019-12-01":"2020-02-20"]
    print("Pre-COVID (2019-12-01 to 2020-02-20) vol_target_scale:")
    print(f"  mean={pre_covid.mean():.4f} max={pre_covid.max():.4f} "
          f"days>1.2={(pre_covid > 1.2).sum()} days>1.0={(pre_covid > 1.0).sum()}/{len(pre_covid)}")
    peak_day = pre_covid.idxmax()
    print(f"  peak scale day: {peak_day.date()} scale={pre_covid.max():.4f} "
          f"realized_vol_20={realized_vol_20.loc[peak_day]:.5f}")
    print()

    header = (f"{'window':18s} {'variant':14s} {'final_value':>13s} {'d_final':>11s} "
              f"{'sharpe':>8s} {'d_sh':>7s} {'mdd':>8s} {'d_mdd':>7s}")
    print(header)
    for label, (start, end) in WINDOWS.items():
        res_a = simulate(tr, pva_scale, start, end, PVA_MIN_LEVERAGE_SCALE, 1.0)
        res_d = simulate(tr, vol_target_scale, start, end, VT_FLOOR, VT_CEILING)
        for name, res in (("(a)PVA_base", res_a), ("(d)VolTarget", res_d)):
            d_final = res["final_value"] - res_a["final_value"]
            d_sh = res["sharpe_ratio"] - res_a["sharpe_ratio"]
            d_mdd = (res["max_drawdown"] - res_a["max_drawdown"]) * 100
            print(f"{label:18s} {name:14s} {res['final_value']:13,.0f} {d_final:+11,.0f} "
                  f"{res['sharpe_ratio']:8.3f} {d_sh:+7.3f} {res['max_drawdown']*100:7.2f}% {d_mdd:+6.2f}pp")


if __name__ == "__main__":
    main()
