#!/usr/bin/env python3
"""Build a controlled-adaptation protocol report for Group A++.

arXiv 2609.04917 recommends predeclared triggers, shadow comparison, approval,
rollback, and immutable active-version records before adapting a trading
system. This report checks those pieces from existing governance artifacts and
does not change live strategy state.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALPHA_GATE = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_alpha_translation_readiness.json"
DEFAULT_SELECTION_LEDGER = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_selection_ledger.json"
DEFAULT_INFORMATION_BOM = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_information_bom.json"
DEFAULT_JOINT_EXECUTION = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness.json"
DEFAULT_SHADOW_REGISTRY = PROJECT_ROOT / "report/group_a_plus/latest/shadow_artifact_registry.json"
DEFAULT_ROLLBACK_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_controlled_adaptation_rollback_plan.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_controlled_adaptation.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_controlled_adaptation.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2609_04917_controlled_adaptation/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _registry_count(registry: dict[str, Any]) -> int | None:
    for key in ("artifacts", "entries", "items", "rows"):
        value = registry.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def build_report(
    *,
    alpha_gate_path: Path,
    selection_ledger_path: Path,
    information_bom_path: Path,
    joint_execution_path: Path,
    shadow_registry_path: Path,
    rollback_plan_path: Path | None = None,
    approval_record_path: Path | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    alpha = _load_optional(alpha_gate_path)
    selection = _load_optional(selection_ledger_path)
    bom = _load_optional(information_bom_path)
    joint = _load_optional(joint_execution_path)
    registry = _load_optional(shadow_registry_path)
    rollback_available = bool(rollback_plan_path and rollback_plan_path.exists())
    approval_available = bool(approval_record_path and approval_record_path.exists())
    checks = {
        "predeclared_trigger_available": bool(selection.get("frozen_confirmatory_specification_available")),
        "shadow_comparison_available": bool(_registry_count(registry)),
        "information_bom_available": bool(bom) and bom.get("status") in {"available", "warning"},
        "alpha_translation_gate_clear": bool(alpha) and not alpha.get("blocked_dimensions"),
        "joint_execution_gate_clear": bool(joint) and joint.get("status") == "available_for_manual_review",
        "human_approval_record_available": approval_available,
        "rollback_plan_available": rollback_available,
        "immutable_active_version_record_available": bool(alpha.get("generated_at") and selection.get("generated_at")),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    status = "blocked" if blockers else "ready_for_limited_human_adaptation_review"
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_controlled_adaptation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "shadow_only_controlled_adaptation_protocol_no_weight_change",
        "live_execution_effect": "none",
        "source_paper": {"arxiv": "2609.04917", "concept": "controlled_adaptation_and_authority_matched_governance"},
        "status": status,
        "checks": checks,
        "blocking_reasons": blockers,
        "inputs": {
            "alpha_gate_status": alpha.get("status"),
            "selection_ledger_status": selection.get("status"),
            "information_bom_status": bom.get("status"),
            "joint_execution_status": joint.get("status"),
            "shadow_registry_count": _registry_count(registry),
            "rollback_plan": str(rollback_plan_path) if rollback_plan_path else None,
            "approval_record": str(approval_record_path) if approval_record_path else None,
        },
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "creates_orders": False,
            "latest_strategy_change_allowed": False,
            "controlled_adaptation_protocol_required": True,
        },
        "required_protocol_before_any_live_change": [
            "frozen trigger and candidate specification",
            "forward shadow comparison against current latest strategy",
            "information BOM attached to the candidate",
            "joint signal-portfolio-execution gate clear",
            "human approval record with explicit allowed action",
            "rollback plan that does not rely on the failing model",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Controlled Adaptation",
        "",
        f"- status: {report['status']}",
        f"- blocking_reasons: {', '.join(report['blocking_reasons']) or 'none'}",
        "",
        "| check | passed |",
        "| --- | --- |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in report["checks"].items())
    lines.extend(["", "## Required Protocol", ""])
    lines.extend(f"- {item}" for item in report["required_protocol_before_any_live_change"])
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = as_of or datetime.now().strftime("%Y%m%d")
    return history_dir / f"2609_04917_controlled_adaptation_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha-gate", default=str(DEFAULT_ALPHA_GATE))
    parser.add_argument("--selection-ledger", default=str(DEFAULT_SELECTION_LEDGER))
    parser.add_argument("--information-bom", default=str(DEFAULT_INFORMATION_BOM))
    parser.add_argument("--joint-execution", default=str(DEFAULT_JOINT_EXECUTION))
    parser.add_argument("--shadow-registry", default=str(DEFAULT_SHADOW_REGISTRY))
    parser.add_argument("--rollback-plan", default=str(DEFAULT_ROLLBACK_PLAN))
    parser.add_argument("--approval-record", default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()
    report = build_report(
        alpha_gate_path=_resolve(args.alpha_gate),
        selection_ledger_path=_resolve(args.selection_ledger),
        information_bom_path=_resolve(args.information_bom),
        joint_execution_path=_resolve(args.joint_execution),
        shadow_registry_path=_resolve(args.shadow_registry),
        rollback_plan_path=_resolve(args.rollback_plan) if args.rollback_plan else None,
        approval_record_path=_resolve(args.approval_record) if args.approval_record else None,
        as_of=args.as_of,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    history = _history_path(_resolve(args.history_dir), args.as_of)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    history.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
