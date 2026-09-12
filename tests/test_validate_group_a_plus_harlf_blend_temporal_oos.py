from __future__ import annotations

from scripts.evaluate.validate_group_a_plus_harlf_blend_temporal_oos import build_temporal_oos_validation


def test_temporal_oos_validation_passes_when_train_selects_and_holdout_beats_latest() -> None:
    comparison = {
        "monthly_returns": [
            {"month": "2026-01", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-02", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-03", "harlf_compound": 0.04, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-04", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-05", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
        ]
    }

    report = build_temporal_oos_validation(comparison=comparison, holdout_months=2)

    assert report["status"] == "available"
    assert report["decision"]["oos_window_available"] is True
    assert report["decision"]["temporal_oos_passed"] is True
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["train_best_viable_blend"]["harlf_weight"] > 0


def test_temporal_oos_validation_blocks_when_no_train_viable_blend() -> None:
    comparison = {
        "monthly_returns": [
            {"month": "2026-01", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-02", "harlf_compound": -0.04, "latest_strategy": -0.02, "golden01_0531": -0.02},
            {"month": "2026-03", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-04", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
        ]
    }

    report = build_temporal_oos_validation(comparison=comparison, holdout_months=1)

    assert report["status"] == "blocked"
    assert "no_train_viable_harlf_blend_under_drawdown_constraint" in report["blocking_reasons"]
    assert report["decision"]["oos_window_available"] is True
    assert report["decision"]["temporal_oos_passed"] is False
    assert report["decision"]["promotion_ready"] is False
