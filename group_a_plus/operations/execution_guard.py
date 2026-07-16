"""Pre-trade guards for GroupA+ execution plans."""

from __future__ import annotations

from typing import Any


DEFAULT_LEVERAGED_TICKER = "00631L.TW"
DEFAULT_EXTREME_WARNING_TICKERS = ("0050.TW", "00631L.TW")
VOLATILITY_GATE_ALERT_TYPE = "volatility_gate_high_vol"
TAIL_CONFORMAL_ALERT_TYPE = "tail_specific_conformal_warning"
A2118_EXTREME_RISK_ALERT_TYPE = "a2118_extreme_risk_warning"
COMPOUNDING_REGIME_BLOCKING_STATES = {"MEAN_REVERTING"}


def _volatility_gate_alert(live_signal: dict[str, Any]) -> dict[str, Any] | None:
    alerts = live_signal.get("signal_alerts") or []
    if not isinstance(alerts, list):
        return None
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        if alert.get("type") != VOLATILITY_GATE_ALERT_TYPE:
            continue
        metadata = alert.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("allow_00631l_add") is False:
            return alert
    return None


def _tail_conformal_alert(live_signal: dict[str, Any]) -> dict[str, Any] | None:
    alerts = live_signal.get("signal_alerts") or []
    if not isinstance(alerts, list):
        return None
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        if alert.get("type") != TAIL_CONFORMAL_ALERT_TYPE:
            continue
        metadata = alert.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("allow_00631l_add") is False:
            return alert
    return None


def volatility_gate_blocks_00631l_add(live_signal: dict[str, Any]) -> bool:
    """Return True when the live signal says 00631L additions are blocked."""

    if _volatility_gate_alert(live_signal) is not None:
        return True
    if _tail_conformal_alert(live_signal) is not None:
        return True

    volatility_gate = ((live_signal.get("garch_regime_shadow") or {}).get("volatility_gate") or {})
    return volatility_gate.get("high_vol_gate") is True


def _a2118_extreme_risk_alert(live_signal: dict[str, Any]) -> dict[str, Any] | None:
    alerts = live_signal.get("signal_alerts") or []
    if not isinstance(alerts, list):
        return None
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        if alert.get("type") != A2118_EXTREME_RISK_ALERT_TYPE:
            continue
        metadata = alert.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        if metadata.get("recommended_action") != "pause_new_risk_adds":
            continue
        if metadata.get("allow_new_0050_add") is False or metadata.get("allow_new_00631l_add") is False:
            return alert
    return None


def a2118_extreme_risk_blocks_new_adds(live_signal: dict[str, Any]) -> bool:
    """Return True when A21.18 warning says to pause new 0050/00631L adds."""

    if _a2118_extreme_risk_alert(live_signal) is not None:
        return True
    warning = ((live_signal.get("ncf_live_overlay") or {}).get("a2118_extreme_risk_warning") or {})
    if not isinstance(warning, dict):
        return False
    return bool(
        warning.get("active") is True
        and warning.get("recommended_action") == "pause_new_risk_adds"
    )


def apply_volatility_gate_pre_trade_guard(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    live_signal: dict[str, Any],
    *,
    ticker: str = DEFAULT_LEVERAGED_TICKER,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Block new 00631L exposure during a high-volatility advisory gate.

    This guard is deliberately narrower than a rebalance rule: it never changes
    model target weights, and it only prevents share targets above current
    holdings for the leveraged ticker. Holding or reducing 00631L remains
    executable, as do all other tickers.
    """

    guarded_targets = dict(target_shares)
    current = int(current_shares.get(ticker, 0) or 0)
    target = int(target_shares.get(ticker, current) or 0)
    alert = _volatility_gate_alert(live_signal)
    tail_alert = _tail_conformal_alert(live_signal)
    active = alert is not None or volatility_gate_blocks_00631l_add(live_signal)

    metadata = alert.get("metadata", {}) if isinstance(alert, dict) else {}
    tail_metadata = tail_alert.get("metadata", {}) if isinstance(tail_alert, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    if not isinstance(tail_metadata, dict):
        tail_metadata = {}

    guard: dict[str, Any] = {
        "name": "volatility_gate_no_00631l_add",
        "status": "inactive",
        "ticker": ticker,
        "current_shares": current,
        "requested_target_shares": target,
        "guarded_target_shares": target,
        "blocked_trades": [],
        "policy": metadata.get("trade_policy", "advisory_no_auto_weight_change"),
        "allow_00631l_add": not active,
    }

    if not active:
        return guarded_targets, guard

    guard.update(
        {
            "status": "active_allowed",
            "allow_00631l_add": False,
            "reason": (
                "high_volatility_gate_blocks_new_00631l_exposure"
                if alert is not None
                else "tail_conformal_blocks_new_00631l_exposure"
            ),
            "source_alert_type": (
                VOLATILITY_GATE_ALERT_TYPE
                if alert is not None
                else TAIL_CONFORMAL_ALERT_TYPE if tail_alert is not None else None
            ),
            "volatility_gate": metadata.get("volatility_gate"),
            "reference_00631l_scale": metadata.get("reference_00631l_scale"),
            "tail_conformal": tail_metadata if tail_alert is not None else None,
        }
    )
    if target <= current:
        return guarded_targets, guard

    guarded_targets[ticker] = current
    blocked = {
        "ticker": ticker,
        "side": "buy",
        "current_shares": current,
        "requested_target_shares": target,
        "guarded_target_shares": current,
        "blocked_delta_shares": target - current,
        "reason": "volatility_gate_no_00631l_add" if alert is not None else "tail_conformal_no_00631l_add",
    }
    guard["status"] = "blocked"
    guard["guarded_target_shares"] = current
    guard["blocked_trades"] = [blocked]
    return guarded_targets, guard


def apply_risk_add_pre_trade_guard(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    live_signal: dict[str, Any],
    *,
    tickers: tuple[str, ...] = DEFAULT_EXTREME_WARNING_TICKERS,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Block new 0050/00631L exposure under the A21.18 extreme warning.

    This is advisory-only at the model layer and pre-trade-only at execution:
    it does not alter target weights and it does not prevent holds or sells.
    """

    guarded_targets = dict(target_shares)
    alert = _a2118_extreme_risk_alert(live_signal)
    active = alert is not None or a2118_extreme_risk_blocks_new_adds(live_signal)
    metadata = alert.get("metadata", {}) if isinstance(alert, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    guard: dict[str, Any] = {
        "name": "a2118_extreme_risk_no_new_adds",
        "status": "inactive",
        "tickers": list(tickers),
        "blocked_trades": [],
        "policy": metadata.get("policy", "warning_only_no_weight_change"),
        "recommended_action": metadata.get("recommended_action", "none"),
        "source_alert_type": A2118_EXTREME_RISK_ALERT_TYPE if alert is not None else None,
    }
    if not active:
        return guarded_targets, guard

    blocked: list[dict[str, Any]] = []
    for ticker in tickers:
        current = int(current_shares.get(ticker, 0) or 0)
        target = int(target_shares.get(ticker, current) or 0)
        if target <= current:
            continue
        guarded_targets[ticker] = current
        blocked.append(
            {
                "ticker": ticker,
                "side": "buy",
                "current_shares": current,
                "requested_target_shares": target,
                "guarded_target_shares": current,
                "blocked_delta_shares": target - current,
                "reason": "a2118_extreme_risk_pause_new_adds",
            }
        )
    guard.update(
        {
            "status": "blocked" if blocked else "active_allowed",
            "recommended_action": "pause_new_risk_adds",
            "blocked_trades": blocked,
            "metadata": {
                "thresholds": metadata.get("thresholds"),
                "inputs": metadata.get("inputs"),
            },
        }
    )
    return guarded_targets, guard


def _unwrap_compounding_regime(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("latest"), dict):
        return payload["latest"]
    if isinstance(payload.get("compounding_regime_diagnostic"), dict):
        return payload["compounding_regime_diagnostic"]
    return payload


def compounding_regime_blocks_00631l_add(compounding_regime: dict[str, Any] | None) -> bool:
    """Return True when the compounding diagnostic prohibits new leverage."""

    latest = _unwrap_compounding_regime(compounding_regime)
    regime = str(latest.get("compounding_regime") or "").upper()
    policy = str(latest.get("recommended_policy") or "")
    return regime in COMPOUNDING_REGIME_BLOCKING_STATES or "prohibit_new_leverage" in policy


def apply_compounding_regime_pre_trade_guard(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    compounding_regime: dict[str, Any] | None,
    *,
    ticker: str = DEFAULT_LEVERAGED_TICKER,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Block new 00631L exposure when leveraged compounding is mean-reverting.

    The diagnostic is a leverage-addition guard only. It does not change model
    weights and it never forces 00631L reductions.
    """

    latest = _unwrap_compounding_regime(compounding_regime)
    guarded_targets = dict(target_shares)
    current = int(current_shares.get(ticker, 0) or 0)
    target = int(target_shares.get(ticker, current) or 0)
    active = compounding_regime_blocks_00631l_add(compounding_regime)
    guard: dict[str, Any] = {
        "name": "compounding_regime_no_00631l_add",
        "status": "inactive",
        "ticker": ticker,
        "current_shares": current,
        "requested_target_shares": target,
        "guarded_target_shares": target,
        "blocked_trades": [],
        "policy": "diagnostic_no_auto_weight_change",
        "allow_00631l_add": not active,
        "compounding_regime": latest.get("compounding_regime"),
        "recommended_policy": latest.get("recommended_policy"),
        "date": latest.get("date"),
    }
    if not latest:
        guard["status"] = "unavailable"
        guard["reason"] = "compounding_regime_unavailable"
        return guarded_targets, guard
    if not active:
        return guarded_targets, guard

    guard.update(
        {
            "status": "active_allowed",
            "allow_00631l_add": False,
            "reason": "compounding_regime_blocks_new_00631l_exposure",
        }
    )
    if target <= current:
        return guarded_targets, guard

    guarded_targets[ticker] = current
    blocked = {
        "ticker": ticker,
        "side": "buy",
        "current_shares": current,
        "requested_target_shares": target,
        "guarded_target_shares": current,
        "blocked_delta_shares": target - current,
        "reason": "compounding_regime_no_00631l_add",
    }
    guard["status"] = "blocked"
    guard["guarded_target_shares"] = current
    guard["blocked_trades"] = [blocked]
    return guarded_targets, guard
