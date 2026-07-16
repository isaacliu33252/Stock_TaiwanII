from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import simulate_no_add_guard


def test_mean_reverting_blocks_incremental_00631l_add_without_selling_existing() -> None:
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 100.0],
            "00631L.TW": [50.0, 50.0, 60.0],
            "00632R.TW": [10.0, 10.0, 10.0],
            "00679B.TWO": [25.0, 25.0, 25.0],
        },
        index=idx,
    )
    weights = pd.DataFrame(
        {
            "0050.TW": [0.80, 0.70, 0.60],
            "00631L.TW": [0.00, 0.10, 0.20],
            "00632R.TW": [0.00, 0.00, 0.00],
            "00679B.TWO": [0.00, 0.00, 0.00],
            "cash": [0.20, 0.20, 0.20],
        },
        index=idx,
    )
    regimes = pd.Series(["TRANSITIONAL", "MEAN_REVERTING", "MEAN_REVERTING"], index=idx)

    out = simulate_no_add_guard(prices=prices, target_weights=weights, regimes=regimes, initial_value=100_000.0)

    assert out["blocked_days"] == 2
    assert out["blocked_events"][0]["current_00631l_weight"] == 0.0
    assert out["blocked_events"][0]["requested_00631l_weight"] == 0.1
    assert out["blocked_events"][1]["blocked_00631l_weight"] > 0.0


def test_transitional_regime_allows_00631l_add() -> None:
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 100.0],
            "00631L.TW": [50.0, 50.0, 55.0],
            "00632R.TW": [10.0, 10.0, 10.0],
            "00679B.TWO": [25.0, 25.0, 25.0],
        },
        index=idx,
    )
    weights = pd.DataFrame(
        {
            "0050.TW": [1.0, 0.8, 0.8],
            "00631L.TW": [0.0, 0.2, 0.2],
            "00632R.TW": [0.0, 0.0, 0.0],
            "00679B.TWO": [0.0, 0.0, 0.0],
            "cash": [0.0, 0.0, 0.0],
        },
        index=idx,
    )
    regimes = pd.Series(["TRANSITIONAL", "TRANSITIONAL", "TRANSITIONAL"], index=idx)

    out = simulate_no_add_guard(prices=prices, target_weights=weights, regimes=regimes, initial_value=100_000.0)

    assert out["blocked_days"] == 0
    assert out["metrics"]["final_value"] > 100_000.0


def test_mean_reverting_add_fraction_slows_instead_of_blocks_full_add() -> None:
    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 50.0],
            "00632R.TW": [10.0, 10.0],
            "00679B.TWO": [25.0, 25.0],
        },
        index=idx,
    )
    weights = pd.DataFrame(
        {
            "0050.TW": [1.0, 0.8],
            "00631L.TW": [0.0, 0.2],
            "00632R.TW": [0.0, 0.0],
            "00679B.TWO": [0.0, 0.0],
            "cash": [0.0, 0.0],
        },
        index=idx,
    )
    regimes = pd.Series(["TRANSITIONAL", "MEAN_REVERTING"], index=idx)

    out = simulate_no_add_guard(
        prices=prices,
        target_weights=weights,
        regimes=regimes,
        initial_value=100_000.0,
        mean_reversion_add_fraction=0.5,
    )

    assert out["blocked_days"] == 1
    assert out["blocked_events"][0]["allowed_00631l_add_weight"] == 0.1
    assert out["blocked_events"][0]["blocked_00631l_weight"] == 0.1


def test_trend_persistent_add_fraction_accelerates_incremental_add() -> None:
    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 50.0],
            "00632R.TW": [10.0, 10.0],
            "00679B.TWO": [25.0, 25.0],
        },
        index=idx,
    )
    weights = pd.DataFrame(
        {
            "0050.TW": [1.0, 0.8],
            "00631L.TW": [0.0, 0.2],
            "00632R.TW": [0.0, 0.0],
            "00679B.TWO": [0.0, 0.0],
            "cash": [0.0, 0.0],
        },
        index=idx,
    )
    regimes = pd.Series(["TRANSITIONAL", "TREND_PERSISTENT"], index=idx)

    out = simulate_no_add_guard(
        prices=prices,
        target_weights=weights,
        regimes=regimes,
        initial_value=100_000.0,
        baseline_add_fraction=0.5,
        mean_reversion_add_fraction=0.5,
        trend_persistent_add_fraction=1.0,
    )

    assert out["event_days"] == 1
    assert out["blocked_days"] == 0
    assert out["accelerated_days"] == 1
    assert out["blocked_events"][0]["allowed_00631l_add_weight"] == 0.2
    assert out["blocked_events"][0]["blocked_00631l_weight"] == 0.0
    assert out["blocked_events"][0]["accelerated_00631l_weight"] == 0.1


def test_trend_persistent_add_fraction_by_date_can_reduce_weak_edge_add() -> None:
    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 50.0],
            "00632R.TW": [10.0, 10.0],
            "00679B.TWO": [25.0, 25.0],
        },
        index=idx,
    )
    weights = pd.DataFrame(
        {
            "0050.TW": [1.0, 0.8],
            "00631L.TW": [0.0, 0.2],
            "00632R.TW": [0.0, 0.0],
            "00679B.TWO": [0.0, 0.0],
            "cash": [0.0, 0.0],
        },
        index=idx,
    )
    regimes = pd.Series(["TRANSITIONAL", "TREND_PERSISTENT"], index=idx)
    trend_add_by_date = pd.Series([1.0, 0.9], index=idx)

    out = simulate_no_add_guard(
        prices=prices,
        target_weights=weights,
        regimes=regimes,
        initial_value=100_000.0,
        baseline_add_fraction=0.4,
        mean_reversion_add_fraction=0.0,
        trend_persistent_add_fraction=1.0,
        trend_persistent_add_fraction_by_date=trend_add_by_date,
    )

    assert out["accelerated_days"] == 1
    assert out["blocked_events"][0]["allowed_00631l_add_weight"] == 0.18
    assert out["blocked_events"][0]["effective_trend_persistent_add_fraction"] == 0.9


def test_transaction_cost_bps_reduces_final_value_and_records_cost() -> None:
    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 50.0],
            "00632R.TW": [10.0, 10.0],
            "00679B.TWO": [25.0, 25.0],
        },
        index=idx,
    )
    weights = pd.DataFrame(
        {
            "0050.TW": [1.0, 0.8],
            "00631L.TW": [0.0, 0.2],
            "00632R.TW": [0.0, 0.0],
            "00679B.TWO": [0.0, 0.0],
            "cash": [0.0, 0.0],
        },
        index=idx,
    )
    regimes = pd.Series(["TRANSITIONAL", "TRANSITIONAL"], index=idx)

    no_cost = simulate_no_add_guard(prices=prices, target_weights=weights, regimes=regimes, initial_value=100_000.0)
    with_cost = simulate_no_add_guard(
        prices=prices,
        target_weights=weights,
        regimes=regimes,
        initial_value=100_000.0,
        transaction_cost_bps=10.0,
    )

    assert with_cost["transaction_cost_bps"] == 10.0
    assert with_cost["total_transaction_cost"] > 0.0
    assert with_cost["metrics"]["final_value"] < no_cost["metrics"]["final_value"]
