from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backtest.backtest_group_a_plus_financial_econometrics import (
    _garch_proxy_vol,
    _garch_proxy_vol_downside,
)


def _bdate_series(values: np.ndarray, start: str = "2020-01-02") -> pd.Series:
    dates = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=dates)


def test_downside_proxy_decays_toward_baseline_on_all_up_days():
    rng = np.random.default_rng(0)
    returns = _bdate_series(np.abs(rng.normal(0.01, 0.003, size=300)))  # strictly positive returns

    downside = _garch_proxy_vol_downside(returns)
    symmetric = _garch_proxy_vol(returns)

    # No negative day ever fires the shock term, so downside vol should be
    # persistently lower than the symmetric proxy once past the warmup period.
    assert (downside.iloc[100:] < symmetric.iloc[100:]).all()


def test_downside_proxy_matches_symmetric_when_all_returns_negative():
    rng = np.random.default_rng(1)
    returns = _bdate_series(-np.abs(rng.normal(0.01, 0.003, size=300)))  # strictly negative returns

    downside = _garch_proxy_vol_downside(returns)
    symmetric = _garch_proxy_vol(returns)

    # Every day fires the shock term in both proxies, so they should be identical.
    pd.testing.assert_series_equal(downside, symmetric)


def test_downside_proxy_positive_and_aligned():
    rng = np.random.default_rng(2)
    returns = _bdate_series(rng.normal(0.0005, 0.01, size=250))

    downside = _garch_proxy_vol_downside(returns)

    assert (downside > 0).all()
    assert downside.index.equals(returns.index)
