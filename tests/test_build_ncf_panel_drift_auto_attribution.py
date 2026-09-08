from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_ncf_panel_drift_auto_attribution import build_report, write_outputs


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_auto_attribution_prioritizes_data_freshness_blocker(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "overlap_rows": 10,
            "exceeded_columns": ["h20_prob_up"],
            "trigger_critical_exceeded": ["h20_prob_up"],
            "columns": {"h20_prob_up": {"max_abs_delta": 0.4}},
        },
    )
    remediation = _write_json(tmp_path / "remediation.json", {"actions": []})
    freshness = _write_json(
        tmp_path / "freshness.json",
        {
            "status": "blocked",
            "blockers": ["latest_strategy_explain_target_weight_window_lags_live_signal"],
            "warnings": ["ohlcv_freshness_target_date_mismatch"],
            "summary": {
                "live_signal_actual_data_date": "2026-09-07",
                "ohlcv_target_date": "2026-09-04",
                "latest_strategy_target_weight_window_end": "2026-08-07",
            },
        },
    )

    report = build_report(
        diagnosis_path=diagnosis,
        remediation_plan_path=remediation,
        data_freshness_gate_path=freshness,
        external_sensitivity_governance_path=None,
        panel_manifest_path=None,
        as_of="2026-09-08",
    )

    assert report["status"] == "blocked"
    assert report["primary_attribution"] == "data_or_artifact_freshness"
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["keep_golden2_0830_unchanged"] is True


def test_auto_attribution_records_external_feature_sensitivity(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "blocked",
            "overlap_rows": 10,
            "exceeded_columns": ["confidence"],
            "trigger_critical_exceeded": ["confidence"],
            "columns": {"confidence": {"max_abs_delta": 0.63}},
        },
    )
    remediation = _write_json(
        tmp_path / "remediation.json",
        {
            "actions": [
                {
                    "id": "quantify_external_feature_sensitivity",
                    "status": "required",
                    "reason": "external-feature sensitivity exceeds trigger-critical drift tolerance",
                    "max_trigger_critical_sensitivity": 0.63,
                    "governance_status": "blocked_observation_required",
                }
            ]
        },
    )
    governance = _write_json(
        tmp_path / "governance.json",
        {
            "status": "blocked_observation_required",
            "governance": {"reason": "need more stable observations", "resolution_allowed": False},
        },
    )
    freshness = _write_json(tmp_path / "freshness.json", {"status": "pass", "blockers": [], "warnings": []})

    report = build_report(
        diagnosis_path=diagnosis,
        remediation_plan_path=remediation,
        data_freshness_gate_path=freshness,
        external_sensitivity_governance_path=governance,
        panel_manifest_path=None,
    )

    causes = [row["cause"] for row in report["attributions"]]
    assert "external_feature_sensitivity" in causes
    assert "external_feature_governance_block" in causes
    assert report["status"] == "blocked"


def test_auto_attribution_passes_when_no_material_drift(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "pass",
            "exceeded_columns": [],
            "trigger_critical_exceeded": [],
            "columns": {"h20_prob_up": {"max_abs_delta": 0.0}},
        },
    )
    remediation = _write_json(tmp_path / "remediation.json", {"actions": []})
    freshness = _write_json(tmp_path / "freshness.json", {"status": "pass", "blockers": [], "warnings": []})
    manifest = _write_json(
        tmp_path / "manifest.json",
        {"panels": [{"path": "a.csv", "exists": True, "date_end": "2026-09-04"}]},
    )

    report = build_report(
        diagnosis_path=diagnosis,
        remediation_plan_path=remediation,
        data_freshness_gate_path=freshness,
        external_sensitivity_governance_path=None,
        panel_manifest_path=manifest,
    )

    assert report["status"] == "pass"
    assert report["primary_attribution"] == "no_material_drift"


def test_auto_attribution_blocks_when_diagnosis_missing(tmp_path: Path) -> None:
    remediation = _write_json(tmp_path / "remediation.json", {"actions": []})
    freshness = _write_json(tmp_path / "freshness.json", {"status": "pass", "blockers": [], "warnings": []})

    report = build_report(
        diagnosis_path=tmp_path / "missing.json",
        remediation_plan_path=remediation,
        data_freshness_gate_path=freshness,
        external_sensitivity_governance_path=None,
        panel_manifest_path=None,
    )

    assert report["status"] == "blocked"
    assert report["primary_attribution"] == "panel_drift_diagnosis_missing"


def test_auto_attribution_flags_model_set_or_retrain_change(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "pass",
            "exceeded_columns": [],
            "trigger_critical_exceeded": [],
            "columns": {"h20_prob_up": {"max_abs_delta": 0.03}},
            "source_diagnosis": {
                "model_sets": {
                    "status": "changed",
                    "by_horizon": {
                        "20": {
                            "removed_models": ["tabnet"],
                            "added_models": [],
                            "baseline_val_auc": 0.62,
                            "candidate_val_auc": 0.58,
                        }
                    },
                }
            },
        },
    )
    remediation = _write_json(tmp_path / "remediation.json", {"actions": []})
    freshness = _write_json(tmp_path / "freshness.json", {"status": "pass", "blockers": [], "warnings": []})

    report = build_report(
        diagnosis_path=diagnosis,
        remediation_plan_path=remediation,
        data_freshness_gate_path=freshness,
        external_sensitivity_governance_path=None,
        panel_manifest_path=None,
    )

    causes = [row["cause"] for row in report["attributions"]]
    assert "model_set_or_retrain_change" in causes
    assert report["status"] == "warning"
    assert report["primary_attribution"] == "model_set_or_retrain_change"


def test_auto_attribution_flags_ensemble_weight_reallocation(tmp_path: Path) -> None:
    diagnosis = _write_json(
        tmp_path / "diagnosis.json",
        {
            "status": "pass",
            "exceeded_columns": [],
            "trigger_critical_exceeded": [],
            "columns": {
                "h20_prob_up": {"max_abs_delta": 0.02},
                "ensemble_weight_h20": {"max_abs_delta": 0.31, "max_abs_delta_date": "2026-09-03"},
            },
            "source_diagnosis": {
                "panel_methods": {
                    "baseline_has_ensemble_weights": True,
                    "candidate_has_ensemble_weights": True,
                }
            },
        },
    )
    remediation = _write_json(tmp_path / "remediation.json", {"actions": []})
    freshness = _write_json(tmp_path / "freshness.json", {"status": "pass", "blockers": [], "warnings": []})

    report = build_report(
        diagnosis_path=diagnosis,
        remediation_plan_path=remediation,
        data_freshness_gate_path=freshness,
        external_sensitivity_governance_path=None,
        panel_manifest_path=None,
    )

    causes = [row["cause"] for row in report["attributions"]]
    assert "ensemble_weight_reallocation" in causes
    assert report["status"] == "warning"


def test_write_outputs_writes_json_and_markdown(tmp_path: Path) -> None:
    report = {
        "status": "pass",
        "primary_attribution": "no_material_drift",
        "policy": "diagnostic_only_no_model_change_no_weight_change",
        "attributions": [{"cause": "no_material_drift", "severity": "info", "evidence": [], "recommended_check": "none"}],
        "decision": {
            "creates_orders": False,
            "promotion_allowed": False,
            "training_allowed": False,
            "target_weight_change_allowed": False,
            "keep_golden1_0531_unchanged": True,
            "keep_golden2_0830_unchanged": True,
        },
    }
    output = tmp_path / "latest/auto.json"
    output_md = tmp_path / "latest/auto.md"

    write_outputs(report, output=output, output_md=output_md)

    assert json.loads(output.read_text(encoding="utf-8"))["primary_attribution"] == "no_material_drift"
    assert "NCF Panel Drift Auto Attribution" in output_md.read_text(encoding="utf-8")
