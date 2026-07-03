#!/usr/bin/env python3
"""Tests for persistent GroupA+ alert state tracking."""

from __future__ import annotations

from group_a_plus.operations.alert_state import update_alert_state


def _live_signal(alert_type: str = "total_risk_score") -> dict:
    return {
        "signal_version": 2,
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "actual_data_date": "2026-06-29",
        "signal_alerts": [
            {
                "type": alert_type,
                "level": "medium",
                "title": "Total risk score elevated",
                "reason": "Composite market risk score is elevated.",
                "cooldown_key": f"a2118_a2111_ncf_late_bull_deleverage:2026-06-29:{alert_type}",
                "cooldown_minutes": 5,
            }
        ],
    }


def test_first_seen_alert_is_emitted() -> None:
    state = update_alert_state(_live_signal(), now_iso="2026-06-30T01:00:00Z")

    assert state["summary"]["emitted_count"] == 1
    assert state["summary"]["suppressed_count"] == 0
    assert state["emitted_alerts"][0]["type"] == "total_risk_score"


def test_repeated_alert_inside_cooldown_is_suppressed() -> None:
    first = update_alert_state(_live_signal(), now_iso="2026-06-30T01:00:00Z")
    second = update_alert_state(_live_signal(), first, now_iso="2026-06-30T01:03:00Z")

    assert second["summary"]["emitted_count"] == 0
    assert second["summary"]["suppressed_count"] == 1
    assert second["suppressed_alerts"][0]["type"] == "total_risk_score"


def test_repeated_alert_after_cooldown_is_emitted_again() -> None:
    first = update_alert_state(_live_signal(), now_iso="2026-06-30T01:00:00Z")
    second = update_alert_state(_live_signal(), first, now_iso="2026-06-30T01:06:00Z")

    assert second["summary"]["emitted_count"] == 1
    assert second["summary"]["suppressed_count"] == 0


def test_missing_current_alert_resolves_previous_active_alert() -> None:
    first = update_alert_state(_live_signal(), now_iso="2026-06-30T01:00:00Z")
    cleared_signal = {
        "signal_version": 2,
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "actual_data_date": "2026-06-29",
        "signal_alerts": [],
    }

    second = update_alert_state(cleared_signal, first, now_iso="2026-06-30T01:10:00Z")

    assert second["summary"]["resolved_count"] == 1
    assert second["resolved_alerts"][0]["type"] == "total_risk_score"
    assert second["summary"]["active_state_count"] == 0
