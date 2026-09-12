from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_tail_sensitive_scorecard import (
    build_scorecard,
    write_scorecard,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_scorecard_is_review_only_and_ranks_references(tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    cvar = tmp_path / "cvar.json"
    profit = tmp_path / "profit.json"
    cost = tmp_path / "cost.json"
    _write(
        review,
        {
            "latest_strategy_context": {
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "strategy_status": "active",
                "actual_data_date": "2026-08-24",
                "execution_regime": "golden1",
                "action": "hold_or_align_to_target",
                "target_weights": {"0050.TW": 0.3, "00631L.TW": 0.0, "cash": 0.7},
            },
            "decision": {"target_weight_change_allowed": False},
        },
    )
    _write(
        cvar,
        {
            "promotion_decision": "research_only",
            "ranking_by_starr95": [
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
                {
                    "strategy": "0050_only",
                    "annualized_return": 0.62,
                    "max_drawdown": -0.28,
                    "expected_shortfall_loss_95": 0.038,
                    "starr_95": 16.3,
                    "rachev_95_95": 1.16,
                    "sharpe": 2.18,
                },
                {
                    "strategy": "00631l_only",
                    "annualized_return": 1.08,
                    "max_drawdown": -0.5,
                    "expected_shortfall_loss_95": 0.082,
                    "starr_95": 13.2,
                    "rachev_95_95": 1.01,
                    "sharpe": 1.92,
                },
            ],
        },
    )
    _write(profit, {"active_shadow_candidates": ["staged_reentry", "a2118_seed_averaging"]})
    _write(
        cost,
        {
            "status": "blocked_for_live_promotion",
            "as_of": "2026-08-24",
            "decision": {
                "promote_dynamic_cvar_optimizer": False,
                "allow_00631l_add_from_cost_sweep": False,
            },
            "blocking_reasons": ["dynamic_tangency_cvar_underperforms_defensive_reference_on_return"],
        },
    )

    scorecard = build_scorecard(
        paper_review_path=review,
        cvar_path=cvar,
        profit_readiness_path=profit,
        cost_robustness_path=cost,
    )

    assert scorecard["report_type"] == "group_a_plus_2607_16450_tail_sensitive_scorecard"
    assert scorecard["status"] == "available"
    assert scorecard["decision"]["target_weight_change_allowed"] is False
    assert scorecard["decision"]["allow_00631l_add_from_scorecard"] is False
    assert scorecard["decision"]["promote_dynamic_cvar_optimizer"] is False
    assert scorecard["decision"]["use_for_promotion_review"] is True
    assert scorecard["cost_robustness"]["status"] == "blocked_for_live_promotion"
    assert scorecard["cost_robustness"]["allow_00631l_add_from_cost_sweep"] is False
    assert scorecard["latest_strategy_context"]["strategy_id"] == "a2118_a2111_ncf_late_bull_deleverage"
    assert scorecard["ranked_references"][0]["score"] >= scorecard["ranked_references"][-1]["score"]
    assert any(row["strategy"] == "00631l_only" and row["penalties"] for row in scorecard["ranked_references"])


def test_write_scorecard_writes_history_by_actual_data_date(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "scorecard.json"
    history = tmp_path / "history"
    scorecard = {
        "report_type": "group_a_plus_2607_16450_tail_sensitive_scorecard",
        "latest_strategy_context": {"actual_data_date": "2026-08-24"},
        "decision": {"target_weight_change_allowed": False},
    }

    write_scorecard(scorecard, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == scorecard
    assert (history / "2607_16450_tail_sensitive_scorecard_20260824.json").exists()
