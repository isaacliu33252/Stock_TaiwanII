#!/usr/bin/env python3
"""Validate a signed approval record for the cash-floor guarded candidate."""

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


DEFAULT_TEMPLATE = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_approval_record_TEMPLATE.json"
DEFAULT_SIGNED_RECORD = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_approval_record.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/defensive_cash_floor_signed_approval_validation/history"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "sha256": _sha256(path)}


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _comparable_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def build_validation(
    *,
    template_path: Path = DEFAULT_TEMPLATE,
    signed_record_path: Path = DEFAULT_SIGNED_RECORD,
    as_of: str = "2026-08-07",
) -> dict[str, Any]:
    template_report = _load(template_path)
    signed_record = _load(signed_record_path)
    template = _dict(template_report, "signed_approval_record_template")
    rules = _dict(template_report, "validation_rules")
    blockers: list[str] = []
    warnings: list[str] = []

    if not template_report:
        blockers.append("missing_signed_approval_record_template")
    elif (template_report.get("decision") or {}).get("signed_approval_record_template_ready") is not True:
        blockers.append("signed_approval_record_template_not_ready")
    if not signed_record:
        blockers.append("missing_signed_approval_record")

    approved_actions = _dict(signed_record, "approved_actions")
    acknowledgements = _dict(signed_record, "acknowledgements")
    approval_scope = _dict(signed_record, "approval_scope")
    template_scope = _dict(template, "approval_scope")

    if signed_record:
        for field in rules.get("required_template_fields") or []:
            if field not in signed_record:
                blockers.append(f"signed_record_missing_required_field:{field}")
        for field in ("record_id", "approval_record_schema_version", "source_promotion_review_sha256"):
            if signed_record.get(field) != template.get(field):
                blockers.append(f"signed_record_{field}_mismatch")
        if not _nonempty(signed_record.get("reviewer")):
            blockers.append("signed_record_missing_reviewer")
        if not _nonempty(signed_record.get("reviewer_role")):
            blockers.append("signed_record_missing_reviewer_role")

    approved_at = _parse_iso(signed_record.get("approved_at")) if signed_record else None
    expires_at = _parse_iso(signed_record.get("expires_at")) if signed_record else None
    as_of_dt = _parse_iso(as_of) or _parse_iso(f"{as_of}T00:00:00")
    if signed_record and approved_at is None:
        blockers.append("signed_record_invalid_or_missing_approved_at")
    if signed_record and expires_at is None:
        blockers.append("signed_record_invalid_or_missing_expires_at")
    approved_at_cmp = _comparable_datetime(approved_at)
    expires_at_cmp = _comparable_datetime(expires_at)
    as_of_cmp = _comparable_datetime(as_of_dt)
    if approved_at_cmp is not None and expires_at_cmp is not None and expires_at_cmp <= approved_at_cmp:
        blockers.append("signed_record_expires_at_not_after_approved_at")
    if expires_at_cmp is not None and as_of_cmp is not None and expires_at_cmp <= as_of_cmp:
        blockers.append("signed_record_expired_as_of_validation_date")

    if signed_record:
        for key, expected in template_scope.items():
            if approval_scope.get(key) != expected:
                blockers.append(f"signed_record_approval_scope_mismatch:{key}")
        if approved_actions.get("allow_guarded_candidate_target_output") is not True:
            blockers.append("signed_record_guarded_candidate_target_output_not_approved")
        for key in rules.get("required_false_permissions") or []:
            if approved_actions.get(key) is not False:
                blockers.append(f"signed_record_forbidden_action_not_false:{key}")
        for key in rules.get("required_acknowledgements") or []:
            if acknowledgements.get(key) is not True:
                blockers.append(f"signed_record_missing_acknowledgement:{key}")
        if rules.get("constraint_overrides_must_be_empty") is True and signed_record.get("constraint_overrides") != {}:
            blockers.append("signed_record_constraint_overrides_not_empty")
        if signed_record.get("notes") in (None, ""):
            warnings.append("signed_record_notes_empty")

    valid = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_defensive_cash_floor_signed_approval_validation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "valid_for_guarded_candidate_target_output" if valid else "blocked",
        "policy": "signed_approval_validation_only_no_broker_action_no_auto_rebalance",
        "sources": {
            "signed_approval_record_template": _source(template_path),
            "signed_approval_record": _source(signed_record_path),
        },
        "validation": {
            "signed_record_sha256": _sha256(signed_record_path),
            "template_sha256": _sha256(template_path),
            "record_id": signed_record.get("record_id"),
            "reviewer": signed_record.get("reviewer"),
            "reviewer_role": signed_record.get("reviewer_role"),
            "approved_at": signed_record.get("approved_at"),
            "expires_at": signed_record.get("expires_at"),
            "approval_scope": approval_scope,
        },
        "summary": {
            "signed_approval_record_valid": valid,
            "manual_signature_valid": valid,
            "guarded_candidate_target_output_allowed": valid,
            "signed_record_exists": bool(signed_record),
            "template_ready": (template_report.get("decision") or {}).get("signed_approval_record_template_ready"),
            "reviewer": signed_record.get("reviewer"),
            "expires_at": signed_record.get("expires_at"),
            "target_weight_change_allowed": valid,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "signed_approval_record_valid": valid,
            "manual_signature_valid": valid,
            "guarded_candidate_target_output_allowed": valid,
            "target_weight_change_allowed": valid,
            "auto_rebalance_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_broker_order_output": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"defensive_cash_floor_signed_approval_validation_{stamp}.json"


def write_validation(report: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
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
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--signed-record", default=str(DEFAULT_SIGNED_RECORD))
    parser.add_argument("--as-of", default="2026-08-07")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_validation(
        template_path=Path(args.template),
        signed_record_path=Path(args.signed_record),
        as_of=args.as_of,
    )
    write_validation(report, Path(args.output), None if args.no_history else Path(args.history_dir))
    print(
        "status={status} manual_signature_valid={valid} target_allowed={target} blockers={blockers}".format(
            status=report["status"],
            valid=report["decision"]["manual_signature_valid"],
            target=report["decision"]["target_weight_change_allowed"],
            blockers=report["blocking_reasons"],
        )
    )


if __name__ == "__main__":
    main()
