#!/usr/bin/env python3
"""Validate a signed 2609.04917 bridge approval record."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_signed_approval_TEMPLATE.json"
DEFAULT_SIGNED_RECORD = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_signed_approval.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_signed_approval_validation.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def build_validation(*, template_path: Path, signed_record_path: Path, as_of: str) -> dict[str, Any]:
    template_report = _load(template_path)
    signed = _load(signed_record_path)
    template = _dict(template_report, "signed_approval_record_template")
    rules = _dict(template_report, "validation_rules")
    blockers: list[str] = []
    warnings: list[str] = []

    if not template_report:
        blockers.append("missing_bridge_signed_approval_template")
    elif (template_report.get("decision") or {}).get("signed_approval_record_template_ready") is not True:
        blockers.append("bridge_signed_approval_template_not_ready")
    if not signed:
        blockers.append("missing_bridge_signed_approval_record")

    if signed:
        for field in rules.get("required_template_fields") or []:
            if field not in signed:
                blockers.append(f"signed_record_missing_required_field:{field}")
        for field in ("record_id", "approval_record_schema_version", "source_manual_review_packet_sha256"):
            if signed.get(field) != template.get(field):
                blockers.append(f"signed_record_{field}_mismatch")
        if not _nonempty(signed.get("reviewer")):
            blockers.append("signed_record_missing_reviewer")
        if not _nonempty(signed.get("reviewer_role")):
            blockers.append("signed_record_missing_reviewer_role")

        approved_at = _parse_iso(signed.get("approved_at"))
        expires_at = _parse_iso(signed.get("expires_at"))
        as_of_dt = _parse_iso(as_of) or _parse_iso(f"{as_of}T00:00:00")
        if approved_at is None:
            blockers.append("signed_record_invalid_or_missing_approved_at")
        if expires_at is None:
            blockers.append("signed_record_invalid_or_missing_expires_at")
        if approved_at is not None and expires_at is not None and expires_at <= approved_at:
            blockers.append("signed_record_expires_at_not_after_approved_at")
        if expires_at is not None and as_of_dt is not None and expires_at <= as_of_dt:
            blockers.append("signed_record_expired_as_of_validation_date")

        if _dict(signed, "approval_scope") != _dict(template, "approval_scope"):
            blockers.append("signed_record_approval_scope_mismatch")
        actions = _dict(signed, "approved_actions")
        if actions.get("allow_manual_execution_review_for_trade_preview") is not True:
            blockers.append("signed_record_manual_execution_review_not_approved")
        for key in rules.get("required_false_permissions") or []:
            if actions.get(key) is not False:
                blockers.append(f"signed_record_forbidden_action_not_false:{key}")
        acknowledgements = _dict(signed, "acknowledgements")
        for key in rules.get("required_acknowledgements") or []:
            if acknowledgements.get(key) is not True:
                blockers.append(f"signed_record_missing_acknowledgement:{key}")
        if rules.get("constraint_overrides_must_be_empty") is True and signed.get("constraint_overrides") != {}:
            blockers.append("signed_record_constraint_overrides_not_empty")
        if signed.get("notes") in (None, ""):
            warnings.append("signed_record_notes_empty")

    valid = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_bridge_signed_approval_validation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "valid_for_manual_execution_review_only" if valid else "blocked",
        "policy": "signed_approval_validation_only_no_order_no_auto_rebalance_no_live_promotion",
        "sources": {
            "template": {"path": str(template_path), "sha256": _sha256(template_path), "exists": template_path.exists()},
            "signed_record": {
                "path": str(signed_record_path),
                "sha256": _sha256(signed_record_path),
                "exists": signed_record_path.exists(),
            },
        },
        "summary": {
            "signed_approval_record_valid": valid,
            "manual_execution_review_allowed": valid,
            "live_promotion_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00713_buy": False,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "signed_approval_record_valid": valid,
            "manual_execution_review_allowed": valid,
            "live_execution_allowed": False,
            "live_promotion_allowed": False,
            "auto_rebalance_allowed": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "allow_00713_buy": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--signed-record", default=str(DEFAULT_SIGNED_RECORD))
    parser.add_argument("--as-of", default="2026-09-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = build_validation(
        template_path=_resolve(args.template),
        signed_record_path=_resolve(args.signed_record),
        as_of=args.as_of,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": report["status"],
                "signed_approval_record_valid": report["decision"]["signed_approval_record_valid"],
                "blocking_reasons": report["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
