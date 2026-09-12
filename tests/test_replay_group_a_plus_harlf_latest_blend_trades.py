from __future__ import annotations

import pandas as pd

from scripts.evaluate.replay_group_a_plus_harlf_latest_blend_trades import build_trade_replay


def test_harlf_latest_blend_trade_replay_runs_with_costs_and_lot_rounding() -> None:
    dates = pd.to_datetime(["2026-02-02", "2026-02-03", "2026-03-02", "2026-03-03"])
    close = pd.DataFrame(
        {
            "0050": [100.0, 101.0, 102.0, 103.0],
            "00631L": [50.0, 52.0, 54.0, 55.0],
            "00632R": [10.0, 9.8, 9.5, 9.4],
            "00679B": [30.0, 30.1, 30.2, 30.3],
        },
        index=dates,
    )
    latest = pd.DataFrame(
        {
            "target_weight_0050": [0.6, 0.6, 0.6, 0.6],
            "target_weight_00631L": [0.1, 0.1, 0.1, 0.1],
            "target_weight_00632R": [0.0, 0.0, 0.0, 0.0],
            "target_weight_00679B": [0.1, 0.1, 0.1, 0.1],
            "target_weight_cash": [0.2, 0.2, 0.2, 0.2],
        },
        index=dates,
    )
    mapped = {
        "variants": {
            "drop_2330_renormalize": {
                "meta_agent_monthly_returns": [
                    {"month": "2026-01", "weights": {"0050": 0.5, "00631L": 0.5, "00632R": 0.0, "00679B": 0.0}},
                    {"month": "2026-02", "weights": {"0050": 0.0, "00631L": 1.0, "00632R": 0.0, "00679B": 0.0}},
                ]
            }
        }
    }
    blend = {"best_viable_blend": {"harlf_weight": 0.08, "latest_weight": 0.92}}

    report = build_trade_replay(
        close=close,
        latest_weights=latest,
        mapped_shadow=mapped,
        blend_report=blend,
        initial_value=100_000.0,
        lot_size=10,
        max_turnover_ratio=0.5,
    )

    assert report["status"] == "available"
    assert report["decision"]["trade_level_execution_cost_replay_available"] is True
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["window"]["rebalance_count"] == 2
    assert report["cost_summary"]["total_cost"] > 0
    for event in report["rebalance_events"]:
        for trade in event["trades"]:
            assert trade["shares"] % 10 == 0


def test_harlf_latest_blend_trade_replay_blocks_missing_inputs() -> None:
    report = build_trade_replay(
        close=pd.DataFrame(),
        latest_weights=pd.DataFrame(),
        mapped_shadow={},
        blend_report={},
    )

    assert report["status"] == "blocked"
    assert "missing_close_prices" in report["blocking_reasons"]
    assert "missing_latest_target_weights" in report["blocking_reasons"]
    assert report["decision"]["promotion_ready"] is False
