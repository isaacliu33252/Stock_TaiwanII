"""
Legacy compatibility layer for `FinRL.backtest`.

Canonical implementation lives in `FinRL.backtesting.backtest_engine`.
"""

from .backtest_engine import BacktestConfig, BacktestEngine, BacktestResult

__all__ = ["BacktestEngine", "BacktestConfig", "BacktestResult"]
