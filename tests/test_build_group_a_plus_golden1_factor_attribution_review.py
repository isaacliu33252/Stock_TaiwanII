"""Unit tests for scripts/evaluate/build_group_a_plus_golden1_factor_attribution_review.py's
pure functions -- no DB/network access, synthetic data only."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts" / "evaluate"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_group_a_plus_golden1_factor_attribution_review import (  # noqa: E402
    LETF_TARGET_MULTIPLE,
    _hac_ols,
    _regress_strategy,
    _sample_caveat,
    build_factors,
)


def test_hac_ols_recovers_known_linear_relationship():
    rng = np.random.default_rng(0)
    n = 300
    x = pd.Series(rng.normal(size=n), name="x")
    y = 0.5 * x + pd.Series(rng.normal(scale=0.01, size=n))
    y.name = "y"

    result = _hac_ols(y, pd.DataFrame({"x": x}))

    assert result["coefficients"]["x"]["coef"] == pytest.approx(0.5, abs=0.05)
    assert result["r_squared"] > 0.9


def test_build_factors_letf_xs_is_zero_when_letf_tracks_exact_multiple():
    dates = pd.date_range("2024-01-01", periods=50, freq="B")
    mkt_ret = pd.Series(np.linspace(-0.01, 0.01, 50), index=dates)
    mkt_close = 100.0 * (1.0 + mkt_ret).cumprod()
    letf_close = 100.0 * (1.0 + LETF_TARGET_MULTIPLE * mkt_ret).cumprod()

    factors = build_factors(mkt_close, letf_close)

    assert factors["LETF_XS"].dropna().abs().max() < 1e-9


def test_regress_strategy_returns_none_when_too_few_rows():
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    strategy_ret = pd.Series(0.001, index=dates, name="strategy_return")
    factors = pd.DataFrame(
        {"MKT": 0.001, "LETF_XS": 0.0, "TSMOM": 0.0, "REV1": 0.0}, index=dates
    )

    assert _regress_strategy(strategy_ret, factors) is None


def test_sample_caveat_flags_short_vs_multiyear_window():
    short = _sample_caveat("2025-01-01", "2025-06-01")
    long = _sample_caveat("2017-01-01", "2026-08-01")

    assert "one regime" in short
    assert "multiple regimes" in long
