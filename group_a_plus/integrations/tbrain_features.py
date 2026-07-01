"""TBrain ETF competition style feature helpers for GroupA+.

The 2018 TBrain ETF solution used compact multi-horizon technical features,
institutional-flow squashing, score-weighted model blending, and a direction
plus magnitude confirmation gate.  This module keeps those ideas as reusable
feature/diagnostic primitives; it does not change live allocation by itself.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


KDJ_PARAMS: tuple[tuple[int, int, int], ...] = (
    (9, 3, 3),
    (6, 3, 3),
    (18, 3, 3),
    (24, 3, 3),
    (5, 21, 11),
)
LOCATION_WINDOWS: tuple[int, ...] = (6, 11, 22, 43, 65, 130)
INSTITUTIONAL_FLOW_COLUMNS: tuple[str, ...] = (
    "foreign_net_buy",
    "investment_trust_net_buy",
    "dealer_net_buy",
    "institutional_total_net_buy",
)


def _safe_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    return numer / denom.replace(0, np.nan)


def squash_vector(values: pd.Series | np.ndarray | list[float]) -> np.ndarray:
    """Compress a flow vector with the squashing transform used by TBrainETF."""
    arr = np.asarray(values, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    lengths2 = float(np.sum(np.power(arr, 2)))
    if lengths2 <= 0.0:
        return np.zeros_like(arr, dtype=float)
    length = float(np.sqrt(lengths2))
    return arr * (length / (1.0 + lengths2))


def add_multi_kdj_features(
    df: pd.DataFrame,
    *,
    params: tuple[tuple[int, int, int], ...] = KDJ_PARAMS,
    prefix: str = "tbrain",
) -> pd.DataFrame:
    """Add multi-parameter K/D/J features."""
    out = df.copy()
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    for n, k_period, d_period in params:
        low_n = low.rolling(n, min_periods=n).min()
        high_n = high.rolling(n, min_periods=n).max()
        rsv = _safe_ratio(close - low_n, high_n - low_n) * 100.0
        k = rsv.ewm(alpha=1.0 / k_period, adjust=False, min_periods=k_period).mean()
        d = k.ewm(alpha=1.0 / d_period, adjust=False, min_periods=d_period).mean()
        j = 3.0 * k - 2.0 * d
        tag = f"{n}_{k_period}_{d_period}"
        out[f"{prefix}_kdj_k_{tag}"] = k / 100.0
        out[f"{prefix}_kdj_d_{tag}"] = d / 100.0
        out[f"{prefix}_kdj_j_{tag}"] = j / 100.0
    return out


def add_location_features(
    df: pd.DataFrame,
    *,
    windows: tuple[int, ...] = LOCATION_WINDOWS,
    prefix: str = "tbrain",
) -> pd.DataFrame:
    """Add price/volume location features against TBrainETF MA windows."""
    out = df.copy()
    close = out["close"].astype(float)
    volume = out["volume"].astype(float)
    wcl = (out["high"].astype(float) + out["low"].astype(float) + 2.0 * close) / 4.0
    for window in windows:
        ma_close = close.rolling(window, min_periods=window).mean()
        ma_wcl = wcl.rolling(window, min_periods=window).mean()
        ma_volume = volume.rolling(window, min_periods=window).mean()
        out[f"{prefix}_close_ma{window}_loc"] = _safe_ratio(close, ma_close) - 1.0
        out[f"{prefix}_wcl_ma{window}_loc"] = _safe_ratio(wcl, ma_wcl) - 1.0
        out[f"{prefix}_volume_ma{window}_loc"] = _safe_ratio(volume, ma_volume) - 1.0
    return out


def kdj_j_quantile_snapshot(
    df: pd.DataFrame,
    *,
    param: tuple[int, int, int] = (9, 3, 3),
    q_low: float = 0.10,
    q_high: float = 0.90,
    min_periods: int = 20,
    prefix: str = "tbrain",
) -> dict[str, float]:
    """Latest expanding-history J quantile band for one KDJ parameter set.

    Adapted from StockTradebyZ's ``KDJQuantileFilter``: rather than a fixed
    absolute J cutoff, track where today's J sits against its own expanding
    historical distribution (``expanding().quantile()``, no look-ahead) so the
    threshold adapts to each ticker's regime instead of drifting stale over
    a multi-year bull run. This is a standalone diagnostic — it does not
    touch ``add_tbrain_features``/``tbrain_feature_columns``, which are the
    fixed feature set already baked into the trained NCF models.
    """
    n, k_period, d_period = param
    tag = f"{n}_{k_period}_{d_period}"
    j_col = f"{prefix}_kdj_j_{tag}"
    features = add_multi_kdj_features(df, params=(param,), prefix=prefix)
    j = features[j_col]
    q_low_series = j.expanding(min_periods=min_periods).quantile(q_low)
    q_high_series = j.expanding(min_periods=min_periods).quantile(q_high)
    low_val = q_low_series.iloc[-1]
    high_val = q_high_series.iloc[-1]
    return {
        f"{j_col}_q_low": round(float(low_val), 6) if pd.notna(low_val) else None,
        f"{j_col}_q_high": round(float(high_val), 6) if pd.notna(high_val) else None,
    }


def compute_weekly_close(df: pd.DataFrame) -> pd.Series:
    """Daily close -> weekly close, keyed by each ISO week's last trading day."""
    close = df["close"].astype(float)
    idx = close.index
    year_week = idx.isocalendar().year.astype(str) + "-" + idx.isocalendar().week.astype(str).str.zfill(2)
    weekly = close.groupby(year_week).last()
    last_date_per_week = close.groupby(year_week).apply(lambda s: s.index[-1])
    weekly.index = pd.DatetimeIndex(last_date_per_week.to_numpy())
    return weekly.sort_index().dropna()


def weekly_ma_bull_snapshot(
    df: pd.DataFrame,
    *,
    ma_periods: tuple[int, int, int] = (4, 13, 26),
    prefix: str = "tbrain",
) -> dict[str, Any]:
    """Weekly MA short/mid/long bullish-alignment snapshot.

    Adapted from StockTradebyZ's ``WeeklyMABullFilter``: a higher-timeframe
    trend-structure check (weekly closes, not daily) that is orthogonal to
    the daily-frequency features above — useful as an additional, independent
    confirmation source rather than a replacement for them.
    """
    weekly = compute_weekly_close(df)
    short_w, mid_w, long_w = ma_periods
    if len(weekly) < long_w:
        return {
            "status": "insufficient_history",
            "weeks_available": int(len(weekly)),
            "weeks_required": int(long_w),
        }
    ma_short = weekly.rolling(short_w, min_periods=short_w).mean().iloc[-1]
    ma_mid = weekly.rolling(mid_w, min_periods=mid_w).mean().iloc[-1]
    ma_long = weekly.rolling(long_w, min_periods=long_w).mean().iloc[-1]
    if not (np.isfinite(ma_short) and np.isfinite(ma_mid) and np.isfinite(ma_long)):
        return {"status": "insufficient_history", "weeks_available": int(len(weekly))}
    return {
        "status": "available",
        "ma_periods_weeks": list(ma_periods),
        "ma_short": round(float(ma_short), 4),
        "ma_mid": round(float(ma_mid), 4),
        "ma_long": round(float(ma_long), 4),
        "bull_aligned": bool(ma_short > ma_mid > ma_long),
        "bear_aligned": bool(ma_short < ma_mid < ma_long),
        "weeks_available": int(len(weekly)),
    }


def add_institutional_squash_features(
    df: pd.DataFrame,
    *,
    flow_columns: tuple[str, ...] = INSTITUTIONAL_FLOW_COLUMNS,
    prefix: str = "tbrain",
) -> pd.DataFrame:
    """Add row-wise squashed institutional-flow features when columns exist."""
    out = df.copy()
    available = [col for col in flow_columns if col in out.columns]
    if not available:
        return out
    squashed = np.vstack([squash_vector(row) for row in out[available].to_numpy(dtype=float)])
    for i, col in enumerate(available):
        out[f"{prefix}_squash_{col}"] = squashed[:, i]
    out[f"{prefix}_squash_flow_norm"] = np.linalg.norm(squashed, axis=1)
    return out


def add_tbrain_features(
    df: pd.DataFrame,
    *,
    prefix: str = "tbrain",
) -> pd.DataFrame:
    """Add all currently supported TBrain-style features."""
    out = add_location_features(df, prefix=prefix)
    out = add_multi_kdj_features(out, prefix=prefix)
    out = add_institutional_squash_features(out, prefix=prefix)
    return out


def tbrain_feature_columns(prefix: str = "tbrain") -> list[str]:
    cols: list[str] = []
    for window in LOCATION_WINDOWS:
        cols.extend(
            [
                f"{prefix}_close_ma{window}_loc",
                f"{prefix}_wcl_ma{window}_loc",
                f"{prefix}_volume_ma{window}_loc",
            ]
        )
    for n, k_period, d_period in KDJ_PARAMS:
        tag = f"{n}_{k_period}_{d_period}"
        cols.extend(
            [
                f"{prefix}_kdj_k_{tag}",
                f"{prefix}_kdj_d_{tag}",
                f"{prefix}_kdj_j_{tag}",
            ]
        )
    for col in INSTITUTIONAL_FLOW_COLUMNS:
        cols.append(f"{prefix}_squash_{col}")
    cols.append(f"{prefix}_squash_flow_norm")
    return cols


def score_weighted_ensemble(
    predictions: dict[str, float],
    scores: dict[str, float],
    *,
    floor_score: float = 0.5,
) -> dict[str, Any]:
    """Blend scalar predictions with validation-score weights."""
    usable = {
        name: float(pred)
        for name, pred in predictions.items()
        if name in scores and np.isfinite(pred) and np.isfinite(float(scores[name]))
    }
    if not usable:
        return {"prediction": None, "weights": {}, "method": "score_weighted_ensemble"}
    raw = {name: max(0.0, float(scores[name]) - floor_score) for name in usable}
    total = sum(raw.values())
    if total <= 0.0:
        weights = {name: 1.0 / len(usable) for name in usable}
    else:
        weights = {name: value / total for name, value in raw.items()}
    prediction = sum(weights[name] * usable[name] for name in usable)
    return {
        "prediction": float(prediction),
        "weights": {name: round(float(weight), 4) for name, weight in sorted(weights.items())},
        "method": "score_weighted_ensemble",
    }


def direction_magnitude_gate(
    *,
    probability_up: float,
    predicted_return: float,
    min_probability_edge: float = 0.05,
    min_abs_return: float = 0.002,
) -> dict[str, Any]:
    """Confirm that direction probability and return magnitude agree."""
    prob = float(probability_up)
    ret = float(predicted_return)
    direction = "UP" if prob >= 0.5 else "DOWN"
    probability_edge = abs(prob - 0.5)
    return_side = "UP" if ret > 0.0 else "DOWN" if ret < 0.0 else "FLAT"
    passed = (
        probability_edge >= float(min_probability_edge)
        and abs(ret) >= float(min_abs_return)
        and return_side == direction
    )
    return {
        "passed": bool(passed),
        "direction": direction,
        "return_side": return_side,
        "probability_edge": round(probability_edge, 4),
        "predicted_return": round(ret, 6),
        "min_probability_edge": float(min_probability_edge),
        "min_abs_return": float(min_abs_return),
        "method": "direction_magnitude_gate",
    }


def latest_tbrain_snapshot(df: pd.DataFrame, *, prefix: str = "tbrain") -> dict[str, float]:
    """Return a compact latest-row snapshot for JSON diagnostics."""
    features = add_tbrain_features(df, prefix=prefix)
    if features.empty:
        return {}
    latest = features.iloc[-1]
    selected = [
        f"{prefix}_close_ma6_loc",
        f"{prefix}_close_ma22_loc",
        f"{prefix}_close_ma65_loc",
        f"{prefix}_close_ma130_loc",
        f"{prefix}_volume_ma22_loc",
        f"{prefix}_kdj_k_9_3_3",
        f"{prefix}_kdj_d_9_3_3",
        f"{prefix}_kdj_j_9_3_3",
        f"{prefix}_kdj_k_5_21_11",
        f"{prefix}_kdj_d_5_21_11",
    ]
    out = {}
    for col in selected:
        value = latest.get(col)
        if pd.notna(value):
            out[col] = round(float(value), 6)
    return out
