from __future__ import annotations

import math

import pandas as pd

from group_a_plus.integrations.factor_lens import (
    event_study_forward_returns,
    make_single_asset_factor_data,
    mean_return_by_quantile,
    quantile_spread,
    rank_autocorrelation,
    rolling_time_series_ic,
    time_series_information_coefficient,
)


def test_single_asset_factor_data_and_ic_are_positive_for_aligned_factor() -> None:
    dates = pd.date_range("2026-01-01", periods=12, freq="D")
    factor = pd.Series(range(12), index=dates, dtype=float)
    price = pd.Series([100 + i * i for i in range(12)], index=dates, dtype=float)

    data = make_single_asset_factor_data(
        factor,
        price,
        asset="0050.TW",
        horizons=(1, 3),
        quantiles=3,
    )

    assert data.index.names == ["date", "asset"]
    assert set(data["factor_quantile"].dropna().unique()) == {1.0, 2.0, 3.0}
    ic = time_series_information_coefficient(data)
    assert ic["fwd_ret_1d"] > 0.8


def test_quantile_spread_and_rank_autocorrelation() -> None:
    dates = pd.date_range("2026-01-01", periods=15, freq="D")
    factor = pd.Series(range(15), index=dates, dtype=float)
    price = pd.Series([100 + i * 2 for i in range(15)], index=dates, dtype=float)
    data = make_single_asset_factor_data(
        factor,
        price,
        asset="0050.TW",
        horizons=(1,),
        quantiles=5,
    )

    mean_q = mean_return_by_quantile(data)
    spread = quantile_spread(mean_q)

    assert "fwd_ret_1d" in spread
    assert spread["fwd_ret_1d"] < 0.0
    assert rank_autocorrelation(data) > 0.9


def test_rolling_time_series_ic_supports_spearman() -> None:
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    factor = pd.Series(range(20), index=dates, dtype=float)
    price = pd.Series([100 * (1.01 ** (i * i)) for i in range(20)], index=dates, dtype=float)
    data = make_single_asset_factor_data(
        factor,
        price,
        asset="0050.TW",
        horizons=(1,),
        quantiles=4,
    )

    rolling = rolling_time_series_ic(data, window=5, method="spearman")

    assert rolling["fwd_ret_1d"].dropna().iloc[-1] > 0.9


def test_event_study_forward_returns() -> None:
    dates = pd.date_range("2026-01-01", periods=8, freq="D")
    price = pd.Series([100, 101, 102, 103, 104, 105, 106, 107], index=dates, dtype=float)
    events = pd.Series([False, True, False, True, False, False, False, False], index=dates)

    result = event_study_forward_returns(events, price, horizons=(1, 3))

    assert result["event_count"] == 2
    assert result["horizons"]["1d"]["count"] == 2
    assert result["horizons"]["1d"]["hit_rate_positive"] == 1.0
    assert math.isclose(result["horizons"]["1d"]["mean_return"], ((102 / 101 - 1) + (104 / 103 - 1)) / 2)
