from __future__ import annotations

import pytest

from apply_group_all_execution_gate import (
    _apply_execution_gate,
    _execution_gate_decision,
)


def test_execution_gate_pauses_risk_buys_after_reference_low_break() -> None:
    decision = _execution_gate_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=None,
        observed_low=100.0,
        observed_last=101.0,
        observed_close=None,
    )

    assert decision["trigger"] == "pause_break_reference_low"
    assert decision["risk_buy_fraction"] == 0.0


def test_execution_gate_allows_small_buy_after_reclaiming_reference_low() -> None:
    decision = _execution_gate_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=None,
        observed_low=100.0,
        observed_last=103.0,
        observed_close=None,
    )

    assert decision["trigger"] == "pause_break_reference_low"

    decision = _execution_gate_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=None,
        observed_low=103.0,
        observed_last=103.0,
        observed_close=None,
    )

    assert decision["trigger"] == "partial_recovery_above_reference_low"
    assert decision["risk_buy_fraction"] == pytest.approx(0.10)


def test_apply_execution_gate_only_stages_group_a_risk_buys() -> None:
    rows = [
        {"ticker": "0050.TW", "current_shares": 572, "target_shares": 9702},
        {"ticker": "00631L.TW", "current_shares": 0, "target_shares": 1000},
        {"ticker": "0056.TW", "current_shares": 16879, "target_shares": 1987},
        {"ticker": "00646.TW", "current_shares": 1032, "target_shares": 1531},
    ]
    decision = {"risk_buy_fraction": 0.0}

    gated = _apply_execution_gate(rows, decision)

    assert gated[0]["target_shares"] == 572
    assert gated[1]["target_shares"] == 0
    assert gated[2]["target_shares"] == 1987
    assert gated[3]["target_shares"] == 1531
