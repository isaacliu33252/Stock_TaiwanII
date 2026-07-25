#!/usr/bin/env python3
"""Review the high-dividend active-pain GIFT redesign candidate.

This binds the drawdown failure event audit to the accepted redesign proposal.
It only authorizes a future offline DGR implementation review; it does not
train models, emit target weights, or change live strategy behavior.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_EVENT_AUDIT = LATEST / "llm_state_reward_interface_drawdown_failure_event_audit.json"
DEFAULT_VALIDATION = LATEST / "llm_state_reward_interface_proposal_validation_review.json"
DEFAULT_PROMOTION_GATE = LATEST / "llm_state_reward_interface_promotion_gate_snapshot.json"
DEFAULT_OUTPUT = LATEST / "llm_state_reward_interface_high_dividend_active_pain_redesign_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_redesign_review/history"
PROPOSAL_ID = "gift_research_high_dividend_active_pain_v1"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _accepted_proposal(validation: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    for result in validation.get("proposal_results") or validation.get("results") or []:
        if result.get("proposal_id") == proposal_id and result.get("accepted_for_offline_review") is True:
            return result
    return {}


def build_review(
    *,
    event_audit_path: Path = DEFAULT_EVENT_AUDIT,
    validation_path: Path = DEFAULT_VALIDATION,
    promotion_gate_path: Path = DEFAULT_PROMOTION_GATE,
    min_high_dividend_active_weight: float = 0.05,
    max_high_dividend_active_contribution: float = -0.005,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    event_audit = _load(event_audit_path)
    validation = _load(validation_path)
    promotion_gate = _load(promotion_gate_path)
    proposal = _accepted_proposal(validation, PROPOSAL_ID)
    blockers: list[str] = []
    warnings: list[str] = []

    if not event_audit:
        blockers.append("missing_drawdown_failure_event_audit")
    elif event_audit.get("status") != "available_for_manual_offline_review":
        blockers.append(f"event_audit_not_available:{event_audit.get('status')}")
    if not validation:
        blockers.append("missing_proposal_validation_review")
    elif validation.get("status") != "available_for_manual_offline_review":
        blockers.append(f"proposal_validation_not_available:{validation.get('status')}")
    if not proposal:
        blockers.append(f"proposal_not_accepted:{PROPOSAL_ID}")
    if not promotion_gate:
        blockers.append("missing_promotion_gate_snapshot")

    high_div_weight = _nested(event_audit, "summary", "event_mean_active_weight_by_bucket", "high_dividend")
    high_div_contribution = _nested(event_audit, "summary", "event_sum_active_contribution_by_bucket", "high_dividend")
    dominant_bucket = _nested(event_audit, "summary", "dominant_negative_event_bucket")
    if high_div_weight is None or float(high_div_weight) < min_high_dividend_active_weight:
        blockers.append("high_dividend_active_weight_evidence_below_threshold")
    if high_div_contribution is None or float(high_div_contribution) > max_high_dividend_active_contribution:
        blockers.append("high_dividend_active_contribution_evidence_not_negative_enough")
    if dominant_bucket != "high_dividend":
        warnings.append(f"dominant_negative_event_bucket_not_high_dividend:{dominant_bucket}")

    promotion_gate_passed = _nested(promotion_gate, "decision", "promotion_gate_passed") is True
    if promotion_gate_passed:
        warnings.append("promotion_gate_passed_unexpected_for_redesign_review")

    ready = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_redesign_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "available_for_offline_dgr_design" if ready else "blocked",
        "policy": "redesign_review_only_no_model_training_no_live_action",
        "proposal_id": PROPOSAL_ID,
        "inputs": {
            "event_audit": str(event_audit_path),
            "proposal_validation": str(validation_path),
            "promotion_gate_snapshot": str(promotion_gate_path),
            "min_high_dividend_active_weight": min_high_dividend_active_weight,
            "max_high_dividend_active_contribution": max_high_dividend_active_contribution,
        },
        "evidence": {
            "dominant_negative_event_bucket": dominant_bucket,
            "high_dividend_event_mean_active_weight": high_div_weight,
            "high_dividend_event_sum_active_contribution": high_div_contribution,
            "worst_fold": _nested(event_audit, "summary", "worst_fold"),
            "worst_fold_trough_date": _nested(event_audit, "summary", "worst_fold_trough_date"),
            "accepted_proposal": proposal,
            "promotion_gate_passed": promotion_gate_passed,
        },
        "recommended_offline_interface_changes": {
            "feature_family": "bucket_active_pain",
            "feature_primitives": [
                "active_bucket_weight",
                "active_bucket_return_contribution",
                "active_bucket_drawdown_depth",
                "reward_signal_concentration_hhi",
                "high_dividend_active_pain",
            ],
            "reward_terms": ["active_bucket_drawdown_penalty", "drawdown_penalty", "concentration_penalty"],
            "must_use_lagged_features_only": True,
            "must_freeze_before_oos": True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "available_for_manual_offline_review": ready,
            "offline_dgr_design_allowed": ready,
            "offline_smoke_allowed_after_dgr_green": ready,
            "next_shadow_model_design_allowed": False,
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
    return history_dir / f"llm_state_reward_interface_high_dividend_active_pain_redesign_review_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--event-audit", default=str(DEFAULT_EVENT_AUDIT))
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--promotion-gate", default=str(DEFAULT_PROMOTION_GATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        event_audit_path=_resolve(args.event_audit),
        validation_path=_resolve(args.validation),
        promotion_gate_path=_resolve(args.promotion_gate),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward high-dividend active-pain redesign review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "offline_dgr_design_allowed": review["decision"]["offline_dgr_design_allowed"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
