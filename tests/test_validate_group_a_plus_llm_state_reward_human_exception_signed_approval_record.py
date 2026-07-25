from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.evaluate.validate_group_a_plus_llm_state_reward_human_exception_signed_approval_record import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _schema(path: Path) -> Path:
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
            "allow_model_training_command": False,
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
            "status": "template_ready_for_human_signature",
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
                "approval_record_schema_ready": True,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )


def _signed(path: Path, **overrides: object) -> Path:
    record = {
        "record_id": "gift_non_ppo_shadow_exception_20260722",
        "approval_record_schema_version": 1,
        "source_draft_sha256": "abc123",
        "reviewer": "manual_reviewer",
        "reviewer_role": "research_governance",
        "approved_at": "2026-07-22T09:00:00",
        "expires_at": "2026-07-29T09:00:00",
        "approval_scope": {
            "scope": "non_ppo_offline_shadow_training_queue_review_only",
            "freeze_id": "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721",
            "frozen_manifest_sha256": "freezehash",
            "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
            "allowed_universe": ["0050.TW", "0056.TW"],
            "excluded_tickers": ["00631L.TW", "00632R.TW"],
        },
        "approved_actions": {
            "allow_non_ppo_offline_shadow_training_queue_review": True,
            "allow_model_training_command": False,
            "allow_ppo_training": False,
            "allow_live_signal_output": False,
            "allow_target_weight_output": False,
            "allow_auto_rebalance": False,
            "allow_live_strategy_change": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
        "acknowledgements": {
            "research_shadow_remains_blocked_for_live_allocation": True,
            "non_ppo_offline_shadow_review_only": True,
            "no_live_action_no_target_weight_no_auto_rebalance": True,
            "00631l_and_00632r_remain_excluded": True,
            "golden1_0531_unchanged": True,
            "training_runner_must_preserve_no_action_outputs": True,
        },
        "constraint_overrides": {},
        "notes": "manual research exception review only",
    }
    for key, value in overrides.items():
        record[key] = value
    return _write(path, record)


def test_signed_approval_validator_accepts_valid_record_without_training_permissions(tmp_path: Path) -> None:
    signed = _signed(tmp_path / "signed.json")
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        signed_approval_record_path=signed,
        as_of="2026-07-22",
    )

    assert review["status"] == "valid_for_manual_non_ppo_shadow_queue_review"
    assert review["summary"]["signed_approval_record_valid"] is True
    assert review["summary"]["human_exception_approved"] is True
    assert review["summary"]["non_ppo_shadow_queue_review_allowed"] is True
    assert review["summary"]["training_queue_allowed"] is False
    assert review["decision"]["signed_approval_record_valid"] is True
    assert review["decision"]["training_queue_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["validation"]["signed_record_sha256"] == hashlib.sha256(signed.read_bytes()).hexdigest()


def test_signed_approval_validator_blocks_hash_mismatch(tmp_path: Path) -> None:
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        signed_approval_record_path=_signed(tmp_path / "signed.json", source_draft_sha256="different"),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "signed_record_source_draft_sha256_mismatch" in review["blocking_reasons"]
    assert review["decision"]["human_exception_approved"] is False
    assert review["decision"]["training_queue_allowed"] is False


def test_signed_approval_validator_blocks_missing_acknowledgement(tmp_path: Path) -> None:
    acknowledgements = {
        "research_shadow_remains_blocked_for_live_allocation": True,
        "non_ppo_offline_shadow_review_only": True,
        "no_live_action_no_target_weight_no_auto_rebalance": True,
        "00631l_and_00632r_remain_excluded": True,
        "golden1_0531_unchanged": True,
        "training_runner_must_preserve_no_action_outputs": False,
    }

    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        signed_approval_record_path=_signed(tmp_path / "signed.json", acknowledgements=acknowledgements),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "signed_record_missing_acknowledgement:training_runner_must_preserve_no_action_outputs" in review[
        "blocking_reasons"
    ]
    assert review["decision"]["signed_approval_record_valid"] is False


def test_signed_approval_validator_blocks_expired_record(tmp_path: Path) -> None:
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        signed_approval_record_path=_signed(
            tmp_path / "signed.json",
            approved_at="2026-07-20T09:00:00",
            expires_at="2026-07-21T09:00:00",
        ),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "signed_record_expired_as_of_validation_date" in review["blocking_reasons"]
    assert review["decision"]["human_exception_approved"] is False


def test_signed_approval_validator_blocks_forbidden_action(tmp_path: Path) -> None:
    approved_actions = {
        "allow_non_ppo_offline_shadow_training_queue_review": True,
        "allow_model_training_command": True,
        "allow_ppo_training": False,
        "allow_live_signal_output": False,
        "allow_target_weight_output": False,
        "allow_auto_rebalance": False,
        "allow_live_strategy_change": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
    }

    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        signed_approval_record_path=_signed(tmp_path / "signed.json", approved_actions=approved_actions),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "signed_record_forbidden_action_not_false:allow_model_training_command" in review["blocking_reasons"]
    assert review["decision"]["model_training_allowed"] is False


def test_signed_approval_validator_blocks_missing_signed_record(tmp_path: Path) -> None:
    review = build_review(
        approval_record_schema_path=_schema(tmp_path / "schema.json"),
        signed_approval_record_path=tmp_path / "missing.json",
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "missing_signed_human_exception_approval_record" in review["blocking_reasons"]
    assert review["decision"]["signed_approval_record_valid"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "validation.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_human_exception_signed_approval_validation",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_human_exception_signed_approval_validation_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
