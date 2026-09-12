#!/usr/bin/env python3
"""Build a manual review packet for the 2609.04917 turnover bridge.

This is an unsigned review packet only. It intentionally does not create a
signed approval record and cannot be used as an execution authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BRIDGE = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap465.json"
DEFAULT_REBALANCE = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_rebalance_review_cap465.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_market_impact_turnover_bridge_shadow_cap465.json"
DEFAULT_JOINT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness_turnover_bridge_shadow_cap465.json"
DEFAULT_ALPHA = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_alpha_translation_readiness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_manual_review_packet_cap465.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_manual_review_packet_cap465.md"


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


def _list_value(payload: dict[str, Any], key: str) -> list[str]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def build_packet(
    *,
    bridge_path: Path,
    rebalance_path: Path,
    market_impact_path: Path,
    joint_path: Path,
    alpha_path: Path,
) -> dict[str, Any]:
    bridge = _load(bridge_path)
    rebalance = _load(rebalance_path)
    market_impact = _load(market_impact_path)
    joint = _load(joint_path)
    alpha = _load(alpha_path)

    blocking_reasons: list[str] = []
    blocking_reasons.extend(f"joint:{item}" for item in _list_value(joint, "blocking_reasons"))
    blocking_reasons.extend(f"market_impact:{item}" for item in _list_value(market_impact, "blocking_reasons"))
    blocking_reasons.extend(f"alpha:{item}" for item in alpha.get("blocked_dimensions", []) if isinstance(alpha.get("blocked_dimensions"), list))

    readiness_checks = {
        "bridge_available": bridge.get("status") == "shadow_bridge_available_for_manual_review",
        "rebalance_ready_for_human_review": rebalance.get("status") == "ready_for_human_rebalance_review",
        "bridge_adds_00631l": (rebalance.get("checks") or {}).get("bridge_adds_00631l"),
        "bridge_turnover": (bridge.get("computed") or {}).get("bridge_turnover"),
        "market_impact_status": market_impact.get("status"),
        "joint_execution_status": joint.get("status"),
        "alpha_translation_status": alpha.get("status"),
    }
    packet_ready = bool(
        readiness_checks["bridge_available"]
        and readiness_checks["rebalance_ready_for_human_review"]
        and readiness_checks["bridge_adds_00631l"] is False
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_manual_review_packet",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "unsigned_manual_review_packet_no_approval_no_order_no_weight_change",
        "status": "ready_for_manual_review_packet" if packet_ready else "blocked",
        "candidate": {
            "name": "turnover_bridge_cap465",
            "source": "2609.04917 alpha-translation governance",
            "actual_data_date": bridge.get("actual_data_date"),
            "max_turnover_cap": (bridge.get("limits") or {}).get("max_turnover"),
        },
        "readiness_checks": readiness_checks,
        "trade_preview": bridge.get("bridge_trades") or [],
        "skipped_trade_plan": bridge.get("skipped_trade_plan") or [],
        "unresolved_live_blockers": sorted(set(blocking_reasons)),
        "required_human_acknowledgements": [
            "This packet is not a signed approval record.",
            "The bridge remains shadow-only unless a separate signed approval explicitly authorizes an action.",
            "Auto rebalance remains disabled.",
            "No 00631L add is included in the reviewed bridge.",
            "Joint execution and alpha-translation live promotion gates remain blocked.",
        ],
        "decision": {
            "approval_granted": False,
            "live_execution_allowed": False,
            "auto_rebalance_allowed": False,
            "target_weight_change_allowed": False,
            "manual_review_packet_ready": packet_ready,
        },
        "inputs": {
            "bridge": {"path": str(bridge_path), "sha256": _sha256(bridge_path)},
            "rebalance": {"path": str(rebalance_path), "sha256": _sha256(rebalance_path)},
            "market_impact": {"path": str(market_impact_path), "sha256": _sha256(market_impact_path)},
            "joint": {"path": str(joint_path), "sha256": _sha256(joint_path)},
            "alpha_translation": {"path": str(alpha_path), "sha256": _sha256(alpha_path)},
        },
    }


def _markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Manual Review Packet Cap465",
        "",
        f"- status: {packet['status']}",
        f"- approval_granted: {packet['decision']['approval_granted']}",
        f"- live_execution_allowed: {packet['decision']['live_execution_allowed']}",
        f"- actual_data_date: {packet['candidate']['actual_data_date']}",
        f"- max_turnover_cap: {packet['candidate']['max_turnover_cap']}",
        f"- bridge_turnover: {packet['readiness_checks']['bridge_turnover']}",
        "",
        "## Trade Preview",
        "",
        "| ticker | side | current | target | delta | notional |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in packet.get("trade_preview") or []:
        lines.append(
            f"| {row.get('ticker')} | {row.get('side')} | {row.get('current_shares')} | "
            f"{row.get('target_shares')} | {row.get('delta_shares')} | {float(row.get('notional') or 0.0):.2f} |"
        )
    lines.extend(["", "## Unresolved Live Blockers", ""])
    for item in packet.get("unresolved_live_blockers") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Required Acknowledgements", ""])
    for item in packet.get("required_human_acknowledgements") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default=str(DEFAULT_BRIDGE))
    parser.add_argument("--rebalance", default=str(DEFAULT_REBALANCE))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--joint", default=str(DEFAULT_JOINT))
    parser.add_argument("--alpha", default=str(DEFAULT_ALPHA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    packet = build_packet(
        bridge_path=_resolve(args.bridge),
        rebalance_path=_resolve(args.rebalance),
        market_impact_path=_resolve(args.market_impact),
        joint_path=_resolve(args.joint),
        alpha_path=_resolve(args.alpha),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(packet), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": packet["status"], "approval_granted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
