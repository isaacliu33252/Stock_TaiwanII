#!/usr/bin/env python3
"""Build a human exception approval record schema for future GIFT review.

This artifact defines the fields and validation rules a human approval record
must satisfy. It is not an approval record, does not approve training, does not
queue PPO, and does not change live GroupA+ strategy state.
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

from scripts.evaluate.build_group_a_plus_llm_state_reward_human_exception_record_draft import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_HUMAN_EXCEPTION_DRAFT,
    REQUIRED_EXCLUDED_TICKERS,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_approval_record_schema.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_human_exception_approval_record_schema/history"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _sha256_file(path), "exists": path.exists()}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _draft(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("exception_record_draft")
    return value if isinstance(value, dict) else {}


def _unexpected_permissions(name: str, payload: dict[str, Any]) -> list[str]:
    decision = _decision(payload)
    blockers: list[str] = []
    for key in (
        "human_exception_approved",
        "training_queue_allowed",
        "shadow_training_request_allowed",
        "model_training_allowed",
        "ppo_training_allowed",
        "outputs_actions",
        "outputs_target_weights",
        "promote_to_live",
        "target_weight_change_allowed",
        "auto_rebalance_allowed",
        "allow_00631l_add",
        "allow_00632r_open",
    ):
        if decision.get(key) is True:
            blockers.append(f"{name}_unexpected_permission:{key}")
    return blockers


def build_review(
    *,
    human_exception_draft_path: Path = DEFAULT_HUMAN_EXCEPTION_DRAFT,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    human_exception_draft = _load_json(human_exception_draft_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not human_exception_draft:
        blockers.append("missing_human_exception_record_draft")
    elif _decision(human_exception_draft).get("human_exception_record_draft_ready") is not True:
        blockers.append("human_exception_record_draft_not_ready")

    blockers.extend(_unexpected_permissions("human_exception_draft", human_exception_draft))

    draft = _draft(human_exception_draft)
    excluded_tickers = list(draft.get("excluded_tickers") or [])
    allowed_universe = list(draft.get("allowed_universe") or [])
    required_signoff_fields = list(human_exception_draft.get("required_signoff_fields") or [])
    hard_constraints = draft.get("hard_constraints") if isinstance(draft.get("hard_constraints"), dict) else {}

    for key in ("record_id", "freeze_id", "frozen_manifest_sha256", "proposal_id"):
        if not draft.get(key):
            blockers.append(f"human_exception_draft_missing:{key}")
    if draft.get("scope") != "non_ppo_offline_shadow_training_queue_review_only":
        blockers.append(f"human_exception_draft_invalid_scope:{draft.get('scope')}")
    if draft.get("approval_state") != "draft_not_approved":
        blockers.append(f"human_exception_draft_invalid_approval_state:{draft.get('approval_state')}")

    for ticker in REQUIRED_EXCLUDED_TICKERS:
        if ticker not in excluded_tickers:
            blockers.append(f"human_exception_draft_missing_excluded_ticker:{ticker}")
    if not allowed_universe:
        blockers.append("human_exception_draft_missing:allowed_universe")

    required_constraints = {
        "no_training_in_this_artifact",
        "no_ppo_training",
        "no_live_signal_output",
        "no_target_weight_output",
        "no_auto_rebalance",
        "no_00631l_add",
        "no_00632r_open",
        "no_live_strategy_change",
        "keep_golden1_0531_unchanged",
    }
    for constraint in sorted(required_constraints):
        if hard_constraints.get(constraint) is not True:
            blockers.append(f"human_exception_draft_missing_hard_constraint:{constraint}")

    required_template_fields = [
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
        "notes",
    ]
    required_acknowledgements = [
        "research_shadow_remains_blocked_for_live_allocation",
        "non_ppo_offline_shadow_review_only",
        "no_live_action_no_target_weight_no_auto_rebalance",
        "00631l_and_00632r_remain_excluded",
        "golden1_0531_unchanged",
        "training_runner_must_preserve_no_action_outputs",
    ]
    schema_ready = not blockers
    draft_summary = _summary(human_exception_draft)
    draft_decision = _decision(human_exception_draft)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_human_exception_approval_record_schema",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "template_ready_for_human_signature" if schema_ready else "blocked",
        "policy": "approval_record_schema_only_no_approval_no_training_no_live_action",
        "sources": {
            "human_exception_record_draft": _source(human_exception_draft_path),
        },
        "approval_record_template": {
            "record_id": draft.get("record_id"),
            "approval_record_schema_version": 1,
            "source_draft_sha256": _sha256_file(human_exception_draft_path),
            "reviewer": None,
            "reviewer_role": None,
            "approved_at": None,
            "expires_at": None,
            "approval_scope": {
                "scope": "non_ppo_offline_shadow_training_queue_review_only",
                "freeze_id": draft.get("freeze_id"),
                "frozen_manifest_sha256": draft.get("frozen_manifest_sha256"),
                "proposal_id": draft.get("proposal_id"),
                "allowed_universe": allowed_universe,
                "excluded_tickers": excluded_tickers,
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
            "acknowledgements": {key: False for key in required_acknowledgements},
            "constraint_overrides": {},
            "notes": None,
        },
        "validation_rules": {
            "required_template_fields": required_template_fields,
            "required_signoff_fields_from_draft": required_signoff_fields,
            "required_acknowledgements": required_acknowledgements,
            "must_match_source_draft_sha256": True,
            "reviewer_required": True,
            "approved_at_required": True,
            "expires_at_required": True,
            "expiry_must_be_after_approved_at": True,
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
        "summary": {
            "approval_record_schema_ready": schema_ready,
            "approval_record_template_ready": schema_ready,
            "human_exception_record_draft_ready": draft_decision.get("human_exception_record_draft_ready"),
            "human_exception_approved": False,
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "draft_status": human_exception_draft.get("status"),
            "draft_human_exception_approved": draft_summary.get("human_exception_approved"),
            "eligible_ticker_count": len(allowed_universe),
            "excluded_tickers": excluded_tickers,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "approval_record_schema_ready": schema_ready,
            "approval_record_template_ready": schema_ready,
            "human_exception_approved": False,
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
    return history_dir / f"llm_state_reward_human_exception_approval_record_schema_{stamp}.json"


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
    parser.add_argument("--human-exception-draft", default=str(DEFAULT_HUMAN_EXCEPTION_DRAFT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        human_exception_draft_path=_resolve(args.human_exception_draft),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward human exception approval record schema: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "approval_record_schema_ready": review["decision"]["approval_record_schema_ready"],
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
