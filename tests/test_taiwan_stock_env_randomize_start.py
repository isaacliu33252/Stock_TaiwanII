from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from environments.taiwan_stock_env import TaiwanStockTradingEnv


def _make_df(n: int = 300) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(20260806)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, size=n))
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": rng.integers(1_000, 10_000, size=n),
        }
    )


def test_default_behaviour_unchanged_starts_at_day_zero() -> None:
    env = TaiwanStockTradingEnv(df=_make_df())
    env.reset(seed=123)
    assert env.current_step == 0


def test_randomize_start_off_still_starts_at_day_zero_even_with_seed() -> None:
    env = TaiwanStockTradingEnv(df=_make_df(), randomize_start=False)
    for seed in [1, 2, 3]:
        env.reset(seed=seed)
        assert env.current_step == 0


def test_randomize_start_picks_a_reproducible_index_for_a_given_seed() -> None:
    env = TaiwanStockTradingEnv(df=_make_df(300), randomize_start=True, min_episode_days=100)
    env.reset(seed=42)
    first = env.current_step
    env.reset(seed=42)
    second = env.current_step
    assert first == second


def test_randomize_start_respects_min_episode_days_bound() -> None:
    n = 300
    min_days = 100
    env = TaiwanStockTradingEnv(df=_make_df(n), randomize_start=True, min_episode_days=min_days)
    seen_steps = set()
    for seed in range(30):
        env.reset(seed=seed)
        seen_steps.add(env.current_step)
        # leaves at least min_episode_days rows after the start
        assert env.current_step <= n - 1 - min_days

    # sanity: randomization actually varies across seeds, not stuck at 0
    assert len(seen_steps) > 1


def test_randomize_start_falls_back_to_zero_when_df_too_short() -> None:
    env = TaiwanStockTradingEnv(df=_make_df(50), randomize_start=True, min_episode_days=100)
    env.reset(seed=7)
    assert env.current_step == 0


def test_state_and_peak_value_are_consistent_with_randomized_start_row() -> None:
    env = TaiwanStockTradingEnv(df=_make_df(300), randomize_start=True, min_episode_days=100)
    state, info = env.reset(seed=5)
    assert state.shape == (52,)
    expected_close = env.df.iloc[env.current_step]["close"]
    assert env.peak_value == pytest.approx(env.initial_balance + env.position * expected_close)
