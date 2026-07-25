from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_human_exception_approval_record_schema import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _draft(
    path: Path,
    *,
    ready: bool = True,
    excluded_tickers: list[str] | None = None,
    approved: bool = False,
) -> Path:
    if excluded_tickers is None:
        excluded_tickers = ["00631L.TW", "00632R.TW"]
    return _write(
        path,
        {
            "status": "draft_ready_for_human_review" if ready else "blocked",
            "exception_record_draft": {
                "record_id": "gift_non_ppo_shadow_exception_20260722",
                "scope": "non_ppo_offline_shadow_training_queue_review_only",
                "approval_state": "draft_not_approved",
                "freeze_id": "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721",
                "frozen_manifest_sha256": "abc123",
                "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                "allowed_universe": ["0050.TW", "0056.TW"],
                "excluded_tickers": excluded_tickers,
                "hard_constraints": {
                    "no_training_in_this_artifact": True,
                    "no_ppo_training": True,
                    "no_live_signal_output": True,
                    "no_target_weight_output": True,
                    "no_auto_rebalance": True,
                    "no_00631l_add": "00631L.TW" in excluded_tickers,
                    "no_00632r_open": "00632R.TW" in excluded_tickers,
                    "no_live_strategy_change": True,
                    "keep_golden1_0531_unchanged": True,
                },
            },
            "required_signoff_fields": [
                "reviewer",
                "approved_at",
                "expires_at",
                "explicit_ack_research_shadow_remains_blocked_for_live_allocation",
            ],
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
                "outputs_actions": False,
                "outputs_target_weights": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_approval_record_schema_template_ready_but_not_approved(tmp_path: Path) -> None:
    draft = _draft(tmp_path / "draft.json")

    review = build_review(human_exception_draft_path=draft, as_of="2026-07-22")

    assert review["report_type"] == "group_a_plus_llm_state_reward_human_exception_approval_record_schema"
    assert review["status"] == "template_ready_for_human_signature"
    assert review["summary"]["approval_record_schema_ready"] is True
    assert review["summary"]["approval_record_template_ready"] is True
    assert review["summary"]["human_exception_approved"] is False
    assert review["summary"]["training_queue_allowed"] is False
    assert review["decision"]["approval_record_schema_ready"] is True
    assert review["decision"]["human_exception_approved"] is False
    assert review["decision"]["training_queue_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True
    assert review["approval_record_template"]["record_id"] == "gift_non_ppo_shadow_exception_20260722"
    assert review["approval_record_template"]["reviewer"] is None
    assert review["approval_record_template"]["approved_actions"]["allow_model_training_command"] is False
    assert review["approval_record_template"]["approval_scope"]["excluded_tickers"] == ["00631L.TW", "00632R.TW"]
    assert review["approval_record_template"]["acknowledgements"][
        "research_shadow_remains_blocked_for_live_allocation"
    ] is False
    assert review["validation_rules"]["constraint_overrides_must_be_empty"] is True


def test_approval_record_schema_blocks_when_draft_not_ready(tmp_path: Path) -> None:
    review = build_review(
        human_exception_draft_path=_draft(tmp_path / "draft.json", ready=False),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "human_exception_record_draft_not_ready" in review["blocking_reasons"]
    assert review["decision"]["approval_record_schema_ready"] is False
    assert review["decision"]["model_training_allowed"] is False


def test_approval_record_schema_blocks_when_required_exclusion_missing(tmp_path: Path) -> None:
    review = build_review(
        human_exception_draft_path=_draft(tmp_path / "draft.json", excluded_tickers=["00631L.TW"]),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "human_exception_draft_missing_excluded_ticker:00632R.TW" in review["blocking_reasons"]
    assert "human_exception_draft_missing_hard_constraint:no_00632r_open" in review["blocking_reasons"]
    assert review["decision"]["allow_00632r_open"] is False


def test_approval_record_schema_detects_unexpected_approval_permission(tmp_path: Path) -> None:
    review = build_review(
        human_exception_draft_path=_draft(tmp_path / "draft.json", approved=True),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "human_exception_draft_unexpected_permission:human_exception_approved" in review["blocking_reasons"]
    assert review["decision"]["human_exception_approved"] is False
    assert review["decision"]["training_queue_allowed"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "schema.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_human_exception_approval_record_schema",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_human_exception_approval_record_schema_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
