"""2026-08-11: FinRL/v2/environments/taiwan_stock_env.py's continuous mode
previously bucketed the continuous action into HOLD/BUY_1000/SELL_1000 --
regardless of the actual action value, the policy could only ever produce one
of 3 discrete outcomes, which is not real continuous portfolio-weight
control and confounded a SAC representation-bottleneck pilot (see
GROUP_A_PLUS_20260811... follow-up to arXiv:2606.10448): a trained policy's
backtest looked like a near-frozen small buy-and-hold, which is at least
partly attributable to this crude action space rather than the RL/bottleneck
mechanism itself. This replaces it with `_execute_target_position_trade`:
the action value is read as a target position *ratio*, converted to a target
share count (rounded to MIN_TRADE_UNIT), and the environment trades the real
difference between current and target position.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from FinRL.v2.environments.taiwan_stock_env import TaiwanStockConstants, TaiwanStockTradingEnv


def _make_df(n_days: int = 5, price: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    return pd.DataFrame(
        {
            "date": dates,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1_000_000,
        }
    )


def test_continuous_action_moves_position_toward_target_ratio_not_a_fixed_lot():
    # Cash comfortably covers the full target (0.2 * 40000 = 8000 shares at
    # price=100, well under the 1,000,000 initial capital) so this isolates
    # "does the action reach its target ratio" from cash-affordability
    # clamping (covered separately below).
    df = _make_df(n_days=3, price=100.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="continuous")
    env.reset()

    target_ratio = 0.2
    env.step(np.array([target_ratio], dtype=np.float32))

    expected_shares = round(target_ratio * env.max_position / TaiwanStockConstants.MIN_TRADE_UNIT) * TaiwanStockConstants.MIN_TRADE_UNIT
    assert env.portfolio.position == expected_shares
    assert env.portfolio.position != TaiwanStockConstants.MIN_TRADE_UNIT, (
        "continuous action must not be collapsed to the old fixed BUY_1000 lot size"
    )


def test_continuous_action_can_reduce_position_toward_lower_target():
    df = _make_df(n_days=3, price=100.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="continuous")
    env.reset()

    env.step(np.array([0.8], dtype=np.float32))
    high_position = env.portfolio.position
    env.step(np.array([0.2], dtype=np.float32))
    low_position = env.portfolio.position

    assert low_position < high_position
    expected_low = round(0.2 * env.max_position / TaiwanStockConstants.MIN_TRADE_UNIT) * TaiwanStockConstants.MIN_TRADE_UNIT
    assert low_position == expected_low


def test_continuous_action_zero_ratio_liquidates_toward_zero_position():
    df = _make_df(n_days=3, price=100.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="continuous")
    env.reset()

    env.step(np.array([0.6], dtype=np.float32))
    assert env.portfolio.position > 0
    env.step(np.array([0.0], dtype=np.float32))
    assert env.portfolio.position == 0


def test_continuous_action_at_current_target_does_not_trade():
    df = _make_df(n_days=3, price=100.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="continuous")
    env.reset()

    env.step(np.array([0.4], dtype=np.float32))
    trades_before = len(env.trade_history)
    env.step(np.array([0.4], dtype=np.float32))  # same target ratio again

    assert len(env.trade_history) == trades_before


def test_continuous_buy_partially_fills_when_cash_insufficient_for_full_target():
    # price=50: the full target (40000 shares) would cost ~2,003,000 (with
    # fees), more than the 1,000,000 initial capital, but a single
    # MIN_TRADE_UNIT lot (1000 shares, ~50,150) is easily affordable -- this
    # isolates the "partial fill" branch from the "target itself is
    # unaffordable even at one lot" case.
    df = _make_df(n_days=3, price=50.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="continuous")
    env.reset()

    env.step(np.array([1.0], dtype=np.float32))

    assert 0 < env.portfolio.position < env.max_position, (
        "should buy as many whole lots as affordable, not the full target and not zero"
    )
    assert env.portfolio.cash >= 0


def test_discrete_mode_unaffected_by_continuous_changes():
    df = _make_df(n_days=3, price=100.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="discrete")
    env.reset()

    obs, reward, terminated, truncated, info = env.step(1)  # BUY_1000

    assert env.portfolio.position == TaiwanStockConstants.MIN_TRADE_UNIT
