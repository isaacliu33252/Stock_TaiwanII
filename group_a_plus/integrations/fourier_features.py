"""Fourier Transform trend-decomposition features for NCF models.

Inspired by the stockpredictionai approach (Boris Banushev, 2019):
  https://github.com/borisbanushev/stockpredictionai

Key idea: decompose the close-price series into long/medium/short-term
Fourier trend components, then measure how far the current price deviates
from each trend and how fast each trend is changing.

Unlike the original (which applied FFT on the full training history),
we use a ROLLING window to avoid lookahead bias — each feature value
at time T uses only data up to T.

Features produced
-----------------
fft_3c_dev      — price deviation from 3-component (long-term ~40d period) trend
fft_6c_dev      — price deviation from 6-component (medium-term ~20d period) trend
fft_9c_dev      — price deviation from 9-component (short-term ~13d period) trend
fft_3c_slope_5d — 5-day slope of long-term Fourier trend (positive = accelerating up)
fft_6c_slope_5d — 5-day slope of medium-term trend
fft_9c_slope_5d — 5-day slope of short-term trend

ATFNet-lite spectral features
-----------------------------
fft_power_low/mid/high    — rolling spectral power distribution
fft_spectral_entropy      — normalized entropy of non-DC FFT power
fft_dominant_period       — dominant non-DC period in trading days
fft_high_freq_shock       — high-frequency power relative to low+mid power
fft_time_freq_divergence  — price momentum minus dominant Fourier trend slope
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FOURIER_WINDOW: int = 120         # rolling window (6 months of trading days)
FOURIER_COMPONENTS: tuple[int, ...] = (3, 6, 9)
FOURIER_SLOPE_LAG: int = 5        # days back for slope calculation
SPECTRAL_WINDOWS: tuple[int, ...] = (16, 32, 64)


def _rolling_fft_trend(close_arr: np.ndarray, window: int, n_components: int) -> np.ndarray:
    """Compute rolling Fourier-smoothed trend value for each row.

    For each position i (i >= window-1), fits FFT on the preceding `window`
    rows, zeroes out all frequencies beyond `n_components`, then returns the
    IFFT reconstruction value at the last (current) point of the window.

    Returns NaN for the first (window-1) rows.
    """
    n = len(close_arr)
    result = np.full(n, np.nan)
    if n < window:
        return result

    windows = np.lib.stride_tricks.sliding_window_view(close_arr, window)
    # windows shape: (n - window + 1, window)

    for i, chunk in enumerate(windows):
        coeffs = np.fft.rfft(chunk)
        # Keep DC + first n_components frequencies; zero out the rest
        filtered = np.zeros(len(coeffs), dtype=complex)
        keep = min(n_components + 1, len(coeffs))
        filtered[:keep] = coeffs[:keep]
        trend = np.fft.irfft(filtered, n=window)
        result[i + window - 1] = trend[-1]

    return result


def add_fourier_features(
    df: pd.DataFrame,
    *,
    window: int = FOURIER_WINDOW,
    components: tuple[int, ...] = FOURIER_COMPONENTS,
    slope_lag: int = FOURIER_SLOPE_LAG,
    price_col: str = "close",
    prefix: str = "fft",
) -> pd.DataFrame:
    """Add rolling Fourier trend features to a price DataFrame.

    Parameters
    ----------
    df : DataFrame with at least a `close` column (DatetimeIndex).
    window : rolling window in trading days.
    components : tuple of frequency counts to extract.
    slope_lag : number of days used for trend slope calculation.
    price_col : column to apply FFT on (default 'close').
    prefix : column name prefix (default 'fft').

    Returns
    -------
    DataFrame with new columns added in-place (copy).
    """
    out = df.copy()
    if price_col not in out.columns:
        return out

    close_arr = out[price_col].to_numpy(dtype=float)

    for n_comp in components:
        trend = _rolling_fft_trend(close_arr, window=window, n_components=n_comp)
        trend_s = pd.Series(trend, index=out.index)

        # Deviation: how far current price sits above/below the smooth trend
        out[f"{prefix}_{n_comp}c_dev"] = (out[price_col] / trend_s) - 1.0

        # 5-day slope of the trend itself (normalised by current trend level)
        out[f"{prefix}_{n_comp}c_slope_5d"] = trend_s.pct_change(slope_lag, fill_method=None)

    return out


def _rolling_spectral_stats(close_arr: np.ndarray, window: int) -> dict[str, np.ndarray]:
    """Compute rolling FFT power statistics using only past/current rows."""
    n = len(close_arr)
    out = {
        "power_low": np.full(n, np.nan),
        "power_mid": np.full(n, np.nan),
        "power_high": np.full(n, np.nan),
        "spectral_entropy": np.full(n, np.nan),
        "dominant_period": np.full(n, np.nan),
        "high_freq_shock": np.full(n, np.nan),
    }
    if n < window:
        return out

    windows = np.lib.stride_tricks.sliding_window_view(close_arr, window)
    for i, chunk in enumerate(windows):
        # Work on returns to reduce level/trend dominance and make ETF prices comparable.
        returns = np.diff(np.log(np.maximum(chunk, 1e-12)))
        returns = returns - np.nanmean(returns)
        if not np.isfinite(returns).all() or np.allclose(returns, 0.0):
            continue

        coeffs = np.fft.rfft(returns)
        power = np.abs(coeffs) ** 2
        non_dc = power[1:]
        total = float(non_dc.sum())
        pos = i + window - 1
        if total <= 0.0:
            continue

        bins = np.array_split(non_dc, 3)
        low, mid, high = [float(part.sum() / total) if len(part) else 0.0 for part in bins]
        probs = non_dc / total
        entropy = -float(np.sum(probs * np.log(probs + 1e-12))) / float(np.log(len(probs))) if len(probs) > 1 else 0.0
        dominant_bin = int(np.argmax(non_dc)) + 1
        dominant_period = float((window - 1) / dominant_bin)

        out["power_low"][pos] = low
        out["power_mid"][pos] = mid
        out["power_high"][pos] = high
        out["spectral_entropy"][pos] = entropy
        out["dominant_period"][pos] = dominant_period
        out["high_freq_shock"][pos] = high / max(low + mid, 1e-12)
    return out


def add_atfnet_lite_features(
    df: pd.DataFrame,
    *,
    windows: tuple[int, ...] = SPECTRAL_WINDOWS,
    price_col: str = "close",
    prefix: str = "fft",
) -> pd.DataFrame:
    """Add rolling ATFNet-lite spectral features.

    The implementation is deliberately feature-only: no deep model, no fitted
    frequency attention, and no future rows. It captures the paper's practical
    frequency-domain idea in a form suitable for LightGBM/NCF shadow ablation.
    """
    out = df.copy()
    if price_col not in out.columns:
        return out
    close_arr = out[price_col].to_numpy(dtype=float)
    momentum_5d = pd.Series(close_arr, index=out.index).pct_change(5, fill_method=None)

    for window in windows:
        stats = _rolling_spectral_stats(close_arr, int(window))
        for name, values in stats.items():
            out[f"{prefix}_{window}d_{name}"] = values
        trend = _rolling_fft_trend(close_arr, window=int(window), n_components=3)
        trend_slope = pd.Series(trend, index=out.index).pct_change(5, fill_method=None)
        out[f"{prefix}_{window}d_time_freq_divergence"] = momentum_5d - trend_slope
    return out


def fourier_feature_columns(
    components: tuple[int, ...] = FOURIER_COMPONENTS,
    prefix: str = "fft",
) -> list[str]:
    """Return the ordered list of column names produced by add_fourier_features."""
    cols: list[str] = []
    for n_comp in components:
        cols.append(f"{prefix}_{n_comp}c_dev")
        cols.append(f"{prefix}_{n_comp}c_slope_5d")
    return cols


def atfnet_lite_feature_columns(
    windows: tuple[int, ...] = SPECTRAL_WINDOWS,
    prefix: str = "fft",
) -> list[str]:
    """Return ordered ATFNet-lite spectral feature column names."""
    cols: list[str] = []
    suffixes = (
        "power_low",
        "power_mid",
        "power_high",
        "spectral_entropy",
        "dominant_period",
        "high_freq_shock",
        "time_freq_divergence",
    )
    for window in windows:
        cols.extend(f"{prefix}_{window}d_{suffix}" for suffix in suffixes)
    return cols
