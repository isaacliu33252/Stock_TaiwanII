from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_2601_07131_flow_normalization import _ic_and_auc, build_variants


def test_ic_and_auc_perfect_predictor_scores_near_one() -> None:
    idx = pd.date_range("2020-01-01", periods=200, freq="D")
    feature = pd.Series(np.arange(200), index=idx, dtype=float)
    forward_return = pd.Series(np.arange(200), index=idx, dtype=float)  # perfectly monotonic

    result = _ic_and_auc(feature, forward_return)

    assert result["n"] == 200
    assert result["ic"] > 0.99
    assert result["auc"] > 0.99


def test_ic_and_auc_independent_series_scores_near_chance() -> None:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-01", periods=2000, freq="D")
    feature = pd.Series(rng.normal(size=2000), index=idx)
    forward_return = pd.Series(rng.normal(size=2000), index=idx)

    result = _ic_and_auc(feature, forward_return)

    assert abs(result["ic"]) < 0.1
    assert abs(result["auc"] - 0.5) < 0.1


def test_ic_and_auc_returns_none_below_min_sample() -> None:
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    feature = pd.Series(np.arange(10), index=idx, dtype=float)
    forward_return = pd.Series(np.arange(10), index=idx, dtype=float)

    result = _ic_and_auc(feature, forward_return)

    assert result["ic"] is None
    assert result["auc"] is None
    assert result["n"] == 10


def test_build_variants_price_scaled_matches_production_ncf_formula() -> None:
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    panel = pd.DataFrame(
        {
            "close": [100.0, 100.0, 100.0, 100.0, 100.0],
            "volume": [1_000_000.0] * 5,
            "foreign_net_buy": [500_000.0, -500_000.0, 0.0, 1_000_000.0, 250_000.0],
            "institutional_total_net_buy": [0.0] * 5,
        },
        index=idx,
    )

    variants = build_variants(panel)

    # scripts/misc/ncf_0050.py: inst_foreign_net = foreign_net_buy / (close * 1e6)
    expected = panel["foreign_net_buy"] / (panel["close"] * 1e6)
    pd.testing.assert_series_equal(variants["price_scaled_foreign_net_buy"], expected, check_names=False)

    # Matched-filter variant: fraction of the day's own trading volume.
    expected_vol = panel["foreign_net_buy"] / panel["volume"]
    pd.testing.assert_series_equal(variants["volume_normalized_foreign_net_buy"], expected_vol, check_names=False)


def test_build_variants_raw_is_unnormalized_passthrough() -> None:
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    panel = pd.DataFrame(
        {
            "close": [50.0, 60.0, 70.0],
            "volume": [10.0, 20.0, 30.0],
            "foreign_net_buy": [1.0, 2.0, 3.0],
            "institutional_total_net_buy": [4.0, 5.0, 6.0],
        },
        index=idx,
    )

    variants = build_variants(panel)

    pd.testing.assert_series_equal(variants["raw_foreign_net_buy"], panel["foreign_net_buy"], check_names=False)
