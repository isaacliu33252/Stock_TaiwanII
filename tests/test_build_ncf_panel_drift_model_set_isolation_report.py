from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_ncf_panel_drift_model_set_isolation_report import build_report


def _write_audit(path: Path, *, ensemble: float, h20: float, confidence: float) -> Path:
    path.write_text(
        json.dumps(
            {
                "column_summary": {
                    "ensemble_prob_up": {"max_abs_delta": ensemble, "max_abs_delta_date": "2025-01-02"},
                    "h20_prob_up": {"max_abs_delta": h20, "max_abs_delta_date": "2025-01-03"},
                    "confidence": {"max_abs_delta": confidence, "max_abs_delta_date": "2025-01-06"},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_model_set_isolation_marks_primary_blocker_when_same_method_passes(tmp_path: Path) -> None:
    original_today = _write_audit(tmp_path / "original_today.json", ensemble=0.24, h20=0.26, confidence=0.49)
    original_no_tabnet = _write_audit(
        tmp_path / "original_no_tabnet.json", ensemble=0.24, h20=0.26, confidence=0.49
    )
    no_tabnet_today = _write_audit(tmp_path / "no_tabnet_today.json", ensemble=0.06, h20=0.07, confidence=0.13)

    report = build_report(
        original_vs_today=original_today,
        original_vs_no_tabnet=original_no_tabnet,
        no_tabnet_vs_today=no_tabnet_today,
    )

    assert report["status"] == "model_set_mismatch_isolated"
    assert report["focused_columns"]["no_tabnet_vs_today"]["confidence"]["passes_limit"] is True
    assert report["conclusion"]["same_method_no_tabnet_passes_configured_limits"] is True
    assert report["conclusion"]["model_set_or_baseline_method_mismatch_explains_primary_blocker"] is True
    assert report["conclusion"]["promotion_allowed"] is False
    assert report["conclusion"]["training_allowed"] is False
    assert report["conclusion"]["target_weight_change_allowed"] is False
