from __future__ import annotations

from scripts.evaluate.build_group_a_plus_2608_15841_auxiliary_churn_shadow import build_report


def test_churn_shadow_blocks_negative_final_value_after_costs() -> None:
    report = build_report(
        {
            "window": {"start": "2025-01-02", "end": "2026-09-03"},
            "results": {
                "net_derisk": {
                    "initial_value": 1_000_000.0,
                    "delta_vs_baseline": {
                        "final_value": -100.0,
                        "sharpe_ratio": 0.2,
                        "max_drawdown": 0.01,
                    },
                    "simulation": {
                        "transaction_cost": 50.0,
                        "turnover_value": 100_000.0,
                        "rebalance_count": 3,
                    },
                    "score_behavior": {
                        "golden1_days_score_gt_0": 2,
                        "missed_upside_proxy_days": 1,
                    },
                }
            },
        }
    )

    assert report["summary"]["multi_window_cost_turnover_passed"] is False
    assert report["summary"]["promotion_allowed"] is False
    assert "negative_delta_final_value_after_costs" in report["summary"]["blockers"]
    assert report["variants"][0]["cost_turnover_pass"] is False


def test_churn_shadow_blocks_excessive_turnover_even_with_positive_deltas() -> None:
    report = build_report(
        {
            "results": {
                "downside_only": {
                    "initial_value": 1_000_000.0,
                    "delta_vs_baseline": {
                        "final_value": 10.0,
                        "sharpe_ratio": 0.1,
                        "max_drawdown": 0.01,
                    },
                    "simulation": {
                        "transaction_cost": 1000.0,
                        "turnover_value": 2_000_000.0,
                        "rebalance_count": 10,
                    },
                }
            },
        },
        max_turnover_to_initial=1.5,
    )

    assert report["summary"]["multi_window_cost_turnover_passed"] is False
    assert "turnover_above_limit" in report["summary"]["blockers"]


def test_churn_shadow_passes_research_gate_when_all_cost_checks_clear() -> None:
    report = build_report(
        {
            "results": {
                "downside_only": {
                    "initial_value": 1_000_000.0,
                    "delta_vs_baseline": {
                        "final_value": 10.0,
                        "sharpe_ratio": 0.1,
                        "max_drawdown": 0.01,
                    },
                    "simulation": {
                        "transaction_cost": 100.0,
                        "turnover_value": 100_000.0,
                        "rebalance_count": 2,
                    },
                }
            },
        }
    )

    assert report["summary"]["multi_window_cost_turnover_passed"] is True
    assert report["summary"]["promotion_allowed"] is False
