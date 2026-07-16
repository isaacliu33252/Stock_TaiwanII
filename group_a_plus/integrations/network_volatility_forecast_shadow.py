"""GNHAR-RV network volatility forecast prototype for GroupA+ (shadow, research-only).

Extends the existing univariate HAR-RV forecast (volatility_forecast.py) with a
cross-asset network term, following arXiv:2606.03828's GNHAR specification:

    X_t = mu + A^(d) X^(d)_{t-1} + A^(w) X^(w)_{t-1} + A^(m) X^(m)_{t-1} + eps,
    A^(.) = diag(alpha) + beta * W

using a fully-connected, unweighted 1-stage neighbour graph (W = simple average
of the other nodes' own daily/weekly/monthly log-variance components).

Uses the paper's single most robust configuration -- global-alpha (the daily/
weekly/monthly AR and network coefficients are pooled/shared across all nodes
via one fixed-effects OLS fit; only the intercept is node-specific) with
network order (1,0,1): a daily and a monthly network term, no weekly network
term. Across all five graph types the paper tested, individual-alpha models
were consistently *worse* than the no-network HAR benchmark and excluded from
the Model Confidence Set, while (1,0,1)/(1,1,0) global-alpha were the only
orders always retained (Table 2) -- so this prototype does not implement
individual-alpha or other network orders.

This module only produces forecasts; it does not change any target weight or
alert. Whether pooling neighbour realized-variance information actually beats
the existing univariate HAR-RV walk-forward forecast for 0050.TW must be
checked with scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py
before this is used for anything.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from group_a_plus.integrations.volatility_forecast import (
    GK_FLOOR,
    garman_klass_variance,
    har_features,
)

DEFAULT_TICKERS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "00679B.TWO",
    "00646.TW",
    "00713.TW",
    "00878.TW",
)
NETWORK_ORDER = (1, 0, 1)  # (daily, weekly, monthly) network stages; paper's robust global-alpha choice
MIN_TRAIN_ROWS = 130
DEFAULT_REFIT_EVERY = 21
DEFAULT_ROLLING_WINDOW = 504  # matches volatility_forecast.py's validated univariate window


def build_gk_variance_panel(ohlcv: pd.DataFrame, *, tickers: tuple[str, ...] = DEFAULT_TICKERS) -> pd.DataFrame:
    """Wide Garman-Klass variance panel (one column per ticker), forward-filled."""
    required = {"dt", "ticker", "open", "high", "low", "close"}
    missing = sorted(required - set(ohlcv.columns))
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    frame = ohlcv.copy()
    frame["dt"] = pd.to_datetime(frame["dt"])
    out = pd.DataFrame(index=sorted(frame["dt"].dropna().unique()))
    for ticker in tickers:
        rows = frame.loc[frame["ticker"] == ticker].set_index("dt").sort_index()
        if rows.empty:
            continue
        out[ticker] = garman_klass_variance(rows[["open", "high", "low", "close"]])
    return out.sort_index().ffill()


def _node_features(gk_panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-node daily/weekly/monthly log-variance features (the own HAR terms)."""
    return {ticker: har_features(gk_panel[ticker]) for ticker in gk_panel.columns}


def _neighbor_average(features: dict[str, pd.DataFrame], column: str, target: str) -> pd.Series:
    """Fully-connected 1-stage neighbour average of a log-variance feature column."""
    neighbours = [ticker for ticker in features if ticker != target]
    if not neighbours:
        raise ValueError("at least one neighbour ticker is required")
    stacked = pd.concat([features[n][column] for n in neighbours], axis=1)
    return stacked.mean(axis=1, skipna=False)


def _feature_columns(network_order: tuple[int, int, int]) -> list[str]:
    use_d, use_w, use_m = (order > 0 for order in network_order)
    cols = ["own_d", "own_w", "own_m"]
    if use_d:
        cols.append("net_d")
    if use_w:
        cols.append("net_w")
    if use_m:
        cols.append("net_m")
    return cols


def build_gnhar_design(
    gk_panel: pd.DataFrame,
    *,
    network_order: tuple[int, int, int] = NETWORK_ORDER,
) -> pd.DataFrame:
    """Pooled (node, date) design frame: own HAR terms + neighbour-average network terms.

    One row per (ticker, date), long format, columns ``dt``, ``ticker``,
    ``gk_variance`` (raw, own future-target base) plus ``own_d/own_w/own_m``
    and (only for stages included in ``network_order``) ``net_d/net_w/net_m``.
    """
    if len(gk_panel.columns) < 2:
        raise ValueError("at least two tickers are required to build a network design")
    features = _node_features(gk_panel)
    use_d, use_w, use_m = (order > 0 for order in network_order)
    rows = []
    for ticker in gk_panel.columns:
        own = features[ticker]
        block = pd.DataFrame(index=own.index)
        block["ticker"] = ticker
        block["gk_variance"] = gk_panel[ticker]
        block["own_d"] = own["log_rv_d"]
        block["own_w"] = own["log_rv_w"]
        block["own_m"] = own["log_rv_m"]
        if use_d:
            block["net_d"] = _neighbor_average(features, "log_rv_d", ticker)
        if use_w:
            block["net_w"] = _neighbor_average(features, "log_rv_w", ticker)
        if use_m:
            block["net_m"] = _neighbor_average(features, "log_rv_m", ticker)
        rows.append(block)
    return pd.concat(rows, axis=0).reset_index().rename(columns={"index": "dt"})


def _future_avg_variance(gk_variance: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat([gk_variance.shift(-i) for i in range(1, horizon + 1)], axis=1)
    return future.mean(axis=1, skipna=False)


def _fit_pooled_ols(
    design_slice: pd.DataFrame, feature_cols: list[str], target: pd.Series
) -> tuple[dict[str, float], np.ndarray]:
    """Pooled OLS with ticker fixed intercepts and shared (global-alpha) slope coefficients."""
    dummies = pd.get_dummies(design_slice["ticker"], prefix="mu").astype(float)
    x = np.column_stack([dummies.to_numpy(), design_slice[feature_cols].to_numpy(dtype=float)])
    y = target.to_numpy(dtype=float)
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    intercepts = {
        ticker: float(coef[i]) for i, ticker in enumerate(dummies.columns.str.replace("mu_", "", regex=False))
    }
    slopes = coef[dummies.shape[1] :]
    return intercepts, slopes


def gnhar_rv_walkforward_forecast(
    gk_panel: pd.DataFrame,
    *,
    target: str,
    horizon: int,
    network_order: tuple[int, int, int] = NETWORK_ORDER,
    min_train_rows: int = MIN_TRAIN_ROWS,
    refit_every: int = DEFAULT_REFIT_EVERY,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
) -> pd.Series:
    """Walk-forward GNHAR-RV forecast of ``target``'s average variance over ``horizon`` days.

    Pools all tickers in ``gk_panel`` to fit shared (global-alpha) daily/weekly/
    monthly AR and network coefficients, but only forecasts ``target``. Mirrors
    volatility_forecast.har_rv_walkforward_forecast's no-lookahead walk-forward
    discipline: at each date t, only information available up to and including
    t is used to fit and forecast.
    """
    if target not in gk_panel.columns:
        raise ValueError(f"target ticker missing from gk_panel: {target}")
    feature_cols = _feature_columns(network_order)
    design = build_gnhar_design(gk_panel, network_order=network_order)
    design["target_future_avg"] = design.groupby("ticker")["gk_variance"].transform(
        lambda s: _future_avg_variance(s, horizon)
    )
    design["log_target"] = np.log(design["target_future_avg"].clip(lower=GK_FLOOR))
    design["valid_features"] = design[feature_cols].notna().all(axis=1)

    dates = gk_panel.index
    target_rows = design.loc[design["ticker"] == target].set_index("dt").reindex(dates)

    forecast = pd.Series(np.nan, index=dates, dtype=float)
    intercepts: dict[str, float] | None = None
    slopes: np.ndarray | None = None
    last_fit_idx = -1

    for i, dt in enumerate(dates):
        if not bool(target_rows["valid_features"].iloc[i]):
            continue
        train_end = i - horizon
        if train_end < min_train_rows:
            continue
        if slopes is None or (i - last_fit_idx) >= refit_every:
            train_start = 0 if rolling_window is None else max(0, train_end + 1 - rolling_window)
            train_dates = set(dates[train_start : train_end + 1])
            train_slice = design.loc[design["dt"].isin(train_dates)]
            train_slice = train_slice.loc[train_slice["valid_features"] & train_slice["log_target"].notna()]
            if train_slice["ticker"].nunique() < 2 or len(train_slice) < min_train_rows:
                continue
            intercepts, slopes = _fit_pooled_ols(train_slice, feature_cols, train_slice["log_target"])
            last_fit_idx = i
        if intercepts is None or target not in intercepts or slopes is None:
            continue
        row = target_rows.iloc[i][feature_cols].to_numpy(dtype=float)
        log_forecast = intercepts[target] + float(np.dot(slopes, row))
        forecast.iloc[i] = math.exp(log_forecast)

    return forecast.rename(f"gnhar_rv_forecast_h{horizon}")


def build_multi_horizon_gnhar_forecast(
    ohlcv: pd.DataFrame,
    *,
    target: str = "0050.TW",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    horizons: tuple[int, ...] = (5, 10, 20),
    network_order: tuple[int, int, int] = NETWORK_ORDER,
    refit_every: int = DEFAULT_REFIT_EVERY,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
) -> pd.DataFrame:
    gk_panel = build_gk_variance_panel(ohlcv, tickers=tickers)
    available = tuple(col for col in tickers if col in gk_panel.columns and gk_panel[col].notna().any())
    gk_panel = gk_panel[list(available)].dropna(how="all").ffill()
    out = pd.DataFrame(index=gk_panel.index)
    out["gk_variance"] = gk_panel[target]
    for h in horizons:
        out[f"gnhar_forecast_vol_h{h}"] = gnhar_rv_walkforward_forecast(
            gk_panel,
            target=target,
            horizon=h,
            network_order=network_order,
            refit_every=refit_every,
            rolling_window=rolling_window,
        )
    return out


def latest_gnhar_forecast_snapshot(multi_horizon_frame: pd.DataFrame) -> dict[str, Any]:
    if multi_horizon_frame.empty:
        return {"status": "unavailable", "reason": "empty_frame"}
    row = multi_horizon_frame.iloc[-1]
    horizons = sorted(
        int(c.split("gnhar_forecast_vol_h")[1])
        for c in multi_horizon_frame.columns
        if c.startswith("gnhar_forecast_vol_h")
    )
    snapshot: dict[str, Any] = {"status": "available", "horizons": {}}
    for h in horizons:
        value = row.get(f"gnhar_forecast_vol_h{h}", float("nan"))
        snapshot["horizons"][str(h)] = {"forecast_variance": float(value) if pd.notna(value) else None}
    return snapshot
