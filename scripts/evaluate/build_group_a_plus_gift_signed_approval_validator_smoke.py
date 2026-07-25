#!/usr/bin/env python3
"""Smoke-test GIFT signed approval validation with temporary records.

The smoke test writes candidate signed records only to a temporary directory.
It never creates the formal signed approval record, never approves training,
never queues PPO, and never changes live GroupA+ strategy state.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_SCHEMA = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_approval_record_schema.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/gift_signed_approval_validator_smoke.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/gift_signed_approval_validator_smoke/history"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _approval_record_template(schema: dict[str, Any]) -> dict[str, Any]:
    value = schema.get("approval_record_template")
    return deepcopy(value) if isinstance(value, dict) else {}


def _valid_record_from_template(template: dict[str, Any]) -> dict[str, Any]:
    record = deepcopy(template)
    record["reviewer"] = "validator_smoke_reviewer"
    record["reviewer_role"] = "research_governance_smoke"
    record["approved_at"] = "2026-07-22T09:00:00"
    record["expires_at"] = "2026-07-29T09:00:00"
    record["notes"] = "Temporary validator smoke record; not a formal approval."

    approved_actions = record.setdefault("approved_actions", {})
    approved_actions["allow_non_ppo_offline_shadow_training_queue_review"] = True
    for key in (
        "allow_model_training_command",
        "allow_ppo_training",
        "allow_live_signal_output",
        "allow_target_weight_output",
        "allow_auto_rebalance",
        "allow_live_strategy_change",
        "allow_00631l_add",
        "allow_00632r_open",
    ):
        approved_actions[key] = False

    acknowledgements = record.setdefault("acknowledgements", {})
    for key in list(acknowledgements):
        acknowledgements[key] = True

    record["constraint_overrides"] = {}
    return record


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _compact_validation(review: dict[str, Any]) -> dict[str, Any]:
    decision = _decision(review)
    summary = _summary(review)
    return {
        "status": review.get("status"),
        "signed_approval_record_valid": decision.get("signed_approval_record_valid"),
        "human_exception_approved": decision.get("human_exception_approved"),
        "non_ppo_shadow_queue_review_allowed": decision.get("non_ppo_shadow_queue_review_allowed"),
        "training_queue_allowed": summary.get("training_queue_allowed"),
        "model_training_allowed": decision.get("model_training_allowed"),
        "ppo_training_allowed": decision.get("ppo_training_allowed"),
        "promote_to_live": decision.get("promote_to_live"),
        "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
        "auto_rebalance_allowed": decision.get("auto_rebalance_allowed"),
        "allow_00631l_add": decision.get("allow_00631l_add"),
        "allow_00632r_open": decision.get("allow_00632r_open"),
        "blocking_reasons": review.get("blocking_reasons") or [],
        "warning_reasons": review.get("warning_reasons") or [],
    }


def build_review(
    *,
    schema_path: Path = DEFAULT_SCHEMA,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    from scripts.evaluate.validate_group_a_plus_llm_state_reward_human_exception_signed_approval_record import (
        build_review as validate_signed_record,
    )

    schema = _load(schema_path)
    template = _approval_record_template(schema)
    blockers: list[str] = []
    warnings: list[str] = []
    if not schema:
        blockers.append("missing_human_exception_approval_record_schema")
    elif _decision(schema).get("approval_record_schema_ready") is not True:
        blockers.append("human_exception_approval_record_schema_not_ready")
    if not template:
        blockers.append("missing_approval_record_template")

    smoke_cases: dict[str, Any] = {}
    temp_dir_used = None
    if not blockers:
        with TemporaryDirectory(prefix="gift_signed_approval_smoke_") as tmp:
            temp_dir = Path(tmp)
            temp_dir_used = str(temp_dir)

            valid_record = _valid_record_from_template(template)
            valid_path = _write(temp_dir / "valid_signed_record.json", valid_record)
            valid_review = validate_signed_record(
                approval_record_schema_path=schema_path,
                signed_approval_record_path=valid_path,
                as_of=as_of,
            )
            smoke_cases["valid_non_ppo_shadow_record"] = {
                "input_path_was_temporary": True,
                "validation": _compact_validation(valid_review),
            }

            invalid_00631l = deepcopy(valid_record)
            invalid_00631l["approved_actions"]["allow_00631l_add"] = True
            invalid_00631l_path = _write(temp_dir / "invalid_allow_00631l_add.json", invalid_00631l)
            invalid_00631l_review = validate_signed_record(
                approval_record_schema_path=schema_path,
                signed_approval_record_path=invalid_00631l_path,
                as_of=as_of,
            )
            smoke_cases["invalid_allow_00631l_add"] = {
                "input_path_was_temporary": True,
                "validation": _compact_validation(invalid_00631l_review),
                "expected_blocking_reason": "signed_record_forbidden_action_not_false:allow_00631l_add",
            }

            invalid_training = deepcopy(valid_record)
            invalid_training["approved_actions"]["allow_model_training_command"] = True
            invalid_training_path = _write(temp_dir / "invalid_allow_model_training_command.json", invalid_training)
            invalid_training_review = validate_signed_record(
                approval_record_schema_path=schema_path,
                signed_approval_record_path=invalid_training_path,
                as_of=as_of,
            )
            smoke_cases["invalid_allow_model_training_command"] = {
                "input_path_was_temporary": True,
                "validation": _compact_validation(invalid_training_review),
                "expected_blocking_reason": "signed_record_forbidden_action_not_false:allow_model_training_command",
            }

    valid_case = (smoke_cases.get("valid_non_ppo_shadow_record") or {}).get("validation") or {}
    invalid_00631l_case = (smoke_cases.get("invalid_allow_00631l_add") or {}).get("validation") or {}
    invalid_training_case = (smoke_cases.get("invalid_allow_model_training_command") or {}).get("validation") or {}

    valid_pass = (
        valid_case.get("signed_approval_record_valid") is True
        and valid_case.get("non_ppo_shadow_queue_review_allowed") is True
        and valid_case.get("training_queue_allowed") is False
        and valid_case.get("model_training_allowed") is False
        and valid_case.get("ppo_training_allowed") is False
        and valid_case.get("promote_to_live") is False
        and valid_case.get("target_weight_change_allowed") is False
        and valid_case.get("auto_rebalance_allowed") is False
        and valid_case.get("allow_00631l_add") is False
        and valid_case.get("allow_00632r_open") is False
    )
    invalid_00631l_pass = (
        invalid_00631l_case.get("signed_approval_record_valid") is False
        and "signed_record_forbidden_action_not_false:allow_00631l_add"
        in invalid_00631l_case.get("blocking_reasons", [])
    )
    invalid_training_pass = (
        invalid_training_case.get("signed_approval_record_valid") is False
        and "signed_record_forbidden_action_not_false:allow_model_training_command"
        in invalid_training_case.get("blocking_reasons", [])
    )

    if smoke_cases and not valid_pass:
        blockers.append("valid_non_ppo_shadow_record_not_accepted_safely")
    if smoke_cases and not invalid_00631l_pass:
        blockers.append("invalid_allow_00631l_add_not_blocked")
    if smoke_cases and not invalid_training_pass:
        blockers.append("invalid_allow_model_training_command_not_blocked")

    smoke_passed = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_gift_signed_approval_validator_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "passed" if smoke_passed else "blocked",
        "policy": "validator_smoke_only_temporary_records_no_formal_approval_no_training_no_live_action",
        "sources": {
            "approval_record_schema": {
                "path": str(schema_path),
                "exists": schema_path.exists(),
            }
        },
        "temporary_record_policy": {
            "formal_signed_record_written": False,
            "temporary_directory_prefix": "gift_signed_approval_smoke_",
            "temporary_directory_example": temp_dir_used,
            "temporary_files_removed_after_validation": True,
        },
        "smoke_cases": smoke_cases,
        "summary": {
            "smoke_passed": smoke_passed,
            "valid_non_ppo_shadow_record_accepted": valid_pass,
            "invalid_allow_00631l_add_blocked": invalid_00631l_pass,
            "invalid_allow_model_training_command_blocked": invalid_training_pass,
            "formal_signed_record_written": False,
            "signed_approval_record_valid_in_latest": False,
            "human_exception_approved_in_latest": False,
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
            "validator_smoke_passed": smoke_passed,
            "formal_signed_record_created": False,
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


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"gift_signed_approval_validator_smoke_{as_of.replace('-', '')}.json"


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
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(schema_path=Path(args.schema), as_of=args.as_of)
    write_review(review, Path(args.output), None if args.no_history else Path(args.history_dir))
    print(f"GIFT signed approval validator smoke: {Path(args.output).resolve()}")
    print(json.dumps(review["summary"], ensure_ascii=False, indent=2))
    if review["blocking_reasons"]:
        print(json.dumps({"blocking_reasons": review["blocking_reasons"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
