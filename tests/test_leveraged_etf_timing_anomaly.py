from __future__ import annotations

import pandas as pd
import pytest

from group_a_plus.integrations.leveraged_etf_timing_anomaly import (
    TimingAnomalyThresholds,
    approximate_geometric_return,
    effective_return_ratio,
    rolling_timing_anomaly,
    summarize_timing_anomaly,
)


def test_effective_return_ratio_excludes_small_underlying_moves() -> None:
    idx = pd.date_range("2026-01-01", periods=4)
    etf = pd.Series([0.02, 0.001, -0.02, 0.03], index=idx)
    underlying = pd.Series([0.01, 0.0001, -0.01, 0.015], index=idx)

    ratio = effective_return_ratio(etf, underlying, min_abs_underlying_return=0.0005)

    assert ratio.tolist() == [2.0, 2.0, 2.0]


def test_summarize_timing_anomaly_detects_negative_covariance() -> None:
    idx = pd.date_range("2026-01-01", periods=41, freq="B")
    underlying_returns = pd.Series([0.01 if i % 2 == 0 else -0.01 for i in range(40)], index=idx[1:])
    ratios = pd.Series([1.5 if r > 0 else 2.5 for r in underlying_returns], index=idx[1:])
    etf_returns = ratios * underlying_returns
    underlying_prices = pd.concat([pd.Series([100.0], index=idx[:1]), 100.0 * (1.0 + underlying_returns).cumprod()])
    etf_prices = pd.concat([pd.Series([50.0], index=idx[:1]), 50.0 * (1.0 + etf_returns).cumprod()])

    summary = summarize_timing_anomaly(
        etf_prices,
        underlying_prices,
        target_leverage=2.0,
        thresholds=TimingAnomalyThresholds(negative_covariance_warning=-0.001),
    )

    assert summary["average_effective_leverage"] == pytest.approx(2.0)
    assert summary["covariance_ratio_underlying_return"] < -0.001
    assert "negative_ratio_return_covariance" in summary["warnings"]


def test_rolling_timing_anomaly_returns_latest_window_summary() -> None:
    idx = pd.date_range("2026-01-01", periods=20, freq="B")
    underlying_prices = pd.Series([100.0 + i for i in range(20)], index=idx)
    etf_prices = pd.Series([50.0 + 1.2 * i for i in range(20)], index=idx)

    out = rolling_timing_anomaly(etf_prices, underlying_prices, target_leverage=2.0, window=8)

    assert not out.empty
    assert "average_effective_leverage" in out.columns
    assert out.index[-1] == idx[-1]


def test_approximate_geometric_return_is_below_arithmetic_when_vol_positive() -> None:
    geo = approximate_geometric_return(0.10, 0.30)

    assert geo < 0.10
