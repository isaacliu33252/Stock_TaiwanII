from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_ncf_panel_drift_diagnosis import build_diagnosis


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_diagnosis_marks_trigger_critical_drift_and_keeps_permissions_off(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.60, "confidence": 0.20, "ensemble_prob_up": 0.55},
            {"date": "2025-01-03", "h20_prob_up": 0.70, "confidence": 0.30, "ensemble_prob_up": 0.56},
        ]
    ).to_csv(baseline, index=False)
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.64, "confidence": 0.22, "ensemble_prob_up": 0.58},
            {"date": "2025-01-03", "h20_prob_up": 0.40, "confidence": 0.75, "ensemble_prob_up": 0.57},
        ]
    ).to_csv(candidate, index=False)
    audit = _write_json(
        tmp_path / "drift.json",
        {
            "baseline_panel": str(baseline),
            "candidate_panel": str(candidate),
            "overlap_start": "2025-01-02",
            "overlap_end": "2025-01-03",
            "overlap_rows": 2,
            "column_summary": {
                "h20_prob_up": {
                    "mean_abs_delta": 0.17,
                    "median_abs_delta": 0.17,
                    "max_abs_delta": 0.30,
                    "max_abs_delta_date": "2025-01-03",
                    "signed_delta_at_max_abs": -0.30,
                },
                "confidence": {
                    "mean_abs_delta": 0.235,
                    "median_abs_delta": 0.235,
                    "max_abs_delta": 0.45,
                    "max_abs_delta_date": "2025-01-03",
                    "signed_delta_at_max_abs": 0.45,
                },
                "ensemble_prob_up": {
                    "mean_abs_delta": 0.02,
                    "median_abs_delta": 0.02,
                    "max_abs_delta": 0.03,
                    "max_abs_delta_date": "2025-01-02",
                    "signed_delta_at_max_abs": 0.03,
                },
            },
        },
    )
    baseline_signal = _write_json(
        tmp_path / "baseline_signal.json",
        {
            "last_close_date": "2025-01-03",
            "data_freshness": {"status": "ok", "stale_sources": []},
            "external_features": True,
            "feature_selection": False,
            "horizons": {
                "20": {
                    "classification": {
                        "model_probabilities": {"rf": 0.4, "tabnet": 0.8},
                        "best_model": "tabnet",
                        "val_auc": 0.7,
                    }
                }
            },
        },
    )
    candidate_signal = _write_json(
        tmp_path / "candidate_signal.json",
        {
            "last_close_date": "2025-01-04",
            "data_freshness": {"status": "degraded_stale", "stale_sources": ["external_market_ohlcv"]},
            "external_features": True,
            "feature_selection": False,
            "horizons": {
                "20": {
                    "classification": {
                        "model_probabilities": {"rf": 0.4, "stable_rf": 0.6},
                        "best_model": "stable_rf",
                        "val_auc": 0.8,
                    }
                }
            },
        },
    )
    sensitivity = _write_json(
        tmp_path / "sensitivity.json",
        {
            "column_summary": {
                "confidence": {
                    "max_abs_delta": 0.60,
                    "max_abs_delta_date": "2025-01-02",
                }
            }
        },
    )

    report = build_diagnosis(
        audit,
        baseline_signal=baseline_signal,
        candidate_signal=candidate_signal,
        sensitivity_audit=sensitivity,
    )

    assert report["status"] == "blocked"
    assert report["exceeded_columns"] == ["h20_prob_up", "confidence"]
    assert report["trigger_critical_exceeded"] == ["h20_prob_up", "confidence"]
    assert report["historical_verification_bound_exceeded"] == ["h20_prob_up", "confidence"]
    assert report["columns"]["h20_prob_up"]["baseline_value_at_max"] == 0.70
    assert report["columns"]["h20_prob_up"]["candidate_value_at_max"] == 0.40
    assert report["columns"]["h20_prob_up"]["signed_delta_at_max"] == -0.29999999999999993
    assert report["columns"]["h20_prob_up"]["historical_verification_bound"] == 0.13
    assert report["columns"]["h20_prob_up"]["exceeds_historical_verification_bound"] is True
    assert report["columns"]["confidence"]["tier"] == "trigger_critical"
    assert report["columns"]["ensemble_prob_up"]["exceeds_limit"] is False
    assert report["columns"]["ensemble_prob_up"]["historical_verification_bound"] is None
    assert report["interpretation"]["promotion_allowed"] is False
    assert report["interpretation"]["training_allowed"] is False
    assert report["interpretation"]["target_weight_change_allowed"] is False
    assert report["root_cause_follow_up"]["status"] == "unresolved_requires_diagnosis"
    assert report["root_cause_follow_up"]["exceeded_columns"] == ["h20_prob_up", "confidence"]
    assert "same_method_baseline_vs_candidate" in report["root_cause_follow_up"]["required_checks"]
    source = report["source_diagnosis"]
    assert source["panel_methods"]["baseline_has_horizon_ensemble_method"] is False
    assert source["model_sets"]["status"] == "changed"
    assert source["model_sets"]["by_horizon"]["20"]["removed_models"] == ["tabnet"]
    assert source["model_sets"]["by_horizon"]["20"]["added_models"] == ["stable_rf"]
    assert source["run_context"]["baseline_data_freshness_status"] == "ok"
    assert source["run_context"]["candidate_data_freshness_status"] == "degraded_stale"
    assert source["run_context"]["candidate_stale_sources"] == ["external_market_ohlcv"]
    assert source["sensitivity_audit"]["status"] == "available"
    assert source["sensitivity_audit"]["column_summary"]["confidence"]["max_abs_delta"] == 0.60
    contract = source["artifact_contract"]
    assert contract["status"] == "available"
    assert contract["paired_external_no_external"]["candidate_pair_available"] is False
    assert contract["paired_external_no_external"]["baseline_pair_available"] is False
    assert contract["paired_external_no_external"]["full_attribution_required"] is True
    assert contract["paired_external_no_external"]["full_attribution_possible"] is False
    assert "baseline no-external pair is missing" in contract["paired_external_no_external"]["reason"]


def test_build_diagnosis_marks_historical_bound_even_when_configured_limit_passes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.60, "confidence": 0.20},
            {"date": "2025-01-03", "h20_prob_up": 0.70, "confidence": 0.30},
        ]
    ).to_csv(baseline, index=False)
    pd.DataFrame(
        [
            {"date": "2025-01-02", "h20_prob_up": 0.61, "confidence": 0.21},
            {"date": "2025-01-03", "h20_prob_up": 0.56, "confidence": 0.44},
        ]
    ).to_csv(candidate, index=False)
    audit = _write_json(
        tmp_path / "drift.json",
        {
            "baseline_panel": str(baseline),
            "candidate_panel": str(candidate),
            "overlap_start": "2025-01-02",
            "overlap_end": "2025-01-03",
            "overlap_rows": 2,
            "column_summary": {
                "h20_prob_up": {
                    "mean_abs_delta": 0.075,
                    "median_abs_delta": 0.075,
                    "max_abs_delta": 0.14,
                    "max_abs_delta_date": "2025-01-03",
                },
                "confidence": {
                    "mean_abs_delta": 0.075,
                    "median_abs_delta": 0.075,
                    "max_abs_delta": 0.14,
                    "max_abs_delta_date": "2025-01-03",
                },
            },
        },
    )

    report = build_diagnosis(audit)

    assert report["status"] == "pass"
    assert report["exceeded_columns"] == []
    assert report["historical_verification_bound_exceeded"] == ["h20_prob_up", "confidence"]
    assert report["root_cause_follow_up"]["status"] == "unresolved_requires_diagnosis"


def test_build_diagnosis_reports_paired_artifact_contract(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    baseline_no_external = tmp_path / "baseline_no_external.csv"
    candidate_no_external = tmp_path / "candidate_no_external.csv"
    for path, value in (
        (baseline, 0.70),
        (candidate, 0.40),
        (baseline_no_external, 0.68),
        (candidate_no_external, 0.45),
    ):
        pd.DataFrame([{"date": "2025-01-03", "h20_prob_up": value, "confidence": 0.20}]).to_csv(path, index=False)
    sensitivity = _write_json(
        tmp_path / "sensitivity.json",
        {"column_summary": {"h20_prob_up": {"max_abs_delta": 0.23, "max_abs_delta_date": "2025-01-03"}}},
    )
    audit = _write_json(
        tmp_path / "drift.json",
        {
            "baseline_panel": str(baseline),
            "candidate_panel": str(candidate),
            "overlap_rows": 1,
            "column_summary": {
                "h20_prob_up": {
                    "max_abs_delta": 0.30,
                    "max_abs_delta_date": "2025-01-03",
                }
            },
        },
    )

    report = build_diagnosis(
        audit,
        baseline_no_external_panel=baseline_no_external,
        candidate_no_external_panel=candidate_no_external,
        sensitivity_audit=sensitivity,
    )

    contract = report["source_diagnosis"]["artifact_contract"]
    assert contract["status"] == "available"
    assert contract["missing_provided_artifacts"] == []
    assert contract["artifacts"]["baseline_no_external_panel"]["exists"] is True
    assert contract["artifacts"]["candidate_no_external_panel"]["exists"] is True
    assert contract["paired_external_no_external"]["candidate_pair_available"] is True
    assert contract["paired_external_no_external"]["baseline_pair_available"] is True
    assert contract["paired_external_no_external"]["sensitivity_audit_available"] is True
    assert contract["paired_external_no_external"]["full_attribution_possible"] is True


def test_build_diagnosis_reports_missing_provided_artifacts(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    pd.DataFrame([{"date": "2025-01-03", "h20_prob_up": 0.70}]).to_csv(baseline, index=False)
    pd.DataFrame([{"date": "2025-01-03", "h20_prob_up": 0.40}]).to_csv(candidate, index=False)
    audit = _write_json(
        tmp_path / "drift.json",
        {
            "baseline_panel": str(baseline),
            "candidate_panel": str(candidate),
            "overlap_rows": 1,
            "column_summary": {
                "h20_prob_up": {
                    "max_abs_delta": 0.30,
                    "max_abs_delta_date": "2025-01-03",
                }
            },
        },
    )

    report = build_diagnosis(
        audit,
        candidate_no_external_panel=tmp_path / "missing_candidate_no_external.csv",
    )

    contract = report["source_diagnosis"]["artifact_contract"]
    assert contract["status"] == "missing_provided_artifacts"
    assert contract["missing_provided_artifacts"] == ["candidate_no_external_panel"]
    assert contract["paired_external_no_external"]["candidate_pair_available"] is False
