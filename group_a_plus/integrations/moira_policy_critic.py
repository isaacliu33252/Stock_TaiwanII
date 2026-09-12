"""Moira-style policy critic shadow for GroupA+.

The critic reads shadow diagnostic outputs and proposes review-only rule edits.
It never mutates code, target weights, or live policy. Proposals are text with
explicit validation requirements.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _proposal(
    *,
    proposal_id: str,
    source: str,
    trigger: str,
    candidate_rule: str,
    rationale: str,
    validation_required: list[str],
    priority: int,
) -> dict[str, Any]:
    return {
        "proposal_id": proposal_id,
        "source": source,
        "trigger": trigger,
        "candidate_rule": candidate_rule,
        "rationale": rationale,
        "validation_required": validation_required,
        "priority": priority,
        "status": "research_proposal_only",
        "allowed_to_apply": False,
    }


def build_moira_policy_critic(
    *,
    hierarchical_credit_review: dict[str, Any] | None = None,
    event_execution_quality: dict[str, Any] | None = None,
    relative_exposure_thesis: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    credit = hierarchical_credit_review or {}
    execution = event_execution_quality or {}
    thesis = relative_exposure_thesis or {}
    proposals: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    primary = str(credit.get("primary_attribution") or "")
    credit_evidence = set(credit.get("evidence") or [])
    execution_blockers = set(execution.get("blockers") or [])
    execution_warnings = set(execution.get("warnings") or [])
    thesis_class = str(thesis.get("thesis_class") or "")
    thesis_blockers = set(thesis.get("blocking_evidence") or [])
    quality = _as_float(execution.get("quality_score"), 1.0)

    if primary == "data_freshness_error" or "source_fresh_enough" in execution_blockers:
        proposals.append(
            _proposal(
                proposal_id="freshness_first_review_gate",
                source="hierarchical_credit_review_shadow,event_aware_execution_quality_shadow",
                trigger="forecast_or_execution_review_detects_stale_inputs",
                candidate_rule=(
                    "Before any 00631L/00632R add or large beta reduction, require source_fresh_enough "
                    "and force review-only output when business_stale_days >= 2."
                ),
                rationale="The latest credit review attributed uncertainty primarily to data freshness.",
                validation_required=[
                    "backtest stale-day filter over 2024-2026 daily previews",
                    "measure avoided false rebalance count",
                    "measure opportunity cost on rebound days",
                ],
                priority=1,
            )
        )
    if "execution_guard_satisfied" in execution_blockers or "execution_guard_not_satisfied" in credit_evidence:
        proposals.append(
            _proposal(
                proposal_id="execution_guard_hard_stop_for_new_risk",
                source="hierarchical_credit_review_shadow,event_aware_execution_quality_shadow",
                trigger="execution_guard_false",
                candidate_rule=(
                    "When execution_allowed is false, classify all new 00631L/00632R risk adds as "
                    "blocked_review_only, even if thesis or market-state evidence is supportive."
                ),
                rationale="The current review shows supportive market evidence but execution guard failure.",
                validation_required=[
                    "dry-run daily pipeline replay",
                    "verify no historical guarded candidate would be silently promoted",
                    "manual review of days with guard false and positive next-day return",
                ],
                priority=2,
            )
        )
    if "no_large_00632r_chase_without_staging" in execution_warnings:
        proposals.append(
            _proposal(
                proposal_id="large_inverse_hedge_staging_review",
                source="event_aware_execution_quality_shadow,relative_exposure_thesis_shadow",
                trigger="large_00632r_target_without_staging",
                candidate_rule=(
                    "For proposed 00632R increases above 20 percentage points, require staged execution "
                    "review and explicit max initial fraction before any guarded candidate discussion."
                ),
                rationale="A large inverse hedge may be thesis-supported but still execution-fragile.",
                validation_required=[
                    "replay staged vs full hedge adds in 2024-2026",
                    "stress test rebound whipsaw days",
                    "compare drawdown reduction against hedge decay and opportunity cost",
                ],
                priority=3,
            )
        )
    if "0050_reduction_not_aggressive_in_low_risk_bullish_state" in execution_warnings:
        proposals.append(
            _proposal(
                proposal_id="low_risk_bullish_beta_reduction_cooldown",
                source="event_aware_execution_quality_shadow",
                trigger="large_0050_reduction_in_low_risk_positive_momentum_state",
                candidate_rule=(
                    "When total_risk_score <= 2, tail_risk_score == 0, and 5-day momentum is positive, "
                    "large 0050 reductions should require an explicit hedge thesis or be staged."
                ),
                rationale="The current plan reduces 0050 while low-risk bullish evidence remains present.",
                validation_required=[
                    "compare staged vs immediate 0050 reductions",
                    "measure missed rebound participation",
                    "check 00632R hedge pairing effect",
                ],
                priority=4,
            )
        )
    if thesis_class == "short_term_inverse_hedge_review_only" and thesis_blockers:
        proposals.append(
            _proposal(
                proposal_id="hedge_thesis_blocker_echo",
                source="relative_exposure_thesis_shadow",
                trigger="inverse_hedge_thesis_supported_but_blocked",
                candidate_rule=(
                    "If 00632R thesis is short-term hedge review only and blockers exist, echo blockers "
                    "into execution quality and require human review before any hedge expansion."
                ),
                rationale="The thesis layer supports review but not live hedge expansion.",
                validation_required=[
                    "audit blocker propagation across relative thesis and execution quality outputs",
                    "verify decision fields remain false",
                ],
                priority=5,
            )
        )

    if not proposals:
        warnings.append("no_policy_change_proposal_from_current_shadow_inputs")
    if quality < 0.5:
        blockers.append("execution_quality_below_0_50")

    proposals = sorted(proposals, key=lambda row: int(row["priority"]))
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_moira_style_policy_critic_shadow",
        "policy": "research_proposals_only_no_code_change_no_weight_change",
        "as_of": as_of or str(
            execution.get("as_of") or credit.get("as_of") or thesis.get("as_of") or ""
        ),
        "paper_source": {
            "arxiv_id": "2605.01954",
            "title": "Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading",
            "mapping": "Adapt prompt-style critic into deterministic review-only candidate rule proposals.",
        },
        "status": "blocked_review_only" if blockers else "research_proposals_available",
        "proposal_count": len(proposals),
        "proposals": proposals,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs_summary": {
            "credit_primary_attribution": primary,
            "credit_evidence": sorted(credit_evidence),
            "execution_status": execution.get("status"),
            "execution_quality_score": execution.get("quality_score"),
            "execution_blockers": sorted(execution_blockers),
            "execution_warnings": sorted(execution_warnings),
            "relative_exposure_thesis_class": thesis_class,
            "relative_exposure_blockers": sorted(thesis_blockers),
        },
        "immutable_policy_contract": {
            "may_modify_code": False,
            "may_modify_target_weights": False,
            "may_create_orders": False,
            "may_promote_guarded_candidate": False,
            "requires_backtest": True,
            "requires_signed_approval": True,
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "code_change_allowed": False,
            "guarded_candidate_allowed": False,
            "signed_approval_required_before_any_candidate": True,
            "promote_to_live": False,
        },
    }


def append_moira_policy_critic_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "status": report.get("status"),
        "proposal_count": report.get("proposal_count"),
        "proposal_ids": [row.get("proposal_id") for row in report.get("proposals") or []],
        "blocking_reasons": report.get("blocking_reasons"),
        "warning_reasons": report.get("warning_reasons"),
        "inputs_summary": report.get("inputs_summary"),
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
