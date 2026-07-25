from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_panel_drift_resolution_progress import build_progress, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_panel_drift_resolution_progress_tracks_remaining_observations(tmp_path: Path) -> None:
    remediation = _write(
        tmp_path / "remediation.json",
        {
            "status": "blocked",
            "unresolved_actions": ["quantify_external_feature_sensitivity"],
            "actions": [
                {
                    "id": "isolate_model_set_change",
                    "priority": 2,
                    "status": "resolved",
                    "reason": "model-set mismatch isolated",
                    "recommended_action": "keep same-method baseline shadow-only",
                },
                {
                    "id": "quantify_external_feature_sensitivity",
                    "priority": 4,
                    "status": "required",
                    "reason": "external-feature sensitivity exceeds trigger-critical drift tolerance",
                    "recommended_action": "Keep promotion blocked until sensitivity is stable.",
                },
            ],
        },
    )
    sensitivity = _write(
        tmp_path / "sensitivity.json",
        {
            "status": "blocked_observation_required",
            "checks": {
                "trigger_critical_exceeded": ["h20_prob_up", "confidence"],
                "diagnostic_exceeded": ["ensemble_prob_up"],
            },
            "governance": {
                "required_observation_sessions": 3,
                "completed_observation_sessions": 1,
                "remaining_observation_sessions": 2,
                "stable_observation_sessions": 0,
                "remaining_stable_observation_sessions": 3,
                "resolution_allowed": False,
                "reason": "external-feature sensitivity exceeds trigger-critical limits",
                "next_action": "Run at least two additional observations.",
            },
        },
    )

    report = build_progress(remediation_plan_path=remediation, external_sensitivity_governance_path=sensitivity)

    assert report["status"] == "blocked"
    assert report["summary"]["resolved_count"] == 1
    assert report["summary"]["unresolved_count"] == 1
    assert report["summary"]["remaining_observation_sessions"] == 2
    assert report["summary"]["remaining_stable_observation_sessions"] == 3
    assert report["unresolved_action_ids"] == ["quantify_external_feature_sensitivity"]
    assert report["external_sensitivity"]["stable_observation_sessions"] == 0
    assert report["external_sensitivity"]["remaining_stable_observation_sessions"] == 3
    assert report["external_sensitivity"]["trigger_critical_exceeded"] == ["h20_prob_up", "confidence"]
    assert "complete 3 additional stable" in report["summary"]["next_actions"][1]
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["decision"]["keep_golden1_0531_unchanged"] is True


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    report = {
        "status": "blocked",
        "remediation_status": "blocked",
        "unresolved_action_ids": ["quantify_external_feature_sensitivity"],
        "summary": {
            "remaining_observation_sessions": 2,
            "next_actions": ["complete observations"],
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    output = tmp_path / "latest/panel_drift_resolution_progress.json"
    output_md = tmp_path / "latest/panel_drift_resolution_progress.md"
    history = tmp_path / "history"

    write_outputs(report, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ Panel Drift Resolution Progress" in markdown
    assert "Golden1_0531 unchanged: `True`" in markdown
    assert list(history.glob("panel_drift_resolution_progress_*.json"))
