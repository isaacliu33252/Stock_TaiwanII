from __future__ import annotations

from apply_group_a_plus_execution_gate import _apply_first_stage_gate, _first_stage_fractions


def test_first_stage_fractions_pause_break_low() -> None:
    decision = {"trigger": "pause_break_reference_low", "release_fraction": 0.0}

    fractions = _first_stage_fractions(decision)

    assert fractions["risk_buy_fraction"] == 0.0
    assert fractions["defensive_sleeve_sell_fraction"] == 0.0


def test_first_stage_fractions_follow_recovery_release() -> None:
    decision = {"trigger": "intraday_recovery", "release_fraction": 0.25}

    fractions = _first_stage_fractions(decision)

    assert fractions["risk_buy_fraction"] == 0.25
    assert fractions["defensive_sleeve_sell_fraction"] == 0.25


def test_apply_first_stage_gate_pauses_risk_buys_and_bond_sells() -> None:
    current = {"0050.TW": 89, "00631L.TW": 0, "00632R.TW": 0, "00679B.TWO": 10000}
    target = {"0050.TW": 2248, "00631L.TW": 638, "00632R.TW": 0, "00679B.TWO": 7348}

    gated, staged = _apply_first_stage_gate(
        current,
        target,
        risk_buy_fraction=0.0,
        defensive_sleeve_sell_fraction=0.0,
    )

    assert gated["0050.TW"] == 89
    assert gated["00631L.TW"] == 0
    assert gated["00632R.TW"] == 0
    assert gated["00679B.TWO"] == 10000
    assert staged["0050.TW"]["gate_applied"] is True
    assert staged["00679B.TWO"]["gate_applied"] is True
