#!/usr/bin/env python3
"""Build an automatic attribution report for NCF panel drift diagnostics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_RETRAIN_VAL_AUC_DELTA_LIMIT = 0.02
ENSEMBLE_WEIGHT_DELTA_LIMIT = 0.15
LATEST_DIR = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_DIAGNOSIS = PROJECT_ROOT / "results/ncf_panel_drift_diagnosis_latest.json"
DEFAULT_REMEDIATION_PLAN = PROJECT_ROOT / "results/ncf_panel_drift_remediation_plan_latest.json"
DEFAULT_EXTERNAL_SENSITIVITY_GOVERNANCE = PROJECT_ROOT / "results/ncf_panel_external_feature_sensitivity_governance_latest.json"
DEFAULT_PANEL_MANIFEST = PROJECT_ROOT / "results/ncf_panel_manifest_latest.json"
DEFAULT_DATA_FRESHNESS_GATE = LATEST_DIR / "data_freshness_gate.json"
DEFAULT_OUTPUT = LATEST_DIR / "ncf_panel_drift_auto_attribution.json"
DEFAULT_OUTPUT_MD = LATEST_DIR / "ncf_panel_drift_auto_attribution.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = _resolve(path)
    if not resolved.exists():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def _dict(payload: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list(payload: dict[str, Any] | None, key: str) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _max_column_delta(diagnosis: dict[str, Any] | None) -> float:
    columns = _dict(diagnosis, "columns")
    max_delta = 0.0
    for column in columns.values():
        if not isinstance(column, dict):
            continue
        value = column.get("max_abs_delta")
        if isinstance(value, (int, float)):
            max_delta = max(max_delta, abs(float(value)))
    return max_delta


def _permission_summary() -> dict[str, bool]:
    return {
        "creates_orders": False,
        "promotion_allowed": False,
        "training_allowed": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "model_training_allowed": False,
        "ppo_training_allowed": False,
        "promote_to_live": False,
        "keep_golden1_0531_unchanged": True,
        "keep_golden2_0830_unchanged": True,
    }


def _attribution(
    cause: str,
    *,
    severity: str,
    evidence: list[str],
    recommended_check: str,
) -> dict[str, Any]:
    return {
        "cause": cause,
        "severity": severity,
        "evidence": evidence,
        "recommended_check": recommended_check,
    }


def _freshness_attributions(data_freshness: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data_freshness:
        return [
            _attribution(
                "data_freshness_gate_missing",
                severity="warning",
                evidence=["data_freshness_gate file is missing"],
                recommended_check="run data_freshness_gate before accepting drift attribution",
            )
        ]
    status = data_freshness.get("status")
    blockers = [str(item) for item in _list(data_freshness, "blockers")]
    warnings = [str(item) for item in _list(data_freshness, "warnings")]
    if status not in {"blocked", "warning"} and not blockers and not warnings:
        return []
    summary = _dict(data_freshness, "summary")
    evidence = [
        f"data_freshness_status={status}",
        f"blockers={blockers}",
        f"warnings={warnings}",
    ]
    for key in (
        "live_signal_actual_data_date",
        "live_signal_business_stale_days",
        "ohlcv_target_date",
        "latest_strategy_target_weight_window_end",
    ):
        if summary.get(key) is not None:
            evidence.append(f"{key}={summary[key]}")
    return [
        _attribution(
            "data_or_artifact_freshness",
            severity="blocked" if blockers or status == "blocked" else "warning",
            evidence=evidence,
            recommended_check="refresh upstream data and rebuild live signal, panel manifest, drift audit, and latest strategy explain snapshot",
        )
    ]


def _remediation_attributions(remediation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not remediation:
        return [
            _attribution(
                "remediation_plan_missing",
                severity="warning",
                evidence=["ncf_panel_drift_remediation_plan file is missing"],
                recommended_check="run remediation plan after drift diagnosis",
            )
        ]
    rows = []
    for action in _list(remediation, "actions"):
        if not isinstance(action, dict) or action.get("status") != "required":
            continue
        action_id = str(action.get("id"))
        if action_id == "refresh_stale_candidate_sources":
            rows.append(
                _attribution(
                    "candidate_source_staleness",
                    severity="blocked",
                    evidence=[
                        f"action={action_id}",
                        f"stale_sources={action.get('stale_sources') or []}",
                        str(action.get("reason") or ""),
                    ],
                    recommended_check="refresh stale candidate sources, then rebuild same-day NCF panels and drift diagnosis",
                )
            )
        elif action_id == "quantify_external_feature_sensitivity":
            rows.append(
                _attribution(
                    "external_feature_sensitivity",
                    severity="blocked",
                    evidence=[
                        f"action={action_id}",
                        f"max_trigger_critical_sensitivity={action.get('max_trigger_critical_sensitivity')}",
                        f"governance_status={action.get('governance_status')}",
                        str(action.get("reason") or ""),
                    ],
                    recommended_check="keep external/no-external paired audit running until same-method observations are stable",
                )
            )
        else:
            rows.append(
                _attribution(
                    action_id,
                    severity="blocked",
                    evidence=[str(action.get("reason") or ""), f"action={action_id}"],
                    recommended_check=str(action.get("recommended_action") or "review unresolved remediation action"),
                )
            )
    return rows


def _diagnosis_attributions(diagnosis: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not diagnosis:
        return [
            _attribution(
                "panel_drift_diagnosis_missing",
                severity="blocked",
                evidence=["ncf_panel_drift_diagnosis file is missing"],
                recommended_check="run NCF panel drift diagnosis before attributing panel drift",
            )
        ]
    exceeded = [str(item) for item in _list(diagnosis, "exceeded_columns")]
    trigger = [str(item) for item in _list(diagnosis, "trigger_critical_exceeded")]
    if exceeded:
        return [
            _attribution(
                "panel_value_drift",
                severity="blocked" if trigger else "warning",
                evidence=[
                    f"diagnosis_status={diagnosis.get('status')}",
                    f"exceeded_columns={exceeded}",
                    f"trigger_critical_exceeded={trigger}",
                    f"overlap_rows={diagnosis.get('overlap_rows')}",
                    f"max_column_delta={_max_column_delta(diagnosis)}",
                ],
                recommended_check="inspect the columns and dates with largest deltas before changing promotion gates",
            )
        ]
    if _max_column_delta(diagnosis) <= 0.0:
        return [
            _attribution(
                "no_material_drift",
                severity="info",
                evidence=[
                    f"diagnosis_status={diagnosis.get('status')}",
                    f"exceeded_columns={exceeded}",
                    f"max_column_delta={_max_column_delta(diagnosis)}",
                ],
                recommended_check="no panel-drift remediation is needed unless another gate is blocked",
            )
        ]
    return []


def _model_retrain_attributions(diagnosis: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not diagnosis:
        return []
    model_sets = _dict(_dict(diagnosis, "source_diagnosis"), "model_sets")
    if model_sets.get("status") == "not_available":
        return []
    by_horizon = _dict(model_sets, "by_horizon")
    if model_sets.get("status") == "changed":
        changed_horizons = []
        for horizon, info in by_horizon.items():
            if not isinstance(info, dict):
                continue
            if info.get("removed_models") or info.get("added_models"):
                changed_horizons.append(
                    f"h{horizon}: removed={info.get('removed_models')} added={info.get('added_models')} "
                    f"val_auc {info.get('baseline_val_auc')}->{info.get('candidate_val_auc')}"
                )
        return [
            _attribution(
                "model_set_or_retrain_change",
                severity="warning",
                evidence=changed_horizons or ["model_sets status is changed but no per-horizon detail available"],
                recommended_check="confirm whether the model roster change was an intentional retrain/promotion or an unpinned dependency drift",
            )
        ]
    shifted_horizons = []
    for horizon, info in by_horizon.items():
        if not isinstance(info, dict):
            continue
        baseline_auc = info.get("baseline_val_auc")
        candidate_auc = info.get("candidate_val_auc")
        if not isinstance(baseline_auc, (int, float)) or not isinstance(candidate_auc, (int, float)):
            continue
        delta = abs(float(candidate_auc) - float(baseline_auc))
        if delta > MODEL_RETRAIN_VAL_AUC_DELTA_LIMIT:
            shifted_horizons.append(f"h{horizon}: val_auc {baseline_auc}->{candidate_auc} (delta={delta:.4f})")
    if shifted_horizons:
        return [
            _attribution(
                "model_retrain_score_shift",
                severity="warning",
                evidence=shifted_horizons,
                recommended_check="same model roster but validation AUC shifted beyond "
                f"{MODEL_RETRAIN_VAL_AUC_DELTA_LIMIT}; confirm training window or label availability did not change",
            )
        ]
    return []


def _ensemble_weight_attributions(diagnosis: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not diagnosis:
        return []
    panel_methods = _dict(_dict(diagnosis, "source_diagnosis"), "panel_methods")
    rows = []
    baseline_has_weights = panel_methods.get("baseline_has_ensemble_weights")
    candidate_has_weights = panel_methods.get("candidate_has_ensemble_weights")
    if panel_methods and baseline_has_weights != candidate_has_weights:
        rows.append(
            _attribution(
                "ensemble_weight_schema_change",
                severity="warning",
                evidence=[
                    f"baseline_has_ensemble_weights={baseline_has_weights}",
                    f"candidate_has_ensemble_weights={candidate_has_weights}",
                ],
                recommended_check="confirm whether per-model ensemble weighting was intentionally added, removed, or changed method",
            )
        )
    columns = _dict(diagnosis, "columns")
    flagged = []
    for column, info in columns.items():
        if not column.startswith("ensemble_weight_h") or not isinstance(info, dict):
            continue
        max_abs = info.get("max_abs_delta")
        if isinstance(max_abs, (int, float)) and float(max_abs) > ENSEMBLE_WEIGHT_DELTA_LIMIT:
            flagged.append(f"{column}: max_abs_delta={max_abs} on {info.get('max_abs_delta_date')}")
    if flagged:
        rows.append(
            _attribution(
                "ensemble_weight_reallocation",
                severity="warning",
                evidence=flagged,
                recommended_check="per-model ensemble weighting shifted more than "
                f"{ENSEMBLE_WEIGHT_DELTA_LIMIT}; check whether this tracks a retrain or the expanding-window AUC/Brier reweighting",
            )
        )
    return rows


def _external_governance_attributions(governance: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not governance:
        return []
    status = governance.get("status")
    if status not in {"blocked_observation_required", "blocked_sensitivity_audit_missing"}:
        return []
    governance_block = _dict(governance, "governance")
    return [
        _attribution(
            "external_feature_governance_block",
            severity="blocked",
            evidence=[
                f"governance_status={status}",
                f"reason={governance_block.get('reason')}",
                f"resolution_allowed={governance_block.get('resolution_allowed')}",
            ],
            recommended_check="do not reduce the external-feature blocker until the governance report allows resolution",
        )
    ]


def _manifest_attributions(manifest: dict[str, Any] | None, data_freshness: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return [
            _attribution(
                "ncf_panel_manifest_missing",
                severity="warning",
                evidence=["ncf_panel_manifest file is missing"],
                recommended_check="run panel manifest to compare panel date windows and hashes",
            )
        ]
    panels = [item for item in _list(manifest, "panels") if isinstance(item, dict)]
    date_ends = sorted({str(panel.get("date_end")) for panel in panels if panel.get("date_end")})
    missing = [str(panel.get("path")) for panel in panels if panel.get("exists") is False]
    rows = []
    if len(date_ends) > 1:
        rows.append(
            _attribution(
                "panel_date_window_mismatch",
                severity="warning",
                evidence=[f"panel_date_ends={date_ends}"],
                recommended_check="rebuild lagging NCF panels so all instruments share the same latest panel date",
            )
        )
    if missing:
        rows.append(
            _attribution(
                "panel_file_missing",
                severity="blocked",
                evidence=[f"missing_panels={missing}"],
                recommended_check="rebuild missing panel files before accepting drift or coverage reports",
            )
        )
    freshness_summary = _dict(data_freshness, "summary")
    ohlcv_target = freshness_summary.get("ohlcv_target_date")
    if ohlcv_target and date_ends and max(date_ends) < str(ohlcv_target):
        rows.append(
            _attribution(
                "panel_lags_ohlcv_target",
                severity="warning",
                evidence=[f"latest_panel_date={max(date_ends)}", f"ohlcv_target_date={ohlcv_target}"],
                recommended_check="rebuild panels after OHLCV refresh",
            )
        )
    return rows


def _primary(attributions: list[dict[str, Any]]) -> str:
    priority = {
        "panel_drift_diagnosis_missing": 0,
        "panel_file_missing": 1,
        "data_or_artifact_freshness": 2,
        "candidate_source_staleness": 3,
        "external_feature_sensitivity": 4,
        "external_feature_governance_block": 5,
        "model_set_or_retrain_change": 6,
        "model_retrain_score_shift": 7,
        "ensemble_weight_schema_change": 8,
        "ensemble_weight_reallocation": 9,
        "panel_value_drift": 10,
        "panel_date_window_mismatch": 11,
        "panel_lags_ohlcv_target": 12,
        "no_material_drift": 99,
    }
    return min(attributions, key=lambda row: priority.get(str(row.get("cause")), 50)).get("cause", "unattributed")


def build_report(
    *,
    diagnosis_path: str | Path = DEFAULT_DIAGNOSIS,
    remediation_plan_path: str | Path = DEFAULT_REMEDIATION_PLAN,
    external_sensitivity_governance_path: str | Path | None = DEFAULT_EXTERNAL_SENSITIVITY_GOVERNANCE,
    panel_manifest_path: str | Path | None = DEFAULT_PANEL_MANIFEST,
    data_freshness_gate_path: str | Path | None = DEFAULT_DATA_FRESHNESS_GATE,
    as_of: str | None = None,
) -> dict[str, Any]:
    diagnosis = _optional_json(diagnosis_path)
    remediation = _optional_json(remediation_plan_path)
    governance = _optional_json(external_sensitivity_governance_path)
    manifest = _optional_json(panel_manifest_path)
    data_freshness = _optional_json(data_freshness_gate_path)
    attributions = [
        *_diagnosis_attributions(diagnosis),
        *_freshness_attributions(data_freshness),
        *_remediation_attributions(remediation),
        *_external_governance_attributions(governance),
        *_manifest_attributions(manifest, data_freshness),
        *_model_retrain_attributions(diagnosis),
        *_ensemble_weight_attributions(diagnosis),
    ]
    if not attributions:
        attributions = [
            _attribution(
                "unattributed_requires_manual_review",
                severity="warning",
                evidence=["no automatic attribution rule matched the available artifacts"],
                recommended_check="inspect drift diagnosis, candidate signal freshness, and paired external/no-external panels manually",
            )
        ]
    status = "blocked" if any(row.get("severity") == "blocked" for row in attributions) else (
        "warning" if any(row.get("severity") == "warning" for row in attributions) else "pass"
    )
    return {
        "schema_version": 1,
        "report_type": "ncf_panel_drift_auto_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": status,
        "policy": "diagnostic_only_no_model_change_no_weight_change",
        "primary_attribution": _primary(attributions),
        "attributions": attributions,
        "inputs": {
            "diagnosis": str(_resolve(diagnosis_path)),
            "remediation_plan": str(_resolve(remediation_plan_path)),
            "external_sensitivity_governance": str(_resolve(external_sensitivity_governance_path))
            if external_sensitivity_governance_path
            else None,
            "panel_manifest": str(_resolve(panel_manifest_path)) if panel_manifest_path else None,
            "data_freshness_gate": str(_resolve(data_freshness_gate_path)) if data_freshness_gate_path else None,
        },
        "decision": _permission_summary(),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NCF Panel Drift Auto Attribution",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Primary attribution: `{report.get('primary_attribution')}`",
        f"- Policy: `{report.get('policy')}`",
        "",
        "## Attributions",
        "",
    ]
    for row in report.get("attributions") or []:
        lines.append(f"- `{row.get('cause')}` severity `{row.get('severity')}`")
        for item in row.get("evidence") or []:
            lines.append(f"  - {item}")
        lines.append(f"  - next: {row.get('recommended_check')}")
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            f"- Creates orders: `{report['decision']['creates_orders']}`",
            f"- Promotion allowed: `{report['decision']['promotion_allowed']}`",
            f"- Training allowed: `{report['decision']['training_allowed']}`",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Golden1_0531 unchanged: `{report['decision']['keep_golden1_0531_unchanged']}`",
            f"- Golden2_0830 unchanged: `{report['decision']['keep_golden2_0830_unchanged']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output: Path = DEFAULT_OUTPUT, output_md: Path = DEFAULT_OUTPUT_MD) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis", default=str(DEFAULT_DIAGNOSIS))
    parser.add_argument("--remediation-plan", default=str(DEFAULT_REMEDIATION_PLAN))
    parser.add_argument("--external-sensitivity-governance", default=str(DEFAULT_EXTERNAL_SENSITIVITY_GOVERNANCE))
    parser.add_argument("--panel-manifest", default=str(DEFAULT_PANEL_MANIFEST))
    parser.add_argument("--data-freshness-gate", default=str(DEFAULT_DATA_FRESHNESS_GATE))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        diagnosis_path=args.diagnosis,
        remediation_plan_path=args.remediation_plan,
        external_sensitivity_governance_path=args.external_sensitivity_governance,
        panel_manifest_path=args.panel_manifest,
        data_freshness_gate_path=args.data_freshness_gate,
        as_of=args.as_of,
    )
    write_outputs(report, output=_resolve(args.output), output_md=_resolve(args.output_md))
    print(f"NCF panel drift auto attribution: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "primary_attribution": report["primary_attribution"],
                "promotion_allowed": report["decision"]["promotion_allowed"],
                "training_allowed": report["decision"]["training_allowed"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
