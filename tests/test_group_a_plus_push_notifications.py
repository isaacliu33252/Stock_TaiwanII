#!/usr/bin/env python3
"""Tests for GroupA+ high-severity alert push notifications."""

from __future__ import annotations

import os

import pytest

from group_a_plus.operations.push_notifications import (
    send_alert_notifications,
    send_telegram_message,
)


def _alert_state(*, high_alert: bool = True, medium_alert: bool = False) -> dict:
    emitted = []
    if high_alert:
        emitted.append(
            {
                "type": "execution_blocked",
                "level": "high",
                "title": "Execution blocked",
                "reason": "Execution guard is not satisfied.",
                "status": "emitted",
            }
        )
    if medium_alert:
        emitted.append(
            {
                "type": "total_risk_score",
                "level": "medium",
                "title": "Total risk score elevated",
                "reason": "Composite market risk score is elevated.",
                "status": "emitted",
            }
        )
    return {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "signal_date": "2026-06-29",
        "emitted_alerts": emitted,
        "suppressed_alerts": [],
    }


def _volatility_gate_alert_state() -> dict:
    return {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "signal_date": "2026-07-09",
        "emitted_alerts": [
            {
                "type": "volatility_gate_high_vol",
                "level": "medium",
                "title": "Volatility gate high-vol manual review",
                "reason": "High-volatility gate is active; advisory-only review of 00631L exposure.",
                "status": "emitted",
                "metadata": {
                    "allow_00631l_add": False,
                    "trade_policy": "advisory_no_auto_weight_change",
                },
            }
        ],
        "suppressed_alerts": [],
    }


def test_no_qualifying_alerts_does_not_call_send_fn() -> None:
    calls: list[str] = []
    result = send_alert_notifications(
        _alert_state(high_alert=False, medium_alert=True),
        send_fn=calls.append,
    )

    assert result["sent"] is False
    assert result["alert_count"] == 0
    assert calls == []


def test_high_severity_alert_triggers_send() -> None:
    calls: list[str] = []
    result = send_alert_notifications(
        _alert_state(high_alert=True),
        send_fn=lambda message: (calls.append(message), True)[1],
    )

    assert result["sent"] is True
    assert result["alert_count"] == 1
    assert len(calls) == 1
    assert "Execution blocked" in calls[0]
    assert "a2118_a2111_ncf_late_bull_deleverage" in calls[0]


def test_medium_alert_not_sent_at_default_high_threshold() -> None:
    calls: list[str] = []
    result = send_alert_notifications(
        _alert_state(high_alert=False, medium_alert=True),
        send_fn=calls.append,
    )

    assert result["sent"] is False
    assert calls == []


def test_min_level_medium_includes_medium_alerts() -> None:
    calls: list[str] = []
    result = send_alert_notifications(
        _alert_state(high_alert=False, medium_alert=True),
        min_level="medium",
        send_fn=lambda message: (calls.append(message), True)[1],
    )

    assert result["sent"] is True
    assert result["alert_count"] == 1


def test_volatility_gate_metadata_is_included_in_push_message() -> None:
    calls: list[str] = []
    result = send_alert_notifications(
        _volatility_gate_alert_state(),
        min_level="medium",
        send_fn=lambda message: (calls.append(message), True)[1],
    )

    assert result["sent"] is True
    assert result["alert_count"] == 1
    assert "00631L add: blocked" in calls[0]
    assert "advisory, no auto weight change" in calls[0]


def test_mixed_alerts_only_qualifying_ones_are_sent() -> None:
    calls: list[str] = []
    result = send_alert_notifications(
        _alert_state(high_alert=True, medium_alert=True),
        send_fn=lambda message: (calls.append(message), True)[1],
    )

    assert result["alert_count"] == 1
    assert "Execution blocked" in calls[0]
    assert "Total risk score elevated" not in calls[0]


def test_send_fn_failure_is_reflected_in_sent_flag() -> None:
    result = send_alert_notifications(_alert_state(high_alert=True), send_fn=lambda message: False)

    assert result["sent"] is False
    assert result["alert_count"] == 1


def test_send_telegram_message_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROUP_A_PLUS_ALERT_TELEGRAM_ENABLED", raising=False)

    assert send_telegram_message("test message") is False


def test_send_telegram_message_enabled_without_credentials_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROUP_A_PLUS_ALERT_TELEGRAM_ENABLED", "1")
    for var in (
        "GROUP_A_PLUS_ALERT_TELEGRAM_BOT_TOKEN",
        "GROUP_A_PLUS_ALERT_TELEGRAM_CHAT_ID",
        "FINRL_TELEGRAM_BOT_TOKEN",
        "FINRL_TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(var, raising=False)

    assert send_telegram_message("test message") is False


def test_send_telegram_message_falls_back_to_finrl_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROUP_A_PLUS_ALERT_TELEGRAM_ENABLED", "1")
    monkeypatch.delenv("GROUP_A_PLUS_ALERT_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GROUP_A_PLUS_ALERT_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("FINRL_TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("FINRL_TELEGRAM_CHAT_ID", "fake-chat-id")

    calls: list[str] = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=10: calls.append(req.full_url) or _NullContextManager(),
    )

    assert send_telegram_message("test message") is True
    assert calls and calls[0].startswith("https://api.telegram.org/botfake-token/sendMessage")


class _NullContextManager:
    def __enter__(self) -> "_NullContextManager":
        return self

    def __exit__(self, *args: object) -> bool:
        return False
