"""2026-08-11 fix: FinRL/v2/environments/taiwan_stock_env.py's `_execute_trade`
computed `executed_shares` from position capacity alone (`min(1000, available)`)
*before* checking whether cash was sufficient, and never reset it to 0 when
the cash check failed. `step()` logs a `trade_history` entry whenever
`executed_shares != 0`, so every cash-insufficient buy attempt was logged as
a real, recently-executed trade -- even though the portfolio's actual
position/cash never changed. This corrupted two things: the trade audit
trail (`env.trade_history`), and `_calculate_reward()`'s "trade penalty"
component, which looks up `self.trade_history[-1]` to penalize recent
trading -- so a policy that kept trying (and failing) to buy got penalized
as if it were actually trading every step. Discovered while pilot-testing a
LayerNorm-bottleneck SAC idea (arXiv:2606.10448 follow-up, see
research/shadow/layernorm_bottleneck_sac_trace_20260811.json): a trained
policy showed 617 `trade_history` entries but only 30 real position changes
over a 617-day backtest. The root-level `environments/taiwan_stock_env.py`
already has this exact fix (see
tests/test_taiwan_stock_env_trade_executed_info.py's
`test_trade_executed_false_when_trade_fails`) -- this test covers the
FinRL v2 variant, which had not received the same fix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from FinRL.v2.environments.taiwan_stock_env import TaiwanStockTradingEnv


def _make_df(n_days: int = 5, price: float = 1000.0) -> pd.DataFrame:
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


def test_cash_insufficient_buy_does_not_log_phantom_trade():
    # Price high enough that a single 1000-share buy exceeds initial_capital,
    # so every BUY_1000 attempt must fail on the cash check.
    df = _make_df(n_days=5, price=100_000.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="discrete")
    env.reset()

    for _ in range(3):
        obs, reward, terminated, truncated, info = env.step(1)  # BUY_1000
        if terminated or truncated:
            break

    assert env.portfolio.position == 0
    assert env.portfolio.cash == pytest.approx(1_000_000.0, rel=1e-9)
    assert env.trade_history == [], (
        "cash-insufficient buy attempts must not be logged as executed trades"
    )
    assert env.portfolio.total_trades == 0


def test_successful_buy_still_logs_a_real_trade():
    df = _make_df(n_days=5, price=100.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="discrete")
    env.reset()

    env.step(1)  # BUY_1000, affordable at price=100

    assert env.portfolio.position == 1000
    assert len(env.trade_history) == 1
    assert env.trade_history[0].shares == 1000
    assert env.portfolio.total_trades == 1


def test_trade_penalty_not_triggered_by_failed_buy_attempts():
    """_calculate_reward()'s trade-penalty term reads trade_history[-1]; a
    string of failed buy attempts must not make it look like the agent just
    traded."""
    df = _make_df(n_days=10, price=100_000.0)
    env = TaiwanStockTradingEnv(df=df, initial_capital=1_000_000.0, mode="discrete", reward_mode="composite")
    env.reset()

    for _ in range(5):
        obs, reward, terminated, truncated, info = env.step(1)  # always-failing BUY_1000
        if terminated or truncated:
            break

    assert env.trade_history == []
