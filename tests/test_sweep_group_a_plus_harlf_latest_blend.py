from __future__ import annotations

from scripts.evaluate.sweep_group_a_plus_harlf_latest_blend import build_blend_sweep


def test_harlf_latest_blend_finds_small_viable_sleeve_without_live_changes() -> None:
    comparison = {
        "monthly_returns": [
            {"month": "2026-01", "harlf_compound": 0.10, "latest_strategy": 0.02, "golden01_0531": 0.02},
            {"month": "2026-02", "harlf_compound": -0.015, "latest_strategy": -0.02, "golden01_0531": -0.02},
            {"month": "2026-03", "harlf_compound": 0.10, "latest_strategy": 0.02, "golden01_0531": 0.02},
        ]
    }

    report = build_blend_sweep(comparison=comparison, step=0.05)

    assert report["status"] == "available"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["found_blend_ready_for_latest_strategy_review"] is True


def test_harlf_latest_blend_blocks_without_monthly_returns() -> None:
    report = build_blend_sweep(comparison={})

    assert report["status"] == "blocked"
    assert "missing_comparison_monthly_returns" in report["blocking_reasons"]
