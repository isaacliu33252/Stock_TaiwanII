"""Relative exposure thesis shadow review for GroupA+ ETF legs.

Inspired by Moira's hierarchical selector/trader split, but adapted to
GroupA+'s existing ETF universe. This is not pair trading and does not emit
orders. It reviews whether the relationship among 0050/00631L/00632R/cash is
coherent with current risk and market-state inputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


THESIS_CLASSES = (
    "leverage_expansion_thesis_supported",
    "maintain_unlevered_beta_preferred",
    "delever_to_cash_or_0050",
    "short_term_inverse_hedge_review_only",
    "thesis_conflicted_no_new_risk",
)


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


def _signal_alignment(live_signal: dict[str, Any]) -> tuple[str, str]:
    value = live_signal.get("signal_alignment")
    if isinstance(value, dict):
        return str(value.get("alignment") or ""), str(value.get("dominant_direction") or "")
    return str(value or ""), str(live_signal.get("dominant_direction") or "")


def _target_weights(live_signal: dict[str, Any]) -> dict[str, float]:
    raw = live_signal.get("target_weights") or {}
    return {
        "0050.TW": _as_float(raw.get("0050.TW"), 0.0),
        "00631L.TW": _as_float(raw.get("00631L.TW"), 0.0),
        "00632R.TW": _as_float(raw.get("00632R.TW"), 0.0),
        "00679B.TWO": _as_float(raw.get("00679B.TWO"), 0.0),
        "cash": _as_float(raw.get("cash"), 0.0),
    }


def build_relative_exposure_thesis(live_signal: dict[str, Any]) -> dict[str, Any]:
    features = live_signal.get("latest_features") if isinstance(live_signal.get("latest_features"), dict) else {}
    market_state = live_signal.get("market_state") if isinstance(live_signal.get("market_state"), dict) else {}
    weights = _target_weights(live_signal)
    alignment, dominant_direction = _signal_alignment(live_signal)
    execution_regime = str(live_signal.get("execution_regime") or "")
    execution_allowed = live_signal.get("execution_allowed")
    business_stale_days = _as_int(live_signal.get("business_stale_days"), 0)
    total_risk = _as_int(features.get("total_risk_score"), 0)
    tail_risk = _as_int(features.get("tail_risk_score"), 0)
    ma_gap = _as_float(features.get("ma_gap"), 0.0)
    drawdown = _as_float(features.get("drawdown"), 0.0)
    momentum_5d = _as_float(features.get("exit_momentum_5d"), 0.0)

    reason_codes: list[str] = []
    supports: list[str] = []
    blockers: list[str] = []

    if execution_allowed is False:
        blockers.append("execution_guard_not_satisfied")
    if business_stale_days >= 2:
        blockers.append(f"business_stale_days={business_stale_days}")
    if alignment in {"wide_divergence", "mixed", "conflicted", "divergent"}:
        blockers.append(f"signal_alignment_conflicted={alignment}")
    if dominant_direction == "bullish" or alignment == "bullish_alignment":
        supports.append("bullish_signal_alignment")
    if total_risk <= 2 and tail_risk == 0:
        supports.append("low_tail_and_total_risk")
    if momentum_5d > 0:
        supports.append("positive_5d_momentum")
    if ma_gap > 0:
        supports.append("price_above_moving_average")
    if drawdown <= -0.08:
        blockers.append("drawdown_deep_enough_for_reentry_caution")

    inverse_weight = weights["00632R.TW"]
    leverage_weight = weights["00631L.TW"]
    cash_weight = weights["cash"]

    if inverse_weight >= 0.05:
        thesis = "short_term_inverse_hedge_review_only"
        reason_codes.append("current_00632r_weight_present")
        quality = 0.55 if total_risk >= 5 or tail_risk >= 1 or execution_allowed is False else 0.40
    elif execution_regime == "group_a_plus_defensive" or total_risk >= 7 or tail_risk >= 1:
        thesis = "delever_to_cash_or_0050"
        reason_codes.append("defensive_or_tail_risk_context")
        quality = 0.75 if cash_weight >= 0.45 else 0.60
    elif blockers:
        thesis = "thesis_conflicted_no_new_risk"
        reason_codes.append("new_risk_blocked_by_context")
        quality = 0.35
    elif supports and len(supports) >= 4 and leverage_weight <= 0.10:
        thesis = "leverage_expansion_thesis_supported"
        reason_codes.append("low_risk_bullish_context_supports_leverage")
        quality = 0.70
    else:
        thesis = "maintain_unlevered_beta_preferred"
        reason_codes.append("insufficient_support_for_new_leverage_or_hedge")
        quality = 0.55

    if leverage_weight > 0:
        reason_codes.append("current_00631l_weight_present")
    if cash_weight >= 0.40:
        reason_codes.append("cash_buffer_material")
    if market_state.get("state"):
        reason_codes.append(f"market_state={market_state.get('state')}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_relative_exposure_thesis_shadow",
        "policy": "shadow_only_no_target_weight_change",
        "paper_source": {
            "arxiv_id": "2605.01954",
            "title": "Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading",
            "mapping": "Adapt semantic pair-selection insight to 0050/00631L/00632R/cash relative exposure thesis; not market-neutral pair trading.",
        },
        "thesis_class": thesis,
        "thesis_quality_score": round(float(quality), 4),
        "reason_codes": sorted(set(reason_codes)),
        "supporting_evidence": sorted(set(supports)),
        "blocking_evidence": sorted(set(blockers)),
        "inputs": {
            "requested_as_of_date": live_signal.get("requested_as_of_date"),
            "actual_data_date": live_signal.get("actual_data_date"),
            "business_stale_days": business_stale_days,
            "execution_allowed": execution_allowed,
            "execution_regime": execution_regime,
            "base_regime": live_signal.get("base_regime"),
            "market_state": market_state.get("state"),
            "market_state_label": market_state.get("label_zh"),
            "signal_alignment": alignment,
            "dominant_direction": dominant_direction,
            "total_risk_score": total_risk,
            "tail_risk_score": tail_risk,
            "ma_gap": ma_gap,
            "drawdown": drawdown,
            "exit_momentum_5d": momentum_5d,
            "target_weights": weights,
        },
        "interpretation": {
            "0050_00631l_relation": "same underlying beta with leverage/path dependency, not a normal cointegration spread",
            "00632r_relation": "inverse hedge leg; review-only and short-term by default",
            "cash_relation": "active risk buffer for thesis conflict, stale data, or defensive contexts",
        },
        "decision": {
            "shadow_ready": True,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "requires_backtest_before_guarded_candidate": True,
        },
    }


def append_relative_exposure_thesis_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "thesis_class": report.get("thesis_class"),
        "thesis_quality_score": report.get("thesis_quality_score"),
        "reason_codes": report.get("reason_codes"),
        "supporting_evidence": report.get("supporting_evidence"),
        "blocking_evidence": report.get("blocking_evidence"),
        "inputs": report.get("inputs"),
        "decision": report.get("decision"),
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
