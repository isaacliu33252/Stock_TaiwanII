from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_ncf_2330_fp32_baseline_for_ptq import build_baseline
from scripts.evaluate.build_group_a_plus_ptq_calibration_readiness_review import build_review


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_ncf_2330_baseline_records_original_pipeline_not_torch_ptq(tmp_path: Path) -> None:
    ncf_json = _write_json(
        tmp_path / "ncf_2330.json",
        {
            "last_close_date": "2026-08-20",
            "data_freshness": {
                "status": "degraded_missing",
                "lag_days_vs_reference": {"external_market_ohlcv": 2},
                "missing_sources": ["ohlcv"],
            },
            "horizons": {
                "1": {"classification": {"val_auc": 0.70, "ensemble_val_brier": 0.21}},
                "5": {"classification": {"val_auc": 0.60, "ensemble_val_brier": 0.24}},
                "20": {"classification": {"val_auc": 0.65, "ensemble_val_brier": 0.22}},
            },
        },
    )
    panel = tmp_path / "ncf_2330_panel.csv"
    panel.write_text("date,prob_up_h1\n2026-08-20,0.5\n", encoding="utf-8")

    baseline = build_baseline(as_of="2026-08-21", ncf_json_path=ncf_json, ncf_panel_path=panel)

    assert baseline["model_name"] == "ncf_2330"
    assert baseline["full_precision_metric"] == 0.65
    assert baseline["quantization_applicability"]["torch_ptq_applicable"] is False
    assert baseline["decision"]["fp32_or_original_baseline_available"] is True
    assert baseline["decision"]["target_weight_change_allowed"] is False


def test_ptq_gate_blocks_ncf_2330_original_pipeline_baseline(tmp_path: Path) -> None:
    ptq_eval = _write_json(
        tmp_path / "ptq_eval.json",
        {
            "model_name": "ncf_2330",
            "model_framework": "sklearn_lightgbm_xgboost_catboost_ensemble",
            "model_artifact_type": "scripted_original_pipeline_no_torch_checkpoint",
            "quantization_applicability": {"torch_ptq_applicable": False},
            "full_precision_metric": 0.65,
            "calibration_period": "train_start_to_validation_start_from_ncf_2330_runtime",
            "test_period": "2026-08-20_latest_output_snapshot",
            "activation_calibration_method": "not_applicable_non_torch_original_pipeline",
            "out_of_envelope_rate": 0.0,
            "fallback_precision": "original_pipeline",
            "quantized_results": {},
        },
    )

    review = build_review(as_of="2026-08-21", pdf_path=tmp_path / "paper.pdf", ptq_eval_path=ptq_eval)

    assert review["status"] == "blocked"
    assert review["decision"]["quantized_inference_allowed"] is False
    assert review["ptq_eval_summary"]["torch_ptq_applicable"] is False
    assert "torch_ptq_not_applicable_for_current_model_framework" in review["blocking_reasons"]
    assert "missing_W8A8_result" in review["blocking_reasons"]
