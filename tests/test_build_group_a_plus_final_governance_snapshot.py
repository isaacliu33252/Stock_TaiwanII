from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_final_governance_snapshot import build_snapshot, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_final_governance_snapshot_compacts_latest_artifacts(tmp_path: Path) -> None:
    managed_daily = _write(
        tmp_path / "report/group_a_plus/daily/json/final.json",
        {
            "status_stage": "final",
            "overall_status": "warn",
            "check_date": "2026-07-22",
            "profile": "a2118",
            "signal": {"actual_data_date": "2026-07-22"},
        },
    )
    daily_pointer = _write(
        tmp_path / "report/group_a_plus/latest/daily_status.json",
        {"report_type": "daily_status", "json": str(managed_daily)},
    )
    ops = _write(
        tmp_path / "report/group_a_plus/latest/ops_health.json",
        {
            "status": "warning",
            "pipeline_health": {
                "status": "ok",
                "date_stamp": "20260722",
                "errors": [],
                "missing_outputs": [],
                "final_daily_status": {"status": "ok", "latest_payload_status_stage": "final"},
            },
        },
    )
    promotion = _write(
        tmp_path / "results/promotion.json",
        {
            "decision": "blocked_deployment_consistency_and_model_gates",
            "blocking_gates": ["panel_drift", "deployment_consistency"],
            "deployment_summary_gate": {"status": "pass", "blocking_reasons": []},
            "deployment_consistency_gate": {
                "status": "fail",
                "blocking_reasons": ["gift_signed_approval_record_missing_or_invalid"],
            },
        },
    )
    promotion_diagnostic = _write(
        tmp_path / "report/group_a_plus/latest/promotion_blocked_diagnostic.json",
        {
            "status": "blocked",
            "summary": {
                "panel_drift_failed": True,
                "multi_window_failed": True,
                "deployment_consistency_failed": True,
            },
            "metrics_gate": {"top_failures": [{"variant": "best_by_final_value"}]},
            "panel_drift_gate": {"failed_checks": [{"name": "confidence"}]},
            "multi_window_gate": {"reason": "no candidate passed the multi-window gate"},
            "deployment_consistency_gate": {
                "blocking_reasons": ["gift_signed_approval_record_missing_or_invalid"]
            },
        },
    )
    multi_window_attribution = _write(
        tmp_path / "report/group_a_plus/latest/multi_window_failure_attribution.json",
        {
            "status": "blocked",
            "source_decision": "research_only_no_multi_window_pass",
            "summary": {
                "nearest_candidates": ["garch_guard_frozen"],
                "top_failure_reasons": [{"reason": "final_value_drag", "count": 4}],
            },
        },
    )
    panel_drift_triage = _write(
        tmp_path / "report/group_a_plus/latest/panel_drift_triage.json",
        {
            "status": "blocked",
            "summary": {
                "exceeded_columns": ["ensemble_prob_up", "h20_prob_up", "confidence"],
                "trigger_critical_exceeded": ["h20_prob_up", "confidence"],
                "source_hypotheses": ["horizon_ensemble_or_confidence_blend_check_needed"],
                "top_exceed_months": [{"month": "2025-05", "exceed_count": 6}],
            },
        },
    )
    panel_drift_progress = _write(
        tmp_path / "report/group_a_plus/latest/panel_drift_resolution_progress.json",
        {
            "status": "blocked",
            "unresolved_action_ids": ["quantify_external_feature_sensitivity"],
            "summary": {"remaining_observation_sessions": 2, "remaining_stable_observation_sessions": 3},
            "external_sensitivity": {"status": "blocked_observation_required"},
        },
    )
    observation_log = _write(
        tmp_path / "report/group_a_plus/latest/external_sensitivity_observation_log.json",
        {
            "summary": {
                "observation_count": 1,
                "valid_observation_count": 1,
                "stable_observation_count": 0,
                "latest_observation_date": "2026-07-22",
                "latest_trigger_critical_exceeded": ["h20_prob_up", "confidence"],
            }
        },
    )
    deployment = _write(
        tmp_path / "report/group_a_plus/latest/deployment_summary.json",
        {
            "as_of": "2026-07-23",
            "actual_data_date": "2026-07-22",
            "strategy_id": "a2118",
            "status": "manual_review_required",
            "broker_actionable": True,
            "warning_reasons": ["source_freshness_soft_warning"],
            "target_weights": {"0050.TW": 0.5},
            "final_target_shares": {"0050.TW": 3257},
            "execution_plan_cash": {"current_cash_input": 1_000_000},
            "consistency_review": {"status": "ok"},
            "decision": {
                "creates_orders": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
                "keep_golden1_0531_unchanged": True,
            },
        },
    )

    snapshot = build_snapshot(
        daily_status_path=daily_pointer,
        ops_health_path=ops,
        promotion_gate_path=promotion,
        promotion_blocked_diagnostic_path=promotion_diagnostic,
        multi_window_failure_attribution_path=multi_window_attribution,
        panel_drift_triage_path=panel_drift_triage,
        panel_drift_resolution_progress_path=panel_drift_progress,
        external_sensitivity_observation_log_path=observation_log,
        deployment_summary_path=deployment,
    )

    assert snapshot["as_of"] == "2026-07-23"
    assert snapshot["actual_data_date"] == "2026-07-22"
    assert snapshot["daily_status"]["status_stage"] == "final"
    assert snapshot["ops_health"]["pipeline_status"] == "ok"
    assert snapshot["promotion_gate"]["deployment_summary_gate_status"] == "pass"
    assert snapshot["promotion_blocked_diagnostic"]["status"] == "blocked"
    assert snapshot["promotion_blocked_diagnostic"]["summary"]["panel_drift_failed"] is True
    assert snapshot["promotion_blocked_diagnostic"]["panel_drift_failed_checks"][0]["name"] == "confidence"
    assert snapshot["promotion_blocked_diagnostic"]["multi_window_reason"] == (
        "no candidate passed the multi-window gate"
    )
    assert snapshot["multi_window_failure_attribution"]["nearest_candidates"] == ["garch_guard_frozen"]
    assert snapshot["multi_window_failure_attribution"]["top_failure_reasons"] == [
        {"reason": "final_value_drag", "count": 4}
    ]
    assert snapshot["panel_drift_triage"]["trigger_critical_exceeded"] == ["h20_prob_up", "confidence"]
    assert snapshot["panel_drift_triage"]["top_exceed_months"] == [{"month": "2025-05", "exceed_count": 6}]
    assert snapshot["panel_drift_resolution_progress"]["unresolved_action_ids"] == [
        "quantify_external_feature_sensitivity"
    ]
    assert snapshot["panel_drift_resolution_progress"]["remaining_observation_sessions"] == 2
    assert snapshot["panel_drift_resolution_progress"]["remaining_stable_observation_sessions"] == 3
    assert snapshot["external_sensitivity_observation_log"]["valid_observation_count"] == 1
    assert snapshot["external_sensitivity_observation_log"]["stable_observation_count"] == 0
    assert snapshot["external_sensitivity_observation_log"]["latest_trigger_critical_exceeded"] == [
        "h20_prob_up",
        "confidence",
    ]
    assert snapshot["deployment_summary"]["consistency_review_status"] == "ok"
    assert snapshot["decision"]["creates_orders"] is False
    assert snapshot["decision"]["target_weight_change_allowed"] is False
    assert snapshot["decision"]["auto_rebalance_allowed"] is False
    assert snapshot["decision"]["allow_00631l_add"] is False
    assert snapshot["decision"]["allow_00632r_open"] is False
    assert snapshot["decision"]["keep_golden1_0531_unchanged"] is True


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    snapshot = {
        "as_of": "2026-07-23",
        "actual_data_date": "2026-07-22",
        "strategy_id": "a2118",
        "daily_status": {"overall_status": "warn", "status_stage": "final"},
        "ops_health": {"pipeline_status": "ok", "pipeline_date_stamp": "20260722"},
        "promotion_gate": {
            "decision": "blocked_deployment_consistency",
            "blocking_gates": ["deployment_consistency"],
            "deployment_summary_gate_status": "pass",
            "deployment_consistency_gate_status": "fail",
        },
        "deployment_summary": {
            "broker_actionable": True,
            "consistency_review_status": "ok",
            "warning_reasons": [],
        },
        "promotion_blocked_diagnostic": {"status": "blocked"},
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    output = tmp_path / "latest/final_governance_snapshot.json"
    output_md = tmp_path / "latest/final_governance_snapshot.md"
    history = tmp_path / "history"

    write_outputs(snapshot, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == snapshot
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ Final Governance Snapshot" in markdown
    assert "Golden1_0531 unchanged: `True`" in markdown
    assert (history / "final_governance_snapshot_20260723.json").exists()
