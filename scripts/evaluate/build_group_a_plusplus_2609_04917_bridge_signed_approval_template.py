#!/usr/bin/env python3
"""Build an unsigned approval template for the 2609.04917 bridge packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_manual_review_packet_cap465.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_signed_approval_TEMPLATE.json"
DEFAULT_SIGNED_RECORD = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_signed_approval.json"

REQUIRED_ACKS = (
    "manual_review_packet_read",
    "shadow_only_until_signed_record_valid",
    "no_00631l_add_acknowledged",
    "auto_rebalance_disabled_acknowledged",
    "live_promotion_blockers_acknowledged",
    "separate_broker_order_preparation_required",
)

FORBIDDEN_ACTIONS = (
    "allow_live_promotion",
    "allow_auto_rebalance",
    "allow_00631l_add",
    "allow_00713_buy",
    "allow_unreviewed_target_weight_change",
)


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


def build_template(*, packet_path: Path, target_signed_record_path: Path, as_of: str) -> dict[str, Any]:
    packet = _load(packet_path)
    packet_ready = (packet.get("decision") or {}).get("manual_review_packet_ready") is True
    template_ready = bool(packet_ready and (packet.get("decision") or {}).get("approval_granted") is False)
    blockers: list[str] = []
    if not packet:
        blockers.append("missing_manual_review_packet")
    elif not packet_ready:
        blockers.append("manual_review_packet_not_ready")

    record = {
        "record_id": f"2609_04917_turnover_bridge_cap465_{as_of.replace('-', '')}",
        "approval_record_schema_version": 1,
        "source_manual_review_packet_sha256": _sha256(packet_path),
        "reviewer": None,
        "reviewer_role": None,
        "approved_at": None,
        "expires_at": None,
        "approval_scope": {
            "scope": "group_a_plusplus_2609_04917_turnover_bridge_cap465_manual_action_only",
            "candidate": "turnover_bridge_cap465",
            "actual_data_date": (packet.get("candidate") or {}).get("actual_data_date"),
            "max_turnover_cap": (packet.get("candidate") or {}).get("max_turnover_cap"),
            "allowed_trade_preview": packet.get("trade_preview") or [],
            "excluded_tickers_for_add": ["00631L.TW", "00713.TW"],
        },
        "approved_actions": {},
        "acknowledgements": {key: False for key in REQUIRED_ACKS},
        "constraint_overrides": {},
        "notes": None,
    }
    record["approved_actions"] = {
        "allow_manual_execution_review_for_trade_preview": False,
        **{key: False for key in FORBIDDEN_ACTIONS},
    }
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_bridge_signed_approval_template",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "unsigned_template_ready_for_manual_completion" if template_ready else "blocked",
        "policy": "unsigned_template_only_no_approval_no_order_no_weight_change",
        "signed_approval_record_template": record,
        "manual_completion_required": [
            "reviewer",
            "reviewer_role",
            "approved_at",
            "expires_at",
            "approved_actions.allow_manual_execution_review_for_trade_preview",
            *[f"acknowledgements.{key}" for key in REQUIRED_ACKS],
        ],
        "validation_rules": {
            "required_template_fields": list(record.keys()),
            "required_acknowledgements": list(REQUIRED_ACKS),
            "required_false_permissions": list(FORBIDDEN_ACTIONS),
            "constraint_overrides_must_be_empty": True,
        },
        "validation_target_path": str(target_signed_record_path),
        "blocking_reasons": blockers,
        "decision": {
            "signed_approval_record_template_ready": template_ready,
            "signed_approval_record_valid": False,
            "manual_execution_review_allowed": False,
            "live_promotion_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00713_buy": False,
        },
        "inputs": {
            "manual_review_packet": {"path": str(packet_path), "sha256": _sha256(packet_path)},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--target-signed-record", default=str(DEFAULT_SIGNED_RECORD))
    parser.add_argument("--as-of", default="2026-09-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = build_template(
        packet_path=_resolve(args.packet),
        target_signed_record_path=_resolve(args.target_signed_record),
        as_of=args.as_of,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"], "template_ready": report["decision"]["signed_approval_record_template_ready"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
