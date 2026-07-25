#!/usr/bin/env python3
"""Build manual-approval readiness for the GroupA+ GIFT shadow training package.

This is the last review before a human could consider a separate training
approval artifact. It does not approve training, run PPO, emit target weights,
or change live GroupA+ strategy state.
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

from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_training_request_package import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_REQUEST_PACKAGE,
)
from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_training_readiness_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_TRAINING_READINESS,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_diagnostic_refinement import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_DIAGNOSTIC_REFINEMENT,
)
from scripts.evaluate.build_group_a_plus_llm_state_reward_alignment_remediation_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_ALIGNMENT_REMEDIATION,
)
from scripts.evaluate.build_group_a_plus_research_shadow_decision_snapshot import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_RESEARCH_SHADOW,
)
from scripts.evaluate.build_group_a_plus_llm_state_reward_research_shadow_blocker_triage import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_RESEARCH_SHADOW_TRIAGE,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_manual_approval_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_manual_approval_readiness_review/history"
DEFAULT_HUMAN_EXCEPTION_DRAFT = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_record_draft.json"
)
DEFAULT_SIGNED_APPROVAL_VALIDATION = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_validation.json"
)


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


def _has_unexpected_live_or_training_permission(name: str, payload: dict[str, Any]) -> list[str]:
    decision = _decision(payload)
    blockers: list[str] = []
    for key in (
        "model_training_allowed",
        "ppo_training_allowed",
        "promote_to_live",
        "target_weight_change_allowed",
        "auto_rebalance_allowed",
        "allow_00631l_add",
        "allow_00632r_open",
    ):
        if decision.get(key) is True:
            blockers.append(f"{name}_unexpected_permission:{key}")
    return blockers


def build_review(
    *,
    request_package_path: Path = DEFAULT_REQUEST_PACKAGE,
    training_readiness_path: Path = DEFAULT_TRAINING_READINESS,
    diagnostic_refinement_path: Path = DEFAULT_DIAGNOSTIC_REFINEMENT,
    alignment_remediation_path: Path = DEFAULT_ALIGNMENT_REMEDIATION,
    research_shadow_path: Path = DEFAULT_RESEARCH_SHADOW,
    research_shadow_triage_path: Path = DEFAULT_RESEARCH_SHADOW_TRIAGE,
    human_exception_draft_path: Path = DEFAULT_HUMAN_EXCEPTION_DRAFT,
    signed_approval_validation_path: Path = DEFAULT_SIGNED_APPROVAL_VALIDATION,
    as_of: str = "2026-07-21",
) -> dict[str, Any]:
    request_package = _load_json(request_package_path)
    training_readiness = _load_json(training_readiness_path)
    diagnostic_refinement = _load_json(diagnostic_refinement_path)
    alignment_remediation = _load_json(alignment_remediation_path)
    research_shadow = _load_json(research_shadow_path)
    research_shadow_triage = _load_json(research_shadow_triage_path)
    human_exception_draft = _load_json(human_exception_draft_path)
    signed_approval_validation = _load_json(signed_approval_validation_path)

    blockers: list[str] = []
    warnings: list[str] = []
    queue_blockers: list[str] = []

    if not request_package:
        blockers.append("missing_shadow_training_request_package")
    elif request_package.get("status") != "available_for_manual_review":
        blockers.append(f"request_package_not_available:{request_package.get('status')}")
    elif _summary(request_package).get("package_ready_for_manual_review") is not True:
        blockers.append("request_package_not_ready_for_manual_review")

    if not training_readiness:
        blockers.append("missing_shadow_training_readiness_review")
    elif _decision(training_readiness).get("shadow_training_ready") is not True:
        blockers.append("shadow_training_not_ready")

    if not diagnostic_refinement:
        warnings.append("missing_diagnostic_refinement_review")
    else:
        diagnostic_summary = _summary(diagnostic_refinement)
        remediation_resolves_alignment = (
            _decision(alignment_remediation).get("candidate_resolves_return_alignment_red_for_manual_review")
            is True
        )
        if diagnostic_summary.get("return_alignment_grade") == "red":
            warnings.append("diagnostic_return_alignment_red")
            if remediation_resolves_alignment:
                warnings.append("diagnostic_alignment_red_remediated_for_manual_review")
        if diagnostic_summary.get("ppo_training_queue_allowed_by_alignment") is not True:
            if remediation_resolves_alignment:
                warnings.append("diagnostic_alignment_queue_blocker_reduced_by_remediation")
            else:
                queue_blockers.append("diagnostic_alignment_does_not_allow_ppo_training_queue")

    if not research_shadow:
        queue_blockers.append("missing_research_shadow_decision_snapshot")
    elif research_shadow.get("status") == "blocked":
        if _decision(research_shadow_triage).get("manual_exception_review_ready") is True:
            draft_decision = _decision(human_exception_draft)
            if draft_decision.get("human_exception_record_draft_ready") is True:
                signed_validation_decision = _decision(signed_approval_validation)
                if (
                    signed_validation_decision.get("signed_approval_record_valid") is True
                    and signed_validation_decision.get("human_exception_approved") is True
                    and signed_validation_decision.get("non_ppo_shadow_queue_review_allowed") is True
                ):
                    queue_blockers.append("signed_human_exception_approval_valid_but_training_execution_gate_required")
                else:
                    queue_blockers.append("signed_human_exception_approval_record_missing_or_invalid")
            else:
                queue_blockers.append("human_research_shadow_exception_record_required")
        else:
            queue_blockers.append("research_shadow_decision_snapshot_blocked")

    for name, payload in {
        "request_package": request_package,
        "training_readiness": training_readiness,
        "diagnostic_refinement": diagnostic_refinement,
        "alignment_remediation": alignment_remediation,
        "research_shadow": research_shadow,
        "research_shadow_triage": research_shadow_triage,
        "human_exception_draft": human_exception_draft,
        "signed_approval_validation": signed_approval_validation,
    }.items():
        blockers.extend(_has_unexpected_live_or_training_permission(name, payload))

    package_summary = _summary(request_package)
    readiness_summary = _summary(training_readiness)
    diagnostic_summary = _summary(diagnostic_refinement)
    remediation_summary = _summary(alignment_remediation)
    remediation_decision = _decision(alignment_remediation)
    triage_summary = _summary(research_shadow_triage)
    triage_decision = _decision(research_shadow_triage)
    draft_summary = _summary(human_exception_draft)
    draft_decision = _decision(human_exception_draft)
    signed_validation_summary = _summary(signed_approval_validation)
    signed_validation_decision = _decision(signed_approval_validation)
    research_summary = _summary(research_shadow)
    recommended_candidate = package_summary.get("recommended_regime_rule")
    training_queue_allowed = not blockers and not queue_blockers

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_manual_approval_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_approval_review",
        "policy": "manual_approval_readiness_only_no_training_no_live_action",
        "sources": {
            "request_package": _source(request_package_path),
            "training_readiness": _source(training_readiness_path),
            "diagnostic_refinement": _source(diagnostic_refinement_path),
            "alignment_remediation": _source(alignment_remediation_path),
            "research_shadow_decision_snapshot": _source(research_shadow_path),
            "research_shadow_blocker_triage": _source(research_shadow_triage_path),
            "human_exception_record_draft": _source(human_exception_draft_path),
            "signed_approval_validation": _source(signed_approval_validation_path),
        },
        "summary": {
            "package_ready_for_manual_review": package_summary.get("package_ready_for_manual_review"),
            "shadow_training_ready": readiness_summary.get("shadow_training_ready"),
            "research_shadow_status": research_shadow.get("status"),
            "research_shadow_blocking_reasons_count": len(research_shadow.get("blocking_reasons") or []),
            "diagnostic_return_alignment_grade": diagnostic_summary.get("return_alignment_grade"),
            "diagnostic_mean_reward_future_return_alignment": diagnostic_summary.get(
                "mean_reward_future_return_alignment"
            ),
            "diagnostic_ppo_training_queue_allowed_by_alignment": diagnostic_summary.get(
                "ppo_training_queue_allowed_by_alignment"
            ),
            "alignment_remediation_status": alignment_remediation.get("status"),
            "alignment_remediation_resolves_return_red": remediation_decision.get(
                "candidate_resolves_return_alignment_red_for_manual_review"
            ),
            "alignment_remediation_best_return_alignment_grade": remediation_summary.get(
                "best_acceptable_return_alignment_grade"
            ),
            "alignment_remediation_allows_ppo_queue_by_alignment": remediation_decision.get(
                "candidate_allows_ppo_queue_by_alignment"
            ),
            "research_shadow_triage_status": research_shadow_triage.get("status"),
            "research_shadow_triage_manual_exception_review_ready": triage_decision.get(
                "manual_exception_review_ready"
            ),
            "research_shadow_triage_live_allocation_blocker_count": triage_summary.get(
                "live_allocation_blocker_count"
            ),
            "research_shadow_triage_training_governance_blocker_count": triage_summary.get(
                "training_governance_blocker_count"
            ),
            "human_exception_record_draft_status": human_exception_draft.get("status"),
            "human_exception_record_draft_ready": draft_decision.get("human_exception_record_draft_ready"),
            "human_exception_approved": draft_decision.get("human_exception_approved"),
            "human_exception_training_queue_allowed": draft_summary.get("training_queue_allowed"),
            "signed_approval_validation_status": signed_approval_validation.get("status"),
            "signed_approval_record_valid": signed_validation_decision.get("signed_approval_record_valid"),
            "signed_approval_human_exception_approved": signed_validation_decision.get("human_exception_approved"),
            "signed_approval_non_ppo_shadow_queue_review_allowed": signed_validation_decision.get(
                "non_ppo_shadow_queue_review_allowed"
            ),
            "signed_approval_training_queue_allowed": signed_validation_summary.get("training_queue_allowed"),
            "regime_filter_resolves_5bps_warning": readiness_summary.get("regime_filter_resolves_5bps_warning"),
            "recommended_regime_rule": recommended_candidate,
            "recommended_high_score": package_summary.get("recommended_high_score"),
            "recommended_cost_bps": package_summary.get("recommended_cost_bps"),
            "manual_approval_review_ready": not blockers,
            "manual_approval_to_queue_training_allowed": training_queue_allowed,
        },
        "approval_scope": {
            "may_review_package": not blockers,
            "may_approve_training_queue": training_queue_allowed,
            "may_run_model_training": False,
            "may_run_ppo_training": False,
            "may_emit_actions": False,
            "may_emit_target_weights": False,
            "may_change_live_strategy": False,
            "may_add_00631l": False,
            "may_open_00632r": False,
        },
        "required_manual_decisions": [
            "Confirm whether trend_above_train_median is acceptable as a mandatory regime filter.",
            "Confirm that the red reward-return alignment is acceptable only for offline research, not PPO queueing.",
            "Confirm that global research_shadow blocked status prevents queue approval.",
            "Confirm that Golden1_0531 and A21.18 active allocation remain unchanged.",
        ],
        "minimum_remediation_before_training_queue": [
            "Resolve or explicitly waive research_shadow_decision_snapshot_blocked in a separate human approval record.",
            "Improve diagnostic reward-return alignment out of red grade, or record a human waiver for non-PPO shadow training only.",
            "Keep 00631L.TW and 00632R.TW excluded from the first GIFT shadow training universe.",
            "Preserve no-action/no-target-weight/no-auto-rebalance constraints in the training runner.",
        ],
        "blocking_reasons": sorted(set(blockers)),
        "training_queue_blocking_reasons": sorted(set(queue_blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "manual_approval_review_ready": not blockers,
            "manual_approval_to_queue_training_allowed": training_queue_allowed,
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
    return history_dir / f"llm_state_reward_manual_approval_readiness_review_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-21")
    parser.add_argument("--request-package", default=str(DEFAULT_REQUEST_PACKAGE))
    parser.add_argument("--training-readiness", default=str(DEFAULT_TRAINING_READINESS))
    parser.add_argument("--diagnostic-refinement", default=str(DEFAULT_DIAGNOSTIC_REFINEMENT))
    parser.add_argument("--alignment-remediation", default=str(DEFAULT_ALIGNMENT_REMEDIATION))
    parser.add_argument("--research-shadow", default=str(DEFAULT_RESEARCH_SHADOW))
    parser.add_argument("--research-shadow-triage", default=str(DEFAULT_RESEARCH_SHADOW_TRIAGE))
    parser.add_argument("--human-exception-draft", default=str(DEFAULT_HUMAN_EXCEPTION_DRAFT))
    parser.add_argument("--signed-approval-validation", default=str(DEFAULT_SIGNED_APPROVAL_VALIDATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        request_package_path=_resolve(args.request_package),
        training_readiness_path=_resolve(args.training_readiness),
        diagnostic_refinement_path=_resolve(args.diagnostic_refinement),
        alignment_remediation_path=_resolve(args.alignment_remediation),
        research_shadow_path=_resolve(args.research_shadow),
        research_shadow_triage_path=_resolve(args.research_shadow_triage),
        human_exception_draft_path=_resolve(args.human_exception_draft),
        signed_approval_validation_path=_resolve(args.signed_approval_validation),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward manual approval readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "manual_approval_review_ready": review["decision"]["manual_approval_review_ready"],
                "manual_approval_to_queue_training_allowed": review["decision"][
                    "manual_approval_to_queue_training_allowed"
                ],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "ppo_training_allowed": review["decision"]["ppo_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "blocking_reasons": review["blocking_reasons"],
                "training_queue_blocking_reasons": review["training_queue_blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
