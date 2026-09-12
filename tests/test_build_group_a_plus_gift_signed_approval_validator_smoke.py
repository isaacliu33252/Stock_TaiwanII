from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_gift_signed_approval_validator_smoke import build_review


def _schema() -> dict:
    return {
        "decision": {"approval_record_schema_ready": True},
        "approval_record_template": {
            "record_id": "gift_non_ppo_shadow_exception_20260821",
            "approval_record_schema_version": 1,
            "source_draft_sha256": "abc123",
            "approval_scope": {
                "scope": "non_ppo_offline_shadow_training_queue_review_only",
                "freeze_id": "freeze",
                "frozen_manifest_sha256": "manifest",
                "proposal_id": "proposal",
                "allowed_universe": ["0050.TW"],
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
                "00631l_and_00632r_remain_excluded": False,
                "golden1_0531_unchanged": False,
                "no_live_action_no_target_weight_no_auto_rebalance": False,
                "non_ppo_offline_shadow_review_only": False,
                "research_shadow_remains_blocked_for_live_allocation": False,
                "training_runner_must_preserve_no_action_outputs": False,
            },
            "constraint_overrides": {},
        },
        "validation_rules": {
            "required_template_fields": [
                "record_id",
                "approval_record_schema_version",
                "source_draft_sha256",
                "reviewer",
                "reviewer_role",
                "approved_at",
                "expires_at",
                "approval_scope",
                "approved_actions",
                "acknowledgements",
                "constraint_overrides",
            ],
            "required_false_permissions": [
                "allow_00631l_add",
                "allow_00632r_open",
                "allow_auto_rebalance",
                "allow_live_signal_output",
                "allow_live_strategy_change",
                "allow_model_training_command",
                "allow_ppo_training",
                "allow_target_weight_output",
            ],
            "required_acknowledgements": [
                "00631l_and_00632r_remain_excluded",
                "golden1_0531_unchanged",
                "no_live_action_no_target_weight_no_auto_rebalance",
                "non_ppo_offline_shadow_review_only",
                "research_shadow_remains_blocked_for_live_allocation",
                "training_runner_must_preserve_no_action_outputs",
            ],
            "constraint_overrides_must_be_empty": True,
        },
    }


def test_validator_smoke_uses_non_expired_temporary_record(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(_schema(), ensure_ascii=False), encoding="utf-8")

    review = build_review(schema_path=schema_path, as_of="2026-08-21")

    assert review["status"] == "passed"
    assert review["summary"]["smoke_passed"] is True
    assert review["summary"]["valid_non_ppo_shadow_record_accepted"] is True
    assert review["summary"]["invalid_allow_00631l_add_blocked"] is True
    assert review["summary"]["invalid_allow_model_training_command_blocked"] is True
    valid = review["smoke_cases"]["valid_non_ppo_shadow_record"]["validation"]
    assert "signed_record_expired_as_of_validation_date" not in valid["blocking_reasons"]
    assert review["temporary_record_policy"]["formal_signed_record_written"] is False
