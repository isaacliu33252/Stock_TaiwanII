"""Tests for group_a_plus.integrations.global_features."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.global_features import (
    GLOBAL_FEATURES,
    GLOBAL_INTERACTION_FEATURES,
    GLOBAL_TICKERS,
    add_global_features,
    global_feature_columns,
    global_interaction_feature_columns,
)


def _make_idx(n: int = 120) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-02", periods=n, freq="B")


def _make_ext(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Minimal ext DataFrame with prerequisite interaction-source columns."""
    rng = np.random.default_rng(7)
    n = len(idx)
    return pd.DataFrame(
        {
            "twii_ret": rng.normal(0, 0.01, n),
            "vix": rng.uniform(12, 30, n),
            "us_soxx_ret": rng.normal(0, 0.015, n),
        },
        index=idx,
    )


def _make_close_series(idx: pd.DatetimeIndex, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    prices = np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))) * 1000
    return pd.Series(prices, index=idx)


def _stub_fetch(close_map: dict):
    """Return a fetch_fn that returns pre-built series keyed by ticker."""
    def _fetch(ticker: str, start: str, end: str) -> pd.Series:
        return close_map.get(ticker, pd.Series(dtype=float))
    return _fetch


# ── Column API ────────────────────────────────────────────────────────────────

class TestGlobalFeatureColumns:
    def test_returns_list(self):
        assert isinstance(global_feature_columns(), list)
        assert len(global_feature_columns()) > 0

    def test_interaction_returns_list(self):
        assert isinstance(global_interaction_feature_columns(), list)
        assert len(global_interaction_feature_columns()) > 0

    def test_base_columns_match_module_constant(self):
        assert global_feature_columns() == GLOBAL_FEATURES

    def test_interaction_columns_match_module_constant(self):
        assert global_interaction_feature_columns() == GLOBAL_INTERACTION_FEATURES

    def test_tickers_dict_has_four_entries(self):
        assert len(GLOBAL_TICKERS) == 4

    def test_tickers_include_n225_hsi_jpy_ks11(self):
        keys = set(GLOBAL_TICKERS.keys())
        assert "^N225" in keys
        assert "^HSI" in keys
        assert "JPY=X" in keys
        assert "^KS11" in keys

    def test_no_duplicates_in_feature_lists(self):
        cols = global_feature_columns()
        assert len(cols) == len(set(cols)), "Duplicate column names in GLOBAL_FEATURES"
        icols = global_interaction_feature_columns()
        assert len(icols) == len(set(icols)), "Duplicate column names in GLOBAL_INTERACTION_FEATURES"


# ── add_global_features ───────────────────────────────────────────────────────

class TestAddGlobalFeatures:
    def test_adds_all_base_columns(self):
        idx = _make_idx()
        ext = _make_ext(idx)
        fetch = _stub_fetch({
            "^N225": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 1),
            "^HSI": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 2),
            "JPY=X": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 3),
            "^KS11": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 4),
        })
        result = add_global_features(ext, idx, fetch, "2023-10-01", "2024-07-01")
        for col in global_feature_columns():
            assert col in result.columns, f"Missing column: {col}"

    def test_adds_all_interaction_columns(self):
        idx = _make_idx()
        ext = _make_ext(idx)
        fetch = _stub_fetch({
            "^N225": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 1),
            "^HSI": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 2),
            "JPY=X": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 3),
            "^KS11": _make_close_series(pd.date_range("2023-10-01", periods=len(idx) + 95, freq="B"), 4),
        })
        result = add_global_features(ext, idx, fetch, "2023-10-01", "2024-07-01")
        for col in global_interaction_feature_columns():
            assert col in result.columns, f"Missing interaction column: {col}"

    def test_original_columns_preserved(self):
        idx = _make_idx()
        ext = _make_ext(idx)
        orig_cols = list(ext.columns)
        fetch = _stub_fetch({})  # empty — graceful fallback
        result = add_global_features(ext, idx, fetch, "2023-10-01", "2024-07-01")
        for col in orig_cols:
            assert col in result.columns, f"Original column {col} was removed"

    def test_returns_same_object(self):
        """add_global_features modifies in-place and returns the same DataFrame."""
        idx = _make_idx()
        ext = _make_ext(idx)
        result = add_global_features(ext, idx, _stub_fetch({}), "2023-10-01", "2024-07-01")
        assert result is ext

    def test_empty_fetch_graceful(self):
        """When all tickers return empty series, columns exist but are NaN."""
        idx = _make_idx()
        ext = _make_ext(idx)
        result = add_global_features(ext, idx, _stub_fetch({}), "2023-10-01", "2024-07-01")
        for col in global_feature_columns():
            assert col in result.columns
            assert result[col].isna().all(), f"{col} should be all-NaN when fetch fails"

    def test_fetch_error_graceful(self):
        """If fetch raises, column falls back to NaN without crashing."""
        def _bad_fetch(ticker, start, end):
            if ticker == "^N225":
                raise RuntimeError("simulated network error")
            return pd.Series(dtype=float)

        idx = _make_idx()
        ext = _make_ext(idx)
        result = add_global_features(ext, idx, _bad_fetch, "2023-10-01", "2024-07-01")
        for col in ["n225_ret", "n225_5d_ret", "n225_vs_ma20"]:
            assert col in result.columns
            assert result[col].isna().all()

    def test_shift1_means_no_today_data_in_first_row(self):
        """shift=1 means first row should be NaN (no prior day available in index range)."""
        idx = _make_idx(n=60)
        ext = _make_ext(idx)
        # Provide data only for the exact idx range (so shift(1) gives NaN on first row)
        n225_data = _make_close_series(idx, seed=1)
        fetch = _stub_fetch({"^N225": n225_data, "^HSI": n225_data, "JPY=X": n225_data, "^KS11": n225_data})
        result = add_global_features(ext, idx, fetch, idx[0].strftime("%Y-%m-%d"), idx[-1].strftime("%Y-%m-%d"))
        # After shift(1), first row should be NaN
        assert pd.isna(result["n225_ret"].iloc[0])

    def test_n225_vs_ma20_centered_near_zero(self):
        """For a flat price series, vs_ma20 should be close to 0."""
        idx = _make_idx(n=80)
        ext = _make_ext(idx)
        wide_idx = pd.date_range("2023-07-01", periods=len(idx) + 120, freq="B")
        # Constant price of 30000 — deviation from MA20 should be ~0
        flat = pd.Series(30000.0, index=wide_idx)
        fetch = _stub_fetch({"^N225": flat})
        result = add_global_features(ext, idx, fetch, "2023-07-01", "2024-08-01")
        valid = result["n225_vs_ma20"].dropna()
        assert (valid.abs() < 1e-8).all(), "Flat N225 price should give n225_vs_ma20 ≈ 0"

    def test_output_length_matches_idx(self):
        idx = _make_idx(n=150)
        ext = _make_ext(idx)
        wide = pd.date_range("2023-07-01", periods=len(idx) + 120, freq="B")
        series = _make_close_series(wide, seed=99)
        fetch = _stub_fetch({"^N225": series, "^HSI": series, "JPY=X": series, "^KS11": series})
        result = add_global_features(ext, idx, fetch, "2023-07-01", "2024-12-01")
        for col in global_feature_columns():
            assert len(result[col]) == len(idx), f"{col}: expected {len(idx)} rows"

    def test_interaction_n225_x_twii_is_product(self):
        """n225_x_twii_ret = n225_ret * twii_ret."""
        idx = _make_idx(n=80)
        ext = _make_ext(idx)
        wide = pd.date_range("2023-07-01", periods=len(idx) + 120, freq="B")
        series = _make_close_series(wide, seed=5)
        fetch = _stub_fetch({"^N225": series, "^HSI": series, "JPY=X": series, "^KS11": series})
        result = add_global_features(ext, idx, fetch, "2023-07-01", "2024-12-01")
        expected = result["n225_ret"] * result["twii_ret"]
        pd.testing.assert_series_equal(
            result["n225_x_twii_ret"].dropna(),
            expected.dropna(),
            check_names=False,
            rtol=1e-8,
        )

    def test_interaction_usdjpy_x_vix_uses_existing_vix(self):
        """usdjpy_x_vix = usdjpy_change * vix (where vix comes from pre-existing ext column)."""
        idx = _make_idx(n=80)
        ext = _make_ext(idx)
        wide = pd.date_range("2023-07-01", periods=len(idx) + 120, freq="B")
        series = _make_close_series(wide, seed=6)
        fetch = _stub_fetch({"^N225": series, "^HSI": series, "JPY=X": series, "^KS11": series})
        result = add_global_features(ext, idx, fetch, "2023-07-01", "2024-12-01")
        expected = result["usdjpy_change"] * result["vix"]
        pd.testing.assert_series_equal(
            result["usdjpy_x_vix"].dropna(),
            expected.dropna(),
            check_names=False,
            rtol=1e-8,
        )
