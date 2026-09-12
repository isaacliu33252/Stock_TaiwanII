#!/usr/bin/env python3
"""Fable direction #1 test (2026-09-08): fold the 00631L downside race
classifier's walk-forward probability into PVA's continuous leverage_scale
as a multiplier, instead of using the classifier as an independent gate
(the standalone binary/graduated modes were already tried and left final
trading value negative -- see project_00631l_downside_risk_forecast_20260710).

Method: reconstruct the exact PVA risk_score/leverage_scale formula from
train_dual_group_2024_2026.py (regime_pressure/vol_pressure/downside_pressure
/drawdown_pressure -> risk_score -> vol_scale & regime_scale -> leverage_scale,
bounded to [pva_min_leverage_scale, 1.0]) on real 0050.TW price history, then
multiply it by a dampening function of the classifier's pred_proba, and
backtest the resulting 00631L weight against plain-PVA baseline over the same
4 standard windows.

Research-only, read-only against the DB. Does not touch any live signal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_race_classifier import (
    FEATURE_COLUMNS,
    HORIZON,
    MIN_TRAIN_ROWS,
    RACE_DOWN_THRESHOLD,
    RACE_UP_THRESHOLD,
    REFIT_EVERY,
    TRAIN_WINDOW,
    _build_features,
    _load_ohlc,
    _race_label,
    _resolve_end_date,
    _walkforward_predict,
    DEFAULT_WINDOWS,
)

# ---- PVA formula constants (production values, confirmed from
# results/last_ppo_group_a_backtest_20250101_20260531_20260609_214023.json
# and train_dual_group_2024_2026.py DEFAULT_GROUP_A_PVA_* constants) ----
PVA_TARGET_VOL = 0.012
PVA_MIN_LEVERAGE_SCALE = 0.35
PVA_WEIGHT_S = 0.30   # blend_weight in S state
PVA_WEIGHT_J = 0.0    # blend_weight in J state
PVA_WEIGHT_M = 1.0    # blend_weight in M state
LEVERAGE_CAP = 0.30   # group_a_00631l_max_weight exposure cap
BASE_00631L = 0.20    # base_target_weights (50/20/30 triplet_v4 base)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _rolling_zscore(series: pd.Series, window: int = 252, min_periods: int = 63) -> pd.Series:
    values = series.astype(float)
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std(ddof=1)
    return ((values - mean) / std.replace(0.0, np.nan)).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def build_pva_leverage_scale(db_path: Path, start: str, end: str) -> pd.DataFrame:
    """Reconstruct daily leverage_scale for 0050.TW/00631L.TW from real price history,
    matching train_dual_group_2024_2026.py's _pva_risk_scaled_weights formula exactly."""
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

    # p/v/a raw signals, exactly as _inject_0050_pva_columns computes them
    ma120 = close.rolling(120).mean()
    close_ma120_ratio = close / ma120
    p = close_ma120_ratio.fillna(1.0) - 1.0
    v = close.pct_change(63)
    v = v.fillna(0.0)
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

    # realized_vol_20 / downside_vol_20 / drawdown_20 (env init formula)
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

    out = pd.DataFrame(
        {
            "sjm_state": sjm_state.to_numpy(),
            "risk_score": risk_score,
            "leverage_scale": leverage_scale,
        },
        index=df.index,
    )
    return out


def simulate_weighted_curve(
    total_return_prices: pd.DataFrame,
    execution_regime: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    golden1_00631l_scale: pd.Series,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> pd.Series:
    """Like _simulate_costed_curve but re-derives golden1 weights daily from a
    supplied 00631L scale series (so it can differ every day, not just at
    regime transitions -- PVA leverage_scale changes continuously)."""
    tickers = list(TICKERS)
    shares = {t: 0.0 for t in tickers}
    cash = float(initial_value)
    values: list[float] = []
    prev_key = None
    for dt, price_row in total_return_prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in tickers)
        regime = str(execution_regime.loc[dt]) if dt in execution_regime.index else "golden1"
        if regime == "golden1":
            scale = float(golden1_00631l_scale.loc[dt]) if dt in golden1_00631l_scale.index else 1.0
            base = dict(weights_by_regime["golden1"])
            base_00631l = float(base.get("00631L.TW", 0.0))
            scaled_00631l = min(LEVERAGE_CAP, base_00631l * scale)
            freed = max(0.0, base_00631l - scaled_00631l)
            base["00631L.TW"] = scaled_00631l
            base["0050.TW"] = float(base.get("0050.TW", 0.0)) + freed
            target_weights = base
            key = f"golden1_scale_{scale:.4f}"
        else:
            target_weights = weights_by_regime.get(regime, weights_by_regime["golden1"])
            key = regime
        if key != prev_key:
            current_values = {t: shares[t] * float(price_row[t]) for t in tickers}
            net_value = gross_value
            cost = 0.0
            for _ in range(3):
                target_values = {t: net_value * target_weights.get(t, 0.0) for t in tickers}
                cost, _turnover = _trade_cost(current_values, target_values, commission_rate, slippage_rate, equity_etf_sell_tax)
                net_value = max(gross_value - cost, 0.0)
            shares = {t: net_value * target_weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in tickers}
            cash = net_value * target_weights.get("cash", 0.0)
            gross_value = net_value
            prev_key = key
        values.append(gross_value)
    return pd.Series(values, index=total_return_prices.index, dtype=float)


def main() -> None:
    db_path = Path(DB_PATH)
    overall_end = _resolve_end_date(db_path, "latest")
    feature_start = "2016-01-04"

    ohlc_0050 = _load_ohlc(db_path, "0050.TW", feature_start, overall_end)
    ohlc_631l = _load_ohlc(db_path, "00631L.TW", feature_start, overall_end)
    features = _build_features(ohlc_0050, ohlc_631l, None)[FEATURE_COLUMNS]
    label = _race_label(ohlc_631l["close"].astype(float), HORIZON, RACE_DOWN_THRESHOLD, RACE_UP_THRESHOLD)
    pred_proba = _walkforward_predict(
        features, label,
        train_window=TRAIN_WINDOW, refit_every=REFIT_EVERY, min_train_rows=MIN_TRAIN_ROWS, horizon=HORIZON,
        n_estimators=100, max_depth=2, learning_rate=0.05,
    )
    print(f"pred_proba computed: {pred_proba.notna().sum()} valid days out of {len(pred_proba)}")

    pva_full = build_pva_leverage_scale(db_path, feature_start, overall_end)
    print(f"PVA leverage_scale reconstructed: {len(pva_full)} rows, "
          f"mean={pva_full['leverage_scale'].mean():.4f}, min={pva_full['leverage_scale'].min():.4f}")

    # Blend function: k controls how much extra cut a high downside-race
    # probability applies on top of PVA's own leverage_scale. pred_proba<=0.5
    # -> no extra cut (f=1.0); pred_proba=1.0 -> leverage_scale further
    # multiplied by (1-k). Two blend strengths tested: k=0.25 (mild), k=0.50 (strong).
    blend_strengths = {"k25": 0.25, "k50": 0.50}

    common_kwargs = dict(
        initial_value=1_000_000.0, db=db_path,
        h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )

    all_results = {}
    for win_label, start, end in DEFAULT_WINDOWS:
        end_resolved = _resolve_end_date(db_path, end)
        report, frame = run_a2118(start=start, end=end_resolved, **common_kwargs)
        prices = _load_prices(db_path, list(TICKERS), start, end_resolved)
        total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
        execution_regime = frame["execution_regime"].astype(str)
        weights_by_regime = dict(report["base_weights"])

        pva_scale = pva_full["leverage_scale"].reindex(frame.index).fillna(1.0)
        proba = pred_proba.reindex(frame.index)

        row_result = {}
        # baseline: PVA scale alone (no classifier blend), no lookahead issue since it's real PVA
        baseline_scale = pva_scale
        curve_base = simulate_weighted_curve(
            total_return_prices, execution_regime, weights_by_regime, baseline_scale,
            1_000_000.0, 0.001425, 0.0005, 0.001,
        )
        m_base = _metrics(curve_base, 1_000_000.0)
        row_result["pva_only"] = m_base

        for name, k in blend_strengths.items():
            damp = 1.0 - k * (proba - 0.5).clip(lower=0.0) / 0.5
            damp = damp.fillna(1.0)
            blended_scale = (pva_scale * damp).clip(lower=PVA_MIN_LEVERAGE_SCALE * (1 - k), upper=1.0)
            curve_blend = simulate_weighted_curve(
                total_return_prices, execution_regime, weights_by_regime, blended_scale,
                1_000_000.0, 0.001425, 0.0005, 0.001,
            )
            m_blend = _metrics(curve_blend, 1_000_000.0)
            row_result[f"blend_{name}"] = m_blend

        all_results[win_label] = row_result
        print(f"\n=== {win_label} ({start}..{end_resolved}) ===")
        for variant, m in row_result.items():
            print(f"  {variant:14s}: final={m['final_value']:>12,.0f}  sharpe={m['sharpe_ratio']:.4f}  mdd={m['max_drawdown']*100:.2f}%")

    print("\n=== Summary: blend vs pva_only deltas ===")
    for win_label, row_result in all_results.items():
        base = row_result["pva_only"]
        for name in blend_strengths:
            b = row_result[f"blend_{name}"]
            print(f"  {win_label:18s} {name}: d_final={b['final_value']-base['final_value']:+12,.0f}  "
                  f"d_sharpe={b['sharpe_ratio']-base['sharpe_ratio']:+.4f}  d_mdd={( b['max_drawdown']-base['max_drawdown'])*100:+.2f}pp")

    import json
    out_path = PROJECT_ROOT / "results" / "test_downside_proba_pva_blend_20260908.json"
    out_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
