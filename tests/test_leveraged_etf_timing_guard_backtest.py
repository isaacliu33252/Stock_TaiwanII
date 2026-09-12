from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.backtest_group_a_plus_leveraged_etf_timing_guard import (
    _build_timing_warnings,
    _guarded_weights,
    _variant_regimes,
)
from group_a_plus.integrations.leveraged_etf_timing_anomaly import TimingAnomalyThresholds


def test_guarded_weights_shift_00631l_to_0050_and_00632r_to_cash() -> None:
    weights = {"0050.TW": 0.4, "00631L.TW": 0.2, "00632R.TW": 0.1, "cash": 0.3}

    out = _guarded_weights(weights, guard_631l=True, guard_632r=True)

    assert out["0050.TW"] == pytest.approx(0.6)
    assert out["00631L.TW"] == 0.0
    assert out["00632R.TW"] == 0.0
    assert out["cash"] == pytest.approx(0.4)
    assert abs(sum(out.values()) - 1.0) < 1e-12


def test_variant_regimes_uses_previous_day_warning_without_lookahead() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    regimes = pd.Series(["golden1"] * 4, index=idx)
    warnings = pd.DataFrame(
        {
            "00631L.TW": [False, True, False, False],
            "00632R.TW": [False, False, False, True],
        },
        index=idx,
    )

    out = _variant_regimes(regimes, warnings, mode="combined")

    assert out.iloc[0] == "golden1"
    assert out.iloc[1] == "golden1"
    assert out.iloc[2] == "golden1__timing_guard_1_0"
    assert out.iloc[3] == "golden1"


def test_build_timing_warnings_supports_negative_covariance_policy() -> None:
    idx = pd.date_range("2026-01-01", periods=45, freq="B")
    underlying_returns = pd.Series([0.01 if i % 2 == 0 else -0.01 for i in range(44)], index=idx[1:])
    ratios = pd.Series([1.5 if r > 0 else 2.5 for r in underlying_returns], index=idx[1:])
    etf_631l_returns = ratios * underlying_returns
    etf_632r_returns = -underlying_returns
    prices = pd.DataFrame(
        {
            "0050.TW": pd.concat([pd.Series([100.0], index=idx[:1]), 100.0 * (1.0 + underlying_returns).cumprod()]),
            "00631L.TW": pd.concat([pd.Series([50.0], index=idx[:1]), 50.0 * (1.0 + etf_631l_returns).cumprod()]),
            "00632R.TW": pd.concat([pd.Series([20.0], index=idx[:1]), 20.0 * (1.0 + etf_632r_returns).cumprod()]),
        }
    )

    warnings = _build_timing_warnings(
        prices,
        rolling_window=20,
        thresholds=TimingAnomalyThresholds(negative_covariance_warning=-0.001),
        warning_policy="negative_covariance",
        persistence_days=2,
    )

    assert warnings["00631L.TW"].any()
