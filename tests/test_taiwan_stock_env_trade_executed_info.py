from __future__ import annotations

import numpy as np
import pandas as pd

from environments.taiwan_stock_env import TaiwanStockTradingEnv


def _make_flat_df(n: int = 10, price: float = 100.0) -> pd.DataFrame:
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


def test_trade_executed_true_when_buy_succeeds() -> None:
    """Regression: portfolio_train_v2.py::EnhancedStockTrainer.backtest() reads
    info['trade_executed'] to count trades. This key never existed on the env's
    step() info dict before, so num_trades was silently always 0 regardless of
    whether the model actually traded -- discovered while sanity-checking a
    backtest report during an alpha-reward vs v3 comparison run."""
    env = TaiwanStockTradingEnv(df=_make_flat_df())
    env.reset()
    _, _, _, _, info = env.step(1)  # BUY_1000, should succeed
    assert info["trade_executed"] is True


def test_trade_executed_false_on_hold() -> None:
    env = TaiwanStockTradingEnv(df=_make_flat_df())
    env.reset()
    _, _, _, _, info = env.step(0)  # HOLD
    assert info["trade_executed"] is False


def test_trade_executed_false_when_trade_fails() -> None:
    env = TaiwanStockTradingEnv(df=_make_flat_df(), initial_balance=0.0)
    env.reset()
    _, _, _, _, info = env.step(1)  # BUY_1000, should fail (no cash)
    assert info["trade_executed"] is False
