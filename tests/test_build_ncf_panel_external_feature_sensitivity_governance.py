from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_ncf_panel_external_feature_sensitivity_governance import build_report


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_external_feature_sensitivity_governance_blocks_trigger_critical_sensitivity(tmp_path: Path) -> None:
    sensitivity = _write_json(
        tmp_path / "sensitivity.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.45, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.51, "max_abs_delta_date": "2025-01-03"},
                "confidence": {"max_abs_delta": 0.63, "max_abs_delta_date": "2025-01-06"},
            }
        },
    )
    manifest = _write_json(tmp_path / "manifest.json", {"status": "valid_shadow_baseline"})
    remediation = _write_json(
        tmp_path / "remediation.json",
        {"unresolved_actions": ["quantify_external_feature_sensitivity"]},
    )

    report = build_report(
        sensitivity_audit=sensitivity,
        same_method_baseline_manifest=manifest,
        remediation_plan=remediation,
    )

    assert report["status"] == "blocked_observation_required"
    assert report["checks"]["same_method_baseline_manifest_valid"] is True
    assert report["checks"]["remediation_action_present"] is True
    assert report["checks"]["trigger_critical_exceeded"] == ["h20_prob_up", "confidence"]
    assert report["checks"]["diagnostic_exceeded"] == ["ensemble_prob_up"]
    assert report["governance"]["required_observation_sessions"] == 3
    assert report["governance"]["completed_observation_sessions"] == 1
    assert report["governance"]["resolution_allowed"] is False
    assert report["permissions"]["external_sensitivity_blocker_resolved"] is False
    assert report["permissions"]["promotion_allowed"] is False
    assert report["permissions"]["training_allowed"] is False
    assert report["permissions"]["target_weight_change_allowed"] is False
    assert report["permissions"]["keep_golden1_0531_unchanged"] is True


def test_external_feature_sensitivity_governance_records_missing_audit_as_blocked(tmp_path: Path) -> None:
    manifest = _write_json(tmp_path / "manifest.json", {"status": "valid_shadow_baseline"})
    remediation = _write_json(
        tmp_path / "remediation.json",
        {"unresolved_actions": ["quantify_external_feature_sensitivity"]},
    )

    report = build_report(
        sensitivity_audit=tmp_path / "missing_sensitivity.json",
        same_method_baseline_manifest=manifest,
        remediation_plan=remediation,
        allow_missing_sensitivity_audit=True,
    )

    assert report["status"] == "blocked_sensitivity_audit_missing"
    assert report["checks"]["sensitivity_audit_available"] is False
    assert report["governance"]["resolution_allowed"] is False
    assert report["permissions"]["promotion_allowed"] is False


def test_external_feature_sensitivity_governance_uses_observation_log_counts(tmp_path: Path) -> None:
    sensitivity = _write_json(
        tmp_path / "sensitivity.json",
        {
            "column_summary": {
                "h20_prob_up": {"max_abs_delta": 0.51, "max_abs_delta_date": "2025-01-03"},
                "confidence": {"max_abs_delta": 0.63, "max_abs_delta_date": "2025-01-06"},
            }
        },
    )
    manifest = _write_json(tmp_path / "manifest.json", {"status": "valid_shadow_baseline"})
    remediation = _write_json(
        tmp_path / "remediation.json",
        {"unresolved_actions": ["quantify_external_feature_sensitivity"]},
    )
    observation_log = _write_json(
        tmp_path / "observation_log.json",
        {
            "summary": {
                "valid_observation_count": 2,
                "stable_observation_count": 1,
                "latest_trigger_critical_exceeded": ["h20_prob_up", "confidence"],
            }
        },
    )

    report = build_report(
        sensitivity_audit=sensitivity,
        same_method_baseline_manifest=manifest,
        remediation_plan=remediation,
        observation_log=observation_log,
    )

    assert report["checks"]["observation_log_available"] is True
    assert report["governance"]["completed_observation_sessions"] == 2
    assert report["governance"]["remaining_observation_sessions"] == 1
    assert report["governance"]["stable_observation_sessions"] == 1
    assert report["governance"]["remaining_stable_observation_sessions"] == 2
    assert report["governance"]["latest_trigger_critical_exceeded"] == ["h20_prob_up", "confidence"]
    assert report["governance"]["resolution_allowed"] is False
    assert report["permissions"]["external_sensitivity_blocker_resolved"] is False


def test_external_feature_sensitivity_governance_resolves_after_three_stable_observations(tmp_path: Path) -> None:
    sensitivity = _write_json(
        tmp_path / "sensitivity.json",
        {
            "column_summary": {
                "h20_prob_up": {"max_abs_delta": 0.01},
                "confidence": {"max_abs_delta": 0.02},
            }
        },
    )
    manifest = _write_json(tmp_path / "manifest.json", {"status": "valid_shadow_baseline"})
    remediation = _write_json(
        tmp_path / "remediation.json",
        {"unresolved_actions": ["quantify_external_feature_sensitivity"]},
    )
    observation_log = _write_json(
        tmp_path / "observation_log.json",
        {
            "summary": {
                "valid_observation_count": 3,
                "stable_observation_count": 3,
                "latest_trigger_critical_exceeded": [],
            }
        },
    )

    report = build_report(
        sensitivity_audit=sensitivity,
        same_method_baseline_manifest=manifest,
        remediation_plan=remediation,
        observation_log=observation_log,
    )

    assert report["status"] == "recorded_no_trigger_blocker"
    assert report["governance"]["remaining_observation_sessions"] == 0
    assert report["governance"]["remaining_stable_observation_sessions"] == 0
    assert report["governance"]["resolution_allowed"] is True
    assert report["permissions"]["external_sensitivity_blocker_resolved"] is True
    assert report["permissions"]["promotion_allowed"] is False
