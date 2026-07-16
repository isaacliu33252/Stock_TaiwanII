"""HAR-RV realized-volatility forecast for 0050.TW.

A genuine h-step-ahead forecast of future realized variance, as distinct
from the backward-looking GARCH-proxy ratio/percentile already used by
garch_regime_shadow.py (which only compares recent realized vol to its own
history and never simulates forward).

Method: Corsi (2009) Heterogeneous Autoregressive Realized Volatility
(HAR-RV), fit in log-variance space, using the Garman-Klass (1980) daily
variance estimator as the realized-variance proxy -- the same proxy used by
arXiv 2604.10402v4 (the specialist-routing paper already evaluated in this
project). Forecasts are direct multi-horizon (separate regression per
horizon on the average future variance over that horizon), not iterated
one-step-ahead rollouts.

This module only produces forecasts; it does not change any target weight.
Wiring a decision rule on top of it is a separate, explicit step.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

HORIZONS = (5, 10, 20)
MIN_TRAIN_ROWS = 130
DEFAULT_REFIT_EVERY = 21
GK_FLOOR = 1e-10


def garman_klass_variance(ohlc: pd.DataFrame) -> pd.Series:
    """Daily Garman-Klass variance estimate from open/high/low/close."""
    o = pd.to_numeric(ohlc["open"], errors="coerce")
    h = pd.to_numeric(ohlc["high"], errors="coerce")
    l = pd.to_numeric(ohlc["low"], errors="coerce")
    c = pd.to_numeric(ohlc["close"], errors="coerce")
    log_hl = np.log(h / l)
    log_co = np.log(c / o)
    gk = 0.5 * log_hl**2 - (2.0 * math.log(2.0) - 1.0) * log_co**2
    return gk.clip(lower=GK_FLOOR).rename("gk_variance")


def har_features(gk_variance: pd.Series) -> pd.DataFrame:
    """Daily/weekly/monthly log-variance components used by HAR-RV."""
    log_rv_d = np.log(gk_variance.clip(lower=GK_FLOOR))
    rv_w = gk_variance.rolling(5, min_periods=5).mean()
    rv_m = gk_variance.rolling(22, min_periods=22).mean()
    return pd.DataFrame(
        {
            "log_rv_d": log_rv_d,
            "log_rv_w": np.log(rv_w.clip(lower=GK_FLOOR)),
            "log_rv_m": np.log(rv_m.clip(lower=GK_FLOOR)),
        },
        index=gk_variance.index,
    )


def _future_avg_variance(gk_variance: pd.Series, horizon: int) -> pd.Series:
    """Mean realized variance over the next `horizon` trading days (target)."""
    future = pd.concat([gk_variance.shift(-i) for i in range(1, horizon + 1)], axis=1)
    return future.mean(axis=1, skipna=False)


def _fit_ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coef


def har_rv_walkforward_forecast(
    gk_variance: pd.Series,
    *,
    horizon: int,
    min_train_rows: int = MIN_TRAIN_ROWS,
    refit_every: int = DEFAULT_REFIT_EVERY,
    rolling_window: int | None = None,
) -> pd.Series:
    """Walk-forward HAR-RV forecast of average variance over `horizon` days.

    At each date t, only information up to and including t is used to fit the
    regression (features at time s<=t, targets = mean variance over
    s+1..s+horizon, so the last usable training row is t-horizon). This
    mirrors the walk-forward discipline already used by run_a2118's
    HAR-RV/GRU/XGBoost pool (refit every `refit_every` days, forecast in
    between with frozen coefficients).

    `rolling_window` (in rows), when set, fits on only the trailing N rows
    ending at train_end instead of the full expanding history -- matching
    arXiv 2604.10402v4's 504-day rolling training window. Default (None)
    uses an expanding window.
    """
    features = har_features(gk_variance)
    target = np.log(_future_avg_variance(gk_variance, horizon).clip(lower=GK_FLOOR))
    valid = features.notna().all(axis=1)

    forecast = pd.Series(np.nan, index=gk_variance.index, dtype=float)
    coef: np.ndarray | None = None
    last_fit_idx = -1

    for i, dt in enumerate(gk_variance.index):
        if not valid.iloc[i]:
            continue
        train_end = i - horizon
        if train_end < min_train_rows:
            continue
        if coef is None or (i - last_fit_idx) >= refit_every:
            train_start = 0 if rolling_window is None else max(0, train_end + 1 - rolling_window)
            train_mask = valid.iloc[train_start : train_end + 1] & target.iloc[train_start : train_end + 1].notna()
            train_idx = train_start + np.where(train_mask.to_numpy())[0]
            if len(train_idx) < min_train_rows:
                continue
            x = features.iloc[train_idx][["log_rv_d", "log_rv_w", "log_rv_m"]].to_numpy(dtype=float)
            y = target.iloc[train_idx].to_numpy(dtype=float)
            coef = _fit_ols(x, y)
            last_fit_idx = i
        row = features.iloc[i][["log_rv_d", "log_rv_w", "log_rv_m"]].to_numpy(dtype=float)
        log_forecast = coef[0] + float(np.dot(coef[1:], row))
        forecast.iloc[i] = math.exp(log_forecast)

    return forecast.rename(f"har_rv_forecast_h{horizon}")


def naive_persistence_forecast(gk_variance: pd.Series, *, horizon: int) -> pd.Series:
    """Naive baseline: forecast next-h average variance as today's RV_m (22d)."""
    return gk_variance.rolling(22, min_periods=5).mean().rename(f"naive_forecast_h{horizon}")


DEFAULT_ROLLING_WINDOW = 504  # matches arXiv 2604.10402v4's rolling training window;
# validated 2026-07-10 (evaluate_group_a_plus_volatility_forecast_quality.py) to beat
# expanding-window fits at all three horizons: QLIKE improvement over naive persistence
# was -34.8%/+2.0%/+12.7% (h=5/10/20) with an expanding window vs +2.8%/+11.7%/+15.2%
# with this 504-day rolling window.


def build_multi_horizon_forecast(
    ohlc: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    refit_every: int = DEFAULT_REFIT_EVERY,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
) -> pd.DataFrame:
    gk_variance = garman_klass_variance(ohlc)
    out = pd.DataFrame(index=ohlc.index)
    out["gk_variance"] = gk_variance
    for h in horizons:
        fc = har_rv_walkforward_forecast(gk_variance, horizon=h, refit_every=refit_every, rolling_window=rolling_window)
        out[f"forecast_vol_h{h}"] = fc
        # Ratio/percentile are computed against the forecast series' OWN rolling
        # history, not against raw daily GK variance -- comparing a smoothed
        # h-day-ahead average-variance forecast to a single-day realized-variance
        # median is an apples-to-oranges scale mismatch (caught 2026-07-10: median
        # ratio was 1.54, not ~1.0, when the denominator was gk_variance's median).
        fc_base = fc.rolling(252, min_periods=60)
        out[f"forecast_vol_h{h}_ratio"] = (fc / fc_base.median().replace(0.0, np.nan)).fillna(1.0)
        out[f"forecast_vol_h{h}_percentile"] = fc_base.rank(pct=True).fillna(0.5)
    return out


def latest_forecast_snapshot(multi_horizon_frame: pd.DataFrame) -> dict[str, Any]:
    if multi_horizon_frame.empty:
        return {"status": "unavailable", "reason": "empty_frame"}
    row = multi_horizon_frame.iloc[-1]
    horizons = [int(c.split("forecast_vol_h")[1]) for c in multi_horizon_frame.columns if c.startswith("forecast_vol_h") and c.endswith(("5", "10", "20"))]
    snapshot: dict[str, Any] = {"status": "available", "horizons": {}}
    for h in sorted(set(horizons)):
        snapshot["horizons"][str(h)] = {
            "forecast_variance": float(row.get(f"forecast_vol_h{h}", float("nan"))),
            "ratio_vs_252d_median": float(row.get(f"forecast_vol_h{h}_ratio", float("nan"))),
            "percentile_vs_252d": float(row.get(f"forecast_vol_h{h}_percentile", float("nan"))),
        }
    return snapshot
