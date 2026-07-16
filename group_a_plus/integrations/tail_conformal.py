"""Tail-specific conformal diagnostics for GroupA+ crash warnings.

This module is warning-first. It estimates lower-tail forward return bounds and
forward drawdown risk, but it does not compute portfolio weights.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


DEFAULT_TARGET_TICKER = "00631L.TW"
HORIZONS = (5, 10)


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _conformal_quantile(values: pd.Series, alpha: float) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna().sort_values()
    n = len(clean)
    if n == 0:
        return None
    rank = min(max(math.ceil((n + 1) * (1.0 - alpha)), 1), n)
    return float(clean.iloc[rank - 1])


def _load_close(db_path: Path, ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, str(start.date()), str(end.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.Series(dtype=float)
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float).sort_index()


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-horizon) / close - 1.0


def _forward_mdd(close: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat([close.shift(-step) for step in range(1, horizon + 1)], axis=1)
    return future.min(axis=1) / close - 1.0


def _prediction_from_past_labels(labels: pd.Series, horizon: int, window: int, min_periods: int) -> pd.Series:
    return labels.rolling(window=window, min_periods=min_periods).median().shift(horizon)


def _risk_bucket(close: pd.Series, latest_features: dict[str, Any] | None = None) -> pd.Series:
    ret5 = close.pct_change(5)
    vol20 = close.pct_change().rolling(20, min_periods=10).std()
    vol60 = close.pct_change().rolling(60, min_periods=20).std()
    drawdown = close / close.rolling(252, min_periods=40).max() - 1.0
    bucket = pd.Series("normal", index=close.index, dtype=object)
    bucket[(ret5 < -0.04) | (drawdown < -0.08) | ((vol60 > 0) & (vol20 / vol60 > 1.25))] = "elevated"
    bucket[(ret5 < -0.08) | (drawdown < -0.14) | ((vol60 > 0) & (vol20 / vol60 > 1.60))] = "severe"

    if latest_features:
        latest_total = int(latest_features.get("total_risk_score", 0) or 0)
        latest_tail = int(latest_features.get("tail_risk_score", 0) or 0)
        if latest_total >= 9 or latest_tail >= 2:
            bucket.iloc[-1] = "severe"
        elif latest_total >= 6 or latest_tail >= 1:
            bucket.iloc[-1] = "elevated"
    return bucket


def compute_tail_conformal_diagnostic(
    *,
    db_path: Path,
    actual_date: pd.Timestamp,
    latest_features: dict[str, Any] | None = None,
    ncf_live_overlay: dict[str, Any] | None = None,
    ticker: str = DEFAULT_TARGET_TICKER,
    alpha: float = 0.10,
    calibration_window: int = 252,
    min_calibration: int = 80,
    severe_mdd_threshold: float = -0.08,
) -> dict[str, Any]:
    """Compute lower-tail conformal bounds for the latest available date."""

    actual = pd.Timestamp(actual_date).normalize()
    close = _load_close(
        db_path,
        ticker,
        actual - pd.Timedelta(days=max(900, calibration_window * 5)),
        actual,
    )
    close = close.loc[close.index <= actual].dropna()
    if len(close) < min_calibration + max(HORIZONS) + 5:
        return {
            "status": "unavailable",
            "reason": "insufficient_history",
            "policy": "diagnostic_warning_only_no_weight_change",
            "ticker": ticker,
            "actual_date": str(actual.date()),
            "sample_size": int(len(close)),
        }

    bucket = _risk_bucket(close, latest_features)
    current_bucket = str(bucket.iloc[-1])
    diagnostics: dict[str, Any] = {}
    high_tail = False
    high_reasons: list[str] = []
    min_lower_bound = None
    max_mdd_prob = None

    for horizon in HORIZONS:
        fwd_ret = _forward_return(close, horizon)
        fwd_mdd = _forward_mdd(close, horizon)
        pred = _prediction_from_past_labels(fwd_ret, horizon, calibration_window, min_calibration)
        residual = pred - fwd_ret
        known_cutoff = close.index[-1] - pd.Timedelta(days=horizon)
        eligible = residual.index <= known_cutoff
        bucket_match = bucket == current_bucket
        cal_resid = residual[eligible & bucket_match].tail(calibration_window)
        cal_mdd = fwd_mdd[eligible & bucket_match].tail(calibration_window)
        if len(cal_resid.dropna()) < min_calibration:
            cal_resid = residual[eligible].tail(calibration_window)
            cal_mdd = fwd_mdd[eligible].tail(calibration_window)
            calibration_scope = "all_buckets_fallback"
        else:
            calibration_scope = current_bucket

        q_resid = _conformal_quantile(cal_resid, alpha)
        latest_pred = _float_or_none(pred.dropna().iloc[-1] if pred.dropna().size else None)
        lower = None if q_resid is None or latest_pred is None else latest_pred - q_resid
        mdd_clean = pd.to_numeric(cal_mdd, errors="coerce").dropna()
        mdd_prob = float((mdd_clean <= severe_mdd_threshold).mean()) if len(mdd_clean) else None

        diagnostics[f"h{horizon}"] = {
            "horizon_days": horizon,
            "point_forecast_return": latest_pred,
            "lower_tail_confidence_bound": lower,
            "alpha": float(alpha),
            "nominal_lower_tail_coverage": float(1.0 - alpha),
            "calibration_scope": calibration_scope,
            "calibration_count": int(len(cal_resid.dropna())),
            "lower_tail_residual_quantile": q_resid,
            "prob_mdd_lt_8pct": mdd_prob,
            "mdd_threshold": severe_mdd_threshold,
        }
        if lower is not None:
            min_lower_bound = lower if min_lower_bound is None else min(min_lower_bound, lower)
            if lower <= -0.08:
                high_tail = True
                high_reasons.append(f"h{horizon}_lower_bound_le_8pct")
        if mdd_prob is not None:
            max_mdd_prob = mdd_prob if max_mdd_prob is None else max(max_mdd_prob, mdd_prob)
            if mdd_prob >= 0.35:
                high_tail = True
                high_reasons.append(f"h{horizon}_mdd8_prob_ge_35pct")

    ncf_warning = ((ncf_live_overlay or {}).get("a2118_extreme_risk_warning") or {})
    if ncf_warning.get("active") is True:
        high_reasons.append("a2118_extreme_risk_warning_active")

    return {
        "status": "ok",
        "policy": "diagnostic_warning_only_no_weight_change",
        "ticker": ticker,
        "actual_date": str(actual.date()),
        "state": "TAIL_RISK_HIGH" if high_tail else "TAIL_RISK_NORMAL",
        "recommended_action": "pause_new_00631l_adds_and_monitor_trough" if high_tail else "none",
        "allow_00631l_add": not high_tail,
        "auto_reduce_00631l": False,
        "current_risk_bucket": current_bucket,
        "min_lower_tail_confidence_bound": min_lower_bound,
        "max_prob_mdd_lt_8pct": max_mdd_prob,
        "high_tail_reasons": sorted(set(high_reasons)),
        "diagnostics": diagnostics,
        "rationale": (
            "Tail-specific conformal diagnostic controls lower-tail error separately. "
            "It is used to pause additional leverage and trigger trough monitoring, "
            "not to automatically liquidate 00631L."
        ),
    }
