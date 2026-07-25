from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_high_dividend_active_pain_redesign_review import (
    PROPOSAL_ID,
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _event_audit(path: Path, *, strong_evidence: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "dominant_negative_event_bucket": "high_dividend" if strong_evidence else "bond",
                "event_mean_active_weight_by_bucket": {"high_dividend": 0.10 if strong_evidence else 0.01},
                "event_sum_active_contribution_by_bucket": {"high_dividend": -0.02 if strong_evidence else -0.001},
                "worst_fold": 3,
                "worst_fold_trough_date": "2024-08-05",
            },
        },
    )


def _validation(path: Path, *, accepted: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "proposal_results": [
                {
                    "proposal_id": PROPOSAL_ID,
                    "accepted_for_offline_review": accepted,
                    "feature_families": ["bucket_active_pain"],
                    "feature_primitives": ["high_dividend_active_pain"],
                    "reward_terms": ["active_bucket_drawdown_penalty"],
                }
            ],
        },
    )


def _promotion_gate(path: Path) -> Path:
    return _write(path, {"status": "blocked", "decision": {"promotion_gate_passed": False}})


def test_build_review_allows_only_offline_dgr_design_when_evidence_and_proposal_pass(tmp_path: Path) -> None:
    review = build_review(
        event_audit_path=_event_audit(tmp_path / "event.json"),
        validation_path=_validation(tmp_path / "validation.json"),
        promotion_gate_path=_promotion_gate(tmp_path / "promotion.json"),
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_redesign_review"
    assert review["status"] == "available_for_offline_dgr_design"
    assert review["decision"]["offline_dgr_design_allowed"] is True
    assert review["decision"]["offline_smoke_allowed_after_dgr_green"] is True
    assert review["decision"]["next_shadow_model_design_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_weak_evidence_or_unaccepted_proposal(tmp_path: Path) -> None:
    review = build_review(
        event_audit_path=_event_audit(tmp_path / "event.json", strong_evidence=False),
        validation_path=_validation(tmp_path / "validation.json", accepted=False),
        promotion_gate_path=_promotion_gate(tmp_path / "promotion.json"),
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert f"proposal_not_accepted:{PROPOSAL_ID}" in review["blocking_reasons"]
    assert "high_dividend_active_weight_evidence_below_threshold" in review["blocking_reasons"]
    assert "high_dividend_active_contribution_evidence_not_negative_enough" in review["blocking_reasons"]
    assert review["decision"]["offline_dgr_design_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_redesign_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_high_dividend_active_pain_redesign_review_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
