from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_manual_approval_readiness_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _package(path: Path, *, ready: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_review" if ready else "blocked",
            "summary": {
                "package_ready_for_manual_review": ready,
                "recommended_regime_rule": "trend_above_train_median",
                "recommended_high_score": 1.03,
                "recommended_cost_bps": 5.0,
            },
            "decision": {
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _training(path: Path, *, ready: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "shadow_training_ready": ready,
                "regime_filter_resolves_5bps_warning": True,
            },
            "decision": {
                "shadow_training_ready": ready,
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _diagnostic(path: Path, *, queue_allowed: bool = False) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "return_alignment_grade": "red" if not queue_allowed else "yellow",
                "mean_reward_future_return_alignment": -0.0142,
                "ppo_training_queue_allowed_by_alignment": queue_allowed,
            },
            "decision": {
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _remediation(path: Path, *, resolves: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "best_acceptable_return_alignment_grade": "yellow" if resolves else None,
            },
            "decision": {
                "candidate_resolves_return_alignment_red_for_manual_review": resolves,
                "candidate_allows_ppo_queue_by_alignment": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _research(path: Path, *, blocked: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "blocked" if blocked else "available_for_manual_review",
            "blocking_reasons": ["rl_governance_readiness_blocked"] if blocked else [],
            "summary": {"llm_state_reward_shadow_training_ready": True},
            "decision": {
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _triage(path: Path, *, ready: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_exception_review" if ready else "blocked",
            "summary": {
                "live_allocation_blocker_count": 12,
                "training_governance_blocker_count": 2,
            },
            "decision": {
                "manual_exception_review_ready": ready,
                "manual_exception_to_queue_training_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _draft(path: Path, *, ready: bool = True, approved: bool = False) -> Path:
    return _write(
        path,
        {
            "status": "draft_ready_for_human_review" if ready else "blocked",
            "summary": {
                "human_exception_record_draft_ready": ready,
                "human_exception_approved": approved,
                "training_queue_allowed": False,
            },
            "decision": {
                "human_exception_record_draft_ready": ready,
                "human_exception_approved": approved,
                "training_queue_allowed": False,
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _signed_validation(path: Path, *, valid: bool = False) -> Path:
    return _write(
        path,
        {
            "status": "valid_for_manual_non_ppo_shadow_queue_review" if valid else "blocked",
            "summary": {
                "signed_approval_record_valid": valid,
                "human_exception_approved": valid,
                "non_ppo_shadow_queue_review_allowed": valid,
                "training_queue_allowed": False,
            },
            "decision": {
                "signed_approval_record_valid": valid,
                "human_exception_approved": valid,
                "non_ppo_shadow_queue_review_allowed": valid,
                "training_queue_allowed": False,
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_manual_approval_review_ready_but_training_queue_blocked(tmp_path: Path) -> None:
    review = build_review(
        request_package_path=_package(tmp_path / "package.json"),
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        alignment_remediation_path=_remediation(tmp_path / "remediation.json", resolves=False),
        research_shadow_path=_research(tmp_path / "research.json"),
        research_shadow_triage_path=_triage(tmp_path / "triage.json", ready=False),
        human_exception_draft_path=tmp_path / "missing_draft.json",
        signed_approval_validation_path=tmp_path / "missing_signed_validation.json",
        as_of="2026-07-22",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_manual_approval_readiness_review"
    assert review["status"] == "available_for_manual_approval_review"
    assert review["summary"]["manual_approval_review_ready"] is True
    assert review["summary"]["manual_approval_to_queue_training_allowed"] is False
    assert "research_shadow_decision_snapshot_blocked" in review["training_queue_blocking_reasons"]
    assert "diagnostic_alignment_does_not_allow_ppo_training_queue" in review["training_queue_blocking_reasons"]
    assert "diagnostic_return_alignment_red" in review["warning_reasons"]
    assert review["approval_scope"]["may_review_package"] is True
    assert review["approval_scope"]["may_approve_training_queue"] is False
    assert review["decision"]["shadow_training_request_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_manual_approval_blocks_when_package_not_ready(tmp_path: Path) -> None:
    review = build_review(
        request_package_path=_package(tmp_path / "package.json", ready=False),
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json", queue_allowed=True),
        research_shadow_path=_research(tmp_path / "research.json", blocked=False),
        research_shadow_triage_path=_triage(tmp_path / "triage.json", ready=False),
        human_exception_draft_path=tmp_path / "missing_draft.json",
        signed_approval_validation_path=tmp_path / "missing_signed_validation.json",
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "request_package_not_available:blocked" in review["blocking_reasons"]
    assert review["decision"]["manual_approval_review_ready"] is False
    assert review["decision"]["manual_approval_to_queue_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_manual_approval_reduces_alignment_blocker_when_remediation_resolves(tmp_path: Path) -> None:
    review = build_review(
        request_package_path=_package(tmp_path / "package.json"),
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        alignment_remediation_path=_remediation(tmp_path / "remediation.json"),
        research_shadow_path=_research(tmp_path / "research.json"),
        research_shadow_triage_path=_triage(tmp_path / "triage.json", ready=False),
        human_exception_draft_path=tmp_path / "missing_draft.json",
        signed_approval_validation_path=tmp_path / "missing_signed_validation.json",
        as_of="2026-07-22",
    )

    assert review["status"] == "available_for_manual_approval_review"
    assert "diagnostic_alignment_does_not_allow_ppo_training_queue" not in review[
        "training_queue_blocking_reasons"
    ]
    assert review["training_queue_blocking_reasons"] == ["research_shadow_decision_snapshot_blocked"]
    assert "diagnostic_alignment_red_remediated_for_manual_review" in review["warning_reasons"]
    assert "diagnostic_alignment_queue_blocker_reduced_by_remediation" in review["warning_reasons"]
    assert review["summary"]["alignment_remediation_resolves_return_red"] is True
    assert review["decision"]["manual_approval_to_queue_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False


def test_manual_approval_uses_research_shadow_triage_for_exception_record(tmp_path: Path) -> None:
    review = build_review(
        request_package_path=_package(tmp_path / "package.json"),
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        alignment_remediation_path=_remediation(tmp_path / "remediation.json"),
        research_shadow_path=_research(tmp_path / "research.json"),
        research_shadow_triage_path=_triage(tmp_path / "triage.json"),
        human_exception_draft_path=tmp_path / "missing_draft.json",
        signed_approval_validation_path=tmp_path / "missing_signed_validation.json",
        as_of="2026-07-22",
    )

    assert review["training_queue_blocking_reasons"] == ["human_research_shadow_exception_record_required"]
    assert review["summary"]["research_shadow_triage_manual_exception_review_ready"] is True
    assert review["summary"]["research_shadow_triage_live_allocation_blocker_count"] == 12
    assert review["summary"]["research_shadow_triage_training_governance_blocker_count"] == 2
    assert review["decision"]["manual_approval_to_queue_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_manual_approval_uses_human_exception_record_draft_status(tmp_path: Path) -> None:
    review = build_review(
        request_package_path=_package(tmp_path / "package.json"),
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        alignment_remediation_path=_remediation(tmp_path / "remediation.json"),
        research_shadow_path=_research(tmp_path / "research.json"),
        research_shadow_triage_path=_triage(tmp_path / "triage.json"),
        human_exception_draft_path=_draft(tmp_path / "draft.json"),
        signed_approval_validation_path=tmp_path / "missing_signed_validation.json",
        as_of="2026-07-22",
    )

    assert review["training_queue_blocking_reasons"] == [
        "signed_human_exception_approval_record_missing_or_invalid"
    ]
    assert review["summary"]["human_exception_record_draft_status"] == "draft_ready_for_human_review"
    assert review["summary"]["human_exception_record_draft_ready"] is True
    assert review["summary"]["human_exception_approved"] is False
    assert review["summary"]["human_exception_training_queue_allowed"] is False
    assert review["summary"]["signed_approval_record_valid"] is None
    assert review["decision"]["manual_approval_to_queue_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_manual_approval_uses_signed_approval_validation_but_keeps_execution_gate(tmp_path: Path) -> None:
    review = build_review(
        request_package_path=_package(tmp_path / "package.json"),
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        alignment_remediation_path=_remediation(tmp_path / "remediation.json"),
        research_shadow_path=_research(tmp_path / "research.json"),
        research_shadow_triage_path=_triage(tmp_path / "triage.json"),
        human_exception_draft_path=_draft(tmp_path / "draft.json"),
        signed_approval_validation_path=_signed_validation(tmp_path / "signed_validation.json", valid=True),
        as_of="2026-07-22",
    )

    assert review["training_queue_blocking_reasons"] == [
        "signed_human_exception_approval_valid_but_training_execution_gate_required"
    ]
    assert review["summary"]["signed_approval_validation_status"] == "valid_for_manual_non_ppo_shadow_queue_review"
    assert review["summary"]["signed_approval_record_valid"] is True
    assert review["summary"]["signed_approval_human_exception_approved"] is True
    assert review["summary"]["signed_approval_non_ppo_shadow_queue_review_allowed"] is True
    assert review["summary"]["signed_approval_training_queue_allowed"] is False
    assert review["decision"]["manual_approval_to_queue_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_manual_approval_detects_unexpected_permissions(tmp_path: Path) -> None:
    package = _package(tmp_path / "package.json")
    payload = json.loads(package.read_text(encoding="utf-8"))
    payload["decision"]["model_training_allowed"] = True
    package.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    review = build_review(
        request_package_path=package,
        training_readiness_path=_training(tmp_path / "training.json"),
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json", queue_allowed=True),
        research_shadow_path=_research(tmp_path / "research.json", blocked=False),
        research_shadow_triage_path=_triage(tmp_path / "triage.json", ready=False),
        human_exception_draft_path=tmp_path / "missing_draft.json",
        signed_approval_validation_path=tmp_path / "missing_signed_validation.json",
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "request_package_unexpected_permission:model_training_allowed" in review["blocking_reasons"]
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "manual.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_manual_approval_readiness_review",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_manual_approval_readiness_review_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
