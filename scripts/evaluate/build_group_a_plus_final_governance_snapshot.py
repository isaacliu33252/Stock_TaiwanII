#!/usr/bin/env python3
"""Build a compact final governance snapshot for the latest GroupA+ state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DAILY_STATUS = PROJECT_ROOT / "report/group_a_plus/latest/daily_status.json"
DEFAULT_OPS_HEALTH = PROJECT_ROOT / "report/group_a_plus/latest/ops_health.json"
DEFAULT_PROMOTION_GATE = PROJECT_ROOT / "results/group_a_plus_promotion_gate_20260722.json"
DEFAULT_PROMOTION_BLOCKED_DIAGNOSTIC = PROJECT_ROOT / "report/group_a_plus/latest/promotion_blocked_diagnostic.json"
DEFAULT_MULTI_WINDOW_FAILURE_ATTRIBUTION = PROJECT_ROOT / "report/group_a_plus/latest/multi_window_failure_attribution.json"
DEFAULT_PANEL_DRIFT_TRIAGE = PROJECT_ROOT / "report/group_a_plus/latest/panel_drift_triage.json"
DEFAULT_PANEL_DRIFT_RESOLUTION_PROGRESS = PROJECT_ROOT / "report/group_a_plus/latest/panel_drift_resolution_progress.json"
DEFAULT_EXTERNAL_SENSITIVITY_OBSERVATION_LOG = (
    PROJECT_ROOT / "report/group_a_plus/latest/external_sensitivity_observation_log.json"
)
DEFAULT_DEPLOYMENT_SUMMARY = PROJECT_ROOT / "report/group_a_plus/latest/deployment_summary.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/final_governance_snapshot.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/final_governance_snapshot.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/final_governance_snapshot/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if payload.get("success") is True and isinstance(data, dict) else payload


def _daily_payload(path: Path) -> tuple[dict[str, Any], str | None]:
    pointer = _load(path)
    if isinstance(pointer.get("json"), str):
        managed = _resolve(pointer["json"])
        return _load(managed), str(managed)
    return pointer, str(path) if pointer else None


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def build_snapshot(
    *,
    daily_status_path: Path = DEFAULT_DAILY_STATUS,
    ops_health_path: Path = DEFAULT_OPS_HEALTH,
    promotion_gate_path: Path = DEFAULT_PROMOTION_GATE,
    promotion_blocked_diagnostic_path: Path = DEFAULT_PROMOTION_BLOCKED_DIAGNOSTIC,
    multi_window_failure_attribution_path: Path = DEFAULT_MULTI_WINDOW_FAILURE_ATTRIBUTION,
    panel_drift_triage_path: Path = DEFAULT_PANEL_DRIFT_TRIAGE,
    panel_drift_resolution_progress_path: Path = DEFAULT_PANEL_DRIFT_RESOLUTION_PROGRESS,
    external_sensitivity_observation_log_path: Path = DEFAULT_EXTERNAL_SENSITIVITY_OBSERVATION_LOG,
    deployment_summary_path: Path = DEFAULT_DEPLOYMENT_SUMMARY,
) -> dict[str, Any]:
    daily, daily_payload_path = _daily_payload(daily_status_path)
    ops = _unwrap(_load(ops_health_path))
    promotion = _load(promotion_gate_path)
    promotion_diagnostic = _load(promotion_blocked_diagnostic_path)
    multi_window_attribution = _load(multi_window_failure_attribution_path)
    panel_drift_triage = _load(panel_drift_triage_path)
    panel_drift_progress = _load(panel_drift_resolution_progress_path)
    observation_log = _load(external_sensitivity_observation_log_path)
    deployment = _load(deployment_summary_path)
    pipeline = _dict(ops, "pipeline_health")
    deployment_decision = _dict(deployment, "decision")
    deployment_consistency = _dict(deployment, "consistency_review")
    deployment_summary_gate = _dict(promotion, "deployment_summary_gate")
    deployment_consistency_gate = _dict(promotion, "deployment_consistency_gate")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_final_governance_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": deployment.get("as_of") or daily.get("check_date"),
        "actual_data_date": deployment.get("actual_data_date") or (daily.get("signal") or {}).get("actual_data_date"),
        "strategy_id": deployment.get("strategy_id") or daily.get("profile"),
        "daily_status": {
            "overall_status": daily.get("overall_status"),
            "status_stage": daily.get("status_stage"),
            "check_date": daily.get("check_date"),
            "source_pointer": str(daily_status_path),
            "source_payload": daily_payload_path,
        },
        "ops_health": {
            "status": ops.get("status"),
            "pipeline_status": pipeline.get("status"),
            "pipeline_date_stamp": pipeline.get("date_stamp"),
            "pipeline_errors": pipeline.get("errors") or [],
            "pipeline_missing_outputs": pipeline.get("missing_outputs") or [],
            "final_daily_status": pipeline.get("final_daily_status") or {},
        },
        "promotion_gate": {
            "decision": promotion.get("decision"),
            "blocking_gates": promotion.get("blocking_gates") or [],
            "deployment_summary_gate_status": deployment_summary_gate.get("status"),
            "deployment_summary_gate_blocking_reasons": deployment_summary_gate.get("blocking_reasons") or [],
            "deployment_consistency_gate_status": deployment_consistency_gate.get("status"),
            "deployment_consistency_blocking_reasons": deployment_consistency_gate.get("blocking_reasons") or [],
        },
        "promotion_blocked_diagnostic": {
            "status": promotion_diagnostic.get("status"),
            "summary": promotion_diagnostic.get("summary") or {},
            "metrics_top_failures": (_dict(promotion_diagnostic, "metrics_gate").get("top_failures") or [])[:3],
            "panel_drift_failed_checks": (_dict(promotion_diagnostic, "panel_drift_gate").get("failed_checks") or []),
            "multi_window_reason": _dict(promotion_diagnostic, "multi_window_gate").get("reason"),
            "deployment_consistency_blocking_reasons": (
                _dict(promotion_diagnostic, "deployment_consistency_gate").get("blocking_reasons") or []
            ),
        },
        "multi_window_failure_attribution": {
            "status": multi_window_attribution.get("status"),
            "source_decision": multi_window_attribution.get("source_decision"),
            "nearest_candidates": _dict(multi_window_attribution, "summary").get("nearest_candidates") or [],
            "top_failure_reasons": _dict(multi_window_attribution, "summary").get("top_failure_reasons") or [],
        },
        "panel_drift_triage": {
            "status": panel_drift_triage.get("status"),
            "exceeded_columns": _dict(panel_drift_triage, "summary").get("exceeded_columns") or [],
            "trigger_critical_exceeded": _dict(panel_drift_triage, "summary").get("trigger_critical_exceeded") or [],
            "source_hypotheses": _dict(panel_drift_triage, "summary").get("source_hypotheses") or [],
            "top_exceed_months": _dict(panel_drift_triage, "summary").get("top_exceed_months") or [],
        },
        "panel_drift_resolution_progress": {
            "status": panel_drift_progress.get("status"),
            "unresolved_action_ids": panel_drift_progress.get("unresolved_action_ids") or [],
            "remaining_observation_sessions": _dict(panel_drift_progress, "summary").get(
                "remaining_observation_sessions"
            ),
            "remaining_stable_observation_sessions": _dict(panel_drift_progress, "summary").get(
                "remaining_stable_observation_sessions"
            ),
            "external_sensitivity_status": _dict(panel_drift_progress, "external_sensitivity").get("status"),
        },
        "external_sensitivity_observation_log": {
            "observation_count": _dict(observation_log, "summary").get("observation_count"),
            "valid_observation_count": _dict(observation_log, "summary").get("valid_observation_count"),
            "stable_observation_count": _dict(observation_log, "summary").get("stable_observation_count"),
            "latest_observation_date": _dict(observation_log, "summary").get("latest_observation_date"),
            "latest_trigger_critical_exceeded": _dict(observation_log, "summary").get(
                "latest_trigger_critical_exceeded"
            )
            or [],
        },
        "deployment_summary": {
            "status": deployment.get("status"),
            "broker_actionable": deployment.get("broker_actionable"),
            "consistency_review_status": deployment_consistency.get("status"),
            "blocking_reasons": deployment.get("blocking_reasons") or [],
            "warning_reasons": deployment.get("warning_reasons") or [],
            "target_weights": deployment.get("target_weights") or {},
            "final_target_shares": deployment.get("final_target_shares") or {},
            "execution_plan_cash": deployment.get("execution_plan_cash") or {},
        },
        "decision": {
            "creates_orders": deployment_decision.get("creates_orders") is True,
            "target_weight_change_allowed": deployment_decision.get("target_weight_change_allowed") is True,
            "auto_rebalance_allowed": deployment_decision.get("auto_rebalance_allowed") is True,
            "allow_00631l_add": deployment_decision.get("allow_00631l_add") is True,
            "allow_00632r_open": deployment_decision.get("allow_00632r_open") is True,
            "keep_golden1_0531_unchanged": deployment_decision.get("keep_golden1_0531_unchanged") is True,
        },
        "inputs": {
            "daily_status": str(daily_status_path),
            "ops_health": str(ops_health_path),
            "promotion_gate": str(promotion_gate_path),
            "promotion_blocked_diagnostic": str(promotion_blocked_diagnostic_path),
            "multi_window_failure_attribution": str(multi_window_failure_attribution_path),
            "panel_drift_triage": str(panel_drift_triage_path),
            "panel_drift_resolution_progress": str(panel_drift_resolution_progress_path),
            "external_sensitivity_observation_log": str(external_sensitivity_observation_log_path),
            "deployment_summary": str(deployment_summary_path),
        },
    }


def _markdown(snapshot: dict[str, Any]) -> str:
    daily = snapshot["daily_status"]
    ops = snapshot["ops_health"]
    promotion = snapshot["promotion_gate"]
    deployment = snapshot["deployment_summary"]
    promotion_diagnostic = snapshot.get("promotion_blocked_diagnostic") or {}
    decision = snapshot["decision"]
    lines = [
        "# GroupA+ Final Governance Snapshot",
        "",
        f"- As of: `{snapshot.get('as_of')}`",
        f"- Actual data date: `{snapshot.get('actual_data_date')}`",
        f"- Strategy: `{snapshot.get('strategy_id')}`",
        f"- Daily status: `{daily.get('overall_status')}` stage `{daily.get('status_stage')}`",
        f"- Ops pipeline: `{ops.get('pipeline_status')}` date `{ops.get('pipeline_date_stamp')}`",
        f"- Promotion decision: `{promotion.get('decision')}`",
        f"- Promotion blocking gates: `{promotion.get('blocking_gates')}`",
        f"- Deployment summary gate: `{promotion.get('deployment_summary_gate_status')}`",
        f"- Deployment consistency gate: `{promotion.get('deployment_consistency_gate_status')}`",
        f"- Deployment summary consistency: `{deployment.get('consistency_review_status')}`",
        f"- Promotion diagnostic: `{promotion_diagnostic.get('status')}`",
        f"- Broker actionable: `{deployment.get('broker_actionable')}`",
        "",
        "## Decision Boundary",
        "",
        f"- Creates orders: `{decision.get('creates_orders')}`",
        f"- Target weight change allowed: `{decision.get('target_weight_change_allowed')}`",
        f"- Auto rebalance allowed: `{decision.get('auto_rebalance_allowed')}`",
        f"- 00631L add allowed: `{decision.get('allow_00631l_add')}`",
        f"- 00632R open allowed: `{decision.get('allow_00632r_open')}`",
        f"- Golden1_0531 unchanged: `{decision.get('keep_golden1_0531_unchanged')}`",
        "",
        "## Deployment Warnings",
        "",
    ]
    warnings = deployment.get("warning_reasons") or []
    if not warnings:
        lines.append("- None")
    for warning in warnings:
        lines.append(f"- `{warning}`")
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"final_governance_snapshot_{stamp}.json"


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(snapshot), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, snapshot.get("as_of")).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-status", default=str(DEFAULT_DAILY_STATUS))
    parser.add_argument("--ops-health", default=str(DEFAULT_OPS_HEALTH))
    parser.add_argument("--promotion-gate", default=str(DEFAULT_PROMOTION_GATE))
    parser.add_argument("--promotion-blocked-diagnostic", default=str(DEFAULT_PROMOTION_BLOCKED_DIAGNOSTIC))
    parser.add_argument("--multi-window-failure-attribution", default=str(DEFAULT_MULTI_WINDOW_FAILURE_ATTRIBUTION))
    parser.add_argument("--panel-drift-triage", default=str(DEFAULT_PANEL_DRIFT_TRIAGE))
    parser.add_argument("--panel-drift-resolution-progress", default=str(DEFAULT_PANEL_DRIFT_RESOLUTION_PROGRESS))
    parser.add_argument("--external-sensitivity-observation-log", default=str(DEFAULT_EXTERNAL_SENSITIVITY_OBSERVATION_LOG))
    parser.add_argument("--deployment-summary", default=str(DEFAULT_DEPLOYMENT_SUMMARY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot(
        daily_status_path=_resolve(args.daily_status),
        ops_health_path=_resolve(args.ops_health),
        promotion_gate_path=_resolve(args.promotion_gate),
        promotion_blocked_diagnostic_path=_resolve(args.promotion_blocked_diagnostic),
        multi_window_failure_attribution_path=_resolve(args.multi_window_failure_attribution),
        panel_drift_triage_path=_resolve(args.panel_drift_triage),
        panel_drift_resolution_progress_path=_resolve(args.panel_drift_resolution_progress),
        external_sensitivity_observation_log_path=_resolve(args.external_sensitivity_observation_log),
        deployment_summary_path=_resolve(args.deployment_summary),
    )
    write_outputs(
        snapshot,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Final governance snapshot: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "as_of": snapshot.get("as_of"),
                "daily_status_stage": snapshot["daily_status"]["status_stage"],
                "pipeline_status": snapshot["ops_health"]["pipeline_status"],
                "promotion_decision": snapshot["promotion_gate"]["decision"],
                "keep_golden1_0531_unchanged": snapshot["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
