#!/usr/bin/env python3
"""Build a human checklist for GIFT signed approval completion.

This report is a checklist only. It does not create a signed approval record,
does not approve training, does not queue PPO, and does not change live
GroupA+ strategy state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "latest"
DEFAULT_DRAFT = LATEST_DIR / "llm_state_reward_human_exception_record_draft.json"
DEFAULT_SCHEMA = LATEST_DIR / "llm_state_reward_human_exception_approval_record_schema.json"
DEFAULT_TEMPLATE = LATEST_DIR / "llm_state_reward_human_exception_signed_approval_record_TEMPLATE.json"
DEFAULT_VALIDATION = LATEST_DIR / "llm_state_reward_human_exception_signed_approval_validation.json"
DEFAULT_TARGET_SIGNED_RECORD = LATEST_DIR / "llm_state_reward_human_exception_signed_approval_record.json"
DEFAULT_OUTPUT = LATEST_DIR / "gift_signed_approval_checklist_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/gift_signed_approval_checklist/history"


FORBIDDEN_TRUE_ACTIONS = [
    "allow_model_training_command",
    "allow_ppo_training",
    "allow_live_signal_output",
    "allow_target_weight_output",
    "allow_auto_rebalance",
    "allow_live_strategy_change",
    "allow_00631l_add",
    "allow_00632r_open",
]


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "sha256": _sha256(path)}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _template_payload(template_review: dict[str, Any]) -> dict[str, Any]:
    value = template_review.get("signed_approval_record_template")
    return value if isinstance(value, dict) else {}


def _schema_template(schema_review: dict[str, Any]) -> dict[str, Any]:
    value = schema_review.get("approval_record_template")
    return value if isinstance(value, dict) else {}


def _schema_rules(schema_review: dict[str, Any]) -> dict[str, Any]:
    value = schema_review.get("validation_rules")
    return value if isinstance(value, dict) else {}


def build_review(
    *,
    draft_path: Path = DEFAULT_DRAFT,
    schema_path: Path = DEFAULT_SCHEMA,
    template_path: Path = DEFAULT_TEMPLATE,
    validation_path: Path = DEFAULT_VALIDATION,
    target_signed_record_path: Path = DEFAULT_TARGET_SIGNED_RECORD,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    draft = _load(draft_path)
    schema = _load(schema_path)
    template_review = _load(template_path)
    validation = _load(validation_path)
    signed_record = _load(target_signed_record_path)

    blockers: list[str] = []
    warnings: list[str] = []

    if not draft:
        blockers.append("missing_human_exception_record_draft")
    elif _decision(draft).get("human_exception_record_draft_ready") is not True:
        blockers.append("human_exception_record_draft_not_ready")

    if not schema:
        blockers.append("missing_human_exception_approval_record_schema")
    elif _decision(schema).get("approval_record_schema_ready") is not True:
        blockers.append("human_exception_approval_record_schema_not_ready")

    if not template_review:
        blockers.append("missing_signed_approval_record_template")
    elif _decision(template_review).get("signed_approval_record_template_ready") is not True:
        blockers.append("signed_approval_record_template_not_ready")

    template = _template_payload(template_review)
    schema_template = _schema_template(schema)
    rules = _schema_rules(schema)
    approved_actions = _dict_value(template, "approved_actions")
    acknowledgements = _dict_value(template, "acknowledgements")
    approval_scope = _dict_value(template, "approval_scope")

    if schema_template and template:
        for key in ("record_id", "approval_record_schema_version", "source_draft_sha256"):
            if template.get(key) != schema_template.get(key):
                blockers.append(f"template_schema_mismatch:{key}")
        if approval_scope != _dict_value(schema_template, "approval_scope"):
            blockers.append("template_schema_mismatch:approval_scope")

    required_completion = list(template_review.get("manual_completion_required") or [])
    if not required_completion:
        blockers.append("template_missing_manual_completion_required")

    missing_manual_fields = [
        field
        for field in ("reviewer", "reviewer_role", "approved_at", "expires_at")
        if template.get(field) in (None, "")
    ]
    missing_action_toggles = [
        "approved_actions.allow_non_ppo_offline_shadow_training_queue_review"
        if approved_actions.get("allow_non_ppo_offline_shadow_training_queue_review") is not True
        else None
    ]
    missing_acknowledgements = [
        f"acknowledgements.{key}"
        for key, value in sorted(acknowledgements.items())
        if value is not True
    ]
    forbidden_action_issues = [
        f"approved_actions.{key}_must_remain_false"
        for key in FORBIDDEN_TRUE_ACTIONS
        if approved_actions.get(key) is not False
    ]
    required_false_permissions = list(rules.get("required_false_permissions") or [])
    for key in required_false_permissions:
        if approved_actions.get(key) is not False:
            forbidden_action_issues.append(f"approved_actions.{key}_must_remain_false")

    signed_validation_summary = _summary(validation)
    signed_validation_decision = _decision(validation)
    signed_record_valid = signed_validation_decision.get("signed_approval_record_valid") is True
    human_exception_approved = signed_validation_decision.get("human_exception_approved") is True

    checklist_items = [
        {
            "id": "copy_template_to_target_signed_record_path",
            "status": "done" if signed_record else "pending",
            "target_path": str(target_signed_record_path),
        },
        {
            "id": "fill_manual_identity_and_dates",
            "status": "pending" if missing_manual_fields else "done",
            "missing_fields": missing_manual_fields,
        },
        {
            "id": "approve_only_non_ppo_offline_shadow_queue_review",
            "status": "pending" if any(missing_action_toggles) else "done",
            "required_true_fields": [item for item in missing_action_toggles if item],
        },
        {
            "id": "keep_all_live_and_training_permissions_false",
            "status": "blocked" if forbidden_action_issues else "done",
            "forbidden_true_fields": sorted(set(forbidden_action_issues)),
        },
        {
            "id": "acknowledge_all_safety_constraints",
            "status": "pending" if missing_acknowledgements else "done",
            "missing_acknowledgements": missing_acknowledgements,
        },
        {
            "id": "run_signed_approval_validator",
            "status": "done" if signed_record_valid else "pending",
            "current_validation_status": validation.get("status"),
            "current_blocking_reasons": validation.get("blocking_reasons") or [],
        },
    ]

    manual_completion_ready = not blockers and not forbidden_action_issues
    completion_pending = any(item["status"] in {"pending", "blocked"} for item in checklist_items)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_gift_signed_approval_checklist_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": (
            "signed_record_valid_for_non_ppo_shadow_review"
            if signed_record_valid
            else "manual_completion_pending"
            if manual_completion_ready
            else "blocked"
        ),
        "policy": "manual_checklist_only_no_approval_no_training_no_live_action",
        "sources": {
            "human_exception_record_draft": _source(draft_path),
            "approval_record_schema": _source(schema_path),
            "signed_approval_record_template": _source(template_path),
            "signed_approval_validation": _source(validation_path),
            "target_signed_approval_record": _source(target_signed_record_path),
        },
        "target_signed_record_path": str(target_signed_record_path),
        "checklist_items": checklist_items,
        "manual_completion_fields": {
            "identity_and_dates": ["reviewer", "reviewer_role", "approved_at", "expires_at"],
            "only_field_that_may_be_set_true_in_approved_actions": (
                "allow_non_ppo_offline_shadow_training_queue_review"
            ),
            "acknowledgements_required_true": sorted(acknowledgements.keys()),
            "approved_actions_required_false": sorted(set(FORBIDDEN_TRUE_ACTIONS + required_false_permissions)),
        },
        "scope_snapshot": {
            "record_id": template.get("record_id"),
            "source_draft_sha256": template.get("source_draft_sha256"),
            "approval_scope": approval_scope,
            "excluded_tickers": approval_scope.get("excluded_tickers"),
        },
        "summary": {
            "draft_ready": _decision(draft).get("human_exception_record_draft_ready"),
            "schema_ready": _decision(schema).get("approval_record_schema_ready"),
            "template_ready": _decision(template_review).get("signed_approval_record_template_ready"),
            "signed_record_exists": bool(signed_record),
            "signed_approval_record_valid": signed_record_valid,
            "human_exception_approved": human_exception_approved,
            "manual_completion_ready": manual_completion_ready,
            "manual_completion_pending": completion_pending,
            "non_ppo_shadow_queue_review_allowed_by_signed_validation": signed_validation_summary.get(
                "non_ppo_shadow_queue_review_allowed"
            ),
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "checklist_available_for_manual_completion": manual_completion_ready,
            "signed_approval_record_valid": signed_record_valid,
            "human_exception_approved": human_exception_approved,
            "non_ppo_shadow_queue_review_allowed": signed_validation_summary.get(
                "non_ppo_shadow_queue_review_allowed"
            )
            is True,
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
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"gift_signed_approval_checklist_review_{as_of.replace('-', '')}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(review["as_of"])).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-22")
    parser.add_argument("--draft", default=str(DEFAULT_DRAFT))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--target-signed-record", default=str(DEFAULT_TARGET_SIGNED_RECORD))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        draft_path=Path(args.draft),
        schema_path=Path(args.schema),
        template_path=Path(args.template),
        validation_path=Path(args.validation),
        target_signed_record_path=Path(args.target_signed_record),
        as_of=args.as_of,
    )
    write_review(review, Path(args.output), None if args.no_history else Path(args.history_dir))
    print(f"GIFT signed approval checklist review: {Path(args.output).resolve()}")
    print(json.dumps(review["summary"], ensure_ascii=False, indent=2))
    if review["blocking_reasons"]:
        print(json.dumps({"blocking_reasons": review["blocking_reasons"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
