#!/usr/bin/env python3
"""Tests for current-holdings scenario grid on the volatility guard."""

from __future__ import annotations

from scripts.evaluate.evaluate_group_a_plus_volatility_guard_holdings_scenarios import evaluate_scenarios


def test_holdings_scenarios_block_only_when_current_below_requested() -> None:
    plan = {
        "strategy_id": "a2118",
        "actual_data_date": "2026-07-09",
        "execution_regime": "golden1",
        "current_holdings": {"00631L.TW": 0},
        "target_shares": {"00631L.TW": 0},
        "current_prices": {"00631L.TW": 50.0},
        "pre_trade_guard": {"requested_target_shares": 100},
        "source_live_signal": {
            "signal_alerts": [
                {
                    "type": "volatility_gate_high_vol",
                    "metadata": {
                        "allow_00631l_add": False,
                        "trade_policy": "advisory_no_auto_weight_change",
                    },
                }
            ]
        },
    }

    result = evaluate_scenarios(plan, [0, 50, 100, 150])
    by_current = {row["current_00631l_shares"]: row for row in result["rows"]}

    assert by_current[0]["guard_status"] == "blocked"
    assert by_current[0]["blocked_delta_shares"] == 100
    assert by_current[50]["guard_status"] == "blocked"
    assert by_current[50]["blocked_delta_shares"] == 50
    assert by_current[100]["guard_status"] == "active_allowed"
    assert by_current[100]["blocked_delta_shares"] == 0
    assert by_current[150]["guard_status"] == "active_allowed"
    assert result["summary"]["blocked_scenario_count"] == 2
