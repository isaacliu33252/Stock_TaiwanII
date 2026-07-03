"""Global correlated asset features for NCF models.

Inspired by stockpredictionai (Boris Banushev, 2019) which used global macro
indices as co-variates.  Taiwan semiconductor ETFs are heavily correlated with
Asia-Pacific equity markets and the JPY/USD risk-on/risk-off cycle.

Added assets
------------
^N225   Nikkei 225    — Japan market, shift=1 (closes after Taiwan 1:30pm)
^HSI    Hang Seng     — HK market, shift=1 (closes after Taiwan 1:30pm)
JPY=X   USD/JPY rate  — Risk-off proxy: JPY strengthens when risk appetite falls
^KS11   KOSPI         — Korea tech/semiconductor proxy (Samsung, SK Hynix)

Timing rule: all four close AFTER Taiwan's 1:30pm, so shift=1 (use previous
session's close before the Taiwan open at 9am).

Features produced
-----------------
n225_ret          — Nikkei 1-day return (previous session)
n225_5d_ret       — Nikkei 5-day momentum
n225_vs_ma20      — Nikkei / MA20 − 1 (trend deviation)
hsi_ret           — Hang Seng 1-day return (previous session)
hsi_5d_ret        — Hang Seng 5-day momentum
usdjpy_change     — USD/JPY 1-day change (+ = JPY weakens = risk-on)
usdjpy_vs_ma20    — USD/JPY / MA20 − 1 (JPY trend)
kospi_ret         — KOSPI 1-day return (Korea semiconductor proxy)
kospi_5d_ret      — KOSPI 5-day momentum

Interaction features (call interaction_global_feature_columns() to get names)
-----------------------
n225_x_twii_ret   — 日台聯動確認 (Asia co-movement)
usdjpy_x_vix      — 日圓避險 × VIX spike (risk-off double-confirmation)
hsi_x_n225_ret    — HK-Japan co-movement breadth
n225_x_soxx_ret   — 日美半導體 co-movement (supply-chain signal)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

GLOBAL_TICKERS: dict[str, str] = {
    "^N225": "nikkei225",
    "^HSI": "hang_seng",
    "JPY=X": "usdjpy",
    "^KS11": "kospi",
}

GLOBAL_FEATURES: list[str] = [
    "n225_ret",
    "n225_5d_ret",
    "n225_vs_ma20",
    "hsi_ret",
    "hsi_5d_ret",
    "usdjpy_change",
    "usdjpy_vs_ma20",
    "kospi_ret",
    "kospi_5d_ret",
]

GLOBAL_INTERACTION_FEATURES: list[str] = [
    "n225_x_twii_ret",
    "usdjpy_x_vix",
    "hsi_x_n225_ret",
    "n225_x_soxx_ret",
]


def global_feature_columns() -> list[str]:
    """Return ordered base feature names produced by add_global_features()."""
    return list(GLOBAL_FEATURES)


def global_interaction_feature_columns() -> list[str]:
    """Return interaction feature names (require both global and existing ext features)."""
    return list(GLOBAL_INTERACTION_FEATURES)


def _safe_align(series: pd.Series, idx: pd.DatetimeIndex, shift_n: int = 0) -> np.ndarray:
    """Reindex to Taiwan trading dates then optionally shift."""
    if series is None or series.empty:
        return np.full(len(idx), np.nan)
    s = series.reindex(idx, method="ffill")
    if shift_n:
        s = s.shift(shift_n)
    return s.to_numpy(dtype=float)


def add_global_features(
    ext: pd.DataFrame,
    idx: pd.DatetimeIndex,
    fetch_fn,
    start_ext: str,
    end_ext: str,
) -> pd.DataFrame:
    """Add global correlated asset features to the ext DataFrame.

    Parameters
    ----------
    ext : existing external features DataFrame (modified in-place).
    idx : Taiwan trading date index (same as main_df.index).
    fetch_fn : callable(ticker, start, end) -> pd.Series of Close prices.
               Usually the _fetch_yf wrapper from the NCF script.
    start_ext, end_ext : date strings for the download window.

    Returns
    -------
    ext (same object, modified in-place).
    """
    # ── Nikkei 225 (shift=1) ──────────────────────────────────────────────
    try:
        n225 = fetch_fn("^N225", start_ext, end_ext)
        if not n225.empty:
            n225_ma20 = n225.rolling(20).mean()
            ext["n225_ret"] = _safe_align(n225.pct_change(), idx, shift_n=1)
            ext["n225_5d_ret"] = _safe_align(n225.pct_change(5), idx, shift_n=1)
            ext["n225_vs_ma20"] = _safe_align(n225 / n225_ma20 - 1.0, idx, shift_n=1)
        else:
            for col in ["n225_ret", "n225_5d_ret", "n225_vs_ma20"]:
                ext[col] = np.nan
    except Exception as e:
        print(f"  [GlobalFeat] ^N225 error: {e}")
        for col in ["n225_ret", "n225_5d_ret", "n225_vs_ma20"]:
            ext[col] = np.nan

    # ── Hang Seng (shift=1) ───────────────────────────────────────────────
    try:
        hsi = fetch_fn("^HSI", start_ext, end_ext)
        if not hsi.empty:
            ext["hsi_ret"] = _safe_align(hsi.pct_change(), idx, shift_n=1)
            ext["hsi_5d_ret"] = _safe_align(hsi.pct_change(5), idx, shift_n=1)
        else:
            for col in ["hsi_ret", "hsi_5d_ret"]:
                ext[col] = np.nan
    except Exception as e:
        print(f"  [GlobalFeat] ^HSI error: {e}")
        for col in ["hsi_ret", "hsi_5d_ret"]:
            ext[col] = np.nan

    # ── USD/JPY (shift=1) — higher = JPY weakens = risk-on ───────────────
    try:
        usdjpy = fetch_fn("JPY=X", start_ext, end_ext)
        if not usdjpy.empty:
            usdjpy_ma20 = usdjpy.rolling(20).mean()
            ext["usdjpy_change"] = _safe_align(usdjpy.pct_change(), idx, shift_n=1)
            ext["usdjpy_vs_ma20"] = _safe_align(usdjpy / usdjpy_ma20 - 1.0, idx, shift_n=1)
        else:
            for col in ["usdjpy_change", "usdjpy_vs_ma20"]:
                ext[col] = np.nan
    except Exception as e:
        print(f"  [GlobalFeat] JPY=X error: {e}")
        for col in ["usdjpy_change", "usdjpy_vs_ma20"]:
            ext[col] = np.nan

    # ── KOSPI (shift=1) ───────────────────────────────────────────────────
    try:
        kospi = fetch_fn("^KS11", start_ext, end_ext)
        if not kospi.empty:
            ext["kospi_ret"] = _safe_align(kospi.pct_change(), idx, shift_n=1)
            ext["kospi_5d_ret"] = _safe_align(kospi.pct_change(5), idx, shift_n=1)
        else:
            for col in ["kospi_ret", "kospi_5d_ret"]:
                ext[col] = np.nan
    except Exception as e:
        print(f"  [GlobalFeat] ^KS11 error: {e}")
        for col in ["kospi_ret", "kospi_5d_ret"]:
            ext[col] = np.nan

    # ── Interaction features ───────────────────────────────────────────────
    # These require some existing ext columns (twii_ret, vix, etc.).
    # Fill with NaN if dependency columns are missing.
    n225_arr = ext.get("n225_ret", pd.Series(np.nan, index=idx))
    twii_arr = ext.get("twii_ret", pd.Series(np.nan, index=idx))
    vix_arr = ext.get("vix", pd.Series(np.nan, index=idx))
    hsi_arr = ext.get("hsi_ret", pd.Series(np.nan, index=idx))
    soxx_arr = ext.get("us_soxx_ret", pd.Series(np.nan, index=idx))
    usdjpy_arr = ext.get("usdjpy_change", pd.Series(np.nan, index=idx))

    def _to_arr(x):
        if isinstance(x, pd.Series):
            return x.to_numpy(dtype=float)
        return np.asarray(x, dtype=float)

    ext["n225_x_twii_ret"] = _to_arr(n225_arr) * _to_arr(twii_arr)
    ext["usdjpy_x_vix"] = _to_arr(usdjpy_arr) * _to_arr(vix_arr)
    ext["hsi_x_n225_ret"] = _to_arr(hsi_arr) * _to_arr(n225_arr)
    ext["n225_x_soxx_ret"] = _to_arr(n225_arr) * _to_arr(soxx_arr)

    return ext
