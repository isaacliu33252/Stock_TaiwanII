from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_ncf_panel_drift_remediation_plan import build_plan


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_plan_prioritizes_required_drift_remediation_actions(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "exceeded_columns": ["ensemble_prob_up", "h20_prob_up", "confidence"],
            "trigger_critical_exceeded": ["h20_prob_up", "confidence"],
            "source_diagnosis": {
                "panel_methods": {
                    "baseline_has_horizon_ensemble_method": False,
                    "candidate_has_horizon_ensemble_method": True,
                    "candidate_horizon_ensemble_methods": {"expanding_prior_auc_min60": 374},
                },
                "model_sets": {
                    "status": "changed",
                    "by_horizon": {
                        "1": {"removed_models": ["tabnet"], "added_models": []},
                        "5": {"removed_models": ["tabnet"], "added_models": []},
                        "20": {"removed_models": ["tabnet"], "added_models": ["stable_rf"]},
                    },
                },
                "run_context": {
                    "candidate_stale_sources": ["taifex_futures", "external_market_ohlcv"],
                },
                "sensitivity_audit": {
                    "status": "available",
                    "column_summary": {
                        "h20_prob_up": {"max_abs_delta": 0.51},
                        "confidence": {"max_abs_delta": 0.63},
                    },
                },
            },
        },
    )

    report = build_plan(diagnosis)

    assert report["status"] == "blocked"
    assert report["unresolved_actions"] == [
        "refresh_stale_candidate_sources",
        "isolate_model_set_change",
        "rebuild_same_method_baseline",
        "quantify_external_feature_sensitivity",
    ]
    assert report["actions"][0]["stale_sources"] == ["taifex_futures", "external_market_ohlcv"]
    assert report["actions"][1]["removed_models"] == ["tabnet"]
    assert report["actions"][1]["added_models"] == ["stable_rf"]
    assert report["permissions"]["promotion_allowed"] is False
    assert report["permissions"]["training_allowed"] is False
    assert report["permissions"]["target_weight_change_allowed"] is False
    assert report["permissions"]["keep_golden1_0531_unchanged"] is True


def test_build_plan_reduces_model_set_action_when_isolation_report_resolves_it(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "source_diagnosis": {
                "panel_methods": {
                    "baseline_has_horizon_ensemble_method": False,
                    "candidate_has_horizon_ensemble_method": True,
                },
                "model_sets": {
                    "status": "changed",
                    "by_horizon": {
                        "1": {"removed_models": ["tabnet"], "added_models": []},
                    },
                },
                "run_context": {"candidate_stale_sources": []},
                "sensitivity_audit": {"status": "not_provided", "column_summary": {}},
            },
        },
    )
    isolation = _write_json(
        tmp_path / "isolation.json",
        {
            "status": "model_set_mismatch_isolated",
            "conclusion": {
                "model_set_or_baseline_method_mismatch_explains_primary_blocker": True,
            },
        },
    )

    report = build_plan(diagnosis, isolation_report_path=isolation)

    model_action = next(action for action in report["actions"] if action["id"] == "isolate_model_set_change")
    assert model_action["status"] == "resolved"
    assert "isolate_model_set_change" not in report["unresolved_actions"]
    assert "rebuild_same_method_baseline" in report["unresolved_actions"]


def test_build_plan_reduces_same_method_baseline_action_when_manifest_is_valid(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "source_diagnosis": {
                "panel_methods": {
                    "baseline_has_horizon_ensemble_method": False,
                    "candidate_has_horizon_ensemble_method": True,
                },
                "model_sets": {"status": "same", "by_horizon": {}},
                "run_context": {"candidate_stale_sources": []},
                "sensitivity_audit": {
                    "status": "available",
                    "column_summary": {"confidence": {"max_abs_delta": 0.63}},
                },
            },
        },
    )
    manifest = _write_json(
        tmp_path / "manifest.json",
        {
            "status": "valid_shadow_baseline",
            "permissions": {
                "use_for_shadow_drift_comparison": True,
                "use_for_promotion_gate_baseline": False,
            },
        },
    )

    report = build_plan(diagnosis, same_method_baseline_manifest_path=manifest)

    baseline_action = next(action for action in report["actions"] if action["id"] == "rebuild_same_method_baseline")
    assert baseline_action["status"] == "resolved"
    assert "rebuild_same_method_baseline" not in report["unresolved_actions"]
    assert "quantify_external_feature_sensitivity" in report["unresolved_actions"]
    assert report["permissions"]["promotion_allowed"] is False


def test_build_plan_records_external_sensitivity_governance_without_resolving_blocker(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "source_diagnosis": {
                "panel_methods": {
                    "baseline_has_horizon_ensemble_method": True,
                    "candidate_has_horizon_ensemble_method": True,
                },
                "model_sets": {"status": "same", "by_horizon": {}},
                "run_context": {"candidate_stale_sources": []},
                "sensitivity_audit": {
                    "status": "available",
                    "column_summary": {
                        "h20_prob_up": {"max_abs_delta": 0.51},
                        "confidence": {"max_abs_delta": 0.63},
                    },
                },
            },
        },
    )
    governance = _write_json(
        tmp_path / "governance.json",
        {
            "status": "blocked_observation_required",
            "governance": {"resolution_allowed": False},
        },
    )

    report = build_plan(diagnosis, external_sensitivity_governance_path=governance)

    action = next(action for action in report["actions"] if action["id"] == "quantify_external_feature_sensitivity")
    assert action["status"] == "required"
    assert action["governance_status"] == "blocked_observation_required"
    assert action["governance_resolution_allowed"] is False
    assert "quantify_external_feature_sensitivity" in report["unresolved_actions"]
