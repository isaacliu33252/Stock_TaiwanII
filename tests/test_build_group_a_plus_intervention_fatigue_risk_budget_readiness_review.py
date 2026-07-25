from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_intervention_fatigue_risk_budget_readiness_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_review_blocks_when_governance_inputs_block(tmp_path: Path) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rebalance = tmp_path / "rebalance.json"
    market = tmp_path / "market.json"
    dynamic = tmp_path / "dynamic.json"
    research = tmp_path / "research.json"
    intervention_history = tmp_path / "missing_intervention_history.json"
    broker_holdings = tmp_path / "missing_broker_holdings.json"
    broker_reconciliation = tmp_path / "missing_broker_reconciliation.json"
    _write(execution_plan, {"orders": []})
    _write(
        rebalance,
        {
            "status": "available",
            "dates": {"requested_as_of_date": "2026-07-20"},
            "weights": {"target_weights": {"00631L.TW": 0.2, "cash": 0.3}, "cash_buffer_gap_reference": 0.3},
            "decision": {
                "auto_rebalance_allowed": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
            },
        },
    )
    _write(
        market,
        {
            "status": "blocked",
            "computed": {
                "turnover": 0.51,
                "trade_rows": [
                    {
                        "ticker": "00631L.TW",
                        "current_shares": 0,
                        "target_shares": 100,
                        "delta_shares": 100,
                    }
                ],
            },
            "decision": {"auto_rebalance_allowed": False, "allow_00631l_add": False},
        },
    )
    _write(
        dynamic,
        {"status": "blocked", "decision": {"tail_cost_readiness_ready": False, "allow_00631l_add": False}},
    )
    _write(research, {"status": "blocked", "decision": {"allow_00631l_add": False}})

    review = build_review(
        execution_plan_path=execution_plan,
        rebalance_path=rebalance,
        market_impact_path=market,
        dynamic_cvar_path=dynamic,
        research_shadow_path=research,
        intervention_history_path=intervention_history,
        broker_holdings_history_path=broker_holdings,
        broker_reconciliation_path=broker_reconciliation,
    )

    assert review["report_type"] == "group_a_plus_intervention_fatigue_risk_budget_readiness_review"
    assert review["status"] == "blocked"
    assert review["intervention_fatigue"]["trade_count_nonzero"] == 1
    assert review["intervention_fatigue"]["leverage_change_count"] == 1
    assert review["intervention_fatigue"]["has_00631l_add_attempt"] is True
    assert review["risk_budget_pacing"]["leverage_budget_target_weight"] == 0.2
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert "broker_holdings_time_series_missing" in review["blocking_reasons"]
    assert "intervention_history_not_normalized" in review["blocking_reasons"]
    assert "market_impact_readiness_blocked" in review["blocking_reasons"]
    assert "turnover_at_or_above_pacing_limit" in review["blocking_reasons"]


def test_build_review_uses_normalized_intervention_history(tmp_path: Path) -> None:
    execution_plan = tmp_path / "execution_plan.json"
    rebalance = tmp_path / "rebalance.json"
    market = tmp_path / "market.json"
    dynamic = tmp_path / "dynamic.json"
    research = tmp_path / "research.json"
    intervention_history = tmp_path / "intervention_history.json"
    broker_holdings = tmp_path / "broker_holdings.json"
    broker_reconciliation = tmp_path / "broker_reconciliation.json"
    _write(execution_plan, {"orders": []})
    _write(
        rebalance,
        {
            "status": "available",
            "dates": {"requested_as_of_date": "2026-07-20"},
            "weights": {"target_weights": {"00631L.TW": 0.2, "cash": 0.3}},
            "decision": {
                "auto_rebalance_allowed": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
            },
        },
    )
    _write(
        market,
        {
            "status": "blocked",
            "computed": {"turnover": 0.1, "trade_rows": []},
            "decision": {"auto_rebalance_allowed": False, "allow_00631l_add": False},
        },
    )
    _write(dynamic, {"status": "blocked", "decision": {"tail_cost_readiness_ready": False}})
    _write(research, {"status": "blocked", "decision": {"allow_00631l_add": False}})
    _write(
        intervention_history,
        {
            "status": "available",
            "history_type": "system_observed_daily_status_not_broker_fills",
            "coverage": {
                "entry_count": 3,
                "blocked_entry_count": 2,
                "leverage_intervention_count": 2,
                "hedge_intervention_count": 0,
                "first_check_date": "2026-07-14",
                "last_check_date": "2026-07-20",
                "source_file_count": 2,
            },
            "entries": [{"ticker": "00631L.TW"}],
        },
    )
    _write(
        broker_holdings,
        {
            "status": "sample_available",
            "history_type": "transaction_derived_incomplete_not_authoritative_broker_positions",
            "authoritative_broker_export": False,
            "coverage": {
                "transaction_count": 276,
                "snapshot_count": 170,
                "first_transaction_date": "2022-09-14",
                "last_transaction_date": "2026-07-17",
                "latest_position_count": 12,
                "negative_position_count": 7,
            },
        },
    )
    _write(
        broker_reconciliation,
        {
            "status": "blocked",
            "summary": {
                "matched_confirmed_count": 1,
                "mismatched_confirmed_count": 1,
                "missing_confirmed_count": 0,
                "negative_position_count": 7,
                "authoritative_broker_export": False,
            },
            "decision": {"broker_holdings_reconciled": False, "can_generate_live_orders": False},
        },
    )

    review = build_review(
        execution_plan_path=execution_plan,
        rebalance_path=rebalance,
        market_impact_path=market,
        dynamic_cvar_path=dynamic,
        research_shadow_path=research,
        intervention_history_path=intervention_history,
        broker_holdings_history_path=broker_holdings,
        broker_reconciliation_path=broker_reconciliation,
    )

    assert "intervention_history_not_normalized" not in review["blocking_reasons"]
    assert "broker_holdings_time_series_missing" not in review["blocking_reasons"]
    assert "broker_holdings_time_series_sample_only" in review["blocking_reasons"]
    assert "broker_holdings_time_series_has_negative_positions" in review["blocking_reasons"]
    assert "broker_holdings_reconciliation_blocked" in review["blocking_reasons"]
    assert "broker_holdings_not_order_authoritative" in review["blocking_reasons"]
    assert review["intervention_fatigue"]["normalized_history_available"] is True
    assert review["intervention_fatigue"]["history_entry_count"] == 3
    assert review["intervention_history"]["last_check_date"] == "2026-07-20"
    assert review["broker_holdings_time_series"]["transaction_count"] == 276
    assert review["broker_holdings_time_series"]["negative_position_count"] == 7
    assert review["broker_holdings_reconciliation"]["mismatched_confirmed_count"] == 1


def test_write_review_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_intervention_fatigue_risk_budget_readiness_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "20260720.json").read_text(encoding="utf-8")) == review
