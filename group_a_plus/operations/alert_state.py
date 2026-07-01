"""Persistent alert-state tracking for GroupA+ live signals."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_LIVE_SIGNAL_PATH = Path("report/group_a_plus/latest/live_signal.json")
DEFAULT_ALERT_STATE_PATH = Path("report/group_a_plus/latest/alert_state.json")


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


def _should_emit(alert_state: dict[str, Any], now: datetime, cooldown_minutes: int) -> bool:
    last_emitted = _parse_iso(alert_state.get("last_emitted_at"))
    if last_emitted is None:
        return True
    return now - last_emitted >= timedelta(minutes=max(cooldown_minutes, 0))


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

    for raw_alert in current_alerts:
        if not isinstance(raw_alert, dict):
            continue
        condition_key = _condition_key(strategy_id, raw_alert)
        cooldown_key = _cooldown_key(strategy_id, signal_date, raw_alert)
        state_key = cooldown_key
        cooldown_minutes = int(raw_alert.get("cooldown_minutes", 5) or 0)
        previous = previous_alerts.get(state_key, {})
        if not isinstance(previous, dict):
            previous = {}

        first_seen = previous.get("first_seen_at") or now_text
        seen_count = int(previous.get("seen_count", 0) or 0) + 1
        should_emit = _should_emit(previous, now, cooldown_minutes)
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
        target.append(
            {
                "state_key": state_key,
                "condition_key": condition_key,
                "type": raw_alert.get("type"),
                "level": raw_alert.get("level"),
                "title": raw_alert.get("title"),
                "reason": raw_alert.get("reason"),
                "status": status,
            }
        )

    resolved: list[dict[str, Any]] = []
    for state_key, previous in previous_alerts.items():
        if not isinstance(previous, dict):
            continue
        condition_key = str(previous.get("condition_key") or state_key)
        if condition_key in active_condition_keys:
            continue
        if previous.get("active") is False and previous.get("resolved") is True:
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


def update_alert_state_from_files(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL_PATH,
    state_path: Path = DEFAULT_ALERT_STATE_PATH,
    output_path: Path | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    live_signal = _unwrap_standard_json(_load_json(live_signal_path))
    previous_state = _load_json(state_path) if state_path.exists() else {}
    state = update_alert_state(live_signal, previous_state, now_iso=now_iso)

    target = output_path or state_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state
