#!/usr/bin/env python3
"""Summarize GroupA+ panel-drift remediation progress."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REMEDIATION_PLAN = PROJECT_ROOT / "results/ncf_panel_drift_remediation_plan_20260722.json"
DEFAULT_EXTERNAL_SENSITIVITY_GOVERNANCE = (
    PROJECT_ROOT / "results/ncf_panel_external_feature_sensitivity_governance_20260722.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/panel_drift_resolution_progress.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/panel_drift_resolution_progress.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/panel_drift_resolution_progress/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _permissions() -> dict[str, bool]:
    return {
        "creates_orders": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "training_allowed": False,
        "model_training_allowed": False,
        "ppo_training_allowed": False,
        "promote_to_live": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
        "keep_golden1_0531_unchanged": True,
    }


def _actions(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for action in plan.get("actions", []) or []:
        if not isinstance(action, dict):
            continue
        compact = {
            "id": action.get("id"),
            "priority": action.get("priority"),
            "status": action.get("status"),
            "reason": action.get("reason"),
            "recommended_action": action.get("recommended_action"),
        }
        if action.get("status") == "resolved":
            resolved.append(compact)
        else:
            unresolved.append(compact)
    return resolved, unresolved


def build_progress(
    *,
    remediation_plan_path: Path = DEFAULT_REMEDIATION_PLAN,
    external_sensitivity_governance_path: Path = DEFAULT_EXTERNAL_SENSITIVITY_GOVERNANCE,
) -> dict[str, Any]:
    plan = _load(remediation_plan_path)
    sensitivity = _load(external_sensitivity_governance_path)
    resolved_actions, unresolved_actions = _actions(plan)
    governance = sensitivity.get("governance") if isinstance(sensitivity.get("governance"), dict) else {}
    required_sessions = int(governance.get("required_observation_sessions") or 0)
    completed_sessions = int(governance.get("completed_observation_sessions") or 0)
    remaining_sessions = max(0, required_sessions - completed_sessions)
    stable_sessions = int(governance.get("stable_observation_sessions") or 0)
    remaining_stable_sessions = int(
        governance.get("remaining_stable_observation_sessions")
        if governance.get("remaining_stable_observation_sessions") is not None
        else max(0, required_sessions - stable_sessions)
    )
    resolution_allowed = governance.get("resolution_allowed") is True
    status = "ready_for_gate_recheck" if not unresolved_actions and resolution_allowed else "blocked"
    next_actions = [item.get("recommended_action") for item in unresolved_actions if item.get("recommended_action")]
    if remaining_stable_sessions:
        next_actions.append(
            f"complete {remaining_stable_sessions} additional stable same-method external-sensitivity observation session(s)"
        )
    if not next_actions:
        next_actions.append("rerun promotion gate after all panel-drift remediation checks remain resolved")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_panel_drift_resolution_progress",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "policy": "diagnostic_only_no_strategy_change_no_weight_change",
        "active_allocation_impact": "none",
        "remediation_status": plan.get("status"),
        "unresolved_action_ids": plan.get("unresolved_actions") or [],
        "resolved_actions": resolved_actions,
        "unresolved_actions": unresolved_actions,
        "external_sensitivity": {
            "status": sensitivity.get("status"),
            "required_observation_sessions": required_sessions,
            "completed_observation_sessions": completed_sessions,
            "remaining_observation_sessions": remaining_sessions,
            "stable_observation_sessions": stable_sessions,
            "remaining_stable_observation_sessions": remaining_stable_sessions,
            "resolution_allowed": resolution_allowed,
            "reason": governance.get("reason"),
            "next_action": governance.get("next_action"),
            "trigger_critical_exceeded": ((sensitivity.get("checks") or {}).get("trigger_critical_exceeded") or []),
            "diagnostic_exceeded": ((sensitivity.get("checks") or {}).get("diagnostic_exceeded") or []),
        },
        "summary": {
            "resolved_count": len(resolved_actions),
            "unresolved_count": len(unresolved_actions),
            "remaining_observation_sessions": remaining_sessions,
            "remaining_stable_observation_sessions": remaining_stable_sessions,
            "next_actions": next_actions,
        },
        "decision": _permissions(),
        "inputs": {
            "remediation_plan": str(remediation_plan_path),
            "external_sensitivity_governance": str(external_sensitivity_governance_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Panel Drift Resolution Progress",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Remediation status: `{report.get('remediation_status')}`",
        f"- Unresolved actions: `{report.get('unresolved_action_ids')}`",
        f"- Remaining observation sessions: `{report['summary'].get('remaining_observation_sessions')}`",
        "",
        "## Next Actions",
        "",
    ]
    for action in report["summary"].get("next_actions") or []:
        lines.append(f"- {action}")
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            f"- Creates orders: `{report['decision']['creates_orders']}`",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Auto rebalance allowed: `{report['decision']['auto_rebalance_allowed']}`",
            f"- Golden1_0531 unchanged: `{report['decision']['keep_golden1_0531_unchanged']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path) -> Path:
    return history_dir / f"panel_drift_resolution_progress_{datetime.now().strftime('%Y%m%d')}.json"


def write_outputs(
    report: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remediation-plan", default=str(DEFAULT_REMEDIATION_PLAN))
    parser.add_argument("--external-sensitivity-governance", default=str(DEFAULT_EXTERNAL_SENSITIVITY_GOVERNANCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_progress(
        remediation_plan_path=_resolve(args.remediation_plan),
        external_sensitivity_governance_path=_resolve(args.external_sensitivity_governance),
    )
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Panel drift resolution progress: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "unresolved_action_ids": report["unresolved_action_ids"],
                "remaining_observation_sessions": report["summary"]["remaining_observation_sessions"],
                "keep_golden1_0531_unchanged": report["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
