from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.network_volatility_forecast_shadow import (
    build_gk_variance_panel,
    build_gnhar_design,
    build_multi_horizon_gnhar_forecast,
    gnhar_rv_walkforward_forecast,
    latest_gnhar_forecast_snapshot,
)


def _synthetic_ohlcv(tickers: tuple[str, ...], n: int = 900, seed: int = 11) -> pd.DataFrame:
    """Multi-ticker OHLCV with a shared market factor so neighbours carry real signal."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-02", periods=n)
    market_vol = np.abs(rng.normal(0.006, 0.0015, size=n))
    frames = []
    for k, ticker in enumerate(tickers):
        idio_vol = np.abs(rng.normal(0.003, 0.001, size=n))
        returns = rng.normal(0.0002, 0.006, size=n) * (1.0 + 0.3 * k)
        close = 100.0 * np.cumprod(1.0 + returns)
        open_ = close * (1.0 + rng.normal(0.0, 0.001, size=n))
        intraday_range = market_vol + idio_vol
        high = np.maximum(open_, close) * (1.0 + intraday_range)
        low = np.minimum(open_, close) * (1.0 - intraday_range)
        frames.append(
            pd.DataFrame(
                {"dt": dates, "ticker": ticker, "open": open_, "high": high, "low": low, "close": close}
            )
        )
    return pd.concat(frames, axis=0).reset_index(drop=True)


TICKERS = ("A.TW", "B.TW", "C.TW", "D.TW")


def test_build_gk_variance_panel_shape_and_ffill():
    ohlcv = _synthetic_ohlcv(TICKERS)
    panel = build_gk_variance_panel(ohlcv, tickers=TICKERS)
    assert list(panel.columns) == list(TICKERS)
    assert (panel > 0).all().all()
    assert panel.isna().sum().sum() == 0


def test_build_gk_variance_panel_rejects_missing_columns():
    with pytest.raises(ValueError):
        build_gk_variance_panel(pd.DataFrame({"dt": [], "ticker": []}), tickers=TICKERS)


def test_build_gnhar_design_columns_follow_network_order():
    ohlcv = _synthetic_ohlcv(TICKERS)
    panel = build_gk_variance_panel(ohlcv, tickers=TICKERS)

    design_101 = build_gnhar_design(panel, network_order=(1, 0, 1))
    assert {"net_d", "net_m"}.issubset(design_101.columns)
    assert "net_w" not in design_101.columns

    design_000 = build_gnhar_design(panel, network_order=(0, 0, 0))
    assert not {"net_d", "net_w", "net_m"} & set(design_000.columns)

    assert set(design_101["ticker"].unique()) == set(TICKERS)
    assert len(design_101) == len(panel) * len(TICKERS)


def test_build_gnhar_design_requires_multiple_tickers():
    ohlcv = _synthetic_ohlcv(("SOLO.TW",))
    panel = build_gk_variance_panel(ohlcv, tickers=("SOLO.TW",))
    with pytest.raises(ValueError):
        build_gnhar_design(panel)


def test_gnhar_rv_forecast_requires_target_in_panel():
    ohlcv = _synthetic_ohlcv(TICKERS)
    panel = build_gk_variance_panel(ohlcv, tickers=TICKERS)
    with pytest.raises(ValueError):
        gnhar_rv_walkforward_forecast(panel, target="MISSING.TW", horizon=5)


def test_gnhar_rv_forecast_nan_before_warmup_and_populated_after():
    ohlcv = _synthetic_ohlcv(TICKERS)
    panel = build_gk_variance_panel(ohlcv, tickers=TICKERS)
    forecast = gnhar_rv_walkforward_forecast(panel, target="A.TW", horizon=5, rolling_window=252)
    assert forecast.iloc[:100].isna().all()
    assert forecast.iloc[-200:].notna().all()
    assert (forecast.dropna() > 0).all()


def test_gnhar_rv_forecast_no_lookahead():
    """Truncating history after date t must not change the forecast made at t."""
    ohlcv = _synthetic_ohlcv(TICKERS)
    panel = build_gk_variance_panel(ohlcv, tickers=TICKERS)
    full_forecast = gnhar_rv_walkforward_forecast(
        panel, target="A.TW", horizon=5, rolling_window=252, refit_every=21
    )

    cutoff = 700
    truncated_panel = panel.iloc[: cutoff + 1]
    truncated_forecast = gnhar_rv_walkforward_forecast(
        truncated_panel, target="A.TW", horizon=5, rolling_window=252, refit_every=21
    )

    check_idx = cutoff - 5  # last index where the truncated series still has a full horizon of data
    if pd.notna(full_forecast.iloc[check_idx]) and pd.notna(truncated_forecast.iloc[check_idx]):
        assert full_forecast.iloc[check_idx] == pytest.approx(truncated_forecast.iloc[check_idx])


def test_build_multi_horizon_gnhar_forecast_shape_and_snapshot():
    ohlcv = _synthetic_ohlcv(TICKERS)
    frame = build_multi_horizon_gnhar_forecast(
        ohlcv, target="A.TW", tickers=TICKERS, horizons=(5, 10), rolling_window=252
    )
    for h in (5, 10):
        assert f"gnhar_forecast_vol_h{h}" in frame.columns

    snapshot = latest_gnhar_forecast_snapshot(frame)
    assert snapshot["status"] == "available"
    for h in (5, 10):
        entry = snapshot["horizons"][str(h)]
        assert entry["forecast_variance"] is None or entry["forecast_variance"] > 0


def test_latest_gnhar_forecast_snapshot_empty_frame():
    snapshot = latest_gnhar_forecast_snapshot(pd.DataFrame())
    assert snapshot["status"] == "unavailable"
