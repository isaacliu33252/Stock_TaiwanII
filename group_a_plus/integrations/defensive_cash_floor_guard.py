"""Guarded defensive cash-floor candidate for GroupA+.

This module prepares a formal candidate view for the validated
`cash55_risk7_tail1` rule. It is deliberately disabled by default and must not
mutate live `target_weights` unless a separate signed approval and integration
change explicitly wires it into execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_VARIANT = "cash55_risk7_tail1"
DEFAULT_CASH_FLOOR = 0.55
DEFAULT_TOTAL_RISK_MIN = 7
DEFAULT_TAIL_RISK_MIN = 1


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_weights(weights: dict[str, Any], tickers: tuple[str, ...] = DEFAULT_TICKERS) -> dict[str, float]:
    normalized = {ticker: max(0.0, _as_float(weights.get(ticker), 0.0)) for ticker in tickers}
    normalized["cash"] = max(0.0, _as_float(weights.get("cash"), 0.0))
    total = sum(normalized.values())
    if total <= 0:
        return {**{ticker: 0.0 for ticker in tickers}, "cash": 1.0}
    return {key: value / total for key, value in normalized.items()}


def raise_cash_floor(
    weights: dict[str, Any],
    *,
    cash_floor: float = DEFAULT_CASH_FLOOR,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> tuple[dict[str, float], bool]:
    """Raise cash to a floor by reducing positive risky weights pro-rata."""
    adjusted = normalize_weights(weights, tickers)
    gap = float(cash_floor) - adjusted.get("cash", 0.0)
    if gap <= 1e-12:
        return adjusted, False
    risk_tickers = [ticker for ticker in tickers if adjusted.get(ticker, 0.0) > 0]
    total_risk = sum(adjusted[ticker] for ticker in risk_tickers)
    if total_risk <= 0:
        return adjusted, False
    take = min(gap, total_risk)
    for ticker in risk_tickers:
        adjusted[ticker] -= take * adjusted[ticker] / total_risk
    adjusted["cash"] += take
    return normalize_weights(adjusted, tickers), True


def _latest_features(live_signal: dict[str, Any]) -> dict[str, Any]:
    features = live_signal.get("latest_features")
    return features if isinstance(features, dict) else {}


def _signed_review_status(review: dict[str, Any] | None) -> dict[str, Any]:
    decision = (review or {}).get("decision") if isinstance(review, dict) else {}
    return {
        "review_status": (review or {}).get("status") if isinstance(review, dict) else None,
        "signed_review_ready": bool((decision or {}).get("signed_review_ready")),
        "manual_signature_valid": bool((decision or {}).get("manual_signature_valid")),
        "allow_prepare_guarded_integration_after_signature": bool(
            (decision or {}).get("allow_prepare_guarded_integration_after_signature")
        ),
    }


def build_guarded_candidate(
    live_signal: dict[str, Any],
    *,
    signed_review: dict[str, Any] | None = None,
    enabled: bool = False,
    cash_floor: float = DEFAULT_CASH_FLOOR,
    total_risk_min: int = DEFAULT_TOTAL_RISK_MIN,
    tail_risk_min: int = DEFAULT_TAIL_RISK_MIN,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> dict[str, Any]:
    """Build a disabled-by-default candidate adjustment for a live signal."""
    target_weights = normalize_weights(dict(live_signal.get("target_weights") or {}), tickers)
    features = _latest_features(live_signal)
    execution_regime = str(live_signal.get("execution_regime") or "")
    total_risk = _as_int(features.get("total_risk_score"), 0)
    tail_risk = _as_int(features.get("tail_risk_score"), 0)
    trigger = execution_regime == "group_a_plus_defensive" and (
        total_risk >= int(total_risk_min) or tail_risk >= int(tail_risk_min)
    )
    candidate_weights, changed = raise_cash_floor(target_weights, cash_floor=cash_floor, tickers=tickers) if trigger else (
        dict(target_weights),
        False,
    )
    signed = _signed_review_status(signed_review)
    guarded_output_allowed = bool(enabled and signed["manual_signature_valid"])
    target_weight_change_allowed = bool(guarded_output_allowed and changed)
    reason_codes: list[str] = []
    if not enabled:
        reason_codes.append("candidate_disabled_by_default")
    if not signed["manual_signature_valid"]:
        reason_codes.append("manual_signature_not_valid")
    if execution_regime != "group_a_plus_defensive":
        reason_codes.append(f"execution_regime_not_defensive={execution_regime or 'unknown'}")
    elif not trigger:
        reason_codes.append("defensive_risk_threshold_not_met")
    if trigger:
        reason_codes.append("cash_floor_trigger_met")
    if changed:
        reason_codes.append("candidate_weights_differ_from_formal_target")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_defensive_cash_floor_guarded_candidate",
        "policy": "guarded_formal_candidate_disabled_by_default",
        "variant": DEFAULT_VARIANT,
        "enabled": bool(enabled),
        "can_apply_to_formal_target": target_weight_change_allowed,
        "triggered": bool(trigger),
        "changed": bool(changed),
        "reason_codes": reason_codes,
        "rule": {
            "scope": "group_a_plus_defensive_only",
            "cash_floor": float(cash_floor),
            "total_risk_min": int(total_risk_min),
            "tail_risk_min": int(tail_risk_min),
            "mechanism": "reduce positive risky ETF weights pro-rata into cash",
        },
        "inputs": {
            "requested_as_of_date": live_signal.get("requested_as_of_date"),
            "actual_data_date": live_signal.get("actual_data_date"),
            "execution_regime": execution_regime,
            "base_regime": live_signal.get("base_regime"),
            "execution_allowed": live_signal.get("execution_allowed"),
            "total_risk_score": total_risk,
            "tail_risk_score": tail_risk,
        },
        "formal_reference": {
            "target_weights": target_weights,
            "cash_weight": target_weights.get("cash", 0.0),
        },
        "candidate": {
            "target_weights": candidate_weights,
            "cash_weight": candidate_weights.get("cash", 0.0),
            "cash_floor_gap_closed": max(0.0, candidate_weights.get("cash", 0.0) - target_weights.get("cash", 0.0)),
        },
        "signed_review": signed,
        "decision": {
            "prepared_for_guarded_integration": True,
            "outputs_candidate_weights": True,
            "guarded_candidate_target_output_allowed": guarded_output_allowed,
            "manual_signature_valid": signed["manual_signature_valid"],
            "target_weight_change_allowed": target_weight_change_allowed,
            "auto_rebalance_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def append_guarded_candidate_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "variant": report.get("variant"),
        "enabled": report.get("enabled"),
        "triggered": report.get("triggered"),
        "changed": report.get("changed"),
        "can_apply_to_formal_target": report.get("can_apply_to_formal_target"),
        "inputs": report.get("inputs"),
        "formal_reference": report.get("formal_reference"),
        "candidate": report.get("candidate"),
        "decision": report.get("decision"),
        "reason_codes": report.get("reason_codes"),
    }
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("date") != date:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("date") or ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
