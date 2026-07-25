#!/usr/bin/env python3
"""Draft a human exception record for future GIFT non-PPO shadow review.

This artifact is a draft only. It does not approve training, queue PPO, emit
target weights, or change live GroupA+ strategy state.
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

from scripts.evaluate.build_group_a_plus_llm_state_reward_research_shadow_blocker_triage import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_RESEARCH_SHADOW_TRIAGE,
)
from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_training_request_package import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_REQUEST_PACKAGE,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_MANUAL_APPROVAL = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_manual_approval_readiness_review.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_human_exception_record_draft.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_human_exception_record_draft/history"
REQUIRED_EXCLUDED_TICKERS = ["00631L.TW", "00632R.TW"]


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


def _boundary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("request_boundary")
    return value if isinstance(value, dict) else {}


def _unexpected_permissions(name: str, payload: dict[str, Any]) -> list[str]:
    decision = _decision(payload)
    blockers: list[str] = []
    for key in (
        "shadow_training_request_allowed",
        "manual_exception_to_queue_training_allowed",
        "manual_approval_to_queue_training_allowed",
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
    triage_path: Path = DEFAULT_RESEARCH_SHADOW_TRIAGE,
    manual_approval_path: Path = DEFAULT_MANUAL_APPROVAL,
    request_package_path: Path = DEFAULT_REQUEST_PACKAGE,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    triage = _load_json(triage_path)
    manual_approval = _load_json(manual_approval_path)
    request_package = _load_json(request_package_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not triage:
        blockers.append("missing_research_shadow_blocker_triage")
    elif _decision(triage).get("manual_exception_review_ready") is not True:
        blockers.append("manual_exception_review_not_ready")

    if not manual_approval:
        blockers.append("missing_manual_approval_readiness_review")
    elif _decision(manual_approval).get("manual_approval_review_ready") is not True:
        blockers.append("manual_approval_review_not_ready")

    if not request_package:
        blockers.append("missing_shadow_training_request_package")
    elif request_package.get("status") != "available_for_manual_review":
        blockers.append(f"request_package_not_available:{request_package.get('status')}")
    elif _summary(request_package).get("package_ready_for_manual_review") is not True:
        blockers.append("request_package_not_ready_for_manual_review")

    for name, payload in {
        "research_shadow_triage": triage,
        "manual_approval": manual_approval,
        "request_package": request_package,
    }.items():
        blockers.extend(_unexpected_permissions(name, payload))

    boundary = _boundary(request_package)
    eligible_tickers = list(boundary.get("eligible_tickers") or [])
    excluded_tickers = list(boundary.get("excluded_tickers") or [])
    state_columns = list(boundary.get("state_columns") or [])
    reward_columns = list(boundary.get("reward_columns") or [])
    hard_constraints = boundary.get("hard_constraints") if isinstance(boundary.get("hard_constraints"), dict) else {}

    for key in ("freeze_id", "frozen_manifest_sha256", "proposal_id"):
        if not boundary.get(key):
            blockers.append(f"request_boundary_missing:{key}")
    if not eligible_tickers:
        blockers.append("request_boundary_missing:eligible_tickers")
    if not state_columns:
        blockers.append("request_boundary_missing:state_columns")
    if not reward_columns:
        blockers.append("request_boundary_missing:reward_columns")

    missing_exclusions = [ticker for ticker in REQUIRED_EXCLUDED_TICKERS if ticker not in excluded_tickers]
    if missing_exclusions:
        blockers.extend(f"request_boundary_missing_excluded_ticker:{ticker}" for ticker in missing_exclusions)

    for ticker, constraint in (("00631L.TW", "no_00631l_add"), ("00632R.TW", "no_00632r_open")):
        if hard_constraints.get(constraint) is not True:
            blockers.append(f"request_boundary_missing_hard_constraint:{constraint}:{ticker}")

    draft_ready = not blockers
    record_id = f"gift_non_ppo_shadow_exception_{as_of.replace('-', '')}"
    triage_summary = _summary(triage)
    triage_decision = _decision(triage)
    manual_decision = _decision(manual_approval)
    package_summary = _summary(request_package)
    classified_blockers = triage.get("classified_blockers") if isinstance(triage.get("classified_blockers"), dict) else {}

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_human_exception_record_draft",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "draft_ready_for_human_review" if draft_ready else "blocked",
        "policy": "human_exception_record_draft_only_no_training_no_live_action",
        "sources": {
            "research_shadow_blocker_triage": _source(triage_path),
            "manual_approval_readiness": _source(manual_approval_path),
            "shadow_training_request_package": _source(request_package_path),
        },
        "exception_record_draft": {
            "record_id": record_id,
            "scope": "non_ppo_offline_shadow_training_queue_review_only",
            "approval_state": "draft_not_approved",
            "requested_by": None,
            "reviewer": None,
            "approved_at": None,
            "expires_at": None,
            "reviewer_required": True,
            "expiry_required": True,
            "freeze_id": boundary.get("freeze_id"),
            "frozen_manifest_sha256": boundary.get("frozen_manifest_sha256"),
            "proposal_id": boundary.get("proposal_id"),
            "allowed_universe": eligible_tickers,
            "excluded_tickers": excluded_tickers,
            "state_columns": state_columns,
            "reward_columns": reward_columns,
            "recommended_regime_filter": boundary.get("recommended_regime_filter"),
            "blocked_research_snapshot_acknowledgement_required": True,
            "research_shadow_blockers": classified_blockers,
            "hard_constraints": {
                "no_training_in_this_artifact": True,
                "no_ppo_training": True,
                "no_live_signal_output": True,
                "no_target_weight_output": True,
                "no_auto_rebalance": True,
                "no_00631l_add": True,
                "no_00632r_open": True,
                "no_live_strategy_change": True,
                "keep_golden1_0531_unchanged": True,
            },
        },
        "summary": {
            "human_exception_record_draft_ready": draft_ready,
            "human_exception_approved": False,
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "manual_exception_review_ready": triage_decision.get("manual_exception_review_ready"),
            "manual_approval_review_ready": manual_decision.get("manual_approval_review_ready"),
            "package_ready_for_manual_review": package_summary.get("package_ready_for_manual_review"),
            "research_shadow_blocker_count": triage_summary.get("research_shadow_blocker_count"),
            "live_allocation_blocker_count": triage_summary.get("live_allocation_blocker_count"),
            "training_governance_blocker_count": triage_summary.get("training_governance_blocker_count"),
            "eligible_ticker_count": len(eligible_tickers),
            "excluded_tickers": excluded_tickers,
            "recommended_regime_rule": package_summary.get("recommended_regime_rule"),
        },
        "required_signoff_fields": [
            "reviewer",
            "approved_at",
            "expires_at",
            "explicit_ack_research_shadow_remains_blocked_for_live_allocation",
            "explicit_ack_non_ppo_offline_shadow_review_only",
            "explicit_ack_no_live_action_no_target_weight_no_auto_rebalance",
            "explicit_ack_00631l_and_00632r_remain_excluded",
            "explicit_ack_golden1_0531_unchanged",
        ],
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "human_exception_record_draft_ready": draft_ready,
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
    return history_dir / f"llm_state_reward_human_exception_record_draft_{stamp}.json"


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
    parser.add_argument("--triage", default=str(DEFAULT_RESEARCH_SHADOW_TRIAGE))
    parser.add_argument("--manual-approval", default=str(DEFAULT_MANUAL_APPROVAL))
    parser.add_argument("--request-package", default=str(DEFAULT_REQUEST_PACKAGE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        triage_path=_resolve(args.triage),
        manual_approval_path=_resolve(args.manual_approval),
        request_package_path=_resolve(args.request_package),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward human exception record draft: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "human_exception_record_draft_ready": review["decision"]["human_exception_record_draft_ready"],
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
