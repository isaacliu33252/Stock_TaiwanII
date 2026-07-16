#!/usr/bin/env python3
"""Improvement sweep for GroupA+ specialist routing.

Tests narrower, more conservative translations of the specialist routes:

- high_vol_confirmed: high-vol route acts only with risk/momentum confirmation.
- semiconductor_no_add_only: TSMC-led narrow breadth blocks 00631L adds only;
  confirmed TSMC weakness halves 00631L.
- crash_partial: crash route keeps 30% of golden1 00631L and moves the rest to 0050.
- online_regret_router: route is selected from rolling risk-sensitive loss history.
- regime_similarity_router: route is selected from time-decayed, state-similar
  historical risk-sensitive loss.

Research-only. No active allocation files are changed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _simulate_costed_curve, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.risk_sensitive_loss import risk_sensitive_loss, underprediction_loss
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_specialist_routing_backtest import (
    DEFAULT_WINDOWS,
    SPECIALIST_CRASH_REGIME,
    SPECIALIST_HIGH_REGIME,
    SPECIALIST_SEMI_REGIME,
    _garman_klass_variance,
    _load_ohlc,
    _metric_delta,
    _parse_windows,
    _resolve,
    _resolve_end_date,
    _risk_forecast_candidates,
    _route_counts,
    _routing_risk_diagnostics,
    _scale_00631l,
    _semiconductor_health_frame,
    build_specialist_route_frame,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame
from backtest_group_a_plus_defensive_basket import _load_total_return_prices


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_specialist_routing_improvement_sweep_latest.json"
SPECIALIST_CRASH_PARTIAL_REGIME = "specialist_crash_partial_00631l_to_0050"
SPECIALIST_HIGH_SOFT_REGIME = "specialist_high_soft_00631l_75_to_0050"
SPECIALIST_SEMI_SOFT_REGIME = "specialist_semi_soft_00631l_75_to_0050"
SPECIALIST_CRASH_SOFT_REGIME = "specialist_crash_soft_00631l_50_to_0050"
SPECIALIST_HIGH_SCALE_85_REGIME = "specialist_high_scale_00631l_85_to_0050"
SPECIALIST_HIGH_SCALE_75_REGIME = "specialist_high_scale_00631l_75_to_0050"
SPECIALIST_HIGH_SCALE_65_REGIME = "specialist_high_scale_00631l_65_to_0050"
SPECIALIST_SEMI_SCALE_90_REGIME = "specialist_semi_scale_00631l_90_to_0050"
SPECIALIST_SEMI_SCALE_80_REGIME = "specialist_semi_scale_00631l_80_to_0050"
SPECIALIST_SEMI_SCALE_70_REGIME = "specialist_semi_scale_00631l_70_to_0050"
SPECIALIST_CRASH_SCALE_75_REGIME = "specialist_crash_scale_00631l_75_to_0050"
SPECIALIST_CRASH_SCALE_50_REGIME = "specialist_crash_scale_00631l_50_to_0050"
SPECIALIST_CRASH_SCALE_25_REGIME = "specialist_crash_scale_00631l_25_to_0050"
SIMILARITY_GRID = (
    {"name": "regime_similarity_h21_bw1_mw2", "time_halflife": 21.0, "similarity_bandwidth": 1.0, "min_effective_weight": 2.0},
    {"name": "regime_similarity_h21_bw2_mw2", "time_halflife": 21.0, "similarity_bandwidth": 2.0, "min_effective_weight": 2.0},
    {"name": "regime_similarity_h63_bw1_mw2", "time_halflife": 63.0, "similarity_bandwidth": 1.0, "min_effective_weight": 2.0},
    {"name": "regime_similarity_h63_bw2_mw2", "time_halflife": 63.0, "similarity_bandwidth": 2.0, "min_effective_weight": 2.0},
    {"name": "regime_similarity_h126_bw2_mw2", "time_halflife": 126.0, "similarity_bandwidth": 2.0, "min_effective_weight": 2.0},
    {"name": "regime_similarity_h63_bw3_mw5", "time_halflife": 63.0, "similarity_bandwidth": 3.0, "min_effective_weight": 5.0},
)
ONLINE_GUARD_GRID = (
    {"name": "online_regret_guard_m05_c2", "min_relative_improvement": 0.05, "confirm_days": 2},
    {"name": "online_regret_guard_m05_c3", "min_relative_improvement": 0.05, "confirm_days": 3},
    {"name": "online_regret_guard_m10_c2", "min_relative_improvement": 0.10, "confirm_days": 2},
    {"name": "online_regret_guard_m10_c3", "min_relative_improvement": 0.10, "confirm_days": 3},
)
COST_AWARE_GRID = (
    {"name": "online_regret_cost_p02_soft", "switch_penalty_rate": 0.02},
    {"name": "online_regret_cost_p05_soft", "switch_penalty_rate": 0.05},
    {"name": "online_regret_cost_p10_soft", "switch_penalty_rate": 0.10},
)
SOFT_EXPOSURE_GRID = (
    {"name": "online_regret_soft_h85_s75_c60", "high": 0.85, "semi": 0.75, "crash": 0.60},
    {"name": "online_regret_soft_h95_s90_c80", "high": 0.95, "semi": 0.90, "crash": 0.80},
    {"name": "online_regret_soft_h95_s85_c80", "high": 0.95, "semi": 0.85, "crash": 0.80},
    {"name": "online_regret_soft_h95_s80_c70", "high": 0.95, "semi": 0.80, "crash": 0.70},
    {"name": "online_regret_soft_h100_s80_c70", "high": 1.00, "semi": 0.80, "crash": 0.70},
    {"name": "online_regret_soft_h100_s100_c100", "high": 1.00, "semi": 1.00, "crash": 1.00},
    {"name": "online_regret_soft_h100_s100_c95", "high": 1.00, "semi": 1.00, "crash": 0.95},
    {"name": "online_regret_soft_h100_s100_c90", "high": 1.00, "semi": 1.00, "crash": 0.90},
    {"name": "online_regret_soft_h100_s100_c70", "high": 1.00, "semi": 1.00, "crash": 0.70},
    {"name": "online_regret_soft_h100_s100_c80", "high": 1.00, "semi": 1.00, "crash": 0.80},
    {"name": "online_regret_soft_h100_s100_c60", "high": 1.00, "semi": 1.00, "crash": 0.60},
    {"name": "online_regret_soft_h90_s80_c70", "high": 0.90, "semi": 0.80, "crash": 0.70},
    {"name": "online_regret_soft_h90_s75_c70", "high": 0.90, "semi": 0.75, "crash": 0.70},
    {"name": "online_regret_soft_h90_s75_c60", "high": 0.90, "semi": 0.75, "crash": 0.60},
    {"name": "online_regret_soft_h85_s80_c70", "high": 0.85, "semi": 0.80, "crash": 0.70},
    {"name": "online_regret_soft_h85_s80_c60", "high": 0.85, "semi": 0.80, "crash": 0.60},
    {"name": "online_regret_soft_h85_s75_c70", "high": 0.85, "semi": 0.75, "crash": 0.70},
    {"name": "online_regret_soft_h80_s75_c50", "high": 0.80, "semi": 0.75, "crash": 0.50},
    {"name": "online_regret_soft_h80_s70_c50", "high": 0.80, "semi": 0.70, "crash": 0.50},
    {"name": "online_regret_soft_h75_s70_c40", "high": 0.75, "semi": 0.70, "crash": 0.40},
)


def _current_weights(value: float, price_row: pd.Series, shares: dict[str, float], cash: float) -> dict[str, float]:
    if value <= 0.0:
        return {ticker: 0.0 for ticker in TICKERS} | {"cash": 1.0}
    weights = {
        ticker: float(shares.get(ticker, 0.0) or 0.0) * float(price_row[ticker]) / value
        for ticker in TICKERS
    }
    weights["cash"] = float(cash) / value
    return _normalize(weights)


def _cap_00631l_add(target: dict[str, float], current: dict[str, float]) -> tuple[dict[str, float], bool, float]:
    target_w = _normalize(dict(target))
    current_631l = float(current.get("00631L.TW", 0.0) or 0.0)
    target_631l = float(target_w.get("00631L.TW", 0.0) or 0.0)
    excess_add = max(target_631l - current_631l, 0.0)
    if excess_add <= 1e-12:
        return target_w, False, 0.0
    target_w["00631L.TW"] = current_631l
    target_w["0050.TW"] = float(target_w.get("0050.TW", 0.0) or 0.0) + excess_add
    return _normalize(target_w), True, float(excess_add)


def _simulate_semiconductor_no_add(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    route_frame: pd.DataFrame,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    no_add_days = 0
    capped_weight_sum = 0.0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        base_regime = str(execution_regime.loc[dt])
        tsmc_state = str(route_frame.loc[dt, "tsmc_state"]) if dt in route_frame.index else "None"
        next_regime = SPECIALIST_SEMI_REGIME if base_regime == "golden1" and tsmc_state == "tsmc_weak_confirmed" else base_regime
        no_add = base_regime == "golden1" and tsmc_state == "tsmc_led_narrow"
        if next_regime != current_regime:
            current_w = _current_weights(gross_value, price_row, shares, cash)
            weights = _normalize(weights_by_regime[next_regime])
            if no_add:
                weights, capped, capped_weight = _cap_00631l_add(weights, current_w)
                if capped:
                    no_add_days += 1
                    capped_weight_sum += capped_weight
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_regime = next_regime
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "no_add_days": int(no_add_days),
        "capped_00631l_weight_sum": round(float(capped_weight_sum), 6),
        "policy": "tsmc_led_narrow_no_add_tsmc_weak_half",
    }


def _high_vol_confirmed_regime(execution_regime: pd.Series, route_frame: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
    out = execution_regime.copy()
    total_risk = pd.to_numeric(frame.get("total_risk_score"), errors="coerce").reindex(out.index).fillna(0)
    momentum = pd.to_numeric(frame.get("exit_momentum"), errors="coerce").reindex(out.index).fillna(0.0)
    confirmed = (
        (out.astype(str) == "golden1")
        & (route_frame["route"].reindex(out.index) == "high_volatility")
        & (total_risk >= 6)
        & (momentum < 0.0)
    )
    out.loc[confirmed] = SPECIALIST_HIGH_REGIME
    return out


def _crash_partial_regime(execution_regime: pd.Series, route_frame: pd.DataFrame) -> pd.Series:
    out = execution_regime.copy()
    mask = (out.astype(str) == "golden1") & (route_frame["route"].reindex(out.index) == "crash_deleverage")
    out.loc[mask] = SPECIALIST_CRASH_PARTIAL_REGIME
    return out


def _online_regret_route_frame(
    route_frame: pd.DataFrame,
    *,
    db_path: Path,
    start: str,
    end: str,
    lookback: int = 252,
    min_periods: int = 60,
) -> pd.DataFrame:
    try:
        ohlc = _load_ohlc(db_path, "0050.TW", start, end)
    except Exception:
        ohlc = pd.DataFrame()
    if ohlc.empty:
        out = route_frame.copy()
        out["route"] = "neutral"
        out["online_regret_router"] = True
        return out
    realized = _garman_klass_variance(ohlc)
    target_next = realized.shift(-1).reindex(route_frame.index)
    forecasts = _risk_forecast_candidates(realized).reindex(route_frame.index)
    losses = pd.DataFrame(index=route_frame.index)
    for route in forecasts.columns:
        losses[route] = risk_sensitive_loss(target_next, forecasts[route])
    rolling = losses.rolling(lookback, min_periods=min_periods).mean().shift(1)
    selected = pd.Series(index=route_frame.index, dtype=object)
    valid = rolling.notna().any(axis=1)
    selected.loc[valid] = rolling.loc[valid].idxmin(axis=1)
    selected = selected.fillna(route_frame["route"])
    out = route_frame.copy()
    out["route"] = selected.astype(str)
    out["online_regret_router"] = True
    return out


def _online_regret_cost_aware_route_frame(
    route_frame: pd.DataFrame,
    *,
    db_path: Path,
    start: str,
    end: str,
    lookback: int = 252,
    min_periods: int = 60,
    switch_penalty_rate: float = 0.05,
) -> pd.DataFrame:
    try:
        ohlc = _load_ohlc(db_path, "0050.TW", start, end)
    except Exception:
        ohlc = pd.DataFrame()
    out = route_frame.copy()
    out["online_regret_cost_aware_router"] = True
    out["online_regret_switch_penalty_rate"] = float(switch_penalty_rate)
    if ohlc.empty:
        out["route"] = "neutral"
        return out

    realized = _garman_klass_variance(ohlc)
    target_next = realized.shift(-1).reindex(route_frame.index)
    forecasts = _risk_forecast_candidates(realized).reindex(route_frame.index)
    losses = pd.DataFrame(index=route_frame.index)
    for route in forecasts.columns:
        losses[route] = risk_sensitive_loss(target_next, forecasts[route])
    rolling = losses.rolling(lookback, min_periods=min_periods).mean().shift(1)
    base_route = route_frame["route"].astype(str).reindex(route_frame.index)
    penalty_base = rolling.median(axis=1).abs().fillna(0.0) * float(switch_penalty_rate)
    adjusted = rolling.copy()
    for route in adjusted.columns:
        adjusted[route] = adjusted[route] + penalty_base.where(base_route != route, 0.0)
    selected = pd.Series(index=route_frame.index, dtype=object)
    valid = adjusted.notna().any(axis=1)
    selected.loc[valid] = adjusted.loc[valid].idxmin(axis=1)
    selected = selected.fillna(base_route)
    out["route"] = selected.astype(str)
    return out


def _online_regret_guard_route_frame(
    route_frame: pd.DataFrame,
    *,
    db_path: Path,
    start: str,
    end: str,
    lookback: int = 252,
    min_periods: int = 60,
    min_relative_improvement: float = 0.05,
    confirm_days: int = 2,
) -> pd.DataFrame:
    try:
        ohlc = _load_ohlc(db_path, "0050.TW", start, end)
    except Exception:
        ohlc = pd.DataFrame()
    out = route_frame.copy()
    out["online_regret_guard_router"] = True
    out["online_regret_guard_min_relative_improvement"] = float(min_relative_improvement)
    out["online_regret_guard_confirm_days"] = int(confirm_days)
    if ohlc.empty:
        out["route"] = "neutral"
        return out

    realized = _garman_klass_variance(ohlc)
    target_next = realized.shift(-1).reindex(route_frame.index)
    forecasts = _risk_forecast_candidates(realized).reindex(route_frame.index)
    losses = pd.DataFrame(index=route_frame.index)
    for route in forecasts.columns:
        losses[route] = risk_sensitive_loss(target_next, forecasts[route])
    rolling = losses.rolling(lookback, min_periods=min_periods).mean().shift(1)
    best_route = pd.Series(index=route_frame.index, dtype=object)
    valid = rolling.notna().any(axis=1)
    best_route.loc[valid] = rolling.loc[valid].idxmin(axis=1)

    base_route = route_frame["route"].astype(str).reindex(route_frame.index)
    best_score = pd.Series(index=route_frame.index, dtype=float)
    base_score = pd.Series(index=route_frame.index, dtype=float)
    for dt in route_frame.index:
        candidate = best_route.loc[dt]
        if pd.notna(candidate) and str(candidate) in rolling.columns:
            best_score.loc[dt] = rolling.loc[dt, str(candidate)]
        original = base_route.loc[dt]
        if pd.notna(original) and str(original) in rolling.columns:
            base_score.loc[dt] = rolling.loc[dt, str(original)]

    relative_improvement = (base_score - best_score) / base_score.abs().clip(lower=1e-12)
    eligible = (
        best_route.notna()
        & (best_route.astype(str) != base_route)
        & (relative_improvement >= float(min_relative_improvement))
    )
    if int(confirm_days) > 1:
        confirmed = eligible.copy()
        for offset in range(1, int(confirm_days)):
            confirmed &= eligible.shift(offset).fillna(False) & (best_route == best_route.shift(offset))
        eligible = confirmed

    selected = base_route.copy()
    selected.loc[eligible] = best_route.loc[eligible].astype(str)
    out["route"] = selected.astype(str)
    out["online_regret_guard_relative_improvement"] = relative_improvement
    return out


def _state_feature_frame(route_frame: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    features = pd.DataFrame(index=route_frame.index)
    for col in ("ma_gap", "drawdown", "exit_momentum", "total_risk_score", "tail_risk_score"):
        if col in frame:
            features[col] = pd.to_numeric(frame[col], errors="coerce").reindex(route_frame.index)
        else:
            features[col] = 0.0
    features["route_high_vol"] = (route_frame["route"] == "high_volatility").astype(float)
    features["route_semiconductor"] = (route_frame["route"] == "semiconductor_risk").astype(float)
    features["route_crash"] = (route_frame["route"] == "crash_deleverage").astype(float)
    return features.ffill().fillna(0.0)


def _weighted_route_scores(
    losses: pd.DataFrame,
    features: pd.DataFrame,
    dt: pd.Timestamp,
    *,
    lookback: int,
    time_halflife: float,
    similarity_bandwidth: float,
    min_effective_weight: float,
) -> pd.Series | None:
    if dt not in losses.index:
        return None
    pos = losses.index.get_loc(dt)
    if not isinstance(pos, int) or pos <= 0:
        return None
    hist_idx = losses.index[max(0, pos - int(lookback)):pos]
    if len(hist_idx) < 20:
        return None
    hist_losses = losses.loc[hist_idx]
    valid_rows = hist_losses.notna().any(axis=1)
    hist_idx = hist_idx[valid_rows.to_numpy()]
    if len(hist_idx) < 20:
        return None
    hist_losses = losses.loc[hist_idx]
    hist_features = features.loc[hist_idx]
    current = features.loc[dt]
    scale = hist_features.std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    dist2 = (((hist_features - current) / scale) ** 2).sum(axis=1)
    age = pd.Series(range(len(hist_idx), 0, -1), index=hist_idx, dtype=float)
    time_weight = 0.5 ** (age / float(time_halflife))
    sim_weight = (-dist2 / (2.0 * float(similarity_bandwidth) ** 2)).map(math.exp)
    weights = (time_weight * sim_weight).reindex(hist_idx).fillna(0.0)
    if float(weights.sum()) < float(min_effective_weight):
        return None
    scores: dict[str, float] = {}
    for route in hist_losses.columns:
        clean = pd.to_numeric(hist_losses[route], errors="coerce")
        mask = clean.notna() & (weights > 0)
        if not mask.any():
            continue
        denom = float(weights[mask].sum())
        if denom > 0.0:
            scores[route] = float((clean[mask] * weights[mask]).sum() / denom)
    return pd.Series(scores, dtype=float) if scores else None


def _regime_similarity_route_frame(
    route_frame: pd.DataFrame,
    frame: pd.DataFrame,
    *,
    db_path: Path,
    start: str,
    end: str,
    lookback: int = 252,
    time_halflife: float = 63.0,
    similarity_bandwidth: float = 2.0,
    min_effective_weight: float = 5.0,
) -> pd.DataFrame:
    try:
        ohlc = _load_ohlc(db_path, "0050.TW", start, end)
    except Exception:
        ohlc = pd.DataFrame()
    out = route_frame.copy()
    out["regime_similarity_router"] = True
    if ohlc.empty:
        out["route"] = "neutral"
        return out
    realized = _garman_klass_variance(ohlc)
    target_next = realized.shift(-1).reindex(route_frame.index)
    forecasts = _risk_forecast_candidates(realized).reindex(route_frame.index)
    losses = pd.DataFrame(index=route_frame.index)
    for route in forecasts.columns:
        losses[route] = risk_sensitive_loss(target_next, forecasts[route])
    features = _state_feature_frame(route_frame, frame)
    selected = pd.Series(index=route_frame.index, dtype=object)
    for dt in route_frame.index:
        scores = _weighted_route_scores(
            losses,
            features,
            pd.Timestamp(dt),
            lookback=lookback,
            time_halflife=time_halflife,
            similarity_bandwidth=similarity_bandwidth,
            min_effective_weight=min_effective_weight,
        )
        selected.loc[dt] = scores.idxmin() if scores is not None and not scores.empty else route_frame.loc[dt, "route"]
    out["route"] = selected.astype(str)
    return out


def _combined_improved_regime(execution_regime: pd.Series, route_frame: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
    out = _high_vol_confirmed_regime(execution_regime, route_frame, frame)
    crash = _crash_partial_regime(execution_regime, route_frame)
    out.loc[crash == SPECIALIST_CRASH_PARTIAL_REGIME] = SPECIALIST_CRASH_PARTIAL_REGIME
    weak = (
        (execution_regime.astype(str) == "golden1")
        & (route_frame["route"].reindex(execution_regime.index) == "semiconductor_risk")
        & (route_frame["tsmc_state"].reindex(execution_regime.index) == "tsmc_weak_confirmed")
    )
    out.loc[weak] = SPECIALIST_SEMI_REGIME
    return out


def _combined_soft_regime(execution_regime: pd.Series, route_frame: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
    out = execution_regime.copy()
    total_risk = pd.to_numeric(frame.get("total_risk_score"), errors="coerce").reindex(out.index).fillna(0)
    momentum = pd.to_numeric(frame.get("exit_momentum"), errors="coerce").reindex(out.index).fillna(0.0)
    route = route_frame["route"].reindex(out.index)
    golden = out.astype(str) == "golden1"
    high = golden & (route == "high_volatility") & (total_risk >= 6) & (momentum < 0.0)
    semi = golden & (route == "semiconductor_risk") & (route_frame["tsmc_state"].reindex(out.index) == "tsmc_weak_confirmed")
    crash = golden & (route == "crash_deleverage")
    out.loc[high] = SPECIALIST_HIGH_SOFT_REGIME
    out.loc[semi] = SPECIALIST_SEMI_SOFT_REGIME
    out.loc[crash] = SPECIALIST_CRASH_SOFT_REGIME
    return out


def _combined_scaled_regime(execution_regime: pd.Series, route_frame: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
    out = execution_regime.copy()
    total_risk = pd.to_numeric(frame.get("total_risk_score"), errors="coerce").reindex(out.index).fillna(0)
    tail_risk = pd.to_numeric(frame.get("tail_risk_score"), errors="coerce").reindex(out.index).fillna(0)
    momentum = pd.to_numeric(frame.get("exit_momentum"), errors="coerce").reindex(out.index).fillna(0.0)
    route = route_frame["route"].reindex(out.index)
    tsmc_state = route_frame["tsmc_state"].reindex(out.index).astype(str)
    golden = out.astype(str) == "golden1"

    high = golden & (route == "high_volatility") & (total_risk >= 6) & (momentum < 0.0)
    out.loc[high] = SPECIALIST_HIGH_SCALE_85_REGIME
    out.loc[high & ((total_risk >= 7) | (tail_risk >= 2))] = SPECIALIST_HIGH_SCALE_75_REGIME
    out.loc[high & ((total_risk >= 8) | (tail_risk >= 3))] = SPECIALIST_HIGH_SCALE_65_REGIME

    semi = golden & (route == "semiconductor_risk") & (tsmc_state == "tsmc_weak_confirmed")
    out.loc[semi] = SPECIALIST_SEMI_SCALE_90_REGIME
    out.loc[semi & ((total_risk >= 6) | (tail_risk >= 2))] = SPECIALIST_SEMI_SCALE_80_REGIME
    out.loc[semi & ((total_risk >= 8) | (tail_risk >= 3))] = SPECIALIST_SEMI_SCALE_70_REGIME

    crash = golden & (route == "crash_deleverage")
    out.loc[crash] = SPECIALIST_CRASH_SCALE_75_REGIME
    out.loc[crash & ((total_risk >= 6) | (tail_risk >= 2))] = SPECIALIST_CRASH_SCALE_50_REGIME
    out.loc[crash & ((total_risk >= 8) | (tail_risk >= 3))] = SPECIALIST_CRASH_SCALE_25_REGIME
    return out


def _combined_param_soft_regime(
    execution_regime: pd.Series,
    route_frame: pd.DataFrame,
    frame: pd.DataFrame,
    *,
    suffix: str,
    high_exposure: float,
    semi_exposure: float,
    crash_exposure: float,
) -> pd.Series:
    out = execution_regime.copy()
    total_risk = pd.to_numeric(frame.get("total_risk_score"), errors="coerce").reindex(out.index).fillna(0)
    momentum = pd.to_numeric(frame.get("exit_momentum"), errors="coerce").reindex(out.index).fillna(0.0)
    route = route_frame["route"].reindex(out.index)
    tsmc_state = route_frame["tsmc_state"].reindex(out.index).astype(str)
    golden = out.astype(str) == "golden1"
    if float(high_exposure) < 0.999999:
        high = golden & (route == "high_volatility") & (total_risk >= 6) & (momentum < 0.0)
        out.loc[high] = f"specialist_high_{suffix}"
    if float(semi_exposure) < 0.999999:
        semi = golden & (route == "semiconductor_risk") & (tsmc_state == "tsmc_weak_confirmed")
        out.loc[semi] = f"specialist_semi_{suffix}"
    if float(crash_exposure) < 0.999999:
        crash = golden & (route == "crash_deleverage")
        out.loc[crash] = f"specialist_crash_{suffix}"
    return out


def _simulate_variant(
    *,
    variant: str,
    total_return_prices: pd.DataFrame,
    execution_regime: pd.Series,
    route_frame: pd.DataFrame,
    frame: pd.DataFrame,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any], pd.Series]:
    if variant == "high_vol_confirmed":
        regimes = _high_vol_confirmed_regime(execution_regime, route_frame, frame)
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif variant == "semiconductor_no_add_only":
        regimes = execution_regime.copy()
        curve, sim = _simulate_semiconductor_no_add(total_return_prices, regimes, route_frame, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif variant == "crash_partial":
        regimes = _crash_partial_regime(execution_regime, route_frame)
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif variant.startswith("online_regret_soft_h"):
        config = next((item for item in SOFT_EXPOSURE_GRID if item["name"] == variant), None)
        if config is None:
            raise ValueError(f"missing soft exposure config: {variant}")
        regimes = _combined_param_soft_regime(
            execution_regime,
            route_frame,
            frame,
            suffix=variant.removeprefix("online_regret_"),
            high_exposure=float(config["high"]),
            semi_exposure=float(config["semi"]),
            crash_exposure=float(config["crash"]),
        )
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif (
        variant in {"online_regret_soft", "online_regret_guard_m05_c2_soft"}
        or variant.startswith("online_regret_cost_")
    ):
        regimes = _combined_soft_regime(execution_regime, route_frame, frame)
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif variant == "online_regret_scaled":
        regimes = _combined_scaled_regime(execution_regime, route_frame, frame)
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif (
        variant in {"online_regret_router", "regime_similarity_router"}
        or variant.startswith("regime_similarity_h")
        or variant.startswith("online_regret_guard_")
    ):
        regimes = _combined_improved_regime(execution_regime, route_frame, frame)
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    elif variant == "combined_improved":
        regimes = _combined_improved_regime(execution_regime, route_frame, frame)
        curve, sim = _simulate_costed_curve(total_return_prices, regimes, weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax)
    else:
        raise ValueError(f"unknown variant: {variant}")
    return curve, sim, regimes


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    initial_value: float,
    ncf_panel_631l: str | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=ncf_panel_631l,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end)
    chip_features = _load_chip_features(db_path, prices.index, start, end)
    gate_frame = _build_volatility_gate_frame(prices, chip_features).reindex(frame.index)
    semiconductor_frame = _semiconductor_health_frame(prices, db_path).reindex(frame.index)
    base_route_frame = build_specialist_route_frame(frame, gate_frame, semiconductor_frame)
    online_route_frame = _online_regret_route_frame(base_route_frame, db_path=db_path, start=start, end=end)
    cost_aware_frames = {
        str(config["name"]): _online_regret_cost_aware_route_frame(
            base_route_frame,
            db_path=db_path,
            start=start,
            end=end,
            switch_penalty_rate=float(config["switch_penalty_rate"]),
        )
        for config in COST_AWARE_GRID
    }
    online_guard_frames = {
        str(config["name"]): _online_regret_guard_route_frame(
            base_route_frame,
            db_path=db_path,
            start=start,
            end=end,
            min_relative_improvement=float(config["min_relative_improvement"]),
            confirm_days=int(config["confirm_days"]),
        )
        for config in ONLINE_GUARD_GRID
    }
    similarity_route_frame = _regime_similarity_route_frame(
        base_route_frame,
        frame,
        db_path=db_path,
        start=start,
        end=end,
    )
    similarity_grid_frames = {
        str(config["name"]): _regime_similarity_route_frame(
            base_route_frame,
            frame,
            db_path=db_path,
            start=start,
            end=end,
            time_halflife=float(config["time_halflife"]),
            similarity_bandwidth=float(config["similarity_bandwidth"]),
            min_effective_weight=float(config["min_effective_weight"]),
        )
        for config in SIMILARITY_GRID
    }
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, prices.index)

    execution_regime = frame["execution_regime"].astype(str)
    a2118_report_metrics = dict(report["metrics"])
    a2118_report_execution = dict(report["execution"])
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])
    weights_by_regime[SPECIALIST_HIGH_REGIME] = _scale_00631l(golden_weights, 0.50, destination="0050.TW")
    weights_by_regime[SPECIALIST_SEMI_REGIME] = _scale_00631l(golden_weights, 0.50, destination="0050.TW")
    weights_by_regime[SPECIALIST_CRASH_REGIME] = _scale_00631l(golden_weights, 0.0, destination="cash")
    weights_by_regime[SPECIALIST_CRASH_PARTIAL_REGIME] = _scale_00631l(golden_weights, 0.30, destination="0050.TW")
    weights_by_regime[SPECIALIST_HIGH_SOFT_REGIME] = _scale_00631l(golden_weights, 0.75, destination="0050.TW")
    weights_by_regime[SPECIALIST_SEMI_SOFT_REGIME] = _scale_00631l(golden_weights, 0.75, destination="0050.TW")
    weights_by_regime[SPECIALIST_CRASH_SOFT_REGIME] = _scale_00631l(golden_weights, 0.50, destination="0050.TW")
    weights_by_regime[SPECIALIST_HIGH_SCALE_85_REGIME] = _scale_00631l(golden_weights, 0.85, destination="0050.TW")
    weights_by_regime[SPECIALIST_HIGH_SCALE_75_REGIME] = _scale_00631l(golden_weights, 0.75, destination="0050.TW")
    weights_by_regime[SPECIALIST_HIGH_SCALE_65_REGIME] = _scale_00631l(golden_weights, 0.65, destination="0050.TW")
    weights_by_regime[SPECIALIST_SEMI_SCALE_90_REGIME] = _scale_00631l(golden_weights, 0.90, destination="0050.TW")
    weights_by_regime[SPECIALIST_SEMI_SCALE_80_REGIME] = _scale_00631l(golden_weights, 0.80, destination="0050.TW")
    weights_by_regime[SPECIALIST_SEMI_SCALE_70_REGIME] = _scale_00631l(golden_weights, 0.70, destination="0050.TW")
    weights_by_regime[SPECIALIST_CRASH_SCALE_75_REGIME] = _scale_00631l(golden_weights, 0.75, destination="0050.TW")
    weights_by_regime[SPECIALIST_CRASH_SCALE_50_REGIME] = _scale_00631l(golden_weights, 0.50, destination="0050.TW")
    weights_by_regime[SPECIALIST_CRASH_SCALE_25_REGIME] = _scale_00631l(golden_weights, 0.25, destination="0050.TW")
    for config in SOFT_EXPOSURE_GRID:
        suffix = str(config["name"]).removeprefix("online_regret_")
        weights_by_regime[f"specialist_high_{suffix}"] = _scale_00631l(
            golden_weights,
            float(config["high"]),
            destination="0050.TW",
        )
        weights_by_regime[f"specialist_semi_{suffix}"] = _scale_00631l(
            golden_weights,
            float(config["semi"]),
            destination="0050.TW",
        )
        weights_by_regime[f"specialist_crash_{suffix}"] = _scale_00631l(
            golden_weights,
            float(config["crash"]),
            destination="0050.TW",
        )

    baseline_curve, baseline_execution = _simulate_costed_curve(
        total_return_prices,
        execution_regime,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)

    variants: dict[str, Any] = {
        "baseline_a2118": {
            "metrics": baseline_metrics,
            "execution": baseline_execution,
            "delta_vs_baseline": {},
            "changed_days": 0,
            "same_simulator_baseline": True,
            "a2118_report_metrics_reference": a2118_report_metrics,
            "a2118_report_execution_reference": a2118_report_execution,
        }
    }
    sweep_variants = [
        "high_vol_confirmed",
        "semiconductor_no_add_only",
        "crash_partial",
        "online_regret_router",
        "online_regret_soft",
        *(str(config["name"]) for config in SOFT_EXPOSURE_GRID),
        "online_regret_scaled",
        *cost_aware_frames.keys(),
        *online_guard_frames.keys(),
        "online_regret_guard_m05_c2_soft",
        "regime_similarity_router",
        *similarity_grid_frames.keys(),
        "combined_improved",
    ]
    for variant in sweep_variants:
        if variant == "online_regret_router":
            route_frame = online_route_frame
        elif variant in {"online_regret_soft", "online_regret_scaled"} or variant.startswith("online_regret_soft_h"):
            route_frame = online_route_frame
        elif variant in cost_aware_frames:
            route_frame = cost_aware_frames[variant]
        elif variant == "online_regret_guard_m05_c2_soft":
            route_frame = online_guard_frames["online_regret_guard_m05_c2"]
        elif variant in online_guard_frames:
            route_frame = online_guard_frames[variant]
        elif variant == "regime_similarity_router":
            route_frame = similarity_route_frame
        elif variant in similarity_grid_frames:
            route_frame = similarity_grid_frames[variant]
        else:
            route_frame = base_route_frame
        curve, sim, regimes = _simulate_variant(
            variant=variant,
            total_return_prices=total_return_prices,
            execution_regime=execution_regime,
            route_frame=route_frame,
            frame=frame,
            weights_by_regime=weights_by_regime,
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
        metrics = _metrics(curve, initial_value)
        variants[variant] = {
            "metrics": metrics,
            "execution": sim,
            "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
            "changed_days": int((regimes != execution_regime).sum()),
            "extra_rebalances": int(sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
            "extra_turnover_value": float(sim["turnover_value"] - baseline_execution.get("turnover_value", 0.0)),
        }

    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "route_counts": _route_counts(base_route_frame, execution_regime),
        "online_route_counts": _route_counts(online_route_frame, execution_regime),
        "cost_aware_route_counts": {
            name: _route_counts(route_frame, execution_regime)
            for name, route_frame in cost_aware_frames.items()
        },
        "online_guard_route_counts": {
            name: _route_counts(route_frame, execution_regime)
            for name, route_frame in online_guard_frames.items()
        },
        "similarity_route_counts": _route_counts(similarity_route_frame, execution_regime),
        "similarity_grid_route_counts": {
            name: _route_counts(route_frame, execution_regime)
            for name, route_frame in similarity_grid_frames.items()
        },
        "base_routing_risk_diagnostics": _routing_risk_diagnostics(base_route_frame, db_path=db_path, start=start, end=end),
        "online_routing_risk_diagnostics": _routing_risk_diagnostics(online_route_frame, db_path=db_path, start=start, end=end),
        "cost_aware_routing_risk_diagnostics": {
            name: _routing_risk_diagnostics(route_frame, db_path=db_path, start=start, end=end)
            for name, route_frame in cost_aware_frames.items()
        },
        "online_guard_routing_risk_diagnostics": {
            name: _routing_risk_diagnostics(route_frame, db_path=db_path, start=start, end=end)
            for name, route_frame in online_guard_frames.items()
        },
        "similarity_routing_risk_diagnostics": _routing_risk_diagnostics(similarity_route_frame, db_path=db_path, start=start, end=end),
        "similarity_grid_routing_risk_diagnostics": {
            name: _routing_risk_diagnostics(route_frame, db_path=db_path, start=start, end=end)
            for name, route_frame in similarity_grid_frames.items()
        },
        "variants": variants,
        "a2118_report_metrics_reference": a2118_report_metrics,
        "a2118_report_execution_reference": a2118_report_execution,
        "dividend_coverage": dividend_coverage,
    }


def build_promotion_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "empty", "eligible_variants": [], "variants": {}}
    frame = pd.DataFrame(rows)
    if frame.empty or "variant" not in frame:
        return {"status": "empty", "eligible_variants": [], "variants": {}}

    windows = sorted(str(item) for item in frame["window"].dropna().unique())
    required_windows = max(min(len(windows), 3), 1)
    out: dict[str, Any] = {}
    for variant, group in frame.groupby("variant"):
        variant = str(variant)
        if variant == "baseline_a2118":
            continue
        final_ok = pd.to_numeric(group.get("delta_final_value"), errors="coerce").fillna(0.0) >= -1e-9
        sharpe_ok = pd.to_numeric(group.get("delta_sharpe_ratio"), errors="coerce").fillna(0.0) >= -1e-9
        mdd_delta = pd.to_numeric(group.get("delta_max_drawdown"), errors="coerce").fillna(0.0)
        mdd_ok = mdd_delta >= -0.005
        changed_ok = pd.to_numeric(group.get("changed_days"), errors="coerce").fillna(0) <= 60
        no_op_sane = True
        if variant.endswith("_c100"):
            no_op_sane = bool(
                (pd.to_numeric(group.get("delta_final_value"), errors="coerce").fillna(0.0).abs() <= 1e-6).all()
                and (pd.to_numeric(group.get("changed_days"), errors="coerce").fillna(0).astype(int) == 0).all()
            )
        is_no_op_control = variant.endswith("_c100")
        eligible = bool(
            not is_no_op_control
            and
            int(final_ok.sum()) >= required_windows
            and int(sharpe_ok.sum()) >= required_windows
            and bool(mdd_ok.all())
            and bool(changed_ok.all())
            and no_op_sane
        )
        out[variant] = {
            "eligible": eligible,
            "no_op_control": is_no_op_control,
            "windows": int(len(group)),
            "final_value_noninferior_windows": int(final_ok.sum()),
            "sharpe_noninferior_windows": int(sharpe_ok.sum()),
            "mdd_gate_pass": bool(mdd_ok.all()),
            "changed_days_gate_pass": bool(changed_ok.all()),
            "no_op_sanity_pass": no_op_sane,
            "max_changed_days": int(pd.to_numeric(group.get("changed_days"), errors="coerce").fillna(0).max()),
            "worst_delta_final_value": float(pd.to_numeric(group.get("delta_final_value"), errors="coerce").fillna(0.0).min()),
            "worst_delta_sharpe_ratio": float(pd.to_numeric(group.get("delta_sharpe_ratio"), errors="coerce").fillna(0.0).min()),
            "worst_delta_max_drawdown": float(mdd_delta.min()),
        }
    eligible_variants = sorted(name for name, payload in out.items() if payload["eligible"])
    return {
        "status": "available",
        "policy": "research_only_fixed_gate_no_auto_promotion",
        "required_windows": required_windows,
        "rules": {
            "final_value": "delta_final_value >= 0 in at least required_windows",
            "sharpe": "delta_sharpe_ratio >= 0 in at least required_windows",
            "max_drawdown": "delta_max_drawdown >= -0.005 in every tested window",
            "changed_days": "changed_days <= 60 in every tested window",
            "no_op_sanity": "variants ending c100 must have zero delta and zero changed_days",
        },
        "eligible_variants": eligible_variants,
        "variants": out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--windows", default=None, help="Comma-separated label:start:end windows.")
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = _resolve(args.db)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    panel = str(_resolve(args.ncf_panel_631l)) if args.ncf_panel_631l else None
    windows = []
    rows: list[dict[str, Any]] = []
    for label, start, end in _parse_windows(args.windows):
        result = evaluate_window(
            label=label,
            start=start,
            end=end,
            db_path=db_path,
            initial_value=args.initial_value,
            ncf_panel_631l=panel,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax,
        )
        windows.append(result)
        for variant, payload in result["variants"].items():
            base_diag = result.get("base_routing_risk_diagnostics") or {}
            online_diag = result.get("online_routing_risk_diagnostics") or {}
            similarity_diag = result.get("similarity_routing_risk_diagnostics") or {}
            if variant in {"online_regret_router", "online_regret_soft", "online_regret_scaled"}:
                variant_diag = online_diag
            elif variant.startswith("online_regret_cost_"):
                variant_diag = (result.get("cost_aware_routing_risk_diagnostics") or {}).get(variant, {})
            elif variant == "online_regret_guard_m05_c2_soft":
                variant_diag = (result.get("online_guard_routing_risk_diagnostics") or {}).get("online_regret_guard_m05_c2", {})
            elif variant.startswith("online_regret_guard_"):
                variant_diag = (result.get("online_guard_routing_risk_diagnostics") or {}).get(variant, {})
            elif variant == "regime_similarity_router":
                variant_diag = similarity_diag
            else:
                variant_diag = (result.get("similarity_grid_routing_risk_diagnostics") or {}).get(variant, {})
            baseline_metrics = result["variants"]["baseline_a2118"]["metrics"]
            final_ratio = (
                float(payload["metrics"]["final_value"]) / float(baseline_metrics["final_value"])
                if float(baseline_metrics["final_value"]) != 0.0
                else None
            )
            delta = payload.get("delta_vs_baseline", {})
            promotion_candidate = bool(
                variant != "baseline_a2118"
                and final_ratio is not None
                and final_ratio >= 0.965
                and float(delta.get("delta_sharpe_ratio", 0.0) or 0.0) >= 0.0
                and float(delta.get("delta_max_drawdown", 0.0) or 0.0) >= -0.01
            )
            rows.append(
                {
                    "window": label,
                    "variant": variant,
                    **payload["metrics"],
                    "final_ratio_vs_baseline": final_ratio,
                    "promotion_candidate_balanced": promotion_candidate,
                    "transaction_cost": payload["execution"].get("transaction_cost"),
                    "turnover_value": payload["execution"].get("turnover_value"),
                    "rebalance_count": payload["execution"].get("rebalance_count"),
                    **payload.get("delta_vs_baseline", {}),
                    "changed_days": payload.get("changed_days", 0),
                    "extra_transaction_cost": payload.get("extra_transaction_cost", 0.0),
                    "extra_turnover_value": payload.get("extra_turnover_value", 0.0),
                    "base_miss_best_rate": base_diag.get("miss_best_rate"),
                    "online_miss_best_rate": online_diag.get("miss_best_rate"),
                    "similarity_miss_best_rate": similarity_diag.get("miss_best_rate"),
                    "variant_miss_best_rate": variant_diag.get("miss_best_rate"),
                    "base_underprediction_positive_rate": base_diag.get("underprediction_positive_rate"),
                    "online_underprediction_positive_rate": online_diag.get("underprediction_positive_rate"),
                    "similarity_underprediction_positive_rate": similarity_diag.get("underprediction_positive_rate"),
                    "variant_underprediction_positive_rate": variant_diag.get("underprediction_positive_rate"),
                    "variant_mean_selected_regret": variant_diag.get("mean_selected_regret"),
                    **result["route_counts"],
                }
            )

    report = {
        "experiment": "group_a_plus_specialist_routing_improvement_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_allocation_change",
        "variants": {
            "high_vol_confirmed": "high-vol route acts only when total_risk_score>=6 and exit_momentum<0",
            "semiconductor_no_add_only": "tsmc_led_narrow blocks adds only; tsmc_weak_confirmed halves 00631L",
            "crash_partial": "crash route keeps 30% of golden1 00631L and moves the rest to 0050",
            "online_regret_router": "rolling risk-sensitive loss selects route; improved mapping then applies",
            "online_regret_soft": "rolling risk-sensitive loss selects route; soft 00631L reductions apply",
            **{
                str(config["name"]): (
                    "rolling risk-sensitive loss selects route; local soft exposure grid "
                    f"(high={config['high']}, semi={config['semi']}, crash={config['crash']})"
                )
                for config in SOFT_EXPOSURE_GRID
            },
            "online_regret_scaled": "rolling risk-sensitive loss selects route; tiered 00631L exposure reductions apply",
            **{
                str(config["name"]): (
                    "cost-aware rolling risk-sensitive loss route selection with soft 00631L reductions "
                    f"(switch_penalty_rate={config['switch_penalty_rate']})"
                )
                for config in COST_AWARE_GRID
            },
            **{
                str(config["name"]): (
                    "guarded rolling risk-sensitive loss route override "
                    f"(min_relative_improvement={config['min_relative_improvement']}, "
                    f"confirm_days={config['confirm_days']})"
                )
                for config in ONLINE_GUARD_GRID
            },
            "online_regret_guard_m05_c2_soft": "guarded online regret route override; soft 00631L reductions apply",
            "regime_similarity_router": "time-decayed, state-similar risk-sensitive loss selects route; improved mapping then applies",
            **{
                str(config["name"]): (
                    "grid route selected by time-decayed, state-similar risk-sensitive loss "
                    f"(halflife={config['time_halflife']}, bandwidth={config['similarity_bandwidth']}, "
                    f"min_effective_weight={config['min_effective_weight']})"
                )
                for config in SIMILARITY_GRID
            },
            "combined_improved": "confirmed high-vol + weak semiconductor half + crash partial",
        },
        "windows": windows,
        "rows": rows,
        "promotion_gate": build_promotion_gate(rows),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for row in rows:
        if row["variant"] == "baseline_a2118":
            continue
        print(
            f"{row['window']} {row['variant']}: "
            f"final={row['final_value']:.0f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, "
            f"d_final={row.get('delta_final_value', 0.0):.0f}, "
            f"d_sharpe={row.get('delta_sharpe_ratio', 0.0):.4f}, "
            f"changed_days={row.get('changed_days', 0)}"
        )


if __name__ == "__main__":
    main()
