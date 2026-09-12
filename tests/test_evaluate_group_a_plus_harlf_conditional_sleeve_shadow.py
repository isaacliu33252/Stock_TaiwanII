from __future__ import annotations

from scripts.evaluate.evaluate_group_a_plus_harlf_conditional_sleeve_shadow import build_conditional_sleeve_shadow


def test_conditional_sleeve_shadow_rejects_when_gate_disables_all_harlf() -> None:
    comparison = {
        "monthly_returns": [
            {"month": "2026-01", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-02", "harlf_compound": -0.04, "latest_strategy": -0.02, "golden01_0531": -0.02},
            {"month": "2026-03", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-04", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-05", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
        ]
    }

    report = build_conditional_sleeve_shadow(comparison=comparison, warmup_months=3)

    assert report["status"] == "available"
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["candidate_ready_for_latest_strategy_review"] is False
    assert report["nonzero_harlf_months"] == 0


def test_conditional_sleeve_shadow_can_identify_review_candidate_when_gate_passes() -> None:
    comparison = {
        "monthly_returns": [
            {"month": "2026-01", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-02", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-03", "harlf_compound": 0.02, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-04", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
            {"month": "2026-05", "harlf_compound": 0.03, "latest_strategy": 0.01, "golden01_0531": 0.01},
        ]
    }

    report = build_conditional_sleeve_shadow(comparison=comparison, warmup_months=3)

    assert report["nonzero_harlf_months"] > 0
    assert report["decision"]["candidate_ready_for_latest_strategy_review"] is True


def test_conditional_sleeve_shadow_blocks_missing_inputs() -> None:
    report = build_conditional_sleeve_shadow(comparison={})

    assert report["status"] == "blocked"
    assert "missing_comparison_monthly_returns" in report["blocking_reasons"]
    assert report["decision"]["promotion_ready"] is False
