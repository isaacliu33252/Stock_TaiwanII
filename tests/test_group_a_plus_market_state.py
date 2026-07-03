from __future__ import annotations

from group_a_plus.operations.market_state import classify_market_state


def test_bull_trend_can_split_acceleration_and_late_overheat() -> None:
    acceleration = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.06,
            "drawdown": -0.01,
            "exit_momentum_5d": 0.03,
            "total_risk_score": 2,
            "tail_risk_score": 0,
        },
    )
    overheat = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.14,
            "drawdown": -0.02,
            "exit_momentum_5d": 0.02,
            "total_risk_score": 6,
            "tail_risk_score": 0,
        },
    )

    assert acceleration["bucket"] == "bull_trend"
    assert acceleration["state"] == "bull_acceleration"
    assert acceleration["allocation_bias"] == "00631L high weight"
    assert overheat["bucket"] == "bull_trend"
    assert overheat["state"] == "late_bull_overheat"


def test_bull_pullback_splits_shallow_and_deep() -> None:
    shallow = classify_market_state(
        "golden1",
        {
            "ma_gap": 0.01,
            "drawdown": -0.04,
            "exit_momentum_5d": -0.01,
            "total_risk_score": 4,
            "tail_risk_score": 0,
        },
    )
    deep = classify_market_state(
        "golden1",
        {
            "ma_gap": -0.01,
            "drawdown": -0.08,
            "exit_momentum_5d": -0.02,
            "total_risk_score": 5,
            "tail_risk_score": 0,
        },
    )

    assert shallow["bucket"] == "bull_pullback"
    assert shallow["state"] == "bull_pullback_shallow"
    assert deep["bucket"] == "bull_pullback"
    assert deep["state"] == "bull_pullback_deep"


def test_recovery_splits_early_and_confirmed() -> None:
    early = classify_market_state(
        "group_a_plus_recovery",
        {
            "ma_gap": 0.0,
            "drawdown": -0.07,
            "exit_momentum_5d": 0.005,
            "total_risk_score": 5,
            "tail_risk_score": 0,
        },
    )
    confirmed = classify_market_state(
        "group_a_plus_recovery",
        {
            "ma_gap": 0.02,
            "drawdown": -0.04,
            "exit_momentum_5d": 0.02,
            "total_risk_score": 4,
            "tail_risk_score": 0,
        },
    )

    assert early["state"] == "recovery_early"
    assert confirmed["state"] == "recovery_confirmed"


def test_choppy_range_splits_by_risk_and_alignment() -> None:
    low_risk = classify_market_state(
        "golden1",
        {
            "ma_gap": -0.01,
            "drawdown": -0.04,
            "exit_momentum_5d": 0.01,
            "total_risk_score": 3,
            "tail_risk_score": 0,
        },
    )
    high_risk = classify_market_state(
        "golden1",
        {
            "ma_gap": -0.04,
            "drawdown": -0.05,
            "exit_momentum_5d": 0.0,
            "total_risk_score": 7,
            "tail_risk_score": 0,
        },
        signal_alignment={"alignment": "bearish_alignment", "dominant_direction": "bearish"},
    )

    assert low_risk["state"] == "choppy_range_low_risk"
    assert high_risk["state"] == "choppy_range_high_risk"


def test_defensive_and_crash_states_remain_separate() -> None:
    breakdown = classify_market_state(
        "group_a_plus_defensive",
        {
            "ma_gap": -0.03,
            "drawdown": -0.09,
            "exit_momentum_5d": -0.02,
            "total_risk_score": 7,
            "tail_risk_score": 0,
        },
    )
    crash = classify_market_state(
        "group_a_plus_defensive",
        {
            "ma_gap": -0.05,
            "drawdown": -0.07,
            "exit_momentum_5d": -0.03,
            "total_risk_score": 9,
            "tail_risk_score": 1,
        },
    )

    assert breakdown["state"] == "bear_breakdown"
    assert breakdown["allocation_bias"] == "cash"
    assert crash["state"] == "crash_risk"
    assert crash["allocation_bias"] == "00632R hedge or full defense"
