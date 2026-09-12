"""Regime-weighted conformal tail-risk shadow diagnostics.

Inspired by arXiv:2602.03903. This module is deliberately review-only: it
calibrates an additive lower-tail safety buffer, but never computes weights or
orders. Promotion would require historical exceedance validation against the
existing Group A+ tail_conformal guard.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_TARGET_TICKER = "00631L.TW"
DEFAULT_HORIZONS = (5, 10)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def weighted_quantile(values: pd.Series, weights: pd.Series, quantile: float) -> float | None:
    """Return the smallest value whose cumulative normalized weight reaches q."""
    if quantile <= 0.0:
        quantile = 0.0
    elif quantile >= 1.0:
        quantile = 1.0
    frame = pd.DataFrame({"value": values, "weight": weights}).dropna()
    frame = frame[frame["weight"] > 0.0].sort_values("value")
    if frame.empty:
        return None
    total = float(frame["weight"].sum())
    if total <= 0.0:
        return None
    cumulative = frame["weight"].cumsum() / total
    idx = cumulative.searchsorted(quantile, side="left")
    idx = min(int(idx), len(frame) - 1)
    return float(frame["value"].iloc[idx])


def effective_sample_size(weights: pd.Series) -> float | None:
    clean = pd.to_numeric(weights, errors="coerce").dropna()
    clean = clean[clean > 0.0]
    if clean.empty:
        return None
    numerator = float(clean.sum() ** 2)
    denominator = float((clean**2).sum())
    if denominator <= 0.0:
        return None
    return numerator / denominator


def _prediction_from_past_labels(labels: pd.Series, horizon: int, window: int, min_periods: int) -> pd.Series:
    return labels.rolling(window=window, min_periods=min_periods).median().shift(horizon)


def _regime_features(close: pd.Series) -> pd.DataFrame:
    ret = close.pct_change(fill_method=None)
    features = pd.DataFrame(index=close.index)
    features["realized_vol_20d"] = ret.rolling(20, min_periods=10).std()
    features["mean_abs_return_20d"] = ret.abs().rolling(20, min_periods=10).mean()
    return features


def _standardize_to_calibration(features: pd.DataFrame, calibration_index: pd.Index, target_dt: pd.Timestamp) -> pd.DataFrame:
    cal = features.reindex(calibration_index).dropna()
    if cal.empty or target_dt not in features.index:
        return pd.DataFrame(index=features.index, columns=features.columns, dtype=float)
    mean = cal.mean()
    std = cal.std(ddof=0).replace(0.0, np.nan)
    return (features - mean) / std


def _time_decay_weights(index: pd.Index, target_dt: pd.Timestamp, half_life: float) -> pd.Series:
    if half_life <= 0:
        raise ValueError("half_life must be positive")
    dates = pd.to_datetime(index)
    target = pd.Timestamp(target_dt)
    age_days = (target - dates).days.astype(float)
    decay = math.log(2.0) / float(half_life)
    return pd.Series(np.exp(-decay * age_days), index=index, dtype=float)


def _regime_kernel_weights(
    standardized_features: pd.DataFrame,
    index: pd.Index,
    target_dt: pd.Timestamp,
    bandwidth: float,
) -> pd.Series:
    if bandwidth <= 0:
        raise ValueError("bandwidth must be positive")
    target = standardized_features.loc[target_dt] if target_dt in standardized_features.index else None
    if target is None or target.isna().any():
        return pd.Series(np.nan, index=index, dtype=float)
    cal_features = standardized_features.reindex(index)
    dist2 = ((cal_features - target) ** 2).sum(axis=1)
    return np.exp(-0.5 * dist2 / (bandwidth**2))


def _calibration_weights(
    *,
    close: pd.Series,
    calibration_index: pd.Index,
    target_dt: pd.Timestamp,
    half_life: float,
    bandwidth: float,
    min_effective_sample_size: int,
    use_regime_kernel: bool,
    features: pd.DataFrame | None = None,
) -> tuple[pd.Series, dict[str, Any]]:
    time_weights = _time_decay_weights(calibration_index, target_dt, half_life)
    if not use_regime_kernel:
        ess_used = effective_sample_size(time_weights)
        normalized = time_weights / time_weights.sum() if time_weights.sum() > 0 else time_weights
        effective_memory_days = float(((pd.Timestamp(target_dt) - pd.to_datetime(normalized.index)).days * normalized).sum())
        return time_weights, {
            "mode": "time_weighted_conformal",
            "fallback_reason": None,
            "effective_sample_size": _finite(ess_used),
            "regime_effective_sample_size": None,
            "effective_memory_days": _finite(effective_memory_days),
            "half_life_days": float(half_life),
            "bandwidth": None,
            "min_effective_sample_size": int(min_effective_sample_size),
            "current_regime_features": {},
        }

    features = features if features is not None else _regime_features(close)
    standardized = _standardize_to_calibration(features, calibration_index, target_dt)
    kernel = _regime_kernel_weights(standardized, calibration_index, target_dt, bandwidth)
    regime_weights = time_weights * kernel
    ess_regime = effective_sample_size(regime_weights)
    if ess_regime is not None and ess_regime >= min_effective_sample_size:
        weights = regime_weights
        mode = "regime_weighted_conformal"
        fallback_reason = None
    else:
        weights = time_weights
        mode = "time_weighted_conformal_fallback"
        fallback_reason = "low_effective_sample_size_or_missing_regime_features"
    ess_used = effective_sample_size(weights)
    normalized = weights / weights.sum() if weights.sum() > 0 else weights
    effective_memory_days = float(((pd.Timestamp(target_dt) - pd.to_datetime(normalized.index)).days * normalized).sum())
    return weights, {
        "mode": mode,
        "fallback_reason": fallback_reason,
        "effective_sample_size": _finite(ess_used),
        "regime_effective_sample_size": _finite(ess_regime),
        "effective_memory_days": _finite(effective_memory_days),
        "half_life_days": float(half_life),
        "bandwidth": float(bandwidth),
        "min_effective_sample_size": int(min_effective_sample_size),
        "current_regime_features": {
            key: _finite(value) for key, value in features.loc[target_dt].to_dict().items()
        }
        if target_dt in features.index
        else {},
    }


def build_regime_weighted_tail_conformal_shadow(
    *,
    close: pd.Series,
    ticker: str = DEFAULT_TARGET_TICKER,
    as_of: str | None = None,
    alpha: float = 0.10,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    calibration_window: int = 504,
    min_calibration: int = 120,
    half_life: float = 126.0,
    bandwidth: float = 1.0,
    min_effective_sample_size: int = 60,
    severe_lower_tail_threshold: float = -0.08,
    use_regime_kernel: bool = True,
) -> dict[str, Any]:
    prices = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    prices.index = pd.to_datetime(prices.index)
    if as_of:
        prices = prices.loc[prices.index <= pd.Timestamp(as_of)]
    if len(prices) < min_calibration + max(horizons) + 20:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_regime_weighted_tail_conformal_shadow",
            "policy": "shadow_only_no_weight_change",
            "status": "unavailable",
            "reason": "insufficient_history",
            "ticker": ticker,
            "as_of": str(pd.Timestamp(as_of).date()) if as_of else None,
            "sample_size": int(len(prices)),
            "decision": {"creates_orders": False, "changes_target_weights": False, "blocks_trades": False},
        }

    target_dt = pd.Timestamp(prices.index[-1])
    diagnostics: dict[str, Any] = {}
    high_reasons: list[str] = []

    for horizon in horizons:
        fwd_ret = prices.shift(-horizon) / prices - 1.0
        pred = _prediction_from_past_labels(fwd_ret, horizon, calibration_window, min_calibration)
        residual = pred - fwd_ret
        known_cutoff = target_dt - pd.Timedelta(days=horizon)
        eligible = residual.index <= known_cutoff
        cal_resid = residual[eligible].dropna().tail(calibration_window)
        if len(cal_resid) < min_calibration:
            diagnostics[f"h{horizon}"] = {
                "horizon_days": int(horizon),
                "status": "unavailable",
                "reason": "insufficient_calibration",
                "calibration_count": int(len(cal_resid)),
            }
            continue

        weights, weight_diag = _calibration_weights(
            close=prices,
            calibration_index=cal_resid.index,
            target_dt=target_dt,
            half_life=half_life,
            bandwidth=bandwidth,
            min_effective_sample_size=min_effective_sample_size,
            use_regime_kernel=use_regime_kernel,
        )
        weighted_level = min(1.0, (1.0 - alpha) * (1.0 + 1.0 / float(weights.sum())))
        buffer = weighted_quantile(cal_resid, weights, weighted_level)
        latest_pred = _finite(pred.dropna().iloc[-1] if pred.dropna().size else None)
        lower = None if buffer is None or latest_pred is None else latest_pred - buffer
        if lower is not None and lower <= severe_lower_tail_threshold:
            high_reasons.append(f"h{horizon}_lower_bound_le_{abs(severe_lower_tail_threshold):.0%}")

        diagnostics[f"h{horizon}"] = {
            "horizon_days": int(horizon),
            "status": "ok",
            "point_forecast_return": latest_pred,
            "lower_tail_confidence_bound": _finite(lower),
            "nominal_alpha": float(alpha),
            "weighted_conformal_level": _finite(weighted_level),
            "lower_tail_residual_buffer": _finite(buffer),
            "calibration_count": int(len(cal_resid)),
            "weight_diagnostics": weight_diag,
        }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_regime_weighted_tail_conformal_shadow",
        "policy": "shadow_only_no_weight_change",
        "status": "ok",
        "ticker": ticker,
        "as_of": str(target_dt.date()),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2602.03903.pdf",
            "title": "Taming Tail Risk in Financial Markets: Conformal Calibration for Nonstationary Portfolio VaR",
            "imported_concept": "time-decayed and regime-similarity weighted one-sided conformal VaR buffer",
        },
        "diagnostics": diagnostics,
        "summary": {
            "state": "TAIL_RISK_SHADOW_HIGH" if high_reasons else "TAIL_RISK_SHADOW_NORMAL",
            "high_tail_reasons": sorted(set(high_reasons)),
            "recommended_next_step": "walk_forward_compare_against_existing_tail_conformal_before_promotion",
        },
        "decision": {
            "creates_orders": False,
            "changes_target_weights": False,
            "blocks_trades": False,
            "production_guard_changed": False,
        },
    }
