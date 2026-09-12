from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from environments.reward_function_alpha import AlphaRewardFunction
from environments.taiwan_stock_env import TaiwanStockTradingEnv


def _make_flat_df(n: int = 40, price: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n)
    closes = np.full(n, price)
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": np.full(n, 1000),
        }
    )


def test_create_env_style_kwargs_no_longer_raise_type_error() -> None:
    """Regression guard: portfolio_train_v2.py's EnhancedStockTrainer.create_env()
    passes turnover_penalty/min_hold_days/short_hold_penalty in env_config.
    Before this fix, TaiwanStockTradingEnv.__init__ did not accept them and
    every call crashed with TypeError."""
    env = TaiwanStockTradingEnv(
        df=_make_flat_df(),
        turnover_penalty=0.01,
        min_hold_days=20,
        short_hold_penalty=0.02,
    )
    env.reset()
    state, reward, terminated, truncated, info = env.step(0)  # HOLD
    assert np.isfinite(reward)


def test_turnover_penalty_applied_on_executed_trade_not_on_hold() -> None:
    env = TaiwanStockTradingEnv(df=_make_flat_df(), turnover_penalty=0.05, min_hold_days=0, short_hold_penalty=0.0)
    env.reset()

    _, reward_hold, *_ = env.step(0)  # HOLD -- no trade
    assert reward_hold > -0.05

    _, reward_buy, *_, info_buy = env.step(1)  # BUY_1000 -- executes
    assert info_buy["reward_breakdown"].get("turnover_penalty") == -0.05


def test_turnover_penalty_not_applied_when_trade_fails() -> None:
    # No cash at all -> BUY should fail to execute -> no turnover penalty.
    env = TaiwanStockTradingEnv(
        df=_make_flat_df(), initial_balance=0.0, turnover_penalty=0.05, min_hold_days=0, short_hold_penalty=0.0
    )
    env.reset()
    _, reward, terminated, truncated, info = env.step(1)  # BUY_1000, should fail (no cash)
    assert "turnover_penalty" not in info["reward_breakdown"]


def test_short_hold_penalty_applied_when_selling_before_min_hold_days() -> None:
    env = TaiwanStockTradingEnv(
        df=_make_flat_df(), turnover_penalty=0.0, min_hold_days=20, short_hold_penalty=0.10
    )
    env.reset()
    env.step(1)  # BUY at step 0 -> last_buy_step = 0
    env.step(0)  # HOLD, step 1 (still T+2 locked)
    env.step(0)  # HOLD, step 2 -> T+2 settlement clears, shares now sellable
    _, reward, terminated, truncated, info = env.step(2)  # SELL_1000 at step 3, well before 20-day hold
    assert "short_hold_penalty" in info["reward_breakdown"]
    assert info["reward_breakdown"]["short_hold_penalty"] < 0


def test_short_hold_penalty_not_applied_after_min_hold_days_satisfied() -> None:
    env = TaiwanStockTradingEnv(
        df=_make_flat_df(n=30), turnover_penalty=0.0, min_hold_days=5, short_hold_penalty=0.10
    )
    env.reset()
    env.step(1)  # BUY at step 0
    for _ in range(5):
        env.step(0)  # HOLD for 5 days -> now well past min_hold_days
    _, reward, terminated, truncated, info = env.step(2)  # SELL after holding long enough
    assert "short_hold_penalty" not in info["reward_breakdown"]


def test_short_hold_penalty_not_applied_without_a_prior_buy() -> None:
    env = TaiwanStockTradingEnv(
        df=_make_flat_df(), turnover_penalty=0.0, min_hold_days=20, short_hold_penalty=0.10, initial_shares=1000
    )
    env.reset()
    # position came from initial_shares, never bought in-episode -> last_buy_step is None
    _, reward, terminated, truncated, info = env.step(2)  # SELL_1000
    assert "short_hold_penalty" not in info["reward_breakdown"]


def test_defaults_match_finrl_environments_version() -> None:
    env = TaiwanStockTradingEnv(df=_make_flat_df())
    assert env.turnover_penalty == 0.01
    assert env.min_hold_days == 20
    assert env.short_hold_penalty == 0.02


def test_turnover_penalty_is_additive_on_top_of_whatever_reward_func_returns() -> None:
    """AlphaRewardFunction.calculate() on its own telescopes exactly to
    log(terminal alpha) when called directly (see test_reward_function_alpha.py).
    But the env layers turnover_penalty/short_hold_penalty on top of *any*
    reward_func's return value, unconditionally, inside step() -- so with a
    nonzero turnover_penalty the reward the agent actually receives is NOT
    reward_func.calculate()'s own alpha_reward; it is alpha_reward minus the
    env-level penalties. A caller wanting a truly clean alpha-only training
    signal must explicitly pass turnover_penalty=0.0 and
    short_hold_penalty=0.0 to the env constructor -- reward_variant="alpha"
    in portfolio_train_v2.py alone does not give a clean signal, since
    create_env() always passes nonzero turnover_penalty/short_hold_penalty
    regardless of reward_variant."""
    df = _make_flat_df(n=10, price=100.0)
    df.loc[df.index[1:], "close"] = [101.0, 102.0, 101.5, 103.0, 104.0, 103.5, 105.0, 106.0, 107.0]
    df["open"] = df["high"] = df["low"] = df["close"]

    def run_episode(turnover_penalty: float, short_hold_penalty: float) -> tuple[float, float]:
        env = TaiwanStockTradingEnv(
            df=df,
            reward_func=AlphaRewardFunction(clip=10.0),
            turnover_penalty=turnover_penalty,
            min_hold_days=0,
            short_hold_penalty=short_hold_penalty,
        )
        env.reset()
        _, first_reward, _, _, first_info = env.step(1)  # BUY -- exactly one executed trade
        total_reward = first_reward
        total_alpha_from_breakdown = first_info["reward_breakdown"]["alpha_reward"]
        for _ in range(6):
            _, r, terminated, truncated, info = env.step(0)  # HOLD
            total_reward += r
            total_alpha_from_breakdown += info["reward_breakdown"]["alpha_reward"]
            if terminated:
                break
        return total_reward, total_alpha_from_breakdown

    reward_with_penalty, alpha_with_penalty = run_episode(turnover_penalty=0.01, short_hold_penalty=0.0)
    reward_without_penalty, alpha_without_penalty = run_episode(turnover_penalty=0.0, short_hold_penalty=0.0)

    # reward_func.calculate()'s own alpha_reward accounting is identical either
    # way -- the env's penalties never feed back into what calculate() computes.
    assert alpha_with_penalty == pytest.approx(alpha_without_penalty)
    # but the reward actually returned by step() differs by exactly the penalty
    assert reward_without_penalty == pytest.approx(alpha_without_penalty, abs=1e-9)
    assert reward_with_penalty == pytest.approx(alpha_with_penalty - 0.01, abs=1e-9)
    assert reward_with_penalty != pytest.approx(reward_without_penalty, abs=1e-9)
