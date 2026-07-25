from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_human_exception_signed_approval_record_template import (
    build_review,
    write_review,
)
from scripts.evaluate.validate_group_a_plus_llm_state_reward_human_exception_signed_approval_record import (
    build_review as build_validation,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _schema(path: Path, *, ready: bool = True, allow_model_training: bool = False) -> Path:
    template = {
        "record_id": "gift_non_ppo_shadow_exception_20260722",
        "approval_record_schema_version": 1,
        "source_draft_sha256": "abc123",
        "reviewer": None,
        "reviewer_role": None,
        "approved_at": None,
        "expires_at": None,
        "approval_scope": {
            "scope": "non_ppo_offline_shadow_training_queue_review_only",
            "freeze_id": "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721",
            "frozen_manifest_sha256": "freezehash",
            "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
            "allowed_universe": ["0050.TW", "0056.TW"],
            "excluded_tickers": ["00631L.TW", "00632R.TW"],
        },
        "approved_actions": {
            "allow_non_ppo_offline_shadow_training_queue_review": False,
            "allow_model_training_command": allow_model_training,
            "allow_ppo_training": False,
            "allow_live_signal_output": False,
            "allow_target_weight_output": False,
            "allow_auto_rebalance": False,
            "allow_live_strategy_change": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
        "acknowledgements": {
            "research_shadow_remains_blocked_for_live_allocation": False,
            "non_ppo_offline_shadow_review_only": False,
            "no_live_action_no_target_weight_no_auto_rebalance": False,
            "00631l_and_00632r_remain_excluded": False,
            "golden1_0531_unchanged": False,
            "training_runner_must_preserve_no_action_outputs": False,
        },
        "constraint_overrides": {},
        "notes": None,
    }
    return _write(
        path,
        {
            "status": "template_ready_for_human_signature" if ready else "blocked",
            "approval_record_template": template,
            "validation_rules": {
                "required_template_fields": list(template.keys()),
                "required_acknowledgements": list(template["acknowledgements"].keys()),
                "constraint_overrides_must_be_empty": True,
                "required_false_permissions": [
                    "allow_ppo_training",
                    "allow_live_signal_output",
                    "allow_target_weight_output",
                    "allow_auto_rebalance",
                    "allow_live_strategy_change",
                    "allow_00631l_add",
                    "allow_00632r_open",
                ],
            },
            "decision": {
                "approval_record_schema_ready": ready,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )


def test_signed_approval_record_template_ready_but_not_valid_or_approved(tmp_path: Path) -> None:
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        as_of="2026-07-22",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_human_exception_signed_approval_record_template"
    assert review["status"] == "unsigned_template_ready_for_manual_completion"
    assert review["summary"]["signed_approval_record_template_ready"] is True
    assert review["summary"]["signed_approval_record_valid"] is False
    assert review["summary"]["human_exception_approved"] is False
    assert review["summary"]["training_queue_allowed"] is False
    assert review["decision"]["signed_approval_record_template_ready"] is True
    assert review["decision"]["training_queue_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    template = review["signed_approval_record_template"]
    assert template["reviewer"] is None
    assert template["approved_at"] is None
    assert template["expires_at"] is None
    assert template["approved_actions"]["allow_non_ppo_offline_shadow_training_queue_review"] is False
    assert template["approved_actions"]["allow_model_training_command"] is False
    assert template["approval_scope"]["excluded_tickers"] == ["00631L.TW", "00632R.TW"]
    assert all(value is False for value in template["acknowledgements"].values())


def test_signed_approval_record_template_does_not_pass_validator(tmp_path: Path) -> None:
    schema = _schema(tmp_path / "schema.json")
    review = build_review(approval_record_schema_path=schema, as_of="2026-07-22")
    template_path = _write(tmp_path / "signed_TEMPLATE.json", review["signed_approval_record_template"])

    validation = build_validation(
        approval_record_schema_path=schema,
        signed_approval_record_path=template_path,
        as_of="2026-07-22",
    )

    assert validation["status"] == "blocked"
    assert "signed_record_missing_reviewer" in validation["blocking_reasons"]
    assert "signed_record_invalid_or_missing_approved_at" in validation["blocking_reasons"]
    assert "signed_record_non_ppo_shadow_queue_review_not_approved" in validation["blocking_reasons"]
    assert validation["decision"]["human_exception_approved"] is False
    assert validation["decision"]["training_queue_allowed"] is False


def test_signed_approval_record_template_blocks_when_schema_not_ready(tmp_path: Path) -> None:
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json", ready=False),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "human_exception_approval_record_schema_not_ready" in review["blocking_reasons"]
    assert review["decision"]["signed_approval_record_template_ready"] is False
    assert review["decision"]["model_training_allowed"] is False


def test_signed_approval_record_template_blocks_if_schema_allows_training(tmp_path: Path) -> None:
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json", allow_model_training=True),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "schema_template_forbidden_action_not_false:allow_model_training_command" in review["blocking_reasons"]
    assert review["decision"]["model_training_allowed"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "template.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_human_exception_signed_approval_record_template",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_human_exception_signed_approval_record_template_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
