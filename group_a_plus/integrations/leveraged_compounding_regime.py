"""Sequence-aware compounding regime diagnostics for leveraged ETF exposure.

The regime is diagnostic-only.  It addresses the specific failure mode where
volatility is treated as sufficient reason to de-lever a daily-reset leveraged
ETF, ignoring serial dependence and rebound behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


TREND_PERSISTENT = "TREND_PERSISTENT"
MEAN_REVERTING = "MEAN_REVERTING"
TRANSITIONAL = "TRANSITIONAL"


@dataclass(frozen=True)
class CompoundingRegimeThresholds:
    ar1_trend_min: float = 0.05
    ar1_revert_max: float = -0.05
    variance_ratio_trend_min: float = 1.02
    variance_ratio_revert_max: float = 0.98
    trend_persistence_min: float = 0.60
    trend_persistence_revert_max: float = 0.55
    reversal_speed_revert_min: float = 0.55
    reversal_speed_trend_max: float = 0.45
    drawdown_recovery_revert_min: float = 0.50
    trend_score_min: int = 4
    mean_reversion_score_min: int = 3


def rolling_ar1(returns: pd.Series, window: int) -> pd.Series:
    def _ar1(x: np.ndarray) -> float:
        valid = x[np.isfinite(x)]
        if len(valid) < 3 or np.nanstd(valid[:-1]) == 0.0 or np.nanstd(valid[1:]) == 0.0:
            return np.nan
        return float(np.corrcoef(valid[:-1], valid[1:])[0, 1])

    return returns.rolling(window, min_periods=window).apply(_ar1, raw=True)


def positive_streak(returns: pd.Series) -> pd.Series:
    is_pos = returns > 0.0
    return is_pos.astype(int).groupby((~is_pos).cumsum()).cumsum()


def negative_streak(returns: pd.Series) -> pd.Series:
    is_neg = returns < 0.0
    return is_neg.astype(int).groupby((~is_neg).cumsum()).cumsum()


def rolling_variance_ratio(returns: pd.Series, *, aggregation: int = 5, window: int = 20) -> pd.Series:
    daily_var = returns.rolling(window, min_periods=window).var()
    aggregated = returns.rolling(aggregation, min_periods=aggregation).sum()
    aggregated_var = aggregated.rolling(window, min_periods=window).var()
    ratio = aggregated_var / (float(aggregation) * daily_var)
    return ratio.replace([np.inf, -np.inf], np.nan)


def trend_persistence(returns: pd.Series, window: int = 20) -> pd.Series:
    pos = (returns > 0.0).rolling(window, min_periods=window).sum()
    neg = (returns < 0.0).rolling(window, min_periods=window).sum()
    active = ((returns > 0.0) | (returns < 0.0)).rolling(window, min_periods=window).sum()
    return pd.concat([pos, neg], axis=1).max(axis=1) / active.replace(0.0, np.nan)


def reversal_speed(returns: pd.Series, window: int = 20) -> pd.Series:
    signs = np.sign(returns).replace(0.0, np.nan)
    flips = (signs != signs.shift(1)) & signs.notna() & signs.shift(1).notna()
    active = signs.notna() & signs.shift(1).notna()
    return flips.astype(float).rolling(window, min_periods=window).sum() / active.astype(float).rolling(
        window, min_periods=window
    ).sum().replace(0.0, np.nan)


def drawdown_recovery_ratio(close: pd.Series, window: int = 20) -> pd.Series:
    def _ratio(x: np.ndarray) -> float:
        if len(x) < 3 or not np.all(np.isfinite(x)):
            return np.nan
        peak_pos = int(np.argmax(x))
        trough_pos = int(np.argmin(x[peak_pos:]) + peak_pos)
        peak = float(x[peak_pos])
        trough = float(x[trough_pos])
        current = float(x[-1])
        drawdown = peak - trough
        if drawdown <= 0.0:
            return 0.0
        return float(np.clip((current - trough) / drawdown, 0.0, 2.0))

    return close.rolling(window, min_periods=window).apply(_ratio, raw=True)


def rolling_compounding_effect(
    price_00631l: pd.Series,
    price_0050: pd.Series,
    *,
    leverage: float = 2.0,
    window: int = 20,
) -> pd.Series:
    ret_00631l = price_00631l.astype(float).pct_change(window)
    ret_0050 = price_0050.astype(float).reindex(price_00631l.index).pct_change(window)
    return ret_00631l - float(leverage) * ret_0050


def build_compounding_features(
    price_00631l: pd.Series,
    price_0050: pd.Series,
    *,
    short_window: int = 5,
    long_window: int = 20,
) -> pd.DataFrame:
    price_00631l = price_00631l.astype(float).sort_index()
    price_0050 = price_0050.astype(float).reindex(price_00631l.index).astype(float)
    returns = price_00631l.pct_change()
    ret_0050 = price_0050.pct_change()
    out = pd.DataFrame(index=price_00631l.index)
    out["rolling_AR1_5d"] = rolling_ar1(returns, short_window)
    out["rolling_AR1_20d"] = rolling_ar1(returns, long_window)
    out["variance_ratio"] = rolling_variance_ratio(returns, aggregation=short_window, window=long_window)
    out["trend_persistence"] = trend_persistence(returns, long_window)
    out["reversal_speed"] = reversal_speed(returns, long_window)
    out["positive_return_streak"] = positive_streak(returns).astype(float)
    out["negative_return_streak"] = negative_streak(returns).astype(float)
    out["drawdown_recovery_ratio"] = drawdown_recovery_ratio(price_00631l, long_window)
    out["00631L_vs_0050_relative_momentum"] = (
        (1.0 + returns).rolling(long_window, min_periods=long_window).apply(np.prod, raw=True) - 1.0
    ) - ((1.0 + ret_0050).rolling(long_window, min_periods=long_window).apply(np.prod, raw=True) - 1.0)
    out["compounding_effect_20d"] = rolling_compounding_effect(price_00631l, price_0050, window=20)
    out["compounding_effect_60d"] = rolling_compounding_effect(price_00631l, price_0050, window=60)
    out["compounding_effect_120d"] = rolling_compounding_effect(price_00631l, price_0050, window=120)
    out["realized_volatility_20d"] = returns.rolling(20, min_periods=20).std()
    out["realized_volatility_60d"] = returns.rolling(60, min_periods=60).std()
    out["volatility_persistence_ratio"] = out["realized_volatility_20d"] / out["realized_volatility_60d"].replace(
        0.0, np.nan
    )
    return out


def classify_compounding_regime(
    features: pd.DataFrame,
    thresholds: CompoundingRegimeThresholds = CompoundingRegimeThresholds(),
) -> pd.DataFrame:
    frame = features.copy()
    trend_score = (
        (frame["rolling_AR1_20d"] >= thresholds.ar1_trend_min).astype(int)
        + (frame["rolling_AR1_5d"] > 0.0).astype(int)
        + (frame["variance_ratio"] >= thresholds.variance_ratio_trend_min).astype(int)
        + (frame["trend_persistence"] >= thresholds.trend_persistence_min).astype(int)
        + (frame["reversal_speed"] <= thresholds.reversal_speed_trend_max).astype(int)
        + (frame["00631L_vs_0050_relative_momentum"] > 0.0).astype(int)
    )
    mean_reversion_score = (
        (frame["rolling_AR1_20d"] <= thresholds.ar1_revert_max).astype(int)
        + (frame["rolling_AR1_5d"] < 0.0).astype(int)
        + (frame["variance_ratio"] <= thresholds.variance_ratio_revert_max).astype(int)
        + (frame["trend_persistence"] <= thresholds.trend_persistence_revert_max).astype(int)
        + (frame["reversal_speed"] >= thresholds.reversal_speed_revert_min).astype(int)
        + (
            (frame["drawdown_recovery_ratio"] >= thresholds.drawdown_recovery_revert_min)
            & (frame["00631L_vs_0050_relative_momentum"] <= 0.0)
        ).astype(int)
    )
    frame["trend_score"] = trend_score
    frame["mean_reversion_score"] = mean_reversion_score
    frame["compounding_regime"] = TRANSITIONAL
    frame.loc[
        (trend_score >= thresholds.trend_score_min)
        & (mean_reversion_score < thresholds.mean_reversion_score_min),
        "compounding_regime",
    ] = TREND_PERSISTENT
    frame.loc[
        (mean_reversion_score >= thresholds.mean_reversion_score_min)
        & (trend_score < thresholds.trend_score_min),
        "compounding_regime",
    ] = MEAN_REVERTING
    frame["recommended_policy"] = frame["compounding_regime"].map(
        {
            TREND_PERSISTENT: "do_not_reduce_00631l_for_high_volatility_alone",
            MEAN_REVERTING: "prohibit_new_leverage_or_reduce_rebalance_frequency",
            TRANSITIONAL: "maintain_a2118_no_active_overlay",
        }
    )
    return frame
