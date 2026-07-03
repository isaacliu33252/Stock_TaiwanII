"""Tests for group_a_plus.integrations.fourier_features."""
import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.fourier_features import (
    FOURIER_COMPONENTS,
    FOURIER_WINDOW,
    SPECTRAL_WINDOWS,
    add_atfnet_lite_features,
    add_fourier_features,
    atfnet_lite_feature_columns,
    fourier_feature_columns,
    _rolling_fft_trend,
)


def _make_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV-like DataFrame with a simple trend + noise."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    trend = np.linspace(100, 140, n)
    noise = rng.normal(0, 1.5, n)
    close = trend + noise
    return pd.DataFrame(
        {
            "open": close - rng.uniform(0, 0.5, n),
            "high": close + rng.uniform(0, 1.0, n),
            "low": close - rng.uniform(0, 1.0, n),
            "close": close,
            "volume": rng.integers(1_000, 10_000, n),
        },
        index=dates,
    )


class TestFourierFeatureColumns:
    def test_returns_list(self):
        cols = fourier_feature_columns()
        assert isinstance(cols, list)
        assert len(cols) > 0

    def test_expected_names(self):
        cols = fourier_feature_columns()
        for n in FOURIER_COMPONENTS:
            assert f"fft_{n}c_dev" in cols
            assert f"fft_{n}c_slope_5d" in cols

    def test_length_is_2x_components(self):
        cols = fourier_feature_columns()
        assert len(cols) == 2 * len(FOURIER_COMPONENTS)

    def test_custom_prefix(self):
        cols = fourier_feature_columns(prefix="myprefix")
        assert all(c.startswith("myprefix_") for c in cols)

    def test_atfnet_lite_columns(self):
        cols = atfnet_lite_feature_columns()
        for window in SPECTRAL_WINDOWS:
            assert f"fft_{window}d_power_low" in cols
            assert f"fft_{window}d_spectral_entropy" in cols
            assert f"fft_{window}d_time_freq_divergence" in cols


class TestAddFourierFeatures:
    def test_adds_expected_columns(self):
        df = _make_df()
        result = add_fourier_features(df)
        for col in fourier_feature_columns():
            assert col in result.columns, f"Missing column: {col}"

    def test_original_columns_preserved(self):
        df = _make_df()
        result = add_fourier_features(df)
        for col in df.columns:
            assert col in result.columns

    def test_nan_in_first_window_rows(self):
        df = _make_df(n=200)
        result = add_fourier_features(df, window=FOURIER_WINDOW)
        for col in fourier_feature_columns():
            n_nan = result[col].isna().sum()
            assert n_nan >= FOURIER_WINDOW - 1, (
                f"{col}: expected >={FOURIER_WINDOW - 1} NaNs, got {n_nan}"
            )

    def test_no_nan_after_window(self):
        df = _make_df(n=200)
        result = add_fourier_features(df, window=FOURIER_WINDOW)
        tail = result.iloc[FOURIER_WINDOW + 10:]
        for col in fourier_feature_columns():
            assert tail[col].notna().all(), f"{col} has NaN after warm-up period"

    def test_dev_feature_is_scale_invariant(self):
        """Multiplying prices by a constant should not change dev features."""
        df = _make_df(n=200)
        df2 = df.copy()
        df2["close"] = df2["close"] * 10

        r1 = add_fourier_features(df)
        r2 = add_fourier_features(df2)

        for n in FOURIER_COMPONENTS:
            col = f"fft_{n}c_dev"
            diff = (r1[col] - r2[col]).abs().dropna()
            assert diff.max() < 1e-6, f"{col} is not scale-invariant"

    def test_missing_close_column_graceful(self):
        df = pd.DataFrame({"open": [1, 2, 3]})
        result = add_fourier_features(df)
        assert list(result.columns) == ["open"]

    def test_short_series_returns_all_nan(self):
        df = _make_df(n=30)
        result = add_fourier_features(df, window=FOURIER_WINDOW)
        for col in fourier_feature_columns():
            assert result[col].isna().all(), f"{col} should be all-NaN for short series"


class TestAtfnetLiteFeatures:
    def test_adds_expected_columns(self):
        df = _make_df(n=160)
        result = add_atfnet_lite_features(df, windows=(16, 32))
        for col in atfnet_lite_feature_columns(windows=(16, 32)):
            assert col in result.columns

    def test_power_ratios_are_bounded_after_warmup(self):
        df = _make_df(n=120)
        result = add_atfnet_lite_features(df, windows=(16,))
        tail = result.iloc[20:].dropna(subset=["fft_16d_power_low"])
        assert not tail.empty
        for col in ["fft_16d_power_low", "fft_16d_power_mid", "fft_16d_power_high", "fft_16d_spectral_entropy"]:
            assert ((tail[col] >= 0.0) & (tail[col] <= 1.0)).all(), col

    def test_high_freq_shock_is_finite_after_warmup(self):
        df = _make_df(n=120)
        result = add_atfnet_lite_features(df, windows=(16,))
        tail = result.iloc[20:].dropna(subset=["fft_16d_high_freq_shock"])
        assert np.isfinite(tail["fft_16d_high_freq_shock"]).all()

    def test_missing_close_column_graceful(self):
        df = pd.DataFrame({"open": [1, 2, 3]})
        result = add_atfnet_lite_features(df, windows=(16,))
        assert list(result.columns) == ["open"]


class TestRollingFftTrend:
    def test_output_length_matches_input(self):
        arr = np.linspace(100, 200, 300)
        result = _rolling_fft_trend(arr, window=120, n_components=3)
        assert len(result) == 300

    def test_first_window_minus_one_are_nan(self):
        arr = np.linspace(100, 200, 300)
        result = _rolling_fft_trend(arr, window=120, n_components=3)
        assert np.all(np.isnan(result[:119]))

    def test_values_after_window_are_finite(self):
        arr = np.linspace(100, 200, 300)
        result = _rolling_fft_trend(arr, window=120, n_components=3)
        assert np.all(np.isfinite(result[119:]))

    def test_more_components_gives_closer_fit(self):
        """More Fourier components should give a trend closer to the original price."""
        n = 200
        rng = np.random.default_rng(0)
        arr = np.linspace(100, 140, n) + rng.normal(0, 0.5, n)
        trend_3 = _rolling_fft_trend(arr, window=120, n_components=3)
        trend_9 = _rolling_fft_trend(arr, window=120, n_components=9)
        # 9-component trend should fit closer to actuals than 3-component
        valid = slice(119, n)
        mae_3 = np.abs(trend_3[valid] - arr[valid]).mean()
        mae_9 = np.abs(trend_9[valid] - arr[valid]).mean()
        assert mae_9 <= mae_3, f"9-component MAE ({mae_9:.4f}) should be <= 3-component MAE ({mae_3:.4f})"

    def test_short_array_returns_all_nan(self):
        arr = np.linspace(100, 200, 50)
        result = _rolling_fft_trend(arr, window=120, n_components=3)
        assert np.all(np.isnan(result))
