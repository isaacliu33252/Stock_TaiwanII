from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.volatility_forecast import (
    build_multi_horizon_forecast,
    garman_klass_variance,
    har_rv_walkforward_forecast,
    latest_forecast_snapshot,
    naive_persistence_forecast,
)


def _synthetic_ohlc(n: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-02", periods=n)
    returns = rng.normal(0.0003, 0.01, size=n)
    close = 100.0 * np.cumprod(1.0 + returns)
    open_ = close * (1.0 + rng.normal(0.0, 0.002, size=n))
    intraday_range = np.abs(rng.normal(0.006, 0.003, size=n)) + 1e-4
    high = np.maximum(open_, close) * (1.0 + intraday_range)
    low = np.minimum(open_, close) * (1.0 - intraday_range)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=dates)


def test_garman_klass_variance_positive_and_aligned():
    ohlc = _synthetic_ohlc()
    gk = garman_klass_variance(ohlc)
    assert (gk > 0).all()
    assert gk.index.equals(ohlc.index)


def test_har_rv_forecast_nan_before_warmup_and_populated_after():
    ohlc = _synthetic_ohlc()
    gk = garman_klass_variance(ohlc)
    forecast = har_rv_walkforward_forecast(gk, horizon=5, rolling_window=252)
    assert forecast.iloc[:100].isna().all()
    assert forecast.iloc[-200:].notna().all()
    assert (forecast.dropna() > 0).all()


def test_har_rv_forecast_no_lookahead():
    """Truncating history after date t must not change the forecast made at t."""
    ohlc = _synthetic_ohlc()
    gk = garman_klass_variance(ohlc)
    full_forecast = har_rv_walkforward_forecast(gk, horizon=5, rolling_window=252, refit_every=21)

    cutoff = 700
    truncated_gk = gk.iloc[: cutoff + 1]
    truncated_forecast = har_rv_walkforward_forecast(truncated_gk, horizon=5, rolling_window=252, refit_every=21)

    check_idx = cutoff - 5  # last index where the truncated series still has a full horizon of data
    if pd.notna(full_forecast.iloc[check_idx]) and pd.notna(truncated_forecast.iloc[check_idx]):
        assert full_forecast.iloc[check_idx] == pytest.approx(truncated_forecast.iloc[check_idx])


def test_naive_persistence_forecast_matches_rolling_mean():
    ohlc = _synthetic_ohlc()
    gk = garman_klass_variance(ohlc)
    naive = naive_persistence_forecast(gk, horizon=10)
    expected = gk.rolling(22, min_periods=5).mean()
    pd.testing.assert_series_equal(naive, expected.rename(naive.name))


def test_build_multi_horizon_forecast_shape_and_snapshot():
    ohlc = _synthetic_ohlc()
    frame = build_multi_horizon_forecast(ohlc, rolling_window=252)
    for h in (5, 10, 20):
        assert f"forecast_vol_h{h}" in frame.columns
        assert f"forecast_vol_h{h}_percentile" in frame.columns

    snapshot = latest_forecast_snapshot(frame)
    assert snapshot["status"] == "available"
    for h in (5, 10, 20):
        entry = snapshot["horizons"][str(h)]
        assert entry["forecast_variance"] > 0
        assert 0.0 <= entry["percentile_vs_252d"] <= 1.0


def test_latest_forecast_snapshot_empty_frame():
    snapshot = latest_forecast_snapshot(pd.DataFrame())
    assert snapshot["status"] == "unavailable"
