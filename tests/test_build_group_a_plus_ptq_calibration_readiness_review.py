from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_ptq_calibration_readiness_review import build_review


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_ptq_readiness_blocks_without_eval_file(tmp_path: Path) -> None:
    review = build_review(
        as_of="2026-08-21",
        pdf_path=tmp_path / "2608.12259.pdf",
        ptq_eval_path=tmp_path / "missing_eval.json",
    )

    assert review["status"] == "blocked"
    assert review["decision"]["quantized_inference_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "missing_ptq_calibration_eval" in review["blocking_reasons"]
    assert "no_quantized_precision_passed_readiness_gate" in review["blocking_reasons"]


def test_ptq_readiness_requires_w4a4_percentile_and_layerwise_review(tmp_path: Path) -> None:
    pdf = tmp_path / "2608.12259.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    eval_path = _write_json(
        tmp_path / "ptq_eval.json",
        {
            "model_name": "ncf_2330_shadow",
            "full_precision_metric": 0.10,
            "calibration_period": "2024-01-01:2024-12-31",
            "test_period": "2025-01-01:2025-12-31",
            "activation_calibration_method": "percentile_p99",
            "fallback_precision": "W8A8",
            "out_of_envelope_rate": 0.03,
            "quantized_results": {
                "W8A8": {"metric": 0.099},
                "W4_weight_only": {"metric": 0.097},
                "W4A4": {
                    "metric": 0.096,
                    "percentile_sweep_tested": False,
                    "layerwise_exception_reviewed": False,
                },
            },
        },
    )

    review = build_review(as_of="2026-08-21", pdf_path=pdf, ptq_eval_path=eval_path)

    assert review["status"] == "blocked"
    assert review["precision_checks"]["W8A8"]["status"] == "passed"
    assert review["precision_checks"]["W4_weight_only"]["status"] == "passed"
    assert review["precision_checks"]["W4A4"]["status"] == "blocked"
    assert review["decision"]["quantized_inference_allowed"] is False
    assert review["decision"]["promotable_precisions_for_research_review"] == ["W8A8", "W4_weight_only"]
    assert "W4A4_missing_percentile_sweep" in review["blocking_reasons"]
    assert "W4A4_missing_layerwise_exception_review" in review["blocking_reasons"]
