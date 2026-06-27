"""
Legacy compatibility wrapper for the old `FinRL.backtest.backtest_engine` path.
"""

from ..backtesting.backtest_engine import BacktestConfig, BacktestEngine, BacktestResult

__all__ = ["BacktestEngine", "BacktestConfig", "BacktestResult"]
