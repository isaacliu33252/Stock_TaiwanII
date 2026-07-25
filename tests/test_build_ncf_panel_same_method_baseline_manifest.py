from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_ncf_panel_same_method_baseline_manifest import build_manifest


def _write(path: Path, payload: str = "x") -> Path:
    path.write_text(payload, encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_same_method_baseline_manifest_validates_shadow_only_baseline(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.csv")
    same_panel = _write(tmp_path / "same.csv")
    same_signal = _write_json(tmp_path / "same.json", {"ticker": "00631L.TW"})
    validation = _write_json(
        tmp_path / "validation.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.06, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.07, "max_abs_delta_date": "2025-01-03"},
                "confidence": {"max_abs_delta": 0.13, "max_abs_delta_date": "2025-01-06"},
            }
        },
    )
    isolation = _write_json(
        tmp_path / "isolation.json",
        {
            "conclusion": {
                "same_method_no_tabnet_passes_configured_limits": True,
            }
        },
    )

    manifest = build_manifest(
        original_baseline_panel=original,
        same_method_baseline_panel=same_panel,
        same_method_baseline_signal=same_signal,
        validation_drift_audit=validation,
        isolation_report=isolation,
    )

    assert manifest["status"] == "valid_shadow_baseline"
    assert manifest["checks"]["same_method_validation_passes_limits"] is True
    assert manifest["checks"]["model_set_isolation_passed"] is True
    assert manifest["permissions"]["use_for_shadow_drift_comparison"] is True
    assert manifest["permissions"]["use_for_promotion_gate_baseline"] is False
    assert manifest["permissions"]["promotion_allowed"] is False
    assert manifest["permissions"]["training_allowed"] is False
    assert manifest["permissions"]["target_weight_change_allowed"] is False
    assert manifest["permissions"]["keep_golden1_0531_unchanged"] is True
