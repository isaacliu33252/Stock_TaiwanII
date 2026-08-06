from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.governance.significance import (
    bootstrap_final_value_ci,
    jobson_korkie_memmel_test,
)


def _synthetic_returns(n: int, mean: float, std: float, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(rng.normal(mean, std, size=n), index=idx)


def test_jk_test_similar_distribution_series_is_not_significant() -> None:
    # Two independent draws from the SAME distribution -- not literally
    # identical (which makes the JK asymptotic variance theta exactly 0, an
    # undefined edge case handled separately below), but no real Sharpe gap.
    a = _synthetic_returns(2000, 0.0005, 0.01, seed=1)
    b = _synthetic_returns(2000, 0.0005, 0.01, seed=101)
    a.index = b.index

    result = jobson_korkie_memmel_test(a, b)

    assert result["status"] == "ok"
    assert result["significant_at_5pct"] is False


def test_jk_test_identical_series_reports_degenerate_variance() -> None:
    """theta (the JK asymptotic variance) is exactly 0 when a==b -- a real
    edge case of the formula, not a bug -- and must be reported, not raise."""
    a = _synthetic_returns(300, 0.0005, 0.01, seed=1)

    result = jobson_korkie_memmel_test(a, a.copy())

    assert result["status"] == "degenerate_variance"


def test_jk_test_detects_large_sharpe_difference() -> None:
    a = _synthetic_returns(1000, 0.003, 0.005, seed=2)  # high mean, low vol -> high Sharpe
    b = _synthetic_returns(1000, -0.001, 0.02, seed=3)  # negative mean, high vol -> negative Sharpe
    a.index = b.index

    result = jobson_korkie_memmel_test(a, b)

    assert result["status"] == "ok"
    assert result["sharpe_a"] > result["sharpe_b"]
    assert result["significant_at_1pct"] is True


def test_jk_test_reports_insufficient_data() -> None:
    a = _synthetic_returns(10, 0.0, 0.01, seed=4)
    b = _synthetic_returns(10, 0.0, 0.01, seed=5)

    result = jobson_korkie_memmel_test(a, b)

    assert result["status"] == "insufficient_data"


def test_bootstrap_ci_contains_one_for_identical_series() -> None:
    a = _synthetic_returns(400, 0.0005, 0.01, seed=6)
    result = bootstrap_final_value_ci(a, a.copy(), n_boot=200, block_size=20)

    assert result["status"] == "ok"
    assert result["ci_lower"] <= 1.0 <= result["ci_upper"]
    assert result["a_significantly_better"] is False
    assert result["a_significantly_worse"] is False


def test_bootstrap_ci_detects_clear_outperformance() -> None:
    a = _synthetic_returns(400, 0.004, 0.01, seed=7)
    b = _synthetic_returns(400, -0.004, 0.01, seed=8)
    a.index = b.index

    result = bootstrap_final_value_ci(a, b, n_boot=200, block_size=20)

    assert result["status"] == "ok"
    assert result["point_final_value_ratio_a_over_b"] > 1.0
    assert result["a_significantly_better"] is True


def test_bootstrap_ci_insufficient_data() -> None:
    a = _synthetic_returns(10, 0.0, 0.01, seed=9)
    b = _synthetic_returns(10, 0.0, 0.01, seed=10)

    result = bootstrap_final_value_ci(a, b, block_size=20)

    assert result["status"] == "insufficient_data"
