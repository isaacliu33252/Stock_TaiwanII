#!/usr/bin/env python3
"""Triage research-shadow blockers for a future GIFT shadow-training exception.

The consolidated research-shadow snapshot can be blocked for many reasons that
primarily guard live leverage, inverse hedges, or broker-action promotion. This
artifact classifies those blockers for a future human exception review. It does
not grant an exception, train a model, run PPO, emit target weights, or change
live GroupA+ strategy state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_research_shadow_decision_snapshot import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_RESEARCH_SHADOW,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_research_shadow_blocker_triage.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_research_shadow_blocker_triage/history"
DEFAULT_MANUAL_APPROVAL = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_manual_approval_readiness_review.json"
)

LIVE_ALLOCATION_BLOCKERS = {
    "finstressts_snapshot_blocked",
    "trigate_vol_memory_blocks_leverage_add",
    "illiquidity_network_readiness_blocked",
    "speculative_influence_network_readiness_blocked",
    "sin_lite_proxy_blocked",
    "hmm_wj_synthetic_scenario_readiness_blocked",
    "dynamic_cvar_tail_cost_readiness_blocked",
    "synthetic_augmentation_validation_readiness_blocked",
    "intervention_fatigue_risk_budget_readiness_blocked",
    "letf_tracking_error_effective_fee_readiness_blocked",
    "asian_etf_tail_analytics_readiness_blocked",
    "reduced_rank_correlation_readiness_blocked",
}
TRAINING_GOVERNANCE_BLOCKERS = {
    "rl_governance_readiness_blocked",
    "llm_state_reward_interface_readiness_blocked",
}


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _sha256_file(path), "exists": path.exists()}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def build_review(
    *,
    research_shadow_path: Path = DEFAULT_RESEARCH_SHADOW,
    manual_approval_path: Path = DEFAULT_MANUAL_APPROVAL,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    research_shadow = _load_json(research_shadow_path)
    manual_approval = _load_json(manual_approval_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not research_shadow:
        blockers.append("missing_research_shadow_decision_snapshot")
    if not manual_approval:
        blockers.append("missing_manual_approval_readiness_review")

    research_blockers = list(research_shadow.get("blocking_reasons") or [])
    live_allocation = [item for item in research_blockers if item in LIVE_ALLOCATION_BLOCKERS]
    training_governance = [item for item in research_blockers if item in TRAINING_GOVERNANCE_BLOCKERS]
    uncategorized = [
        item
        for item in research_blockers
        if item not in LIVE_ALLOCATION_BLOCKERS and item not in TRAINING_GOVERNANCE_BLOCKERS
    ]
    if uncategorized:
        warnings.extend(f"uncategorized_research_shadow_blocker:{item}" for item in uncategorized)

    manual_decision = _decision(manual_approval)
    manual_summary = _summary(manual_approval)
    if manual_decision.get("manual_approval_review_ready") is not True:
        blockers.append("manual_approval_review_not_ready")
    if manual_decision.get("manual_approval_to_queue_training_allowed") is True:
        blockers.append("manual_approval_unexpectedly_allows_training_queue")
    if manual_decision.get("model_training_allowed") is True or manual_decision.get("ppo_training_allowed") is True:
        blockers.append("manual_approval_unexpectedly_allows_training")
    if manual_decision.get("promote_to_live") is True:
        blockers.append("manual_approval_unexpectedly_promotes_to_live")
    if manual_decision.get("allow_00631l_add") is True or manual_decision.get("allow_00632r_open") is True:
        blockers.append("manual_approval_unexpectedly_allows_blocked_ticker_action")

    exception_review_ready = (
        not blockers
        and manual_decision.get("manual_approval_review_ready") is True
        and bool(research_blockers)
    )
    training_queue_blockers = list(manual_approval.get("training_queue_blocking_reasons") or [])

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_research_shadow_blocker_triage",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_exception_review",
        "policy": "research_shadow_blocker_triage_only_no_training_no_live_action",
        "sources": {
            "research_shadow_decision_snapshot": _source(research_shadow_path),
            "manual_approval_readiness": _source(manual_approval_path),
        },
        "summary": {
            "research_shadow_status": research_shadow.get("status"),
            "research_shadow_blocker_count": len(research_blockers),
            "live_allocation_blocker_count": len(live_allocation),
            "training_governance_blocker_count": len(training_governance),
            "uncategorized_blocker_count": len(uncategorized),
            "manual_approval_review_ready": manual_decision.get("manual_approval_review_ready"),
            "manual_approval_queue_blockers": training_queue_blockers,
            "alignment_remediation_resolves_return_red": manual_summary.get("alignment_remediation_resolves_return_red"),
            "manual_exception_review_ready": exception_review_ready,
            "human_exception_record_required": exception_review_ready,
        },
        "classified_blockers": {
            "live_allocation_or_broker_action_blockers": live_allocation,
            "training_governance_blockers": training_governance,
            "uncategorized_blockers": uncategorized,
        },
        "manual_exception_scope": {
            "may_review_exception": exception_review_ready,
            "may_approve_non_ppo_shadow_queue_without_additional_record": False,
            "may_run_model_training": False,
            "may_run_ppo_training": False,
            "may_emit_actions": False,
            "may_emit_target_weights": False,
            "may_change_live_strategy": False,
            "may_add_00631l": False,
            "may_open_00632r": False,
        },
        "required_human_exception_record_fields": [
            "scope: non-PPO offline shadow experiment only",
            "allowed universe excluding 00631L.TW and 00632R.TW",
            "frozen GIFT state/reward manifest hash",
            "explicit acknowledgement that research_shadow remains blocked for live allocation",
            "explicit no-live-action/no-target-weight/no-auto-rebalance constraints",
            "expiry date and reviewer identity",
        ],
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "manual_exception_review_ready": exception_review_ready,
            "human_exception_record_required": exception_review_ready,
            "manual_exception_to_queue_training_allowed": False,
            "shadow_training_request_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_research_shadow_blocker_triage_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-22")
    parser.add_argument("--research-shadow", default=str(DEFAULT_RESEARCH_SHADOW))
    parser.add_argument("--manual-approval", default=str(DEFAULT_MANUAL_APPROVAL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        research_shadow_path=_resolve(args.research_shadow),
        manual_approval_path=_resolve(args.manual_approval),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward research-shadow blocker triage: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "research_shadow_blocker_count": review["summary"]["research_shadow_blocker_count"],
                "live_allocation_blocker_count": review["summary"]["live_allocation_blocker_count"],
                "training_governance_blocker_count": review["summary"]["training_governance_blocker_count"],
                "manual_exception_review_ready": review["decision"]["manual_exception_review_ready"],
                "manual_exception_to_queue_training_allowed": review["decision"][
                    "manual_exception_to_queue_training_allowed"
                ],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "ppo_training_allowed": review["decision"]["ppo_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
