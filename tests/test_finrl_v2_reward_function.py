from __future__ import annotations

import pytest

from FinRL.v2.environments.reward_function import RewardConfig, RewardFunction, TradingMetrics


def test_capital_reward_uses_daily_return_without_default_scale_jump() -> None:
    reward_func = RewardFunction()
    prev = TradingMetrics(portfolio_value=1_000_000)
    current = TradingMetrics(portfolio_value=1_010_000)

    reward, details = reward_func.calculate(current_metrics=current, prev_metrics=prev)

    assert details["capital_reward"] == pytest.approx(0.01)
    assert reward == pytest.approx(0.01)


def test_capital_reward_weight_is_applied_when_configured() -> None:
    reward_func = RewardFunction(RewardConfig(capital_reward_weight=2.5))
    prev = TradingMetrics(portfolio_value=1_000_000)
    current = TradingMetrics(portfolio_value=1_010_000)

    reward, details = reward_func.calculate(current_metrics=current, prev_metrics=prev)

    assert details["capital_reward"] == pytest.approx(0.025)
    assert reward == pytest.approx(0.025)


def test_capital_reward_clamps_before_weighting() -> None:
    reward_func = RewardFunction(RewardConfig(capital_reward_weight=3.0))
    prev = TradingMetrics(portfolio_value=1_000_000)
    current = TradingMetrics(portfolio_value=1_500_000)

    reward, details = reward_func.calculate(current_metrics=current, prev_metrics=prev)

    assert details["capital_reward"] == pytest.approx(0.30)
    assert reward == pytest.approx(0.30)
