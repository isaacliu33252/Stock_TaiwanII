from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_catalog import build_catalog
from scripts.evaluate.validate_group_a_plus_llm_state_reward_interface_proposals import (
    SAMPLE_PROPOSALS,
    build_review,
    validate_proposal,
    write_review,
    write_sample_proposals,
)


def _catalog(tmp_path: Path) -> dict:
    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps({"status": "blocked", "decision": {"llm_state_reward_interface_ready": False}}),
        encoding="utf-8",
    )
    return build_catalog(readiness_path=readiness, as_of="2026-07-20")


def test_validate_proposal_accepts_catalog_compliant_research_proposal(tmp_path: Path) -> None:
    result = validate_proposal(SAMPLE_PROPOSALS[0], _catalog(tmp_path))

    assert result["status"] == "accepted_for_offline_review"
    assert result["accepted_for_offline_review"] is True
    assert result["rejection_reasons"] == []
    assert result["decision"]["promote_to_live"] is False
    assert result["decision"]["target_weight_change_allowed"] is False
    assert result["decision"]["auto_rebalance_allowed"] is False
    assert result["decision"]["allow_00631l_add"] is False
    assert result["decision"]["allow_00632r_open"] is False


def test_validate_proposal_accepts_downside_tail_decay_research_proposal(tmp_path: Path) -> None:
    result = validate_proposal(SAMPLE_PROPOSALS[1], _catalog(tmp_path))

    assert result["proposal_id"] == "gift_research_downside_vol_letf_tail_decay_v1"
    assert result["status"] == "accepted_for_offline_review"
    assert result["accepted_for_offline_review"] is True
    assert result["rejection_reasons"] == []
    assert result["reward_terms"] == ["drawdown_penalty", "volatility_scaling", "letf_tail_decay_cost"]
    assert result["decision"]["promote_to_live"] is False
    assert result["decision"]["allow_00631l_add"] is False
    assert result["decision"]["allow_00632r_open"] is False


def test_validate_proposal_accepts_high_dividend_active_pain_research_proposal(tmp_path: Path) -> None:
    result = validate_proposal(SAMPLE_PROPOSALS[2], _catalog(tmp_path))

    assert result["proposal_id"] == "gift_research_high_dividend_active_pain_v1"
    assert result["status"] == "accepted_for_offline_review"
    assert result["accepted_for_offline_review"] is True
    assert result["rejection_reasons"] == []
    assert "bucket_active_pain" in result["feature_families"]
    assert "high_dividend_active_pain" in result["feature_primitives"]
    assert "active_bucket_drawdown_penalty" in result["reward_terms"]
    assert result["decision"]["promote_to_live"] is False
    assert result["decision"]["allow_00631l_add"] is False
    assert result["decision"]["allow_00632r_open"] is False


def test_validate_proposal_rejects_live_target_weight_request(tmp_path: Path) -> None:
    result = validate_proposal(SAMPLE_PROPOSALS[3], _catalog(tmp_path))

    assert result["status"] == "rejected"
    assert result["accepted_for_offline_review"] is False
    assert "outputs_actions" in result["rejection_reasons"]
    assert "outputs_target_weights" in result["rejection_reasons"]
    assert "uses_test_time_llm_queries" in result["rejection_reasons"]
    assert "executes_generated_code_live" in result["rejection_reasons"]
    assert "requested_live_effect:allow_00631l_add" in result["rejection_reasons"]
    assert "requested_live_effect:target_weight_change" in result["rejection_reasons"]
    assert result["decision"]["allow_00631l_add"] is False


def test_build_review_summarizes_sample_proposals(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog(tmp_path), ensure_ascii=False), encoding="utf-8")
    proposals_path = tmp_path / "proposals.json"
    write_sample_proposals(proposals_path)

    review = build_review(catalog_path=catalog_path, proposals_path=proposals_path, as_of="2026-07-20")

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_proposal_validation_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["accepted_for_offline_review_count"] == 3
    assert review["summary"]["rejected_count"] == 1
    assert "gift_research_downside_vol_letf_tail_decay_v1" in review["summary"]["accepted_proposal_ids"]
    assert "gift_research_high_dividend_active_pain_v1" in review["summary"]["accepted_proposal_ids"]
    assert review["decision"]["offline_review_allowed_for_accepted_proposals"] is True
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_proposal_validation_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_proposal_validation_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
