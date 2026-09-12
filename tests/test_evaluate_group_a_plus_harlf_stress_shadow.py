from __future__ import annotations

from scripts.evaluate.evaluate_group_a_plus_harlf_stress_shadow import build_stress_report


def test_harlf_stress_report_keeps_candidate_research_only() -> None:
    branch_rows = []
    meta_rows = []
    for idx in range(1, 8):
        month = f"2026-{idx:02d}"
        branch_rows.extend(
            [
                {"month": month, "branch": "equal_weight", "net_return": 0.01, "turnover_cost": 0.0},
                {"month": month, "branch": "combined", "net_return": 0.02, "turnover_cost": 0.001},
                {"month": month, "branch": "market_only", "net_return": 0.03, "turnover_cost": 0.001},
                {"month": month, "branch": "sentiment_only", "net_return": 0.04, "turnover_cost": 0.001},
            ]
        )
        meta_rows.append({"month": month, "selected_branch": "sentiment_only", "net_return": 0.04})
    branch_rows.append({"month": "2026-08", "branch": "equal_weight", "net_return": -0.05, "turnover_cost": 0.0})
    branch_rows.append({"month": "2026-08", "branch": "combined", "net_return": 0.01, "turnover_cost": 0.001})
    branch_rows.append({"month": "2026-08", "branch": "market_only", "net_return": 0.02, "turnover_cost": 0.001})
    branch_rows.append({"month": "2026-08", "branch": "sentiment_only", "net_return": 0.03, "turnover_cost": 0.001})
    meta_rows.append({"month": "2026-08", "selected_branch": "sentiment_only", "net_return": 0.03})

    report = build_stress_report(
        branch_report={"report_type": "branch", "branch_returns": branch_rows},
        meta_report={"report_type": "meta", "monthly_decisions": meta_rows},
    )

    assert report["status"] == "available"
    assert report["decision"]["stress_test_available"] is True
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["promotion_ready"] is False


def test_harlf_stress_report_blocks_when_inputs_missing() -> None:
    report = build_stress_report(branch_report={}, meta_report={})

    assert report["status"] == "blocked"
    assert "missing_branch_or_meta_monthly_returns" in report["blocking_reasons"]
    assert report["decision"]["stress_test_available"] is False
