#!/usr/bin/env python3
"""Tests for persistent GroupA+ alert state tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from group_a_plus.operations.alert_state import (
    _crash_risk_alerts,
    _ops_health_error_alerts,
    _network_spillover_alerts,
    update_alert_state,
    update_alert_state_from_files,
)


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


def test_emitted_alert_preserves_metadata() -> None:
    signal = _live_signal("volatility_gate_high_vol")
    signal["signal_alerts"][0]["metadata"] = {
        "allow_00631l_add": False,
        "trade_policy": "advisory_no_auto_weight_change",
    }

    state = update_alert_state(signal, now_iso="2026-06-30T01:00:00Z")

    metadata = state["emitted_alerts"][0]["metadata"]
    assert metadata["allow_00631l_add"] is False
    assert metadata["trade_policy"] == "advisory_no_auto_weight_change"


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


def _live_signal_on_date(date_str: str, *, cooldown_minutes: int, alert_type: str = "total_risk_score") -> dict:
    return {
        "signal_version": 2,
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "actual_data_date": date_str,
        "signal_alerts": [
            {
                "type": alert_type,
                "level": "medium",
                "title": "Total risk score elevated",
                "reason": "Composite market risk score is elevated.",
                "cooldown_key": f"a2118_a2111_ncf_late_bull_deleverage:{date_str}:{alert_type}",
                "cooldown_minutes": cooldown_minutes,
            }
        ],
    }


def test_cooldown_spans_across_days_for_same_condition() -> None:
    """Fable audit (2026-07-08, #7): cooldown_key bakes in the signal date,
    so a naive per-state_key cooldown check resets to "never emitted" every
    new day regardless of how recently the same underlying condition last
    fired. The same condition recurring the next day, only a few hours after
    the previous run, must still be suppressed within a 20h cooldown."""
    first = update_alert_state(
        _live_signal_on_date("2026-06-29", cooldown_minutes=1200), now_iso="2026-06-29T23:30:00Z"
    )
    second = update_alert_state(
        _live_signal_on_date("2026-06-30", cooldown_minutes=1200), first, now_iso="2026-06-30T10:00:00Z"
    )

    assert second["summary"]["emitted_count"] == 0
    assert second["summary"]["suppressed_count"] == 1


def test_cooldown_emits_again_next_day_past_window() -> None:
    first = update_alert_state(
        _live_signal_on_date("2026-06-29", cooldown_minutes=1200), now_iso="2026-06-29T23:30:00Z"
    )
    second = update_alert_state(
        _live_signal_on_date("2026-06-30", cooldown_minutes=1200), first, now_iso="2026-06-30T23:35:00Z"
    )

    assert second["summary"]["emitted_count"] == 1
    assert second["summary"]["suppressed_count"] == 0


def test_resolved_alert_older_than_retention_is_pruned() -> None:
    """resolved_alerts/alerts history must not grow without bound -- an
    entry resolved more than RESOLVED_ALERT_RETENTION_DAYS ago is dropped on
    the next update instead of being carried forward forever."""
    first = update_alert_state(_live_signal(), now_iso="2026-01-01T00:00:00Z")
    cleared_signal = {
        "signal_version": 2,
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "actual_data_date": "2026-06-29",
        "signal_alerts": [],
    }
    resolved = update_alert_state(cleared_signal, first, now_iso="2026-01-02T00:00:00Z")
    assert resolved["summary"]["resolved_count"] == 1

    long_after = update_alert_state(cleared_signal, resolved, now_iso="2026-07-05T00:00:00Z")

    assert long_after["alerts"] == {}


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


def _ops_health_payload(
    *,
    system_errors=(),
    artifact_status="ok",
    pipeline_status="ok",
    external_status="ok",
    execution_plan_freshness=None,
    external_error_tickers=None,
    external_ticker_errors=None,
) -> dict:
    if external_error_tickers is not None or external_ticker_errors is not None:
        # Real collect_external_data_freshness() shape for a readable report
        # with overall_status=="error": it never sets "errors", only
        # "error_tickers"/"external_error_tickers" (see ops_health.py
        # collect_external_data_freshness). Callers that care about the
        # rendered alert text (not just alert presence) should use this shape.
        external_data_freshness = {
            "status": external_status,
            "error_tickers": list(external_ticker_errors or []),
            "external_error_tickers": list(external_error_tickers or []),
        }
    else:
        external_data_freshness = {"status": external_status, "errors": ["ohlcv_freshness_report_unreadable"]}
    return {
        "success": True,
        "data": {
            "system_resources": {"errors": list(system_errors)},
            "artifact_health": {
                "status": artifact_status,
                "missing_required": ["execution_plan"],
                "execution_plan_freshness": execution_plan_freshness or {"status": "fresh", "lag_days": 1.0},
            },
            "pipeline_health": {"status": pipeline_status, "errors": ["pipeline_manifest_unreadable"]},
            "external_data_freshness": external_data_freshness,
        },
    }


def test_ops_health_disk_errors_are_excluded() -> None:
    alerts = _ops_health_error_alerts(_ops_health_payload(system_errors=["disk_free_below_2pct"]))
    assert alerts == []


def test_ops_health_non_disk_system_error_is_surfaced() -> None:
    alerts = _ops_health_error_alerts(
        _ops_health_payload(system_errors=["disk_free_below_2pct", "memory_available_below_5pct"])
    )
    assert len(alerts) == 1
    assert alerts[0]["type"] == "ops_health_system_resources"
    assert "memory_available_below_5pct" in alerts[0]["reason"]
    assert "disk_free_below_2pct" not in alerts[0]["reason"]


def test_ops_health_artifact_pipeline_external_errors_are_surfaced() -> None:
    alerts = _ops_health_error_alerts(
        _ops_health_payload(artifact_status="error", pipeline_status="error", external_status="error")
    )
    types = {alert["type"] for alert in alerts}
    assert types == {"ops_health_artifact_missing", "ops_health_pipeline", "ops_health_external_data"}
    assert all(alert["level"] == "high" for alert in alerts)


def test_ops_health_external_error_tickers_are_named_in_reason() -> None:
    # 2026-07-28 Fable audit: with only error_tickers/external_error_tickers
    # populated (the real producer shape, see collect_external_data_freshness
    # in ops_health.py), the old fallback rendered an empty ticker list and
    # the alert reason came out as "External data freshness error(s): .".
    alerts = _ops_health_error_alerts(
        _ops_health_payload(
            external_status="error",
            external_error_tickers=["^GSPC", "^TNX", "^IRX", "GC=F"],
        )
    )
    external_alerts = [a for a in alerts if a["type"] == "ops_health_external_data"]
    assert len(external_alerts) == 1
    reason = external_alerts[0]["reason"]
    for ticker in ("^GSPC", "^TNX", "^IRX", "GC=F"):
        assert ticker in reason


def test_ops_health_external_error_tickers_combine_with_error_tickers() -> None:
    alerts = _ops_health_error_alerts(
        _ops_health_payload(
            external_status="error",
            external_ticker_errors=["2330.TW"],
            external_error_tickers=["^GSPC"],
        )
    )
    external_alerts = [a for a in alerts if a["type"] == "ops_health_external_data"]
    assert len(external_alerts) == 1
    reason = external_alerts[0]["reason"]
    assert "2330.TW" in reason
    assert "^GSPC" in reason


def test_execution_plan_lag_under_a_week_is_medium() -> None:
    alerts = _ops_health_error_alerts(
        _ops_health_payload(execution_plan_freshness={"status": "stale", "lag_days": 5.0, "max_lag_days": 3})
    )
    plan_alerts = [a for a in alerts if a["type"] == "ops_health_execution_plan_stale"]
    assert len(plan_alerts) == 1
    assert plan_alerts[0]["level"] == "medium"
    assert "5.00" in plan_alerts[0]["reason"]


def test_execution_plan_lag_over_a_week_is_high() -> None:
    alerts = _ops_health_error_alerts(
        _ops_health_payload(execution_plan_freshness={"status": "stale", "lag_days": 10.14, "max_lag_days": 3})
    )
    plan_alerts = [a for a in alerts if a["type"] == "ops_health_execution_plan_stale"]
    assert len(plan_alerts) == 1
    assert plan_alerts[0]["level"] == "high"


def test_crash_risk_alert_is_advisory_only() -> None:
    alerts = _crash_risk_alerts(
        {
            "status": "available",
            "as_of": "2026-07-09",
            "alert_active": True,
            "signal_alert": {
                "type": "00631l_multisource_crash_risk",
                "level": "medium",
                "title": "00631L multi-source crash-risk alert",
                "reason": "At least two crash-risk source families are active.",
                "metadata": {"category_score": 2},
            },
        },
        signal_date="2026-07-09",
    )

    assert len(alerts) == 1
    assert alerts[0]["type"] == "00631l_multisource_crash_risk"
    assert alerts[0]["metadata"]["trade_policy"] == "advisory_no_auto_weight_change"
    assert alerts[0]["metadata"]["auto_deleverage"] is False


def test_crash_risk_stale_snapshot_alert() -> None:
    alerts = _crash_risk_alerts(
        {"status": "available", "as_of": "2026-07-07", "alert_active": True},
        signal_date="2026-07-09",
    )

    assert len(alerts) == 1
    assert alerts[0]["type"] == "00631l_crash_risk_snapshot_stale"
    assert alerts[0]["level"] == "medium"
    assert alerts[0]["metadata"]["stale_snapshot"] is True


def test_crash_risk_degraded_family_produces_watch_alert() -> None:
    alerts = _crash_risk_alerts(
        {
            "status": "available",
            "as_of": "2026-07-09",
            "alert_active": False,
            "freshness": {
                "status": "degraded",
                "stale_family_count": 1,
                "families": {
                    "options_tail": {"latest_date_at_or_before_as_of": "2026-07-09", "lag_days_vs_as_of": 0, "stale": False},
                    "liquidity_forced_selling": {"latest_date_at_or_before_as_of": "2026-07-09", "lag_days_vs_as_of": 0, "stale": False},
                    "cross_market_shock": {"latest_date_at_or_before_as_of": "2026-07-07", "lag_days_vs_as_of": 2, "stale": True},
                },
            },
        },
        signal_date="2026-07-09",
    )

    assert len(alerts) == 1
    assert alerts[0]["type"] == "00631l_crash_risk_family_degraded"
    assert alerts[0]["level"] == "watch"
    assert alerts[0]["metadata"]["stale_families"] == ["cross_market_shock"]
    assert alerts[0]["metadata"]["auto_deleverage"] is False


def test_crash_risk_degraded_family_coexists_with_active_alert() -> None:
    alerts = _crash_risk_alerts(
        {
            "status": "available",
            "as_of": "2026-07-09",
            "alert_active": True,
            "signal_alert": {
                "type": "00631l_multisource_crash_risk",
                "level": "medium",
                "title": "00631L multi-source crash-risk alert",
                "reason": "At least two crash-risk source families are active.",
                "metadata": {"category_score": 2},
            },
            "freshness": {
                "status": "degraded",
                "stale_family_count": 1,
                "families": {
                    "cross_market_shock": {"latest_date_at_or_before_as_of": "2026-07-07", "lag_days_vs_as_of": 2, "stale": True},
                },
            },
        },
        signal_date="2026-07-09",
    )

    types = [a["type"] for a in alerts]
    assert "00631l_crash_risk_family_degraded" in types
    assert "00631l_multisource_crash_risk" in types


def test_crash_risk_fresh_status_produces_no_degraded_alert() -> None:
    alerts = _crash_risk_alerts(
        {
            "status": "available",
            "as_of": "2026-07-09",
            "alert_active": False,
            "freshness": {"status": "ok", "stale_family_count": 0, "families": {}},
        },
        signal_date="2026-07-09",
    )

    assert alerts == []


def test_crash_risk_one_day_lag_is_not_stale_if_inactive() -> None:
    alerts = _crash_risk_alerts(
        {"status": "available", "as_of": "2026-07-08", "alert_active": False},
        signal_date="2026-07-09",
    )

    assert alerts == []


def test_execution_plan_fresh_produces_no_alert() -> None:
    alerts = _ops_health_error_alerts(
        _ops_health_payload(execution_plan_freshness={"status": "fresh", "lag_days": 0.5, "max_lag_days": 3})
    )
    assert not [a for a in alerts if a["type"] == "ops_health_execution_plan_stale"]


def test_update_alert_state_from_files_merges_ops_health_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        live_signal_path = tmp / "live_signal.json"
        state_path = tmp / "alert_state.json"
        ops_health_path = tmp / "ops_health.json"

        live_signal_path.write_text(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                        "actual_data_date": "2026-07-08",
                        "signal_alerts": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        ops_health_path.write_text(
            json.dumps(_ops_health_payload(pipeline_status="error")),
            encoding="utf-8",
        )

        state = update_alert_state_from_files(
            live_signal_path=live_signal_path,
            state_path=state_path,
            ops_health_path=ops_health_path,
            network_spillover_path=tmp / "missing_spillover.json",
            crash_risk_alert_path=tmp / "missing_crash_risk_alert.json",
            now_iso="2026-07-08T15:00:00Z",
        )

    assert state["summary"]["emitted_count"] == 1
    assert state["emitted_alerts"][0]["type"] == "ops_health_pipeline"


def _network_spillover_payload(*, crisis: bool, systemic: float, target_in: float) -> dict:
    return {
        "latest_snapshot": {
            "status": "available",
            "model_family": "rolling_lagged_vol_spillover_shadow",
            "date": "2026-07-09",
            "edge_density": 0.25,
            "systemic_score": 0.05,
            "systemic_percentile_252d": systemic,
            "target_in_percentile_252d": target_in,
            "crisis_regime": crisis,
        },
        "recovery_boost_gate": {
            "allow_recovery_boost": False,
            "reason": "spillover_blocked",
        },
    }


def test_network_spillover_high_snapshot_is_surfaced_as_advisory_alert() -> None:
    alerts = _network_spillover_alerts(_network_spillover_payload(crisis=True, systemic=1.0, target_in=0.996))

    assert len(alerts) == 1
    assert alerts[0]["type"] == "network_spillover_high"
    assert alerts[0]["level"] == "high"
    assert alerts[0]["metadata"]["trade_policy"] == "advisory_no_auto_weight_change"
    assert alerts[0]["metadata"]["allow_recovery_boost"] is False


def test_network_spillover_normal_snapshot_has_no_alert() -> None:
    alerts = _network_spillover_alerts(_network_spillover_payload(crisis=False, systemic=0.50, target_in=0.40))

    assert alerts == []


def test_network_spillover_stale_snapshot_is_surfaced_without_gate_decision() -> None:
    alerts = _network_spillover_alerts(
        _network_spillover_payload(crisis=True, systemic=1.0, target_in=0.996),
        signal_date="2026-07-10",
    )

    assert len(alerts) == 1
    assert alerts[0]["type"] == "network_spillover_snapshot_stale"
    assert alerts[0]["metadata"]["stale_snapshot"] is True
    assert "allow_recovery_boost" not in alerts[0]["metadata"]


def test_update_alert_state_from_files_merges_network_spillover_alert() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        live_signal_path = tmp / "live_signal.json"
        state_path = tmp / "alert_state.json"
        ops_health_path = tmp / "ops_health.json"
        spillover_path = tmp / "spillover.json"

        live_signal_path.write_text(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                        "actual_data_date": "2026-07-09",
                        "signal_alerts": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        ops_health_path.write_text(json.dumps(_ops_health_payload()), encoding="utf-8")
        spillover_path.write_text(
            json.dumps(_network_spillover_payload(crisis=True, systemic=1.0, target_in=0.996)),
            encoding="utf-8",
        )

        state = update_alert_state_from_files(
            live_signal_path=live_signal_path,
            state_path=state_path,
            ops_health_path=ops_health_path,
            network_spillover_path=spillover_path,
            crash_risk_alert_path=tmp / "missing_crash_risk_alert.json",
            now_iso="2026-07-10T02:35:00Z",
        )

    assert state["summary"]["emitted_count"] == 1
    assert state["emitted_alerts"][0]["type"] == "network_spillover_high"
