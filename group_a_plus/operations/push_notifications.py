"""Push notifications for GroupA+ high-severity alerts.

Closes the gap flagged in the 2026-07-04 Fable audit: the alert pipeline
(`alert_state.py`) previously only wrote emitted alerts to a JSON file, with
no channel that would actually reach a human during the unattended
23:00/23:30 daily run. This reuses the Telegram-notification pattern already
used by `FinRL/portfolio_train_v2.py` (bot API + env-var credentials), scoped
to its own env vars so it can be enabled independently of training
notifications, falling back to the FinRL credentials if set.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import Any, Callable

_SEVERITY = {"low": 0, "medium": 1, "high": 2}


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def send_telegram_message(message: str) -> bool:
    """Send a Telegram message when credentials are configured. Returns True if sent."""
    if os.getenv("GROUP_A_PLUS_ALERT_TELEGRAM_ENABLED") != "1":
        return False

    token = _env_first("GROUP_A_PLUS_ALERT_TELEGRAM_BOT_TOKEN", "FINRL_TELEGRAM_BOT_TOKEN")
    chat_id = _env_first("GROUP_A_PLUS_ALERT_TELEGRAM_CHAT_ID", "FINRL_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True
    except Exception:
        return False


def _format_alert_message(strategy_id: str, signal_date: str, alerts: list[dict[str, Any]]) -> str:
    lines = [f"<b>GroupA+ alert</b> ({strategy_id}, {signal_date})"]
    for alert in alerts:
        title = alert.get("title") or alert.get("type") or "Alert"
        reason = alert.get("reason") or ""
        lines.append(f"- {title}: {reason}")
        metadata = alert.get("metadata") if isinstance(alert.get("metadata"), dict) else {}
        if metadata.get("allow_00631l_add") is False:
            lines.append("  00631L add: blocked (advisory, no auto weight change)")
    return "\n".join(lines)


def send_alert_notifications(
    alert_state: dict[str, Any],
    *,
    min_level: str = "high",
    send_fn: Callable[[str], bool] = send_telegram_message,
) -> dict[str, Any]:
    """Push one message for this run's newly emitted alerts at/above `min_level`.

    Only `emitted_alerts` (i.e. not cooldown-suppressed) qualify, so a
    condition that is still active but within its cooldown window does not
    trigger a duplicate push.
    """
    threshold = _SEVERITY.get(min_level, _SEVERITY["high"])
    emitted = alert_state.get("emitted_alerts") or []
    qualifying = [
        alert
        for alert in emitted
        if isinstance(alert, dict) and _SEVERITY.get(str(alert.get("level")), -1) >= threshold
    ]
    if not qualifying:
        return {"sent": False, "reason": "no_qualifying_alerts", "alert_count": 0}

    message = _format_alert_message(
        str(alert_state.get("strategy_id") or "unknown_strategy"),
        str(alert_state.get("signal_date") or ""),
        qualifying,
    )
    sent = send_fn(message)
    return {"sent": sent, "alert_count": len(qualifying), "message": message}
