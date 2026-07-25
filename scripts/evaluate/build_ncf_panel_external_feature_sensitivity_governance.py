#!/usr/bin/env python3
"""Governance report for NCF external-feature sensitivity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIGGER_LIMITS = {"h20_prob_up": 0.15, "confidence": 0.28}
DIAGNOSTIC_LIMITS = {"ensemble_prob_up": 0.15}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _optional_json(path: str | Path) -> dict[str, Any] | None:
    resolved = _resolve(path)
    if not resolved.exists():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def _column_gate(summary: dict[str, Any], limits: dict[str, float], *, tier: str) -> dict[str, Any]:
    out = {}
    for column, limit in limits.items():
        info = summary.get(column) or {}
        value = float(info.get("max_abs_delta") or 0.0)
        out[column] = {
            "tier": tier,
            "max_abs_delta": value,
            "max_abs_delta_date": info.get("max_abs_delta_date"),
            "limit": limit,
            "exceeds_limit": value > limit,
        }
    return out


def _permissions(*, external_sensitivity_blocker_resolved: bool = False) -> dict[str, bool]:
    return {
        "sensitivity_governance_recorded": True,
        "external_sensitivity_blocker_resolved": external_sensitivity_blocker_resolved,
        "promotion_allowed": False,
        "training_allowed": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "model_training_allowed": False,
        "ppo_training_allowed": False,
        "promote_to_live": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
        "keep_golden1_0531_unchanged": True,
    }


def _observation_summary(
    *,
    observation_log: str | Path | None,
    sensitivity_available: bool,
) -> dict[str, Any]:
    required = 3
    if observation_log is None:
        completed = 1 if sensitivity_available else 0
        return {
            "required_observation_sessions": required,
            "completed_observation_sessions": completed,
            "remaining_observation_sessions": max(0, required - completed),
            "stable_observation_sessions": 0,
            "remaining_stable_observation_sessions": required,
            "latest_trigger_critical_exceeded": None,
            "observation_log_available": False,
        }

    payload = _optional_json(observation_log)
    if payload is None:
        completed = 1 if sensitivity_available else 0
        return {
            "required_observation_sessions": required,
            "completed_observation_sessions": completed,
            "remaining_observation_sessions": max(0, required - completed),
            "stable_observation_sessions": 0,
            "remaining_stable_observation_sessions": required,
            "latest_trigger_critical_exceeded": None,
            "observation_log_available": False,
        }

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    observations = [row for row in (payload.get("observations") or []) if isinstance(row, dict)]
    completed = int(
        summary.get("valid_observation_count")
        if summary.get("valid_observation_count") is not None
        else sum(1 for row in observations if row.get("valid_observation") is True)
    )
    stable = int(
        summary.get("stable_observation_count")
        if summary.get("stable_observation_count") is not None
        else sum(1 for row in observations if row.get("stable_observation") is True)
    )
    return {
        "required_observation_sessions": required,
        "completed_observation_sessions": completed,
        "remaining_observation_sessions": max(0, required - completed),
        "stable_observation_sessions": stable,
        "remaining_stable_observation_sessions": max(0, required - stable),
        "latest_trigger_critical_exceeded": summary.get("latest_trigger_critical_exceeded"),
        "observation_log_available": True,
    }


def build_report(
    *,
    sensitivity_audit: str | Path,
    same_method_baseline_manifest: str | Path,
    remediation_plan: str | Path,
    observation_log: str | Path | None = None,
    allow_missing_sensitivity_audit: bool = False,
) -> dict[str, Any]:
    sensitivity = _optional_json(sensitivity_audit) if allow_missing_sensitivity_audit else _load_json(sensitivity_audit)
    manifest = _load_json(same_method_baseline_manifest)
    remediation = _load_json(remediation_plan)
    summary = (sensitivity or {}).get("column_summary") or {}
    trigger = _column_gate(summary, TRIGGER_LIMITS, tier="trigger_critical")
    diagnostic = _column_gate(summary, DIAGNOSTIC_LIMITS, tier="diagnostic")
    trigger_exceeded = [column for column, item in trigger.items() if item["exceeds_limit"]]
    diagnostic_exceeded = [column for column, item in diagnostic.items() if item["exceeds_limit"]]
    baseline_valid = manifest.get("status") == "valid_shadow_baseline"
    prior_action_present = "quantify_external_feature_sensitivity" in remediation.get("unresolved_actions", [])
    sensitivity_missing = sensitivity is None
    observation = _observation_summary(observation_log=observation_log, sensitivity_available=not sensitivity_missing)
    resolution_allowed = (
        not sensitivity_missing
        and baseline_valid
        and prior_action_present
        and not trigger_exceeded
        and observation["stable_observation_sessions"] >= observation["required_observation_sessions"]
    )
    if sensitivity_missing:
        status = "blocked_sensitivity_audit_missing"
    else:
        status = "blocked_observation_required" if trigger_exceeded else "recorded_no_trigger_blocker"
    return {
        "report_type": "ncf_panel_external_feature_sensitivity_governance",
        "status": status,
        "inputs": {
            "sensitivity_audit": str(_resolve(sensitivity_audit)),
            "same_method_baseline_manifest": str(_resolve(same_method_baseline_manifest)),
            "remediation_plan": str(_resolve(remediation_plan)),
            "observation_log": str(_resolve(observation_log)) if observation_log is not None else None,
        },
        "checks": {
            "same_method_baseline_manifest_valid": baseline_valid,
            "remediation_action_present": prior_action_present,
            "sensitivity_audit_available": sensitivity is not None,
            "observation_log_available": observation["observation_log_available"],
            "trigger_critical": trigger,
            "diagnostic": diagnostic,
            "trigger_critical_exceeded": trigger_exceeded,
            "diagnostic_exceeded": diagnostic_exceeded,
        },
        "governance": {
            "required_observation_sessions": observation["required_observation_sessions"],
            "completed_observation_sessions": observation["completed_observation_sessions"],
            "remaining_observation_sessions": observation["remaining_observation_sessions"],
            "stable_observation_sessions": observation["stable_observation_sessions"],
            "remaining_stable_observation_sessions": observation["remaining_stable_observation_sessions"],
            "latest_trigger_critical_exceeded": observation["latest_trigger_critical_exceeded"],
            "resolution_allowed": resolution_allowed,
            "reason": "external-feature sensitivity exceeds trigger-critical limits"
            if trigger_exceeded
            else "external-feature sensitivity audit is missing"
            if sensitivity_missing
            else "external-feature sensitivity stable observation requirement is satisfied"
            if resolution_allowed
            else "external-feature sensitivity does not exceed trigger-critical limits",
            "next_action": (
                "Generate the no-external vs external sensitivity audit before reducing this blocker."
                if sensitivity_missing
                else
                f"Run {observation['remaining_stable_observation_sessions']} additional stable same-method external-sensitivity observation session(s) "
                "after source freshness is ok before reducing this blocker."
            )
            if (trigger_exceeded or sensitivity_missing)
            else "Keep this as recorded context; do not change promotion without other gates clearing.",
        },
        "permissions": _permissions(external_sensitivity_blocker_resolved=resolution_allowed),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensitivity-audit", required=True)
    parser.add_argument("--same-method-baseline-manifest", required=True)
    parser.add_argument("--remediation-plan", required=True)
    parser.add_argument("--observation-log", default=None)
    parser.add_argument("--allow-missing-sensitivity-audit", action="store_true")
    parser.add_argument("--output", default="results/ncf_panel_external_feature_sensitivity_governance_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        sensitivity_audit=args.sensitivity_audit,
        same_method_baseline_manifest=args.same_method_baseline_manifest,
        remediation_plan=args.remediation_plan,
        observation_log=args.observation_log,
        allow_missing_sensitivity_audit=args.allow_missing_sensitivity_audit,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF external feature sensitivity governance: {output}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "trigger_critical_exceeded": report["checks"]["trigger_critical_exceeded"],
                "resolution_allowed": report["governance"]["resolution_allowed"],
                "promotion_allowed": report["permissions"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
