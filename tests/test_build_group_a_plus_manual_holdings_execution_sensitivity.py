from __future__ import annotations

from scripts.evaluate.build_group_a_plus_manual_holdings_execution_sensitivity import (
    _parse_float_list,
    _parse_int_list,
    _summarize_plan,
)


def test_parse_scenario_lists() -> None:
    assert _parse_int_list("0, 3000,5000") == [0, 3000, 5000]
    assert _parse_float_list("0, 100000.5") == [0.0, 100000.5]


def test_summarize_plan_extracts_blocked_00631l_and_trade_deltas() -> None:
    plan = {
        "current_total_assets": 500000.0,
        "planning_status": "ready",
        "execution_allowed": True,
        "actual_data_date": "2026-07-17",
        "target_shares": {
            "0050.TW": 1880,
            "00631L.TW": 500,
            "00632R.TW": 0,
            "00679B.TWO": 0,
        },
        "trades": [
            {"ticker": "0050.TW", "side": "sell", "delta_shares": -914},
            {"ticker": "00679B.TWO", "side": "sell", "delta_shares": -3000},
        ],
        "guard_impact_summary": {
            "blocked_guard_names": ["volatility_gate_no_00631l_add"],
            "active_guard_names": ["volatility_gate_no_00631l_add"],
            "combined_blocked_buys": [
                {
                    "ticker": "00631L.TW",
                    "blocked_delta_shares": 734,
                    "blocked_notional": 23612.78,
                }
            ],
        },
    }

    row = _summarize_plan(plan, cash_balance=0.0, bond_shares=3000)

    assert row["sell_0050_shares"] == 914
    assert row["sell_00679b_shares"] == 3000
    assert row["buy_00631l_shares"] == 0
    assert row["blocked_00631l_add_shares"] == 734
    assert row["blocked_00631l_add_notional"] == 23612.78
