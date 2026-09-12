from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_2511_00390_dynamic_lag_diagnostic import rolling_optimal_lag


def test_rolling_optimal_lag_finds_true_lag_in_synthetic_data() -> None:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    leader_ret = pd.Series(rng.normal(0, 0.01, 400), index=idx)
    # Lagger is driven by the leader's return exactly 2 days earlier, plus noise.
    lagger_ret = leader_ret.shift(2).fillna(0.0) * 0.9 + pd.Series(rng.normal(0, 0.001, 400), index=idx)

    result = rolling_optimal_lag(leader_ret, lagger_ret, window=60)

    assert not result.empty
    # The dominant detected lag should be 2, matching the true generating lag.
    mode_lag = result["best_lag"].mode().iloc[0]
    assert mode_lag == 2


def test_rolling_optimal_lag_prefers_lag_zero_for_contemporaneous_relationship() -> None:
    rng = np.random.default_rng(1)
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    leader_ret = pd.Series(rng.normal(0, 0.01, 400), index=idx)
    lagger_ret = leader_ret * 0.9 + pd.Series(rng.normal(0, 0.001, 400), index=idx)

    result = rolling_optimal_lag(leader_ret, lagger_ret, window=60)

    mode_lag = result["best_lag"].mode().iloc[0]
    assert mode_lag == 0


def test_rolling_optimal_lag_returns_empty_when_series_too_short() -> None:
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    leader_ret = pd.Series(np.zeros(10), index=idx)
    lagger_ret = pd.Series(np.zeros(10), index=idx)

    result = rolling_optimal_lag(leader_ret, lagger_ret, window=60)

    assert result.empty
