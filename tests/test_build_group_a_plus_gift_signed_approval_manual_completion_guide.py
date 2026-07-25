from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_gift_signed_approval_manual_completion_guide import (
    build_guide,
    write_outputs,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_manual_completion_guide_is_informational_only(tmp_path: Path) -> None:
    template = _write(
        tmp_path / "template.json",
        {
            "signed_approval_record_template": {
                "record_id": "gift_non_ppo_shadow_exception_20260723",
                "source_draft_sha256": "abc",
                "approval_scope": {
                    "scope": "non_ppo_offline_shadow_training_queue_review_only",
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
                    "golden1_0531_unchanged": False,
                    "no_live_action_no_target_weight_no_auto_rebalance": False,
                },
            }
        },
    )
    checklist = _write(
        tmp_path / "checklist.json",
        {
            "summary": {
                "manual_completion_ready": True,
                "manual_completion_pending": True,
                "signed_record_exists": False,
            }
        },
    )
    validation = _write(
        tmp_path / "validation.json",
        {
            "summary": {
                "signed_approval_record_valid": False,
                "human_exception_approved": False,
            }
        },
    )
    deployment = _write(
        tmp_path / "deployment.json",
        {
            "status": "manual_review_required",
            "blocking_reasons": [],
            "warning_reasons": ["gift_signed_approval_manual_completion_pending"],
            "decision": {"broker_actionable": True},
            "computed": {
                "target_weights": {"0050.TW": 0.5, "cash": 0.5},
                "execution_target_shares": {"0050.TW": 1},
            },
        },
    )
    target = tmp_path / "signed_record.json"

    guide = build_guide(
        template_path=template,
        checklist_path=checklist,
        validation_path=validation,
        deployment_path=deployment,
        target_signed_record_path=target,
        as_of="2026-07-23",
    )

    assert guide["status"] == "ready_for_human_completion"
    assert guide["summary"]["manual_completion_ready"] is True
    assert guide["summary"]["signed_record_exists"] is False
    assert guide["decision"]["creates_signed_record"] is False
    assert guide["decision"]["training_queue_allowed"] is False
    assert guide["decision"]["model_training_allowed"] is False
    assert guide["decision"]["ppo_training_allowed"] is False
    assert guide["decision"]["promote_to_live"] is False
    assert guide["decision"]["target_weight_change_allowed"] is False
    assert guide["decision"]["auto_rebalance_allowed"] is False
    assert guide["decision"]["allow_00631l_add"] is False
    assert guide["decision"]["allow_00632r_open"] is False
    assert guide["decision"]["keep_golden1_0531_unchanged"] is True
    assert target.exists() is False
    assert guide["manual_fields"]["single_allowed_true_action"] == (
        "approved_actions.allow_non_ppo_offline_shadow_training_queue_review"
    )
    assert "00631L.TW" in guide["scope_snapshot"]["excluded_tickers"]


def test_write_outputs_writes_json_markdown_and_optional_history(tmp_path: Path) -> None:
    guide = {
        "schema_version": 1,
        "report_type": "group_a_plus_gift_signed_approval_manual_completion_guide",
        "generated_at": "2026-07-22T00:00:00",
        "as_of": "2026-07-23",
        "status": "ready_for_human_completion",
        "paths": {
            "template": "template.json",
            "target_signed_record": "signed.json",
            "validation": "validation.json",
        },
        "summary": {
            "manual_completion_ready": True,
            "signed_record_exists": False,
            "signed_approval_record_valid": False,
            "human_exception_approved": False,
        },
        "manual_fields": {
            "identity_and_dates": ["reviewer"],
            "single_allowed_true_action": "approved_actions.allow_non_ppo_offline_shadow_training_queue_review",
            "acknowledgements_required_true": ["golden1_0531_unchanged"],
            "approved_actions_required_false": ["approved_actions.allow_model_training_command"],
        },
        "deployment_snapshot": {"broker_actionable": True, "status": "manual_review_required"},
    }
    output_json = tmp_path / "latest" / "guide.json"
    output_md = tmp_path / "latest" / "guide.md"
    history = tmp_path / "history"

    write_outputs(guide, output_json=output_json, output_md=output_md, history_dir=history)

    assert json.loads(output_json.read_text(encoding="utf-8")) == guide
    assert "GIFT Signed Approval Manual Completion Guide" in output_md.read_text(encoding="utf-8")
    assert (history / "gift_signed_approval_manual_completion_guide_20260723.json").exists()
