from __future__ import annotations

import math

import pytest

from environments.reward_function_alpha import AlphaRewardFunction


def test_matches_paper_formula_log_portfolio_minus_log_benchmark() -> None:
    reward_func = AlphaRewardFunction()

    reward, breakdown = reward_func.calculate(
        portfolio_value=1_010_000,
        previous_portfolio_value=1_000_000,
        position=1000,
        close_price=101.0,
        avg_cost=100.0,
        action=0,
        max_drawdown=0.0,
        trade_history=[],
        previous_close=100.0,
    )

    expected = math.log(1_010_000 / 1_000_000) - math.log(101.0 / 100.0)
    assert reward == pytest.approx(expected)
    assert breakdown["alpha_reward"] == pytest.approx(expected)


def test_zero_reward_when_portfolio_return_exactly_matches_benchmark() -> None:
    # Buy-and-hold with no transaction cost: portfolio grows at exactly the
    # asset's own return, so alpha reward should be ~0 every step.
    reward_func = AlphaRewardFunction()

    reward, _ = reward_func.calculate(
        portfolio_value=1_050_000,
        previous_portfolio_value=1_000_000,
        position=1000,
        close_price=105.0,
        avg_cost=100.0,
        action=0,
        max_drawdown=0.0,
        trade_history=[],
        previous_close=100.0,
    )

    assert reward == pytest.approx(0.0, abs=1e-9)


def test_outperformance_gives_positive_reward() -> None:
    reward_func = AlphaRewardFunction()

    reward, _ = reward_func.calculate(
        portfolio_value=1_050_000,  # portfolio +5%
        previous_portfolio_value=1_000_000,
        position=1000,
        close_price=101.0,  # market only +1%
        avg_cost=100.0,
        action=0,
        max_drawdown=0.0,
        trade_history=[],
        previous_close=100.0,
    )

    assert reward > 0.0


def test_missing_previous_close_treats_benchmark_as_zero() -> None:
    reward_func = AlphaRewardFunction()

    reward, breakdown = reward_func.calculate(
        portfolio_value=1_010_000,
        previous_portfolio_value=1_000_000,
        position=1000,
        close_price=101.0,
        avg_cost=100.0,
        action=0,
        max_drawdown=0.0,
        trade_history=[],
        previous_close=None,
    )

    assert breakdown["benchmark_log_return"] == 0.0
    assert reward == pytest.approx(math.log(1_010_000 / 1_000_000))


def test_zero_or_negative_previous_close_does_not_raise() -> None:
    reward_func = AlphaRewardFunction()

    reward, breakdown = reward_func.calculate(
        portfolio_value=1_010_000,
        previous_portfolio_value=1_000_000,
        position=0,
        close_price=101.0,
        avg_cost=0.0,
        action=0,
        max_drawdown=0.0,
        trade_history=[],
        previous_close=0.0,
    )

    assert breakdown["benchmark_log_return"] == 0.0
    assert math.isfinite(reward)


def test_extreme_return_is_clipped() -> None:
    reward_func = AlphaRewardFunction(clip=0.20)

    reward, _ = reward_func.calculate(
        portfolio_value=10_000_000,  # +900%, would blow past the clip
        previous_portfolio_value=1_000_000,
        position=1000,
        close_price=100.0,
        avg_cost=100.0,
        action=0,
        max_drawdown=0.0,
        trade_history=[],
        previous_close=100.0,
    )

    assert reward == pytest.approx(0.20)


def test_cumulative_alpha_identity_telescopes_to_log_terminal_outperformance() -> None:
    """Property (1) from the paper: summing r_t over an episode equals
    log(alpha_T), the terminal outperformance ratio over buy-and-hold."""
    reward_func = AlphaRewardFunction(clip=10.0)  # disable clipping for this check

    portfolio_path = [1_000_000, 1_020_000, 1_015_000, 1_080_000]
    price_path = [100.0, 101.0, 102.0, 99.0]

    total_reward = 0.0
    for i in range(1, len(portfolio_path)):
        r, _ = reward_func.calculate(
            portfolio_value=portfolio_path[i],
            previous_portfolio_value=portfolio_path[i - 1],
            position=1000,
            close_price=price_path[i],
            avg_cost=100.0,
            action=0,
            max_drawdown=0.0,
            trade_history=[],
            previous_close=price_path[i - 1],
        )
        total_reward += r

    alpha_terminal = (portfolio_path[-1] / portfolio_path[0]) / (price_path[-1] / price_path[0])
    assert total_reward == pytest.approx(math.log(alpha_terminal))
