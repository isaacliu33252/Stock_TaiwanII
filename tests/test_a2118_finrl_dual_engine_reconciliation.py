#!/usr/bin/env python3
"""M6 (2026-07-02 Fable 5 audit) regression: daily-weight resolution for the
FinRL dual-engine reconciliation bridge."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_a2118_finrl_dual_engine_reconciliation import _daily_weights_from_regime


def test_daily_weights_resolves_each_day_from_its_regime() -> None:
    frame = pd.DataFrame(
        {"execution_regime": ["golden1", "golden1", "ncf_late_bull_hedge"]},
        index=pd.date_range("2026-01-02", periods=3, freq="B"),
    )
    base_weights = {
        "golden1": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
        "ncf_late_bull_hedge": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
    }

    weights = _daily_weights_from_regime(frame, base_weights)

    assert list(weights.index) == list(frame.index)
    assert weights.iloc[0]["0050.TW"] == 0.60
    assert weights.iloc[2]["0050.TW"] == 0.70
    assert weights.iloc[2]["00631L.TW"] == 0.10


def test_daily_weights_raises_on_unknown_regime() -> None:
    frame = pd.DataFrame(
        {"execution_regime": ["some_undefined_regime"]},
        index=pd.date_range("2026-01-02", periods=1, freq="B"),
    )
    base_weights = {"golden1": {"0050.TW": 0.60, "cash": 0.40}}

    with pytest.raises(KeyError):
        _daily_weights_from_regime(frame, base_weights)
