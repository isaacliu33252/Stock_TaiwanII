from __future__ import annotations

from scripts.evaluate.evaluate_group_a_plus_harlf_meta_agent_shadow import build_meta_agent_shadow


def test_harlf_meta_agent_uses_trailing_branch_scores_without_live_changes() -> None:
    rows = []
    for idx in range(1, 10):
        month = f"2026-{idx:02d}"
        rows.extend(
            [
                {"month": month, "branch": "equal_weight", "net_return": 0.01, "turnover_cost": 0.0},
                {"month": month, "branch": "market_only", "net_return": 0.02, "turnover_cost": 0.0},
                {"month": month, "branch": "sentiment_only", "net_return": 0.03, "turnover_cost": 0.0},
                {"month": month, "branch": "combined", "net_return": 0.025, "turnover_cost": 0.0},
            ]
        )
    report = build_meta_agent_shadow(
        branch_report={"report_type": "group_a_plus_harlf_branch_ablation_shadow", "branch_returns": rows},
        warmup_months=3,
        lookback_months=3,
    )

    assert report["status"] == "available"
    assert report["decision"]["hierarchical_meta_agent_oos_backtest_available"] is True
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_golden01_0531"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["selected_branch_counts"]["sentiment_only"] == 6


def test_harlf_meta_agent_blocks_when_branch_returns_missing() -> None:
    report = build_meta_agent_shadow(branch_report={}, warmup_months=3, lookback_months=3)

    assert report["status"] == "blocked"
    assert "missing_branch_return_series" in report["blocking_reasons"]
    assert report["decision"]["hierarchical_meta_agent_oos_backtest_available"] is False


def test_harlf_meta_agent_can_apply_defensive_equal_weight_fallback() -> None:
    rows = []
    for idx in range(1, 8):
        month = f"2026-{idx:02d}"
        rows.extend(
            [
                {"month": month, "branch": "equal_weight", "net_return": 0.01, "turnover_cost": 0.0},
                {"month": month, "branch": "market_only", "net_return": 0.02, "turnover_cost": 0.0},
                {"month": month, "branch": "sentiment_only", "net_return": 0.03, "turnover_cost": 0.0},
                {"month": month, "branch": "combined", "net_return": 0.025, "turnover_cost": 0.0},
            ]
        )

    report = build_meta_agent_shadow(
        branch_report={"branch_returns": rows},
        warmup_months=3,
        lookback_months=3,
        defensive_sentiment_score_threshold=0.1,
    )

    assert report["decision"]["defensive_equal_weight_fallback_enabled"] is True
    assert report["monthly_decisions"][0]["selected_branch"] == "equal_weight"
    assert report["monthly_decisions"][0]["raw_selected_branch"] == "sentiment_only"
    assert report["monthly_decisions"][0]["defensive_fallback_applied"] is True


def test_harlf_meta_agent_can_apply_compound_weak_market_fallback() -> None:
    rows = []
    for idx in range(1, 8):
        month = f"2026-{idx:02d}"
        equal_return = -0.01 if idx == 4 else 0.01
        rows.extend(
            [
                {"month": month, "branch": "equal_weight", "net_return": equal_return, "turnover_cost": 0.0},
                {"month": month, "branch": "market_only", "net_return": 0.02, "turnover_cost": 0.0},
                {"month": month, "branch": "sentiment_only", "net_return": 0.03, "turnover_cost": 0.0},
                {"month": month, "branch": "combined", "net_return": 0.025, "turnover_cost": 0.0},
            ]
        )

    report = build_meta_agent_shadow(
        branch_report={"branch_returns": rows},
        warmup_months=3,
        lookback_months=3,
        defensive_sentiment_soft_threshold=0.1,
        defensive_prev_equal_weight_return_max=0.0,
    )

    fallback_rows = [row for row in report["monthly_decisions"] if row["defensive_fallback_applied"]]
    assert fallback_rows
    assert fallback_rows[0]["defensive_fallback_reason"] == "sentiment_soft_threshold_after_weak_equal_weight"
