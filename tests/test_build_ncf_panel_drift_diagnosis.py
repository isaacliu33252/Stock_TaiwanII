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
    assert report["columns"]["h20_prob_up"]["baseline_value_at_max"] == 0.70
    assert report["columns"]["h20_prob_up"]["candidate_value_at_max"] == 0.40
    assert report["columns"]["h20_prob_up"]["signed_delta_at_max"] == -0.29999999999999993
    assert report["columns"]["confidence"]["tier"] == "trigger_critical"
    assert report["columns"]["ensemble_prob_up"]["exceeds_limit"] is False
    assert report["interpretation"]["promotion_allowed"] is False
    assert report["interpretation"]["training_allowed"] is False
    assert report["interpretation"]["target_weight_change_allowed"] is False
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
