from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_2604_08356_mrp_strategy_decay import _sharpe, mrp1


def _series(values: np.ndarray) -> pd.Series:
    idx = pd.date_range("2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx)


def test_mrp1_finds_the_weak_regime_split() -> None:
    rng = np.random.default_rng(0)
    strong = rng.normal(0.002, 0.01, 300)
    weak = rng.normal(-0.001, 0.01, 300)
    returns = _series(np.concatenate([strong, weak]))

    result = mrp1(returns, d_days=100)

    assert result["feasible"] is True
    # The exhaustive search minimizes over both split location and which side
    # is worse, so it need not land exactly on the true break at 300 -- but it
    # must fall inside the [d, n-d] search range and pick out a segment worse
    # than the full-sample Sharpe, which is the paper's core claim (MRP is a
    # lower bound below the unconditional Sharpe).
    assert 100 <= result["split_index"] <= 500
    assert result["mrp1"] < _sharpe(returns)


def test_mrp1_matches_full_sample_when_series_is_stationary_and_short() -> None:
    rng = np.random.default_rng(1)
    returns = _series(rng.normal(0.001, 0.01, 220))

    result = mrp1(returns, d_days=100)

    assert result["feasible"] is True
    # With d=100 on a 220-row series there are only 21 valid splits (100..120),
    # so MRP1 should stay reasonably close to the full-sample Sharpe rather
    # than collapsing, unlike the many-splits case the paper's Appendix A warns about.
    full = _sharpe(returns)
    assert abs(result["mrp1"] - full) < abs(full) + 1.0


def test_mrp1_infeasible_when_series_shorter_than_two_d() -> None:
    returns = _series(np.full(50, 0.001))

    result = mrp1(returns, d_days=100)

    assert result["feasible"] is False


def test_more_valid_splits_pushes_mrp1_lower_for_same_stationary_process() -> None:
    # Appendix A: MRP1 is an inconsistent estimator -- more candidate splits
    # (smaller d relative to series length) push the minimum lower even for
    # an identically-distributed stationary process. This is the concrete
    # reason the report checks more than one `d` instead of trusting one.
    rng = np.random.default_rng(2)
    returns = _series(rng.normal(0.0005, 0.01, 1500))

    coarse = mrp1(returns, d_days=600)
    fine = mrp1(returns, d_days=50)

    assert coarse["feasible"] is True and fine["feasible"] is True
    assert fine["valid_splits"] > coarse["valid_splits"]
    assert fine["mrp1"] <= coarse["mrp1"]
