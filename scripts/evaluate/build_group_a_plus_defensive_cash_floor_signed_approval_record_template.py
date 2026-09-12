#!/usr/bin/env python3
"""Build an unsigned approval-record template for the cash-floor candidate."""

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


DEFAULT_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_approval_record_TEMPLATE.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/defensive_cash_floor_signed_approval_record_template/history"
DEFAULT_TARGET_SIGNED_RECORD = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_approval_record.json"

REQUIRED_ACKNOWLEDGEMENTS = (
    "sparse_27_changed_day_evidence_acknowledged",
    "year_2024_no_trigger_limitation_acknowledged",
    "shadow_replay_not_live_execution_acknowledged",
    "no_00631l_add_and_no_00632r_open_acknowledged",
    "separate_execution_review_required_before_any_order_acknowledged",
    "auto_rebalance_remains_forbidden_acknowledged",
    "rollback_monitor_required_acknowledged",
)

REQUIRED_FALSE_ACTIONS = (
    "allow_auto_rebalance",
    "allow_live_strategy_change",
    "allow_00631l_add",
    "allow_00632r_open",
    "allow_broker_order_output",
    "allow_unreviewed_target_weight_output",
)


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_template(
    *,
    promotion_review_path: Path = DEFAULT_REVIEW,
    as_of: str = "2026-08-07",
    target_signed_record_path: Path = DEFAULT_TARGET_SIGNED_RECORD,
) -> dict[str, Any]:
    promotion_review = _load(promotion_review_path)
    decision = promotion_review.get("decision") if isinstance(promotion_review.get("decision"), dict) else {}
    candidate = promotion_review.get("candidate") if isinstance(promotion_review.get("candidate"), dict) else {}
    promotion_review_sha = _sha256(promotion_review_path)
    template_ready = bool(
        promotion_review
        and decision.get("signed_review_ready") is True
        and decision.get("manual_signature_valid") is False
        and decision.get("target_weight_change_allowed") is False
    )
    blockers = []
    if not promotion_review:
        blockers.append("missing_defensive_cash_floor_signed_promotion_review")
    if promotion_review and decision.get("signed_review_ready") is not True:
        blockers.append("promotion_review_not_ready_for_signature")

    approval_record = {
        "record_id": f"defensive_cash_floor_guarded_candidate_{as_of.replace('-', '')}",
        "approval_record_schema_version": 1,
        "source_promotion_review_sha256": promotion_review_sha,
        "reviewer": None,
        "reviewer_role": None,
        "approved_at": None,
        "expires_at": None,
        "approval_scope": {
            "scope": "group_a_plus_defensive_cash_floor_guarded_candidate_target_output_only",
            "variant": candidate.get("variant", "cash55_risk7_tail1"),
            "cash_floor": candidate.get("cash_floor", 0.55),
            "total_risk_min": candidate.get("total_risk_min", 7),
            "tail_risk_min": candidate.get("tail_risk_min", 1),
            "allowed_execution_regime": "group_a_plus_defensive",
            "excluded_actions": ["00631L_add", "00632R_open", "auto_rebalance", "broker_order_output"],
        },
        "approved_actions": {
            "allow_guarded_candidate_target_output": False,
            **{key: False for key in REQUIRED_FALSE_ACTIONS},
        },
        "acknowledgements": {key: False for key in REQUIRED_ACKNOWLEDGEMENTS},
        "constraint_overrides": {},
        "notes": None,
    }
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_defensive_cash_floor_signed_approval_record_template",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "unsigned_template_ready_for_manual_completion" if template_ready else "blocked",
        "policy": "unsigned_template_only_no_approval_no_live_action",
        "sources": {
            "signed_promotion_review": {
                "path": str(promotion_review_path),
                "exists": promotion_review_path.exists(),
                "sha256": promotion_review_sha,
            }
        },
        "signed_approval_record_template": approval_record,
        "manual_completion_required": [
            "reviewer",
            "reviewer_role",
            "approved_at",
            "expires_at",
            "approved_actions.allow_guarded_candidate_target_output",
            *[f"acknowledgements.{key}" for key in REQUIRED_ACKNOWLEDGEMENTS],
        ],
        "validation_rules": {
            "required_template_fields": list(approval_record.keys()),
            "required_acknowledgements": list(REQUIRED_ACKNOWLEDGEMENTS),
            "required_false_permissions": list(REQUIRED_FALSE_ACTIONS),
            "constraint_overrides_must_be_empty": True,
        },
        "validation_target_path": str(target_signed_record_path),
        "summary": {
            "signed_approval_record_template_ready": template_ready,
            "signed_approval_record_valid": False,
            "manual_signature_valid": False,
            "guarded_candidate_target_output_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
        "blocking_reasons": blockers,
        "decision": {
            "signed_approval_record_template_ready": template_ready,
            "signed_approval_record_valid": False,
            "manual_signature_valid": False,
            "guarded_candidate_target_output_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"defensive_cash_floor_signed_approval_record_template_{stamp}.json"


def write_template(report: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, report.get("as_of")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promotion-review", default=str(DEFAULT_REVIEW))
    parser.add_argument("--as-of", default="2026-08-07")
    parser.add_argument("--target-signed-record", default=str(DEFAULT_TARGET_SIGNED_RECORD))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_template(
        promotion_review_path=Path(args.promotion_review),
        as_of=args.as_of,
        target_signed_record_path=Path(args.target_signed_record),
    )
    write_template(report, Path(args.output), None if args.no_history else Path(args.history_dir))
    print(
        "status={status} template_ready={ready} output={output}".format(
            status=report["status"],
            ready=report["decision"]["signed_approval_record_template_ready"],
            output=args.output,
        )
    )


if __name__ == "__main__":
    main()
