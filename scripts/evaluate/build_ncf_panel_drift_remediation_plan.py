#!/usr/bin/env python3
"""Build a remediation plan from an NCF panel drift diagnosis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = _resolve(path)
    if not resolved.exists():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def _permission_summary() -> dict[str, bool]:
    return {
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


def _model_set_actions(source: dict[str, Any], isolation_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    model_sets = source.get("model_sets") if isinstance(source.get("model_sets"), dict) else {}
    if model_sets.get("status") != "changed":
        return []
    isolated = bool(
        isolation_report
        and (isolation_report.get("conclusion") or {}).get("model_set_or_baseline_method_mismatch_explains_primary_blocker")
        is True
    )
    removed = sorted(
        {
            model
            for info in (model_sets.get("by_horizon") or {}).values()
            for model in info.get("removed_models", [])
        }
    )
    added = sorted(
        {
            model
            for info in (model_sets.get("by_horizon") or {}).values()
            for model in info.get("added_models", [])
        }
    )
    return [
        {
            "id": "isolate_model_set_change",
            "priority": 2,
            "status": "resolved" if isolated else "required",
            "reason": "baseline and candidate NCF panels were generated with different model sets",
            "removed_models": removed,
            "added_models": added,
            "isolation_report_status": isolation_report.get("status") if isolation_report else None,
            "recommended_action": (
                "Model-set mismatch is isolated by the same-method no-TabNet comparison; keep promotion blocked while rebuilding the official same-method baseline and clearing deployment/GIFT gates."
                if isolated
                else
                "Run a same-method shadow comparison before changing any gate: "
                "either regenerate a no-TabNet baseline or run a TabNet-enabled candidate "
                "to isolate model-set drift."
            ),
        }
    ]


def _freshness_actions(source: dict[str, Any]) -> list[dict[str, Any]]:
    run_context = source.get("run_context") if isinstance(source.get("run_context"), dict) else {}
    stale_sources = list(run_context.get("candidate_stale_sources") or [])
    if not stale_sources:
        return []
    return [
        {
            "id": "refresh_stale_candidate_sources",
            "priority": 1,
            "status": "required",
            "reason": "candidate NCF run used degraded or stale sources",
            "stale_sources": stale_sources,
            "recommended_action": "Refresh stale candidate sources, then rebuild NCF panel, drift audit, diagnosis, and promotion gate.",
        }
    ]


def _panel_method_actions(source: dict[str, Any], baseline_manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    methods = source.get("panel_methods") if isinstance(source.get("panel_methods"), dict) else {}
    if methods.get("baseline_has_horizon_ensemble_method") == methods.get("candidate_has_horizon_ensemble_method"):
        return []
    resolved = bool(
        baseline_manifest
        and baseline_manifest.get("status") == "valid_shadow_baseline"
        and (baseline_manifest.get("permissions") or {}).get("use_for_shadow_drift_comparison") is True
    )
    return [
        {
            "id": "rebuild_same_method_baseline",
            "priority": 3,
            "status": "resolved" if resolved else "required",
            "reason": "baseline lacks the candidate panel's explicit horizon ensemble method/weight metadata",
            "candidate_horizon_ensemble_methods": methods.get("candidate_horizon_ensemble_methods", {}),
            "recommended_action": (
                "Same-method shadow baseline manifest is valid; keep it shadow-only and do not use it as a promotion baseline until remaining sensitivity/deployment/GIFT gates clear."
                if resolved
                else
                "Create a same-method baseline panel with expanding_prior_auc_min60 metadata, "
                "then compare candidate against that baseline before considering any gate change."
            ),
        }
    ]


def _sensitivity_actions(source: dict[str, Any], sensitivity_governance: dict[str, Any] | None) -> list[dict[str, Any]]:
    sensitivity = source.get("sensitivity_audit") if isinstance(source.get("sensitivity_audit"), dict) else {}
    governance_blocks = bool(
        sensitivity_governance
        and sensitivity_governance.get("status")
        in {"blocked_observation_required", "blocked_sensitivity_audit_missing"}
    )
    if sensitivity.get("status") != "available" and not governance_blocks:
        return []
    summary = sensitivity.get("column_summary") or {}
    max_trigger = max(
        [
            float((summary.get(column) or {}).get("max_abs_delta") or 0.0)
            for column in ("h20_prob_up", "confidence")
        ],
        default=0.0,
    )
    if max_trigger <= 0.28 and not governance_blocks:
        return []
    return [
        {
            "id": "quantify_external_feature_sensitivity",
            "priority": 4,
            "status": "required",
            "reason": "external-feature sensitivity exceeds trigger-critical drift tolerance"
            if max_trigger > 0.28
            else "external-feature sensitivity governance is blocked or missing",
            "max_trigger_critical_sensitivity": max_trigger,
            "governance_status": sensitivity_governance.get("status") if sensitivity_governance else None,
            "governance_resolution_allowed": (sensitivity_governance.get("governance") or {}).get("resolution_allowed")
            if sensitivity_governance
            else None,
            "recommended_action": (
                "Keep promotion blocked until external feature freshness and sensitivity are stable across a same-method panel rebuild."
            ),
        }
    ]


def build_plan(
    diagnosis_path: str | Path,
    *,
    isolation_report_path: str | Path | None = None,
    same_method_baseline_manifest_path: str | Path | None = None,
    external_sensitivity_governance_path: str | Path | None = None,
) -> dict[str, Any]:
    diagnosis = _load_json(diagnosis_path)
    isolation_report = _optional_json(isolation_report_path)
    baseline_manifest = _optional_json(same_method_baseline_manifest_path)
    sensitivity_governance = _optional_json(external_sensitivity_governance_path)
    source = diagnosis.get("source_diagnosis") if isinstance(diagnosis.get("source_diagnosis"), dict) else {}
    actions = [
        *_freshness_actions(source),
        *_model_set_actions(source, isolation_report),
        *_panel_method_actions(source, baseline_manifest),
        *_sensitivity_actions(source, sensitivity_governance),
    ]
    actions = sorted(actions, key=lambda item: int(item["priority"]))
    unresolved = [item["id"] for item in actions if item.get("status") == "required"]
    return {
        "report_type": "ncf_panel_drift_remediation_plan",
        "source_diagnosis": str(_resolve(diagnosis_path)),
        "status": "blocked" if unresolved else "ready_for_gate_recheck",
        "diagnosis_status": diagnosis.get("status"),
        "model_set_isolation_report": str(_resolve(isolation_report_path)) if isolation_report_path else None,
        "same_method_baseline_manifest": str(_resolve(same_method_baseline_manifest_path))
        if same_method_baseline_manifest_path
        else None,
        "external_sensitivity_governance": str(_resolve(external_sensitivity_governance_path))
        if external_sensitivity_governance_path
        else None,
        "exceeded_columns": diagnosis.get("exceeded_columns", []),
        "trigger_critical_exceeded": diagnosis.get("trigger_critical_exceeded", []),
        "actions": actions,
        "unresolved_actions": unresolved,
        "permissions": _permission_summary(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis", required=True)
    parser.add_argument("--model-set-isolation-report", default=None)
    parser.add_argument("--same-method-baseline-manifest", default=None)
    parser.add_argument("--external-sensitivity-governance", default=None)
    parser.add_argument("--output", default="results/ncf_panel_drift_remediation_plan_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_plan(
        args.diagnosis,
        isolation_report_path=args.model_set_isolation_report,
        same_method_baseline_manifest_path=args.same_method_baseline_manifest,
        external_sensitivity_governance_path=args.external_sensitivity_governance,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF panel drift remediation plan: {output}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "unresolved_actions": report["unresolved_actions"],
                "promotion_allowed": report["permissions"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
