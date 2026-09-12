from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_taiwan_etf_review import build_review, write_review


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_review_keeps_paper_as_review_layer_only(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    cvar = tmp_path / "cvar.json"
    a2118 = tmp_path / "a2118.json"
    a2120 = tmp_path / "a2120.json"
    gjr = tmp_path / "gjr.json"
    cost = tmp_path / "cost.json"

    _write(
        live,
        {
            "success": True,
            "data": {
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "strategy_status": "active",
                "requested_as_of_date": "2026-08-25",
                "actual_data_date": "2026-08-24",
                "execution_regime": "golden1",
                "action": "hold_or_align_to_target",
                "target_weights": {"0050.TW": 0.3, "00631L.TW": 0.0, "cash": 0.7},
                "market_state": {
                    "state": "bull_pullback_deep",
                    "inputs": {"dominant_direction": "bearish"},
                },
            },
        },
    )
    _write(
        cvar,
        {
            "status": "research_only",
            "promotion_decision": "research_only",
            "ranking_by_starr95": [
                {
                    "strategy": "defensive_0050_70_cash30",
                    "annualized_return": 0.4,
                    "max_drawdown": -0.2,
                    "expected_shortfall_loss_95": 0.03,
                    "starr_95": 13.0,
                    "rachev_95_95": 1.1,
                },
                {
                    "strategy": "golden1_frozen_proxy_50_20_30",
                    "annualized_return": 0.5,
                    "max_drawdown": -0.26,
                    "expected_shortfall_loss_95": 0.04,
                    "starr_95": 12.5,
                    "rachev_95_95": 1.0,
                },
            ],
            "00631l_only_tail_diagnostics": {
                "max_drawdown": -0.5,
                "expected_shortfall_loss_95": 0.08,
                "expected_shortfall_loss_99": 0.14,
                "hill_95": {"hill_xi": 0.3},
                "pot_gpd_95": {"shape_xi": 0.04},
            },
        },
    )
    _write(
        a2118,
        {
            "decision": {
                "production": "do_not_promote",
                "production_blockers": ["forward_shadow_monitoring_history_insufficient"],
            }
        },
    )
    _write(a2120, {"status": "inactive", "blockers": ["dominant_direction_bearish"]})
    _write(gjr, {"status": "inactive", "blockers": ["a2126_tail_risk_condition_inactive"]})
    _write(
        cost,
        {
            "status": "blocked_for_live_promotion",
            "as_of": "2026-08-24",
            "decision": {
                "promote_dynamic_cvar_optimizer": False,
                "allow_00631l_add_from_cost_sweep": False,
            },
            "blocking_reasons": ["dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95"],
            "warning_reasons": ["dynamic_tangency_cvar_starr95_below_10_under_cost"],
        },
    )

    review = build_review(
        live_signal_path=live,
        cvar_path=cvar,
        a2118_path=a2118,
        a2120_path=a2120,
        gjr_path=gjr,
        cost_robustness_path=cost,
    )

    assert review["report_type"] == "group_a_plus_2607_16450_taiwan_etf_heavy_tail_cvar_review"
    assert review["decision"]["latest_strategy_remains"] == "a2118_a2111_ncf_late_bull_deleverage"
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["add_tail_sensitive_review_layer"] is True
    assert review["decision"]["allow_00631l_add_from_this_paper"] is False
    assert "cvar_optimizer_not_validated_for_groupa_plus" in review["blocking_reasons"]
    assert "transaction_cost_and_turnover_validation_missing_for_2607_16450" not in review["blocking_reasons"]
    assert (
        "turnover_cost_robustness:dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95"
        in review["blocking_reasons"]
    )
    assert review["cost_robustness_reference"]["status"] == "blocked_for_live_promotion"
    assert review["cost_robustness_reference"]["allow_00631l_add_from_cost_sweep"] is False
    assert review["current_tail_reference"]["00631l_only_tail"]["expected_shortfall_loss_95"] == 0.08


def test_write_review_writes_history_by_actual_data_date(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2607_16450_taiwan_etf_heavy_tail_cvar_review",
        "latest_strategy_context": {"actual_data_date": "2026-08-24"},
        "decision": {"target_weight_change_allowed": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert (history / "2607_16450_taiwan_etf_review_20260824.json").exists()
