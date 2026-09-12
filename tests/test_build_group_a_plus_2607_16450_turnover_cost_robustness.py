from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_turnover_cost_robustness import (
    build_cost_robustness_review,
    write_review,
)


def _report(dynamic_name: str, dynamic_return: float, dynamic_starr: float) -> dict:
    return {
        "ranking_by_starr95": [
            {
                "strategy": dynamic_name,
                "annualized_return": dynamic_return,
                "max_drawdown": -0.11,
                "expected_shortfall_loss_95": 0.02,
                "starr_95": dynamic_starr,
                "rachev_95_95": 1.08,
                "sharpe": 1.1,
            },
            {
                "strategy": "defensive_0050_70_cash30",
                "annualized_return": 0.41,
                "max_drawdown": -0.2,
                "expected_shortfall_loss_95": 0.026,
                "starr_95": 15.6,
                "rachev_95_95": 1.17,
                "sharpe": 2.08,
            },
            {
                "strategy": "golden1_frozen_proxy_50_20_30",
                "annualized_return": 0.5,
                "max_drawdown": -0.26,
                "expected_shortfall_loss_95": 0.035,
                "starr_95": 14.2,
                "rachev_95_95": 1.09,
                "sharpe": 1.99,
            },
        ],
        "strategy_summary": {
            dynamic_name: {
                "mean_rebalance_turnover": 0.12,
                "recent_allocations": [
                    {
                        "date": "2026-08-24",
                        "weights": {"0050.TW": 0.35, "00631L.TW": 0.05, "cash": 0.6},
                    }
                ],
            }
        },
    }


def test_cost_robustness_blocks_dynamic_cvar_when_it_loses_to_defensive_reference() -> None:
    review = build_cost_robustness_review(
        as_of="2026-08-24",
        reports_by_cost={
            0.0: _report("dynamic_tangency_cvar_net_cost0bps", 0.16, 8.1),
            10.0: _report("dynamic_tangency_cvar_net_cost10bps", 0.13, 7.8),
        },
    )

    assert review["report_type"] == "group_a_plus_2607_16450_turnover_cost_robustness"
    assert review["status"] == "blocked_for_live_promotion"
    assert review["decision"]["promote_dynamic_cvar_optimizer"] is False
    assert review["decision"]["allow_00631l_add_from_cost_sweep"] is False
    assert "dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95" in review["blocking_reasons"]
    assert "dynamic_tangency_cvar_underperforms_defensive_reference_on_return" in review["blocking_reasons"]
    assert "dynamic_tangency_cvar_starr95_below_10_under_cost" in review["warning_reasons"]
    assert review["cost_sweep"][1]["allocation_summary"]["latest_weights"]["00631L.TW"] == 0.05


def test_write_review_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2607_16450_turnover_cost_robustness",
        "as_of": "2026-08-24",
        "decision": {"promote_dynamic_cvar_optimizer": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert (history / "2607_16450_turnover_cost_robustness_20260824.json").exists()
