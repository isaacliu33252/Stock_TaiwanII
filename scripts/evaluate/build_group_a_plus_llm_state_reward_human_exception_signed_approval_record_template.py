#!/usr/bin/env python3
"""Build an unsigned human exception approval record template for GIFT review.

This writes a fill-in template only. It is not a signed approval record, does
not approve training, does not queue PPO, and does not change live GroupA+
strategy state.
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

from scripts.evaluate.build_group_a_plus_llm_state_reward_human_exception_approval_record_schema import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_APPROVAL_RECORD_SCHEMA,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_record_TEMPLATE.json"
)
DEFAULT_HISTORY_DIR = (
    PROJECT_ROOT / "report/group_a_plus/llm_state_reward_human_exception_signed_approval_record_template/history"
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


def _template(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("approval_record_template")
    return value if isinstance(value, dict) else {}


def _rules(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("validation_rules")
    return value if isinstance(value, dict) else {}


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def build_review(
    *,
    approval_record_schema_path: Path = DEFAULT_APPROVAL_RECORD_SCHEMA,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    schema = _load_json(approval_record_schema_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not schema:
        blockers.append("missing_human_exception_approval_record_schema")
    elif _decision(schema).get("approval_record_schema_ready") is not True:
        blockers.append("human_exception_approval_record_schema_not_ready")

    template = _template(schema)
    rules = _rules(schema)
    approval_scope = _dict_value(template, "approval_scope")
    approved_actions_template = _dict_value(template, "approved_actions")
    acknowledgements_template = _dict_value(template, "acknowledgements")

    required_false_permissions = list(rules.get("required_false_permissions") or [])
    for key in required_false_permissions:
        if approved_actions_template.get(key) is not False:
            blockers.append(f"schema_template_forbidden_action_not_false:{key}")
    if approved_actions_template.get("allow_model_training_command") is not False:
        blockers.append("schema_template_forbidden_action_not_false:allow_model_training_command")

    if template.get("reviewer") is not None:
        blockers.append("schema_template_reviewer_not_empty")
    if template.get("reviewer_role") is not None:
        blockers.append("schema_template_reviewer_role_not_empty")
    if template.get("approved_at") is not None:
        blockers.append("schema_template_approved_at_not_empty")
    if template.get("expires_at") is not None:
        blockers.append("schema_template_expires_at_not_empty")

    unsigned_template = {
        "record_id": template.get("record_id"),
        "approval_record_schema_version": template.get("approval_record_schema_version"),
        "source_draft_sha256": template.get("source_draft_sha256"),
        "reviewer": None,
        "reviewer_role": None,
        "approved_at": None,
        "expires_at": None,
        "approval_scope": approval_scope,
        "approved_actions": {
            **approved_actions_template,
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
        "acknowledgements": {key: False for key in acknowledgements_template},
        "constraint_overrides": {},
        "notes": None,
    }
    template_ready = not blockers

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_human_exception_signed_approval_record_template",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "unsigned_template_ready_for_manual_completion" if template_ready else "blocked",
        "policy": "unsigned_signed_approval_record_template_only_no_approval_no_training_no_live_action",
        "sources": {
            "approval_record_schema": _source(approval_record_schema_path),
        },
        "signed_approval_record_template": unsigned_template,
        "manual_completion_required": [
            "reviewer",
            "reviewer_role",
            "approved_at",
            "expires_at",
            "approved_actions.allow_non_ppo_offline_shadow_training_queue_review",
            *[f"acknowledgements.{key}" for key in acknowledgements_template],
        ],
        "validation_target_path": str(
            PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_record.json"
        ),
        "summary": {
            "signed_approval_record_template_ready": template_ready,
            "signed_approval_record_valid": False,
            "human_exception_approved": False,
            "non_ppo_shadow_queue_review_allowed": False,
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "schema_ready": _decision(schema).get("approval_record_schema_ready"),
            "record_id": unsigned_template.get("record_id"),
            "source_draft_sha256": unsigned_template.get("source_draft_sha256"),
            "excluded_tickers": approval_scope.get("excluded_tickers"),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "signed_approval_record_template_ready": template_ready,
            "signed_approval_record_valid": False,
            "human_exception_approved": False,
            "non_ppo_shadow_queue_review_allowed": False,
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


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_human_exception_signed_approval_record_template_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-22")
    parser.add_argument("--approval-record-schema", default=str(DEFAULT_APPROVAL_RECORD_SCHEMA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        approval_record_schema_path=_resolve(args.approval_record_schema),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward signed approval record template: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "signed_approval_record_template_ready": review["decision"][
                    "signed_approval_record_template_ready"
                ],
                "signed_approval_record_valid": review["decision"]["signed_approval_record_valid"],
                "human_exception_approved": review["decision"]["human_exception_approved"],
                "training_queue_allowed": review["decision"]["training_queue_allowed"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "ppo_training_allowed": review["decision"]["ppo_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
