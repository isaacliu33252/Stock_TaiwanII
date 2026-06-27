from __future__ import annotations

import pytest

from group_a_plus_second_stage_execution import (
    _build_second_stage_targets,
    _release_decision,
)


CONTROL = {
    "pause_on_break_reference_low": True,
    "break_low_buffer": 0.0,
    "price_tolerance": 0.01,
    "pause_on_open_gap_down": True,
    "pause_open_gap_down_pct": -0.015,
    "release_fraction_by_trigger": {
        "close_above_reference_close": 0.50,
        "intraday_recovery": 0.25,
        "hold_deferred_buys": 0.0,
    },
}


def test_release_decision_pauses_when_0050_breaks_reference_low() -> None:
    decision = _release_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=103.0,
        observed_low=102.7,
        observed_last=104.5,
        observed_close=None,
        twii_recovered=True,
        control=CONTROL,
    )

    assert decision["trigger"] == "pause_break_reference_low"
    assert decision["release_fraction"] == 0.0


def test_release_decision_releases_half_after_close_confirmation() -> None:
    decision = _release_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=103.0,
        observed_low=103.0,
        observed_last=None,
        observed_close=104.2,
        twii_recovered=False,
        control=CONTROL,
    )

    assert decision["trigger"] == "close_above_reference_close"
    assert decision["release_fraction"] == pytest.approx(0.50)


def test_release_decision_releases_quarter_on_intraday_recovery() -> None:
    decision = _release_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=103.0,
        observed_low=103.0,
        observed_last=104.15,
        observed_close=None,
        twii_recovered=False,
        control=CONTROL,
    )

    assert decision["trigger"] == "intraday_recovery"
    assert decision["release_fraction"] == pytest.approx(0.25)
    assert decision["open_gap_pct"] == pytest.approx((103.0 / 104.15) - 1.0)


def test_release_decision_tolerates_rounded_intraday_price_input() -> None:
    decision = _release_decision(
        reference_close=104.1500015258789,
        reference_low=102.80,
        observed_open=None,
        observed_low=103.0,
        observed_last=104.15,
        observed_close=None,
        twii_recovered=False,
        control=CONTROL,
    )

    assert decision["trigger"] == "intraday_recovery"
    assert decision["release_fraction"] == pytest.approx(0.25)


def test_release_decision_pauses_on_large_open_gap_down_before_intraday_recovery() -> None:
    decision = _release_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=102.0,
        observed_low=102.9,
        observed_last=104.2,
        observed_close=None,
        twii_recovered=True,
        control=CONTROL,
    )

    assert decision["trigger"] == "pause_open_gap_down"
    assert decision["release_fraction"] == 0.0
    assert decision["open_gap_pct"] == pytest.approx((102.0 / 104.15) - 1.0)


def test_release_decision_close_confirmation_overrides_large_open_gap_down() -> None:
    decision = _release_decision(
        reference_close=104.15,
        reference_low=102.80,
        observed_open=102.0,
        observed_low=102.9,
        observed_last=None,
        observed_close=104.3,
        twii_recovered=False,
        control=CONTROL,
    )

    assert decision["trigger"] == "close_above_reference_close"
    assert decision["release_fraction"] == pytest.approx(0.50)


def test_second_stage_targets_release_only_deferred_buys() -> None:
    stage_one = {
        "0050.TW": 2286,
        "00631L.TW": 521,
        "00632R.TW": 0,
        "00679B.TWO": 10000,
    }
    full = {
        "0050.TW": 4483,
        "00631L.TW": 1042,
        "00632R.TW": 0,
        "00679B.TWO": 9702,
    }

    targets, released = _build_second_stage_targets(
        stage_one,
        full,
        release_fraction=0.25,
    )

    assert targets["0050.TW"] == 2286 + 549
    assert targets["00631L.TW"] == 521 + 130
    assert targets["00632R.TW"] == 0
    assert targets["00679B.TWO"] == 10000
    assert released["00679B.TWO"] == 0
