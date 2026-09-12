from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.regime_switching_volatility_shadow import (
    build_regime_switching_volatility_shadow,
    coefficient_regime_forecast,
    detect_variance_change_points,
    jump_variation_from_close,
    latest_regime_switching_volatility_snapshot,
    realized_kurtosis_from_close,
    regime_feature_frame,
)


def _synthetic_ohlc(n: int = 900, seed: int = 36) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-02", periods=n)
    vol = np.r_[np.full(n // 3, 0.006), np.full(n // 3, 0.018), np.full(n - 2 * (n // 3), 0.009)]
    returns = rng.normal(0.0002, vol)
    close = 100.0 * np.cumprod(1.0 + returns)
    open_ = close * (1.0 + rng.normal(0.0, 0.0015, size=n))
    intraday_range = np.abs(rng.normal(vol, vol * 0.25)) + 1e-4
    high = np.maximum(open_, close) * (1.0 + intraday_range)
    low = np.minimum(open_, close) * (1.0 - intraday_range)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=dates)


def test_tail_and_jump_features_are_aligned_and_non_negative() -> None:
    ohlc = _synthetic_ohlc()
    kurt = realized_kurtosis_from_close(ohlc["close"])
    jump = jump_variation_from_close(ohlc["close"])
    assert kurt.index.equals(ohlc.index)
    assert jump.index.equals(ohlc.index)
    assert (jump.dropna() >= 0.0).all()
    assert kurt.dropna().iloc[-1] > 0.0


def test_regime_feature_frame_includes_optional_vix_terms() -> None:
    ohlc = _synthetic_ohlc()
    vix = pd.Series(np.linspace(12.0, 25.0, len(ohlc)), index=ohlc.index)
    extras = pd.DataFrame({"txo_pcr_volume_z20": np.linspace(-1.0, 1.0, len(ohlc))}, index=ohlc.index)
    frame = regime_feature_frame(ohlc, vix=vix, extra_features=extras)
    expected = {
        "gk_variance",
        "log_rv_d",
        "log_rv_w",
        "log_rv_m",
        "realized_kurtosis",
        "jump_variation",
        "log_vix_d",
        "log_vix_w",
        "log_vix_m",
        "extra_txo_pcr_volume_z20",
    }
    assert expected.issubset(frame.columns)


def test_detect_variance_change_points_finds_synthetic_shift() -> None:
    idx = pd.bdate_range("2020-01-02", periods=180)
    series = pd.Series(np.r_[np.full(80, 0.0001), np.full(100, 0.002)], index=idx)
    series = series + np.linspace(0.0, 0.00001, len(series))
    points = detect_variance_change_points(series, window=20, log_ratio_threshold=0.5)
    assert points
    assert any(60 <= point <= 100 for point in points)


def test_coefficient_regime_forecast_shape_and_probabilities() -> None:
    ohlc = _synthetic_ohlc()
    extras = pd.DataFrame({"vix_like_z": np.sin(np.arange(len(ohlc)) / 20.0)}, index=ohlc.index)
    frame = coefficient_regime_forecast(
        ohlc,
        horizon=5,
        rolling_window=252,
        n_regimes=2,
        extra_features=extras,
    )
    assert "regime_switch_forecast_vol_h5" in frame.columns
    assert "soft_vol_regime_prob_0_h5" in frame.columns
    assert "soft_vol_regime_prob_1_h5" in frame.columns
    tail = frame.dropna(subset=["regime_switch_forecast_vol_h5"]).tail(50)
    assert not tail.empty
    assert (tail["regime_switch_forecast_vol_h5"] > 0.0).all()
    probs = tail[["soft_vol_regime_prob_0_h5", "soft_vol_regime_prob_1_h5"]].sum(axis=1)
    assert np.allclose(probs.to_numpy(), 1.0)


def test_coefficient_regime_forecast_no_lookahead() -> None:
    ohlc = _synthetic_ohlc()
    full = coefficient_regime_forecast(ohlc, horizon=5, rolling_window=252, n_regimes=2, refit_every=21)
    cutoff = 700
    truncated = coefficient_regime_forecast(
        ohlc.iloc[: cutoff + 1],
        horizon=5,
        rolling_window=252,
        n_regimes=2,
        refit_every=21,
    )
    check_idx = cutoff - 5
    col = "regime_switch_forecast_vol_h5"
    if pd.notna(full[col].iloc[check_idx]) and pd.notna(truncated[col].iloc[check_idx]):
        assert full[col].iloc[check_idx] == pytest.approx(truncated[col].iloc[check_idx])


def test_shadow_snapshot_contract_has_no_weight_or_regime_outputs() -> None:
    ohlc = _synthetic_ohlc()
    frame = build_regime_switching_volatility_shadow(ohlc, horizons=(5,), rolling_window=252)
    assert "policy" in frame.columns
    assert set(frame["policy"].unique()) == {"shadow_only_no_weight_change"}
    forbidden = {"target_weights", "target_shares", "execution_regime", "base_regime"}
    assert forbidden.isdisjoint(frame.columns)

    snapshot = latest_regime_switching_volatility_snapshot(frame)
    assert snapshot["status"] == "available"
    assert snapshot["policy"] == "shadow_only_no_weight_change"
    assert snapshot["outputs_target_weights"] is False
    assert snapshot["outputs_execution_regime"] is False
    assert "5" in snapshot["horizons"]


def test_latest_snapshot_empty_frame() -> None:
    snapshot = latest_regime_switching_volatility_snapshot(pd.DataFrame())
    assert snapshot["status"] == "unavailable"
