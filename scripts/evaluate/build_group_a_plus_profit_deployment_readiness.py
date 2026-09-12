#!/usr/bin/env python3
"""Build a profit deployment readiness report for Group A+.

This report consolidates shadow-only profit-improvement candidates with the
current operational gates that decide whether any candidate can be promoted to
live execution. It does not alter live signals, target weights, or order files.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "profit_deployment_readiness.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "profit_deployment_readiness.md"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"

DEFAULT_INPUTS = {
    "ops_health": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ops_health.json",
    "broker_reconciliation": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_reconciliation_review.json",
    "broker_holding_scope": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holding_scope_review.json",
    "deployment_summary": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_summary.json",
    "daily_artifact_integrity": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_artifact_integrity.json",
    "execution_plan_promotion": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "execution_plan_promotion_readiness.json",
    "staged_reentry": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "staged_reentry_shadow.json",
    "a2120_small_00631l": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2120_small_00631l_reentry_shadow.json",
    "a2118_seed_averaging": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_shadow.json",
    "gjr_post_trigger": PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_post_trigger_severity_shadow.json",
    "tail_sensitive_scorecard_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_tail_sensitive_scorecard.json",
    "turnover_cost_robustness_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_turnover_cost_robustness.json",
    "candidate_tail_review_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_candidate_tail_review.json",
    "staged_reentry_promotion_review": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "staged_reentry_promotion_review.json",
    "regime_switching_volatility_gate_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_regime_switching_volatility_gate.json",
    "tail_dependence_monitor_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_tail_dependence_monitor.json",
    "geopolitical_cvar_overlay_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_geopolitical_cvar_overlay.json",
    "bootstrap_promotion_gate_2607_16450": PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "2607_16450_bootstrap_promotion_gate.json",
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_optional(path: str | Path) -> tuple[dict[str, Any], str | None]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}, f"missing:{resolved}"
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}, f"invalid_json_object:{resolved}"
    return payload, None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _shadow_candidate(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    status = str(payload.get("status") or decision.get("shadow_gate") or "missing")
    queue = str(payload.get("shadow_queue") or decision.get("shadow_queue") or "")
    recommended = payload.get("recommended_shadow_action") or payload.get("recommended_action") or decision.get("reason")
    active = status in {"active_shadow_candidate", "pass", "passed"} or queue == "candidate_for_forward_shadow_monitoring"
    return {
        "name": name,
        "status": status,
        "active_for_profit_review": bool(active),
        "actual_data_date": payload.get("actual_data_date") or payload.get("date"),
        "recommended_shadow_action": recommended,
        "blockers": _as_list(payload.get("blockers") or payload.get("production_blockers") or decision.get("production_blockers")),
        "warnings": _as_list(payload.get("warnings")),
        "live_execution_effect": payload.get("live_execution_effect") or payload.get("policy"),
    }


def _tail_sensitive_review(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "use_for_promotion_review": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_scorecard": False,
            "top_reference": None,
            "warning_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    ranked = payload.get("ranked_references") if isinstance(payload.get("ranked_references"), list) else []
    top = ranked[0] if ranked and isinstance(ranked[0], dict) else {}
    return {
        "status": payload.get("status"),
        "use_for_promotion_review": bool(decision.get("use_for_promotion_review")),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "allow_00631l_add_from_scorecard": bool(decision.get("allow_00631l_add_from_scorecard")),
        "top_reference": top.get("strategy"),
        "top_reference_score": top.get("score"),
        "warning_reasons": _as_list(payload.get("warning_reasons")),
    }


def _cost_robustness_review(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "promote_dynamic_cvar_optimizer": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_cost_sweep": False,
            "blocking_reasons": [],
            "warning_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    return {
        "status": payload.get("status"),
        "promote_dynamic_cvar_optimizer": bool(decision.get("promote_dynamic_cvar_optimizer")),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "allow_00631l_add_from_cost_sweep": bool(decision.get("allow_00631l_add_from_cost_sweep")),
        "blocking_reasons": _as_list(payload.get("blocking_reasons")),
        "warning_reasons": _as_list(payload.get("warning_reasons")),
    }


def _candidate_tail_review(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "live_ready_candidates": [],
            "allow_00631l_add_from_candidate_tail_review": False,
            "candidate_statuses": {},
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    reviews = payload.get("candidate_reviews") if isinstance(payload.get("candidate_reviews"), list) else []
    return {
        "status": payload.get("status"),
        "live_ready_candidates": _as_list(payload.get("live_ready_candidates")),
        "allow_00631l_add_from_candidate_tail_review": bool(
            decision.get("allow_00631l_add_from_candidate_tail_review")
        ),
        "candidate_statuses": {
            str(row.get("name")): row.get("tail_review_status")
            for row in reviews
            if isinstance(row, dict) and row.get("name")
        },
    }


def _staged_reentry_promotion_review(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "target_weight_change_allowed": False,
            "active_event_count": None,
            "blocking_reasons": [],
            "warning_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    event_study = payload.get("event_study") if isinstance(payload.get("event_study"), dict) else {}
    return {
        "status": payload.get("status"),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "active_event_count": event_study.get("active_event_count"),
        "forward_edge_counts": event_study.get("forward_edge_counts"),
        "blocking_reasons": _as_list(payload.get("blocking_reasons")),
        "warning_reasons": _as_list(payload.get("warning_reasons")),
    }


def _regime_switching_volatility_gate(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "promote_regime_switching_volatility_gate": False,
            "target_weight_change_allowed": False,
            "blocking_reasons": [],
            "warning_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    return {
        "status": payload.get("status"),
        "promote_regime_switching_volatility_gate": bool(
            decision.get("promote_regime_switching_volatility_gate")
        ),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "allow_00631l_add_from_regime_gate": bool(decision.get("allow_00631l_add_from_regime_gate")),
        "blocking_reasons": _as_list(payload.get("blocking_reasons")),
        "warning_reasons": _as_list(payload.get("warning_reasons")),
    }


def _tail_dependence_monitor(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "allow_00631l_add_from_tail_dependence": False,
            "high_tail_dependence_assets": [],
            "blocking_reasons": [],
            "warning_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    pairs = payload.get("high_tail_dependence_pairs") if isinstance(payload.get("high_tail_dependence_pairs"), list) else []
    return {
        "status": payload.get("status"),
        "promote_dynamic_copula_gate": bool(decision.get("promote_dynamic_copula_gate")),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "allow_00631l_add_from_tail_dependence": bool(decision.get("allow_00631l_add_from_tail_dependence")),
        "high_tail_dependence_assets": [
            str(row.get("asset")) for row in pairs if isinstance(row, dict) and row.get("asset")
        ],
        "blocking_reasons": _as_list(payload.get("blocking_reasons")),
        "warning_reasons": _as_list(payload.get("warning_reasons")),
    }


def _geopolitical_cvar_overlay(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "state": None,
            "cvar_penalty_multiplier": None,
            "advisory_max_00631l_weight": None,
            "allow_00631l_add_from_geopolitical_overlay": False,
            "blocking_reasons": [],
            "warning_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    overlay = payload.get("overlay") if isinstance(payload.get("overlay"), dict) else {}
    return {
        "status": payload.get("status"),
        "state": score.get("state"),
        "cvar_penalty_multiplier": overlay.get("cvar_penalty_multiplier"),
        "advisory_max_00631l_weight": overlay.get("advisory_max_00631l_weight"),
        "promote_geopolitical_cvar_overlay": bool(decision.get("promote_geopolitical_cvar_overlay")),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "allow_00631l_add_from_geopolitical_overlay": bool(
            decision.get("allow_00631l_add_from_geopolitical_overlay")
        ),
        "blocking_reasons": _as_list(payload.get("blocking_reasons")),
        "warning_reasons": _as_list(payload.get("warning_reasons")),
    }


def _bootstrap_promotion_gate(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "status": "missing",
            "live_ready_candidates": [],
            "allow_00631l_add_from_bootstrap_gate": False,
            "blocking_reasons": [],
        }
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    return {
        "status": payload.get("status"),
        "live_ready_candidates": _as_list(payload.get("live_ready_candidates")),
        "promotion_allowed": bool(decision.get("promotion_allowed")),
        "target_weight_change_allowed": bool(decision.get("target_weight_change_allowed")),
        "allow_00631l_add_from_bootstrap_gate": bool(decision.get("allow_00631l_add_from_bootstrap_gate")),
        "blocking_reasons": _as_list(payload.get("blocking_reasons")),
    }


def _ops_blockers(ops: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(ops.get("status") or "").lower() in {"error", "blocked"}:
        blockers.append("ops_health_not_ok")
    blockers.extend(f"ops_health_error:{item}" for item in _as_list(ops.get("errors")))
    return blockers


def _artifact_blockers(integrity: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(integrity.get("status") or "").lower() in {"error", "blocked"}:
        blockers.append("daily_artifact_integrity_not_ok")
    blockers.extend(f"artifact_integrity_error:{item}" for item in _as_list(integrity.get("errors")))
    return blockers


def _broker_blockers(broker: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(broker.get("status") or "").lower() in {"blocked", "error"}:
        blockers.append("broker_reconciliation_not_actionable")
    blockers.extend(f"broker_reconciliation:{item}" for item in _as_list(broker.get("blocking_reasons")))
    decision = broker.get("decision") if isinstance(broker.get("decision"), dict) else {}
    if decision.get("can_generate_live_orders") is False:
        blockers.append("broker_decision_disallows_live_orders")
    if decision.get("target_weight_change_allowed") is False:
        blockers.append("broker_decision_disallows_target_weight_change")
    return blockers


def _broker_scope_blockers(scope: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not scope:
        return blockers
    if str(scope.get("status") or "").startswith("blocked"):
        blockers.append("broker_holding_scope_not_clear")
    blockers.extend(f"broker_holding_scope:{item}" for item in _as_list(scope.get("blockers")))
    out_of_scope = scope.get("out_of_universe_nonzero_holdings")
    if isinstance(out_of_scope, dict):
        blockers.extend(f"broker_holding_scope_out_of_universe:{ticker}" for ticker in sorted(out_of_scope))
    return blockers


def _deployment_blockers(deployment: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(deployment.get("status") or "").lower() in {"blocked", "error"}:
        blockers.append("deployment_summary_blocked")
    if deployment.get("broker_actionable") is False:
        blockers.append("deployment_summary_not_broker_actionable")
    blockers.extend(f"deployment_summary:{item}" for item in _as_list(deployment.get("blocking_reasons")))
    return blockers


def _execution_plan_promotion_blockers(promotion: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not promotion:
        return blockers
    if str(promotion.get("status") or "") == "blocked":
        blockers.append("execution_plan_promotion_not_ready")
    blockers.extend(f"execution_plan_promotion:{item}" for item in _as_list(promotion.get("blockers")))
    return blockers


def _recommended_next_actions(
    *,
    status: str,
    live_blocked: bool,
    live_ready_candidates: list[str],
    active_candidates: list[str],
    staged_promotion_review: dict[str, Any],
    candidate_tail_review: dict[str, Any],
) -> list[str]:
    if status == "shadow_candidates_blocked_for_live_promotion":
        actions = [
            "continue shadow monitoring; do not prepare target-weight changes until a candidate becomes live-ready",
            "accumulate staged_reentry forward edge rows until promotion review minimums are met",
            "accumulate A21.18 forward shadow parity rows until promotion gate minimums are met",
            "keep 00631L additions blocked unless candidate tail review produces a live-ready candidate",
        ]
        if staged_promotion_review.get("status") == "blocked_for_live_promotion":
            actions.append("rerun staged_reentry event study after new signal dates create 5d/10d/20d forward edge rows")
        if candidate_tail_review.get("status") == "available":
            actions.append("rerun candidate tail review after staged_reentry and A21.18 monitors add new rows")
        return actions

    if live_blocked:
        return [
            "refresh institutional and feature tables until ops_health has no errors",
            "rebuild execution-plan artifacts from the same actual_data_date as the live signal",
            "provide authoritative broker holdings and cash export before allowing live order generation",
            "resolve signed approval and pre-trade guard blockers before promotion",
            "rerun ops_health, daily_artifact_integrity, broker reconciliation, and deployment_summary after fixes",
        ]

    if live_ready_candidates:
        return [
            "run human promotion review only for live_ready_shadow_candidates",
            "confirm broker holdings and execution-plan artifacts match the same actual_data_date before any order generation",
            "rerun candidate tail review and promotion gates immediately before approving target-weight changes",
        ]

    if active_candidates:
        return [
            "continue shadow monitoring for active candidates",
            "do not prepare target-weight changes until promotion gates produce live_ready_shadow_candidates",
        ]

    return [
        "continue daily monitoring until a shadow candidate becomes active",
        "rerun profit deployment readiness after daily signal and shadow artifacts refresh",
    ]


def build_profit_deployment_readiness(
    *,
    ops_health: dict[str, Any],
    broker_reconciliation: dict[str, Any],
    broker_holding_scope: dict[str, Any],
    deployment_summary: dict[str, Any],
    daily_artifact_integrity: dict[str, Any],
    execution_plan_promotion: dict[str, Any],
    staged_reentry: dict[str, Any],
    a2120_small_00631l: dict[str, Any],
    a2118_seed_averaging: dict[str, Any],
    gjr_post_trigger: dict[str, Any],
    tail_sensitive_scorecard_2607_16450: dict[str, Any] | None = None,
    turnover_cost_robustness_2607_16450: dict[str, Any] | None = None,
    candidate_tail_review_2607_16450: dict[str, Any] | None = None,
    staged_reentry_promotion_review: dict[str, Any] | None = None,
    regime_switching_volatility_gate_2607_16450: dict[str, Any] | None = None,
    tail_dependence_monitor_2607_16450: dict[str, Any] | None = None,
    geopolitical_cvar_overlay_2607_16450: dict[str, Any] | None = None,
    bootstrap_promotion_gate_2607_16450: dict[str, Any] | None = None,
    input_errors: list[str] | None = None,
) -> dict[str, Any]:
    shadow_candidates = [
        _shadow_candidate("staged_reentry", staged_reentry),
        _shadow_candidate("a2120_small_00631l", a2120_small_00631l),
        _shadow_candidate("a2118_seed_averaging", a2118_seed_averaging),
        _shadow_candidate("gjr_post_trigger", gjr_post_trigger),
    ]
    tail_review = _tail_sensitive_review(tail_sensitive_scorecard_2607_16450 or {})
    cost_review = _cost_robustness_review(turnover_cost_robustness_2607_16450 or {})
    candidate_tail_review = _candidate_tail_review(candidate_tail_review_2607_16450 or {})
    staged_promotion_review = _staged_reentry_promotion_review(staged_reentry_promotion_review or {})
    regime_vol_gate = _regime_switching_volatility_gate(regime_switching_volatility_gate_2607_16450 or {})
    tail_dependence_monitor = _tail_dependence_monitor(tail_dependence_monitor_2607_16450 or {})
    geopolitical_cvar_overlay = _geopolitical_cvar_overlay(geopolitical_cvar_overlay_2607_16450 or {})
    bootstrap_gate = _bootstrap_promotion_gate(bootstrap_promotion_gate_2607_16450 or {})
    active_candidates = [item["name"] for item in shadow_candidates if item["active_for_profit_review"]]
    deployment_blockers = _unique(
        list(input_errors or [])
        + _ops_blockers(ops_health)
        + _artifact_blockers(daily_artifact_integrity)
        + _execution_plan_promotion_blockers(execution_plan_promotion)
        + _broker_blockers(broker_reconciliation)
        + _broker_scope_blockers(broker_holding_scope)
        + _deployment_blockers(deployment_summary)
    )
    warnings = _unique(
        [f"ops_health_warning:{item}" for item in _as_list(ops_health.get("warnings"))]
        + [f"deployment_summary_warning:{item}" for item in _as_list(deployment_summary.get("warning_reasons"))]
        + [
            f"tail_sensitive_scorecard_2607_16450:{item}"
            for item in _as_list(tail_review.get("warning_reasons"))
        ]
        + [
            f"turnover_cost_robustness_2607_16450:{item}"
            for item in _as_list(cost_review.get("blocking_reasons"))
        ]
        + [
            f"turnover_cost_robustness_2607_16450:{item}"
            for item in _as_list(cost_review.get("warning_reasons"))
        ]
        + [
            f"staged_reentry_promotion_review:{item}"
            for item in _as_list(staged_promotion_review.get("blocking_reasons"))
        ]
        + [
            f"regime_switching_volatility_gate_2607_16450:{item}"
            for item in _as_list(regime_vol_gate.get("blocking_reasons"))
        ]
        + [
            f"regime_switching_volatility_gate_2607_16450:{item}"
            for item in _as_list(regime_vol_gate.get("warning_reasons"))
        ]
        + [
            f"tail_dependence_monitor_2607_16450:{item}"
            for item in _as_list(tail_dependence_monitor.get("blocking_reasons"))
        ]
        + [
            f"tail_dependence_monitor_2607_16450:{item}"
            for item in _as_list(tail_dependence_monitor.get("warning_reasons"))
        ]
        + [
            f"geopolitical_cvar_overlay_2607_16450:{item}"
            for item in _as_list(geopolitical_cvar_overlay.get("blocking_reasons"))
        ]
        + [
            f"geopolitical_cvar_overlay_2607_16450:{item}"
            for item in _as_list(geopolitical_cvar_overlay.get("warning_reasons"))
        ]
        + [
            f"bootstrap_promotion_gate_2607_16450:{item}"
            for item in _as_list(bootstrap_gate.get("blocking_reasons"))
        ]
    )

    live_blocked = bool(deployment_blockers)
    candidate_tail_available = candidate_tail_review.get("status") == "available"
    live_ready_candidates = [
        str(item)
        for item in _as_list(candidate_tail_review.get("live_ready_candidates"))
        if str(item) in set(active_candidates)
    ] if candidate_tail_available else list(active_candidates)
    if active_candidates and live_blocked:
        status = "blocked_profit_candidates_exist"
        profit_impact = "actionable_shadow_candidates_exist_but_live_execution_blocked"
    elif active_candidates and candidate_tail_available and not live_ready_candidates:
        status = "shadow_candidates_blocked_for_live_promotion"
        profit_impact = "shadow_candidates_exist_but_candidate_tail_review_blocks_live_promotion"
    elif active_candidates:
        status = "ready_for_promotion_review"
        profit_impact = "shadow_candidates_available_for_human_promotion_review"
    elif live_blocked:
        status = "blocked_no_active_profit_candidate"
        profit_impact = "no_current_shadow_candidate_and_live_execution_blocked"
    else:
        status = "monitoring"
        profit_impact = "no_current_shadow_candidate"

    decision = {
        "creates_orders": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "shadow_monitoring_allowed": True,
        "requires_human_promotion_review": bool(live_ready_candidates),
    }
    if not live_blocked and live_ready_candidates:
        decision["target_weight_change_allowed"] = "human_review_required"
    recommended_next_actions = _recommended_next_actions(
        status=status,
        live_blocked=live_blocked,
        live_ready_candidates=live_ready_candidates,
        active_candidates=active_candidates,
        staged_promotion_review=staged_promotion_review,
        candidate_tail_review=candidate_tail_review,
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_profit_deployment_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_or_order_change",
        "live_execution_effect": "none",
        "status": status,
        "profit_impact": profit_impact,
        "active_shadow_candidates": active_candidates,
        "live_ready_shadow_candidates": live_ready_candidates,
        "shadow_candidates": shadow_candidates,
        "tail_sensitive_review": tail_review,
        "turnover_cost_robustness_review": cost_review,
        "candidate_tail_review": candidate_tail_review,
        "staged_reentry_promotion_review": staged_promotion_review,
        "regime_switching_volatility_gate": regime_vol_gate,
        "tail_dependence_monitor": tail_dependence_monitor,
        "geopolitical_cvar_overlay": geopolitical_cvar_overlay,
        "bootstrap_promotion_gate": bootstrap_gate,
        "deployment_blockers": deployment_blockers,
        "warnings": warnings,
        "decision": decision,
        "recommended_next_actions": recommended_next_actions,
        "source_status": {
            "ops_health": ops_health.get("status"),
            "broker_reconciliation": broker_reconciliation.get("status"),
            "broker_holding_scope": broker_holding_scope.get("status"),
            "deployment_summary": deployment_summary.get("status"),
            "daily_artifact_integrity": daily_artifact_integrity.get("status"),
            "execution_plan_promotion": execution_plan_promotion.get("status"),
            "tail_sensitive_scorecard_2607_16450": tail_review.get("status"),
            "turnover_cost_robustness_2607_16450": cost_review.get("status"),
            "candidate_tail_review_2607_16450": candidate_tail_review.get("status"),
            "staged_reentry_promotion_review": staged_promotion_review.get("status"),
            "regime_switching_volatility_gate_2607_16450": regime_vol_gate.get("status"),
            "tail_dependence_monitor_2607_16450": tail_dependence_monitor.get("status"),
            "geopolitical_cvar_overlay_2607_16450": geopolitical_cvar_overlay.get("status"),
            "bootstrap_promotion_gate_2607_16450": bootstrap_gate.get("status"),
        },
    }


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Group A+ Profit Deployment Readiness",
        "",
        f"- Status: `{payload['status']}`",
        f"- Profit impact: `{payload['profit_impact']}`",
        f"- Live effect: `{payload['live_execution_effect']}`",
        f"- Active shadow candidates: `{', '.join(payload['active_shadow_candidates']) or 'none'}`",
        f"- Tail-sensitive review: `{payload.get('tail_sensitive_review', {}).get('status', 'missing')}`",
        f"- Tail top reference: `{payload.get('tail_sensitive_review', {}).get('top_reference') or 'none'}`",
        f"- CVaR cost robustness: `{payload.get('turnover_cost_robustness_review', {}).get('status', 'missing')}`",
        f"- Candidate tail review: `{payload.get('candidate_tail_review', {}).get('status', 'missing')}`",
        f"- Staged re-entry promotion: `{payload.get('staged_reentry_promotion_review', {}).get('status', 'missing')}`",
        f"- Regime volatility gate: `{payload.get('regime_switching_volatility_gate', {}).get('status', 'missing')}`",
        f"- Tail-dependence monitor: `{payload.get('tail_dependence_monitor', {}).get('status', 'missing')}`",
        f"- Geopolitical CVaR overlay: `{payload.get('geopolitical_cvar_overlay', {}).get('status', 'missing')}`",
        f"- Bootstrap promotion gate: `{payload.get('bootstrap_promotion_gate', {}).get('status', 'missing')}`",
        "",
        "## Deployment Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["deployment_blockers"])
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in payload["recommended_next_actions"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, path in DEFAULT_INPUTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", default=str(path))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    args = parser.parse_args()

    inputs: dict[str, dict[str, Any]] = {}
    input_errors: list[str] = []
    for name in DEFAULT_INPUTS:
        payload, error = _load_optional(getattr(args, name))
        inputs[name] = payload
        if error:
            input_errors.append(error)

    payload = build_profit_deployment_readiness(input_errors=input_errors, **inputs)

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(_resolve(args.output_md), payload)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = _resolve(args.results_dir) / f"group_a_plus_profit_deployment_readiness_{stamp}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "result_path": str(result_path), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
