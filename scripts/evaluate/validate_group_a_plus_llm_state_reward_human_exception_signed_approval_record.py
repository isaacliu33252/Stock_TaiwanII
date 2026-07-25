#!/usr/bin/env python3
"""Validate a signed human exception approval record for future GIFT review.

The validator checks a human-filled approval record against the generated
schema/template. A valid record may support manual review of a non-PPO offline
shadow queue step, but this validator never runs training, queues PPO, emits
target weights, or changes live GroupA+ strategy state.
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
from scripts.evaluate.build_group_a_plus_llm_state_reward_human_exception_record_draft import (  # noqa: E402
    REQUIRED_EXCLUDED_TICKERS,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_SIGNED_APPROVAL_RECORD = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_record.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_validation.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_human_exception_signed_approval_validation/history"


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


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def build_review(
    *,
    approval_record_schema_path: Path = DEFAULT_APPROVAL_RECORD_SCHEMA,
    signed_approval_record_path: Path = DEFAULT_SIGNED_APPROVAL_RECORD,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    schema = _load_json(approval_record_schema_path)
    signed_record = _load_json(signed_approval_record_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not schema:
        blockers.append("missing_human_exception_approval_record_schema")
    elif _decision(schema).get("approval_record_schema_ready") is not True:
        blockers.append("human_exception_approval_record_schema_not_ready")

    if not signed_record:
        blockers.append("missing_signed_human_exception_approval_record")

    template = _template(schema)
    rules = _rules(schema)
    approved_actions = _dict_value(signed_record, "approved_actions")
    approval_scope = _dict_value(signed_record, "approval_scope")
    acknowledgements = _dict_value(signed_record, "acknowledgements")
    constraint_overrides = signed_record.get("constraint_overrides")

    if signed_record:
        for field in rules.get("required_template_fields") or []:
            if field not in signed_record:
                blockers.append(f"signed_record_missing_required_field:{field}")

        if signed_record.get("record_id") != template.get("record_id"):
            blockers.append("signed_record_record_id_mismatch")
        if signed_record.get("approval_record_schema_version") != template.get("approval_record_schema_version"):
            blockers.append("signed_record_schema_version_mismatch")
        if signed_record.get("source_draft_sha256") != template.get("source_draft_sha256"):
            blockers.append("signed_record_source_draft_sha256_mismatch")

        if not _is_nonempty_string(signed_record.get("reviewer")):
            blockers.append("signed_record_missing_reviewer")
        if not _is_nonempty_string(signed_record.get("reviewer_role")):
            blockers.append("signed_record_missing_reviewer_role")

    approved_at = _parse_iso(signed_record.get("approved_at")) if signed_record else None
    expires_at = _parse_iso(signed_record.get("expires_at")) if signed_record else None
    as_of_dt = _parse_iso(as_of) or _parse_iso(f"{as_of}T00:00:00")
    if signed_record and approved_at is None:
        blockers.append("signed_record_invalid_or_missing_approved_at")
    if signed_record and expires_at is None:
        blockers.append("signed_record_invalid_or_missing_expires_at")
    if approved_at is not None and expires_at is not None and expires_at <= approved_at:
        blockers.append("signed_record_expires_at_not_after_approved_at")
    if expires_at is not None and as_of_dt is not None and expires_at <= as_of_dt:
        blockers.append("signed_record_expired_as_of_validation_date")

    template_scope = _dict_value(template, "approval_scope")
    excluded_tickers = list(approval_scope.get("excluded_tickers") or [])
    if signed_record:
        for key in ("scope", "freeze_id", "frozen_manifest_sha256", "proposal_id"):
            if approval_scope.get(key) != template_scope.get(key):
                blockers.append(f"signed_record_approval_scope_mismatch:{key}")
        if list(approval_scope.get("allowed_universe") or []) != list(template_scope.get("allowed_universe") or []):
            blockers.append("signed_record_allowed_universe_mismatch")
        if excluded_tickers != list(template_scope.get("excluded_tickers") or []):
            blockers.append("signed_record_excluded_tickers_mismatch")
        for ticker in REQUIRED_EXCLUDED_TICKERS:
            if ticker not in excluded_tickers:
                blockers.append(f"signed_record_missing_excluded_ticker:{ticker}")

        if approved_actions.get("allow_non_ppo_offline_shadow_training_queue_review") is not True:
            blockers.append("signed_record_non_ppo_shadow_queue_review_not_approved")
        for key in rules.get("required_false_permissions") or []:
            if approved_actions.get(key) is not False:
                blockers.append(f"signed_record_forbidden_action_not_false:{key}")
        if approved_actions.get("allow_model_training_command") is not False:
            blockers.append("signed_record_forbidden_action_not_false:allow_model_training_command")

        for key in rules.get("required_acknowledgements") or []:
            if acknowledgements.get(key) is not True:
                blockers.append(f"signed_record_missing_acknowledgement:{key}")

        if rules.get("constraint_overrides_must_be_empty") is True and constraint_overrides != {}:
            blockers.append("signed_record_constraint_overrides_not_empty")
        if signed_record.get("notes") in (None, ""):
            warnings.append("signed_record_notes_empty")

    signed_record_valid = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_human_exception_signed_approval_validation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "valid_for_manual_non_ppo_shadow_queue_review" if signed_record_valid else "blocked",
        "policy": "signed_approval_validation_only_no_training_no_live_action",
        "sources": {
            "approval_record_schema": _source(approval_record_schema_path),
            "signed_approval_record": _source(signed_approval_record_path),
        },
        "validation": {
            "signed_record_sha256": _sha256_file(signed_approval_record_path),
            "schema_sha256": _sha256_file(approval_record_schema_path),
            "record_id": signed_record.get("record_id"),
            "reviewer": signed_record.get("reviewer"),
            "reviewer_role": signed_record.get("reviewer_role"),
            "approved_at": signed_record.get("approved_at"),
            "expires_at": signed_record.get("expires_at"),
            "source_draft_sha256": signed_record.get("source_draft_sha256"),
            "approval_scope": approval_scope,
        },
        "summary": {
            "signed_approval_record_valid": signed_record_valid,
            "human_exception_approved": signed_record_valid,
            "non_ppo_shadow_queue_review_allowed": signed_record_valid,
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "signed_record_exists": bool(signed_record),
            "schema_ready": _decision(schema).get("approval_record_schema_ready"),
            "reviewer": signed_record.get("reviewer"),
            "expires_at": signed_record.get("expires_at"),
            "excluded_tickers": excluded_tickers,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "signed_approval_record_valid": signed_record_valid,
            "human_exception_approved": signed_record_valid,
            "non_ppo_shadow_queue_review_allowed": signed_record_valid,
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
    return history_dir / f"llm_state_reward_human_exception_signed_approval_validation_{stamp}.json"


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
    parser.add_argument("--signed-approval-record", default=str(DEFAULT_SIGNED_APPROVAL_RECORD))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        approval_record_schema_path=_resolve(args.approval_record_schema),
        signed_approval_record_path=_resolve(args.signed_approval_record),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward signed approval validation: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "signed_approval_record_valid": review["decision"]["signed_approval_record_valid"],
                "human_exception_approved": review["decision"]["human_exception_approved"],
                "non_ppo_shadow_queue_review_allowed": review["decision"]["non_ppo_shadow_queue_review_allowed"],
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
