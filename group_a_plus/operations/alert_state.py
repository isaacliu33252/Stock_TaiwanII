"""Persistent alert-state tracking for GroupA+ live signals."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_LIVE_SIGNAL_PATH = Path("report/group_a_plus/latest/live_signal.json")
DEFAULT_ALERT_STATE_PATH = Path("report/group_a_plus/latest/alert_state.json")
DEFAULT_OPS_HEALTH_PATH = Path("report/group_a_plus/latest/ops_health.json")
DEFAULT_NETWORK_SPILLOVER_PATH = Path("results/group_a_plus_network_vol_spillover_shadow_latest.json")
DEFAULT_CRASH_RISK_ALERT_PATH = Path("report/group_a_plus/latest/crash_risk_alert.json")

# Fable audit (2026-07-08, #7): cooldown_key bakes in the signal date (see
# _cooldown_key), so a fixed 5-minute cooldown only ever dedupes reruns
# within the same day -- every new day is a brand-new state_key with no
# prior emission, so a still-active condition re-emits (and, once push
# notifications are on, re-pushes) on every single manual/scheduled rerun
# regardless of how recently it last fired. 20h is long enough to collapse
# same-day reruns (the pipeline normally runs once at 23:30) but short
# enough that the next day's scheduled run (~24h later) still emits fresh.
DEFAULT_COOLDOWN_MINUTES = 20 * 60

# How long a resolved alert's entry is kept in alert_state.json's "alerts"
# map after it resolves, before being pruned -- otherwise it grows without
# bound since every historical state_key (one per condition per day) is
# carried forward indefinitely once resolved.
RESOLVED_ALERT_RETENTION_DAYS = 30

# Codes with this prefix are never surfaced as alerts here -- they stay
# visible directly in ops_health.json only (excluded per user direction).
_OPS_HEALTH_EXCLUDED_CODE_PREFIXES = ("disk_",)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap_standard_json(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _condition_key(strategy_id: str, alert: dict[str, Any]) -> str:
    return f"{strategy_id}:{alert.get('type', 'unknown')}"


def _cooldown_key(strategy_id: str, signal_date: str, alert: dict[str, Any]) -> str:
    key = alert.get("cooldown_key")
    if isinstance(key, str) and key:
        return key
    return f"{strategy_id}:{signal_date}:{alert.get('type', 'unknown')}"


def _should_emit(last_emitted: datetime | None, now: datetime, cooldown_minutes: int) -> bool:
    if last_emitted is None:
        return True
    return now - last_emitted >= timedelta(minutes=max(cooldown_minutes, 0))


def _condition_last_emitted_at(previous_alerts: dict[str, Any]) -> dict[str, datetime]:
    """Latest last_emitted_at per condition_key, across all state_keys (i.e.
    across days) -- lets cooldown span day boundaries instead of resetting
    every time cooldown_key rolls over to a new signal date."""
    latest: dict[str, datetime] = {}
    for previous in previous_alerts.values():
        if not isinstance(previous, dict):
            continue
        condition_key = str(previous.get("condition_key") or "")
        last_emitted = _parse_iso(previous.get("last_emitted_at"))
        if not condition_key or last_emitted is None:
            continue
        if condition_key not in latest or last_emitted > latest[condition_key]:
            latest[condition_key] = last_emitted
    return latest


def update_alert_state(
    live_signal: dict[str, Any],
    previous_state: dict[str, Any] | None = None,
    *,
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Merge current live-signal alerts with prior persistent state.

    The output separates currently emitted alerts from alerts suppressed by
    cooldown, while preserving resolved history for auditability.
    """

    previous_state = previous_state or {}
    previous_alerts = previous_state.get("alerts", {})
    if not isinstance(previous_alerts, dict):
        previous_alerts = {}

    now_text = now_iso or _utc_now_iso()
    now = _parse_iso(now_text) or datetime.utcnow().replace(microsecond=0)
    now_text = now.replace(microsecond=0).isoformat() + "Z"

    strategy_id = str(live_signal.get("strategy_id") or "unknown_strategy")
    signal_date = str(live_signal.get("actual_data_date") or live_signal.get("requested_as_of_date") or "")
    current_alerts = live_signal.get("signal_alerts") or []
    if not isinstance(current_alerts, list):
        current_alerts = []

    merged: dict[str, Any] = {}
    emitted: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    active_condition_keys: set[str] = set()
    condition_last_emitted = _condition_last_emitted_at(previous_alerts)

    for raw_alert in current_alerts:
        if not isinstance(raw_alert, dict):
            continue
        condition_key = _condition_key(strategy_id, raw_alert)
        cooldown_key = _cooldown_key(strategy_id, signal_date, raw_alert)
        state_key = cooldown_key
        cooldown_minutes = int(raw_alert.get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES) or 0)
        previous = previous_alerts.get(state_key, {})
        if not isinstance(previous, dict):
            previous = {}

        first_seen = previous.get("first_seen_at") or now_text
        seen_count = int(previous.get("seen_count", 0) or 0) + 1
        should_emit = _should_emit(condition_last_emitted.get(condition_key), now, cooldown_minutes)
        status = "emitted" if should_emit else "suppressed"

        entry = {
            "state_key": state_key,
            "condition_key": condition_key,
            "status": status,
            "active": True,
            "resolved": False,
            "first_seen_at": first_seen,
            "last_seen_at": now_text,
            "last_emitted_at": now_text if should_emit else previous.get("last_emitted_at"),
            "seen_count": seen_count,
            "suppressed_count": int(previous.get("suppressed_count", 0) or 0) + (0 if should_emit else 1),
            "cooldown_minutes": cooldown_minutes,
            "alert": raw_alert,
        }
        merged[state_key] = entry
        active_condition_keys.add(condition_key)

        target = emitted if should_emit else suppressed
        summary = {
            "state_key": state_key,
            "condition_key": condition_key,
            "type": raw_alert.get("type"),
            "level": raw_alert.get("level"),
            "title": raw_alert.get("title"),
            "reason": raw_alert.get("reason"),
            "status": status,
        }
        if isinstance(raw_alert.get("metadata"), dict):
            summary["metadata"] = raw_alert["metadata"]
        target.append(summary)

    resolved: list[dict[str, Any]] = []
    for state_key, previous in previous_alerts.items():
        if not isinstance(previous, dict):
            continue
        condition_key = str(previous.get("condition_key") or state_key)
        if condition_key in active_condition_keys:
            continue
        if previous.get("active") is False and previous.get("resolved") is True:
            resolved_at = _parse_iso(previous.get("resolved_at"))
            if resolved_at is not None and now - resolved_at > timedelta(days=RESOLVED_ALERT_RETENTION_DAYS):
                # Prune: drop from the persisted state entirely instead of
                # carrying every historical (condition, day) pair forward
                # forever.
                continue
            merged[state_key] = previous
            continue

        resolved_entry = {
            **previous,
            "status": "resolved",
            "active": False,
            "resolved": True,
            "resolved_at": previous.get("resolved_at") or now_text,
        }
        merged[state_key] = resolved_entry
        alert = previous.get("alert", {}) if isinstance(previous.get("alert"), dict) else {}
        resolved.append(
            {
                "state_key": state_key,
                "condition_key": condition_key,
                "type": alert.get("type"),
                "level": alert.get("level"),
                "title": alert.get("title"),
                "status": "resolved",
            }
        )

    return {
        "schema_version": 1,
        "generated_at": now_text,
        "strategy_id": strategy_id,
        "signal_date": signal_date,
        "source_signal_version": live_signal.get("signal_version"),
        "summary": {
            "current_alert_count": len(current_alerts),
            "emitted_count": len(emitted),
            "suppressed_count": len(suppressed),
            "resolved_count": len(resolved),
            "active_state_count": sum(1 for item in merged.values() if isinstance(item, dict) and item.get("active") is True),
        },
        "emitted_alerts": emitted,
        "suppressed_alerts": suppressed,
        "resolved_alerts": resolved,
        "alerts": merged,
    }


def _ops_health_error_alerts(ops_health_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn ops_health.json section-level errors into signal-alert-shaped
    dicts so they flow through the same emit/cooldown/push chain as
    signal_alerts, instead of sitting unread in ops_health.json.
    """
    data = _unwrap_standard_json(ops_health_payload) if isinstance(ops_health_payload, dict) else {}
    if not isinstance(data, dict):
        return []

    alerts: list[dict[str, Any]] = []

    system_resources = data.get("system_resources") or {}
    codes = [
        code
        for code in system_resources.get("errors", [])
        if not str(code).startswith(_OPS_HEALTH_EXCLUDED_CODE_PREFIXES)
    ]
    if codes:
        alerts.append(
            {
                "type": "ops_health_system_resources",
                "level": "high",
                "title": "Ops health: system resource error",
                "reason": f"System resource error(s): {', '.join(codes)}.",
            }
        )

    artifact_health = data.get("artifact_health") or {}
    if artifact_health.get("status") == "error":
        missing = artifact_health.get("missing_required") or []
        alerts.append(
            {
                "type": "ops_health_artifact_missing",
                "level": "high",
                "title": "Ops health: required artifact missing",
                "reason": f"Required artifact(s) missing: {', '.join(missing)}.",
            }
        )

    # Fable audit (2026-07-08, #5): execution_plan.json is manually maintained
    # and intentionally not auto-regenerated (see strategy_env/ops_health
    # comments), so a growing lag has no other way to reach a human than an
    # alert -- it previously stopped at a "warning" entry inside
    # artifact_health that this same function's status=="error" check above
    # never surfaces (artifact_health.status only turns "error" when a
    # *required* file is missing, not when execution_plan is merely stale).
    execution_plan_freshness = artifact_health.get("execution_plan_freshness") or {}
    lag_days = execution_plan_freshness.get("lag_days")
    if execution_plan_freshness.get("status") == "stale" and lag_days is not None:
        max_lag_days = execution_plan_freshness.get("max_lag_days")
        level = "high" if lag_days > 7 else "medium"
        alerts.append(
            {
                "type": "ops_health_execution_plan_stale",
                "level": level,
                "title": "Ops health: execution plan stale",
                "reason": (
                    f"execution_plan.json is {lag_days:.2f} days behind live_signal.json "
                    f"(max {max_lag_days}); regenerate it manually."
                ),
            }
        )

    pipeline_health = data.get("pipeline_health") or {}
    if pipeline_health.get("status") == "error":
        errors = pipeline_health.get("errors") or []
        alerts.append(
            {
                "type": "ops_health_pipeline",
                "level": "high",
                "title": "Ops health: pipeline manifest error",
                "reason": f"Pipeline manifest error(s): {', '.join(errors)}.",
            }
        )

    external_freshness = data.get("external_data_freshness") or {}
    if external_freshness.get("status") == "error":
        errors = external_freshness.get("errors") or external_freshness.get("error_tickers") or []
        alerts.append(
            {
                "type": "ops_health_external_data",
                "level": "high",
                "title": "Ops health: external data freshness error",
                "reason": f"External data freshness error(s): {', '.join(str(e) for e in errors)}.",
            }
        )

    return alerts


def _network_spillover_alerts(
    spillover_payload: dict[str, Any],
    *,
    signal_date: str | None = None,
) -> list[dict[str, Any]]:
    """Turn the network volatility-spillover shadow snapshot into alerts.

    This is deliberately advisory-only: the source artifact is research/shadow
    and must not change target weights by itself.
    """
    if not isinstance(spillover_payload, dict):
        return []
    snapshot = spillover_payload.get("latest_snapshot") or {}
    gate = spillover_payload.get("recovery_boost_gate") or {}
    if not isinstance(snapshot, dict) or snapshot.get("status") != "available":
        return []

    snapshot_date = str(snapshot.get("date") or "")
    if signal_date and snapshot_date and snapshot_date != signal_date:
        return [
            {
                "type": "network_spillover_snapshot_stale",
                "level": "medium",
                "title": "Network spillover snapshot stale",
                "reason": (
                    "Network volatility-spillover snapshot date does not match the live signal; "
                    f"snapshot_date={snapshot_date}, signal_date={signal_date}. "
                    "Refresh the shadow snapshot before using its recovery-boost advisory."
                ),
                "metadata": {
                    "trade_policy": "advisory_no_auto_weight_change",
                    "snapshot_date": snapshot_date,
                    "signal_date": signal_date,
                    "model_family": snapshot.get("model_family"),
                    "stale_snapshot": True,
                },
            }
        ]

    systemic_pct = float(snapshot.get("systemic_percentile_252d", 0.0) or 0.0)
    target_in_pct = float(snapshot.get("target_in_percentile_252d", 0.0) or 0.0)
    crisis = bool(snapshot.get("crisis_regime", False))
    if not crisis and systemic_pct < 0.90 and target_in_pct < 0.90:
        return []

    level = "high" if crisis or systemic_pct >= 0.95 or target_in_pct >= 0.95 else "medium"
    return [
        {
            "type": "network_spillover_high",
            "level": level,
            "title": "Network volatility spillover elevated",
            "reason": (
                "Cross-asset realized-volatility spillover is elevated; "
                f"systemic percentile={systemic_pct:.3f}, 0050 in-spillover percentile={target_in_pct:.3f}. "
                "Advisory-only review of recovery 00631L boost."
            ),
            "metadata": {
                "trade_policy": "advisory_no_auto_weight_change",
                "allow_recovery_boost": bool(gate.get("allow_recovery_boost", True)),
                "gate_reason": gate.get("reason"),
                "model_family": snapshot.get("model_family"),
                "snapshot_date": snapshot.get("date"),
                "edge_density": snapshot.get("edge_density"),
                "systemic_score": snapshot.get("systemic_score"),
                "systemic_percentile_252d": systemic_pct,
                "target_in_percentile_252d": target_in_pct,
                "crisis_regime": crisis,
            },
        }
    ]


def _crash_risk_alerts(
    crash_payload: dict[str, Any],
    *,
    signal_date: str | None = None,
) -> list[dict[str, Any]]:
    """Turn the 00631L multi-source crash-risk snapshot into advisory alerts.

    The source was explicitly rejected as a trading/de-risk rule. It is only
    surfaced as alert-only context.
    """
    if not isinstance(crash_payload, dict) or crash_payload.get("status") != "available":
        return []
    snapshot_date = str(crash_payload.get("as_of") or "")
    snapshot_dt = _parse_iso(snapshot_date)
    signal_dt = _parse_iso(signal_date)
    stale = bool(
        signal_date
        and snapshot_date
        and snapshot_date != signal_date
        and snapshot_dt is not None
        and signal_dt is not None
        and signal_dt - snapshot_dt > timedelta(days=1)
    )
    if stale:
        return [
            {
                "type": "00631l_crash_risk_snapshot_stale",
                "level": "medium",
                "title": "00631L crash-risk alert snapshot stale",
                "reason": (
                    "00631L crash-risk alert snapshot date does not match the live signal; "
                    f"snapshot_date={snapshot_date}, signal_date={signal_date}."
                ),
                "metadata": {
                    "trade_policy": "advisory_no_auto_weight_change",
                    "snapshot_date": snapshot_date,
                    "signal_date": signal_date,
                    "stale_snapshot": True,
                },
            }
        ]
    alerts: list[dict[str, Any]] = []
    freshness = crash_payload.get("freshness")
    if isinstance(freshness, dict) and freshness.get("status") == "degraded":
        families = freshness.get("families") if isinstance(freshness.get("families"), dict) else {}
        stale_families = [name for name, info in families.items() if isinstance(info, dict) and info.get("stale")]
        if stale_families:
            alerts.append(
                {
                    "type": "00631l_crash_risk_family_degraded",
                    "level": "watch",
                    "title": "00631L crash-risk source data stale",
                    "reason": (
                        "One or more crash-risk source families have not updated recently, "
                        f"reducing confidence in the current watch level: {', '.join(stale_families)}."
                    ),
                    "metadata": {
                        "trade_policy": "advisory_no_auto_weight_change",
                        "auto_deleverage": False,
                        "snapshot_date": snapshot_date,
                        "stale_families": stale_families,
                        "freshness": freshness,
                    },
                }
            )
    if bool(crash_payload.get("alert_active", False)):
        alert = crash_payload.get("signal_alert")
        if isinstance(alert, dict):
            metadata = alert.get("metadata") if isinstance(alert.get("metadata"), dict) else {}
            alerts.append(
                {
                    **alert,
                    "metadata": {
                        **metadata,
                        "trade_policy": "advisory_no_auto_weight_change",
                        "auto_deleverage": False,
                        "source_snapshot": "report/group_a_plus/latest/crash_risk_alert.json",
                    },
                }
            )
    return alerts


def update_alert_state_from_files(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL_PATH,
    state_path: Path = DEFAULT_ALERT_STATE_PATH,
    ops_health_path: Path = DEFAULT_OPS_HEALTH_PATH,
    network_spillover_path: Path = DEFAULT_NETWORK_SPILLOVER_PATH,
    crash_risk_alert_path: Path = DEFAULT_CRASH_RISK_ALERT_PATH,
    output_path: Path | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    live_signal = _unwrap_standard_json(_load_json(live_signal_path))
    signal_date = str(live_signal.get("actual_data_date") or live_signal.get("requested_as_of_date") or "")
    ops_alerts = _ops_health_error_alerts(_load_json(ops_health_path) if ops_health_path.exists() else {})
    spillover_alerts = _network_spillover_alerts(
        _load_json(network_spillover_path) if network_spillover_path.exists() else {},
        signal_date=signal_date,
    )
    crash_alerts = _crash_risk_alerts(
        _load_json(crash_risk_alert_path) if crash_risk_alert_path.exists() else {},
        signal_date=signal_date,
    )
    all_extra_alerts = [*ops_alerts, *spillover_alerts, *crash_alerts]
    if all_extra_alerts:
        strategy_id = str(live_signal.get("strategy_id") or "unknown_strategy")
        existing_alerts = live_signal.get("signal_alerts") or []
        if not isinstance(existing_alerts, list):
            existing_alerts = []
        for alert in all_extra_alerts:
            alert["cooldown_key"] = f"{strategy_id}:{signal_date}:{alert['type']}"
            alert["cooldown_minutes"] = DEFAULT_COOLDOWN_MINUTES
        live_signal = {**live_signal, "signal_alerts": [*existing_alerts, *all_extra_alerts]}
    previous_state = _load_json(state_path) if state_path.exists() else {}
    state = update_alert_state(live_signal, previous_state, now_iso=now_iso)

    target = output_path or state_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state
