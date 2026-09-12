"""Regime-switching volatility forecast shadow for GroupA+.

Research-only implementation inspired by arXiv:2510.03236.  The paper's most
transferable idea for GroupA+ is not a live allocator, but a volatility-state
forecast layer: segment recent volatility history, fit local HAR-style
coefficients, cluster those coefficients, and output soft regime probabilities.

This module deliberately has no dependency on broker state, target weights, or
execution regimes.  It must not be used to mutate `golden1_0531` or latest
strategy weights without a separate OOS/backtest/trade-replay promotion step.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from group_a_plus.integrations.volatility_forecast import (
    DEFAULT_REFIT_EVERY,
    DEFAULT_ROLLING_WINDOW,
    GK_FLOOR,
    HORIZONS,
    MIN_TRAIN_ROWS,
    _future_avg_variance,
    garman_klass_variance,
    har_features,
)

DEFAULT_REGIMES = 2
DEFAULT_CHANGE_WINDOW = 22
DEFAULT_MIN_SEGMENT_ROWS = 45


def realized_kurtosis_from_close(close: pd.Series, *, window: int = 22) -> pd.Series:
    """Rolling realized kurtosis proxy from daily close-to-close returns."""
    ret = pd.to_numeric(close, errors="coerce").pct_change()
    numerator = ret.pow(4).rolling(window, min_periods=max(5, window // 2)).sum()
    denominator = ret.pow(2).rolling(window, min_periods=max(5, window // 2)).sum().pow(2)
    return (window * numerator / denominator.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)


def jump_variation_from_close(close: pd.Series, *, window: int = 22) -> pd.Series:
    """Rolling jump-variation proxy using daily returns and bipower variation."""
    ret = pd.to_numeric(close, errors="coerce").pct_change()
    realized_var = ret.pow(2).rolling(window, min_periods=max(5, window // 2)).sum()
    bipower = (math.pi / 2.0) * (ret.abs() * ret.shift(1).abs()).rolling(
        window, min_periods=max(5, window // 2)
    ).sum()
    return (realized_var - bipower).clip(lower=0.0).replace([np.inf, -np.inf], np.nan)


def regime_feature_frame(
    ohlc: pd.DataFrame,
    *,
    vix: pd.Series | None = None,
    extra_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build HAR + tail/shock features available from daily OHLC data."""
    gk = garman_klass_variance(ohlc[["open", "high", "low", "close"]])
    har = har_features(gk)
    frame = pd.DataFrame(index=ohlc.index)
    frame["gk_variance"] = gk
    frame["log_rv_d"] = har["log_rv_d"]
    frame["log_rv_w"] = har["log_rv_w"]
    frame["log_rv_m"] = har["log_rv_m"]
    frame["realized_kurtosis"] = realized_kurtosis_from_close(ohlc["close"])
    frame["jump_variation"] = jump_variation_from_close(ohlc["close"])
    if vix is not None:
        aligned_vix = pd.to_numeric(vix.reindex(ohlc.index), errors="coerce").ffill()
        frame["log_vix_d"] = np.log(aligned_vix.clip(lower=GK_FLOOR))
        frame["log_vix_w"] = np.log(aligned_vix.rolling(5, min_periods=5).mean().clip(lower=GK_FLOOR))
        frame["log_vix_m"] = np.log(aligned_vix.rolling(22, min_periods=22).mean().clip(lower=GK_FLOOR))
    if extra_features is not None and not extra_features.empty:
        extras = extra_features.reindex(ohlc.index).ffill()
        for col in extras.columns:
            values = pd.to_numeric(extras[col], errors="coerce")
            if values.notna().any():
                frame[f"extra_{col}"] = values
    return frame


def detect_variance_change_points(
    series: pd.Series,
    *,
    window: int = DEFAULT_CHANGE_WINDOW,
    log_ratio_threshold: float = 0.75,
) -> list[int]:
    """Approximate Mood-test style variance-shift points without heavy deps."""
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    points: list[int] = []
    last_point = -window
    for i in range(window, len(values) - window):
        if i - last_point < window:
            continue
        left = values[i - window : i]
        right = values[i : i + window]
        left = left[np.isfinite(left)]
        right = right[np.isfinite(right)]
        if len(left) < window // 2 or len(right) < window // 2:
            continue
        left_var = float(np.var(left, ddof=1))
        right_var = float(np.var(right, ddof=1))
        if left_var <= 0.0 or right_var <= 0.0:
            continue
        if abs(math.log(right_var / left_var)) >= log_ratio_threshold:
            points.append(i)
            last_point = i
    return points


def _segment_bounds(n: int, change_points: list[int], min_segment_rows: int) -> list[tuple[int, int]]:
    raw = [0] + sorted(p for p in change_points if 0 < p < n) + [n]
    bounds: list[tuple[int, int]] = []
    start = raw[0]
    for end in raw[1:]:
        if end - start < min_segment_rows:
            continue
        bounds.append((start, end))
        start = end
    if not bounds or bounds[-1][1] < n:
        tail_start = bounds[-1][1] if bounds else start
        if n - tail_start >= min_segment_rows:
            bounds.append((tail_start, n))
    return bounds


def _fit_ols(design: np.ndarray, target: np.ndarray, *, ridge: float = 1e-6) -> np.ndarray:
    x = np.column_stack([np.ones(len(design)), design])
    xtx = x.T @ x
    xtx += np.eye(xtx.shape[0]) * ridge
    xty = x.T @ target
    return np.linalg.solve(xtx, xty)


def _standardize(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    mean = frame.mean()
    std = frame.std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    return (frame - mean) / std, mean, std


def _kmeans(points: np.ndarray, k: int, *, max_iter: int = 30) -> tuple[np.ndarray, np.ndarray]:
    if len(points) == 0:
        raise ValueError("cannot cluster an empty point set")
    k = max(1, min(int(k), len(points)))
    if k == 1:
        return np.zeros(len(points), dtype=int), points.mean(axis=0, keepdims=True)
    seed_idx = np.linspace(0, len(points) - 1, k).round().astype(int)
    centers = points[seed_idx].copy()
    labels = np.zeros(len(points), dtype=int)
    for _ in range(max_iter):
        distances = ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        new_centers = centers.copy()
        for j in range(k):
            mask = new_labels == j
            if mask.any():
                new_centers[j] = points[mask].mean(axis=0)
        if np.array_equal(new_labels, labels) and np.allclose(new_centers, centers):
            break
        labels = new_labels
        centers = new_centers
    return labels, centers


def _soft_probabilities(point: np.ndarray, prototypes: np.ndarray) -> np.ndarray:
    distances = np.sqrt(((prototypes - point) ** 2).sum(axis=1))
    inv = 1.0 / np.maximum(distances, 1e-9)
    return inv / inv.sum()


def coefficient_regime_forecast(
    ohlc: pd.DataFrame,
    *,
    horizon: int,
    vix: pd.Series | None = None,
    extra_features: pd.DataFrame | None = None,
    n_regimes: int = DEFAULT_REGIMES,
    min_train_rows: int = MIN_TRAIN_ROWS,
    refit_every: int = DEFAULT_REFIT_EVERY,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
    change_window: int = DEFAULT_CHANGE_WINDOW,
    min_segment_rows: int = DEFAULT_MIN_SEGMENT_ROWS,
) -> pd.DataFrame:
    """Walk-forward coefficient-clustered HAR forecast with soft regimes."""
    features = regime_feature_frame(ohlc, vix=vix, extra_features=extra_features)
    feature_cols = [
        "log_rv_d",
        "log_rv_w",
        "log_rv_m",
        "realized_kurtosis",
        "jump_variation",
    ]
    if vix is not None:
        feature_cols.extend(["log_vix_d", "log_vix_w", "log_vix_m"])
    if extra_features is not None and not extra_features.empty:
        feature_cols.extend(col for col in features.columns if col.startswith("extra_"))

    target = np.log(_future_avg_variance(features["gk_variance"], horizon).clip(lower=GK_FLOOR))
    valid = features[feature_cols].notna().all(axis=1)
    out = pd.DataFrame(index=ohlc.index)
    out[f"regime_switch_forecast_vol_h{horizon}"] = np.nan
    out[f"regime_switch_confidence_h{horizon}"] = np.nan
    for j in range(n_regimes):
        out[f"soft_vol_regime_prob_{j}_h{horizon}"] = np.nan

    state: dict[str, Any] | None = None
    last_fit_idx = -1

    for i, _dt in enumerate(ohlc.index):
        if not bool(valid.iloc[i]):
            continue
        train_end = i - horizon
        if train_end < min_train_rows:
            continue
        if state is None or (i - last_fit_idx) >= refit_every:
            train_start = 0 if rolling_window is None else max(0, train_end + 1 - rolling_window)
            train_slice = features.iloc[train_start : train_end + 1]
            target_slice = target.iloc[train_start : train_end + 1]
            train_valid = valid.iloc[train_start : train_end + 1] & target_slice.notna()
            if int(train_valid.sum()) < min_train_rows:
                continue
            x_raw = train_slice.loc[train_valid, feature_cols]
            y_raw = target_slice.loc[train_valid]
            x_std, mean, std = _standardize(x_raw)
            change_points = detect_variance_change_points(
                train_slice["gk_variance"].loc[train_valid],
                window=change_window,
            )
            bounds = _segment_bounds(len(x_std), change_points, min_segment_rows)
            coeffs: list[np.ndarray] = []
            prototypes: list[np.ndarray] = []
            for start, end in bounds:
                if end - start < min_segment_rows:
                    continue
                x_seg = x_std.iloc[start:end].to_numpy(dtype=float)
                y_seg = y_raw.iloc[start:end].to_numpy(dtype=float)
                coeffs.append(_fit_ols(x_seg, y_seg))
                prototypes.append(x_seg.mean(axis=0))
            if len(coeffs) < 1:
                x_all = x_std.to_numpy(dtype=float)
                coeffs = [_fit_ols(x_all, y_raw.to_numpy(dtype=float))]
                prototypes = [x_all.mean(axis=0)]
            coeff_array = np.vstack(coeffs)
            proto_array = np.vstack(prototypes)
            labels, centers = _kmeans(coeff_array, n_regimes)
            regime_coeffs = []
            regime_prototypes = []
            for j in range(len(centers)):
                mask = labels == j
                regime_coeffs.append(coeff_array[mask].mean(axis=0))
                regime_prototypes.append(proto_array[mask].mean(axis=0))
            state = {
                "mean": mean,
                "std": std,
                "coeffs": np.vstack(regime_coeffs),
                "prototypes": np.vstack(regime_prototypes),
                "regime_count": len(regime_coeffs),
                "log_target_floor": float(y_raw.quantile(0.01)),
                "log_target_cap": float(y_raw.quantile(0.99)),
            }
            last_fit_idx = i

        if state is None:
            continue
        row = ((features.iloc[i][feature_cols] - state["mean"]) / state["std"]).to_numpy(dtype=float)
        probs = _soft_probabilities(row, state["prototypes"])
        design = np.r_[1.0, row]
        log_preds = state["coeffs"] @ design
        log_forecast = float(probs @ log_preds)
        log_forecast = min(max(log_forecast, state["log_target_floor"]), state["log_target_cap"])
        forecast = float(np.exp(log_forecast))
        out.iloc[i, out.columns.get_loc(f"regime_switch_forecast_vol_h{horizon}")] = forecast
        out.iloc[i, out.columns.get_loc(f"regime_switch_confidence_h{horizon}")] = float(probs.max())
        for j, prob in enumerate(probs):
            out.iloc[i, out.columns.get_loc(f"soft_vol_regime_prob_{j}_h{horizon}")] = float(prob)

    return out


def build_regime_switching_volatility_shadow(
    ohlc: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    vix: pd.Series | None = None,
    extra_features: pd.DataFrame | None = None,
    n_regimes: int = DEFAULT_REGIMES,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
) -> pd.DataFrame:
    """Build research-only multi-horizon regime-switching volatility shadow."""
    base = regime_feature_frame(ohlc, vix=vix, extra_features=extra_features)
    out = pd.DataFrame(index=ohlc.index)
    out["gk_variance"] = base["gk_variance"]
    out["realized_kurtosis"] = base["realized_kurtosis"]
    out["jump_variation"] = base["jump_variation"]
    out["policy"] = "shadow_only_no_weight_change"
    for h in horizons:
        forecast = coefficient_regime_forecast(
            ohlc,
            horizon=h,
            vix=vix,
            extra_features=extra_features,
            n_regimes=n_regimes,
            rolling_window=rolling_window,
        )
        out = out.join(forecast, how="left")
        fc = out[f"regime_switch_forecast_vol_h{h}"]
        fc_base = fc.rolling(252, min_periods=60)
        out[f"regime_switch_forecast_vol_h{h}_ratio"] = (fc / fc_base.median().replace(0.0, np.nan)).fillna(1.0)
        out[f"regime_switch_forecast_vol_h{h}_percentile"] = fc_base.rank(pct=True).fillna(0.5)
    return out


def latest_regime_switching_volatility_snapshot(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"status": "unavailable", "reason": "empty_frame"}
    row = frame.iloc[-1]
    horizons = sorted(
        int(c.split("regime_switch_forecast_vol_h")[1])
        for c in frame.columns
        if c.startswith("regime_switch_forecast_vol_h") and c.split("regime_switch_forecast_vol_h")[1].isdigit()
    )
    return {
        "status": "available",
        "policy": "shadow_only_no_weight_change",
        "outputs_target_weights": False,
        "outputs_execution_regime": False,
        "horizons": {
            str(h): {
                "forecast_variance": float(row[f"regime_switch_forecast_vol_h{h}"])
                if pd.notna(row.get(f"regime_switch_forecast_vol_h{h}"))
                else None,
                "confidence": float(row[f"regime_switch_confidence_h{h}"])
                if pd.notna(row.get(f"regime_switch_confidence_h{h}"))
                else None,
                "ratio_vs_252d_median": float(row.get(f"regime_switch_forecast_vol_h{h}_ratio", float("nan"))),
                "percentile_vs_252d": float(row.get(f"regime_switch_forecast_vol_h{h}_percentile", float("nan"))),
            }
            for h in horizons
        },
    }
