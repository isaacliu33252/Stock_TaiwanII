#!/usr/bin/env python3
"""Tests for the volatility pre-trade guard shadow audit."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_volatility_pretrade_guard import _audit_no_add_guard_events


def test_audit_no_add_guard_records_only_high_vol_add_attempts() -> None:
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 100.0, 100.0],
            "00631L.TW": [50.0, 50.0, 50.0, 50.0],
            "00632R.TW": [10.0, 10.0, 10.0, 10.0],
            "00679B.TWO": [25.0, 25.0, 25.0, 25.0],
        },
        index=idx,
    )
    regimes = pd.Series(["cash", "golden1", "hedge", "golden1"], index=idx)
    gate_frame = pd.DataFrame(
        {"volatility_gate": ["neutral_vol", "high_vol_defensive", "high_vol_defensive", "neutral_vol"]},
        index=idx,
    )
    weights_by_regime = {
        "cash": {"cash": 1.0},
        "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2},
        "hedge": {"0050.TW": 0.9, "00631L.TW": 0.1},
    }

    audit = _audit_no_add_guard_events(
        prices,
        regimes,
        gate_frame,
        weights_by_regime,
        initial_value=100_000.0,
    )

    assert audit["checked_rebalance_days"] == 4
    assert audit["high_vol_rebalance_days"] == 2
    assert audit["blocked_days"] == 2
    assert audit["cumulative_blocked_00631l_weight"] == pytest.approx(0.3)
    event = audit["events"][0]
    assert event["date"] == "2026-01-05"
    assert event["current_00631l_weight"] == 0.0
    assert event["requested_00631l_weight"] == 0.2
    assert event["guarded_00631l_weight"] == 0.0
    assert audit["events"][1]["requested_00631l_weight"] == 0.1
