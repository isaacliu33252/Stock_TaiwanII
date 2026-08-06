from __future__ import annotations

import pytest

from group_a_plus.portfolio.rebalance_plan import RebalanceConfig, build_rebalance_plan


def _signal(**overrides):
    base = {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "actual_data_date": "2026-07-27",
        "target_weights": {
            "0050.TW": 0.50,
            "00631L.TW": 0.20,
            "00632R.TW": 0.0,
            "cash": 0.30,
        },
        "latest_prices": {
            "0050.TW": 100.0,
            "00631L.TW": 25.0,
            "00632R.TW": 10.0,
        },
    }
    base.update(overrides)
    return base


def test_build_rebalance_plan_from_live_signal_prices() -> None:
    plan = build_rebalance_plan(
        _signal(),
        current_shares={"0050.TW": 4_000, "00631L.TW": 12_000},
        cash=300_000.0,
        config=RebalanceConfig(min_trade_value=1_000.0),
    )

    assert plan.strategy_id == "a2118_a2111_ncf_late_bull_deleverage"
    assert plan.signal_asof == "2026-07-27"
    assert plan.portfolio_value == 1_000_000.0
    assert plan.target_values["0050.TW"] == 500_000.0
    assert plan.target_values["00631L.TW"] == 200_000.0

    by_ticker = {order.ticker: order for order in plan.orders}
    assert by_ticker["0050.TW"].side == "BUY"
    assert by_ticker["0050.TW"].shares == 1_000
    assert by_ticker["00631L.TW"].side == "SELL"
    assert by_ticker["00631L.TW"].shares == 4_000
    assert plan.cash_after_planned == 300_000.0


def test_lot_size_rounding_leaves_residual_cash_warning() -> None:
    plan = build_rebalance_plan(
        _signal(),
        current_shares={"0050.TW": 3_800, "00631L.TW": 8_000},
        cash=420_000.0,
        config=RebalanceConfig(min_trade_value=1.0, lot_sizes={"0050.TW": 1_000}),
    )

    order = next(order for order in plan.orders if order.ticker == "0050.TW")
    assert order.side == "BUY"
    assert order.shares == 1_000
    assert any("planned cash differs from target cash" in warning for warning in plan.warnings)


def test_below_min_trade_value_is_skipped() -> None:
    plan = build_rebalance_plan(
        _signal(target_weights={"0050.TW": 0.501, "00631L.TW": 0.199, "cash": 0.30}),
        current_shares={"0050.TW": 5_000, "00631L.TW": 8_000},
        cash=300_000.0,
        config=RebalanceConfig(min_trade_value=2_000.0),
    )

    assert plan.orders == []
    assert {item["ticker"] for item in plan.skipped} == {"0050.TW", "00631L.TW"}
    assert all(item["reason"] == "below_min_trade_value" for item in plan.skipped)


def test_missing_price_for_target_ticker_fails_fast() -> None:
    with pytest.raises(ValueError, match="missing price for target ticker 00631L.TW"):
        build_rebalance_plan(
            _signal(latest_prices={"0050.TW": 100.0}),
            current_shares={"0050.TW": 5_000},
            cash=500_000.0,
        )


def test_rejects_target_weights_above_one() -> None:
    with pytest.raises(ValueError, match="target_weights sum exceeds 1.0"):
        build_rebalance_plan(
            _signal(target_weights={"0050.TW": 0.8, "00631L.TW": 0.3}),
            current_shares={"0050.TW": 5_000},
            cash=500_000.0,
        )
