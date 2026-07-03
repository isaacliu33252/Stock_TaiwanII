#!/usr/bin/env python3
"""M6 (2026-07-02 Fable 5 audit) regression: Group A+ vs FinRL metric convention.

_metrics() uses risk_free_rate=0 and decimal scale; FinRL's
calculate_sharpe_ratio/calculate_sortino_ratio/calculate_volatility default
to risk_free_rate=0.02 and percentage scale. _metrics_finrl_comparable()
exists to recompute this system's numbers under FinRL's convention so
cross-system comparisons don't hit the resulting ~0.1-0.3 Sharpe offset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_group_a_plus_switch_policy import _metrics, _metrics_finrl_comparable
from FinRL.v2.backtesting.performance_metrics import (
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_volatility,
)


def _synthetic_equity_curve(seed: int = 42, n: int = 500) -> pd.Series:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0006, 0.01, n)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    values = 1_000_000.0 * (1 + pd.Series(returns, index=idx)).cumprod()
    return values


def test_metrics_finrl_comparable_matches_finrl_functions_directly() -> None:
    values = _synthetic_equity_curve()
    returns = values.pct_change().dropna()

    result = _metrics_finrl_comparable(values)

    assert result["sharpe_ratio"] == calculate_sharpe_ratio(returns)
    assert result["sortino_ratio"] == calculate_sortino_ratio(returns)
    assert result["volatility"] == calculate_volatility(returns)
    assert result["risk_free_rate"] == 0.02


def test_metrics_finrl_comparable_respects_custom_risk_free_rate() -> None:
    values = _synthetic_equity_curve()
    returns = values.pct_change().dropna()

    result = _metrics_finrl_comparable(values, risk_free_rate=0.0)

    # rf=0 should match _metrics()'s own convention closely (same formula
    # shape as _metrics()'s sharpe -- both risk_free_rate=0).
    base = _metrics(values, initial_value=float(values.iloc[0]))
    assert abs(result["sharpe_ratio"] - base["sharpe_ratio"]) < 1e-9
    assert result["sharpe_ratio"] == calculate_sharpe_ratio(returns, risk_free_rate=0.0)


def test_metrics_finrl_comparable_sharpe_lower_than_group_a_plus_default() -> None:
    """The whole point of M6: _metrics()'s own sharpe_ratio (rf=0) should be
    higher than the FinRL-comparable one (rf=0.02 default) for a
    positive-mean-return series -- confirms the systematic offset the audit
    found is real and this helper corrects it."""
    values = _synthetic_equity_curve()

    base = _metrics(values, initial_value=float(values.iloc[0]))
    finrl_comparable = _metrics_finrl_comparable(values)

    assert finrl_comparable["sharpe_ratio"] < base["sharpe_ratio"]
