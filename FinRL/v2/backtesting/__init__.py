"""
================================================================================
FinRL v2 台股量化交易系統 - 回測層初始化
================================================================================
這個模組包含回測和績效評估功能：

主要功能：
    1. performance_metrics - 績效指標計算（Sharpe Ratio, Max Drawdown, Win Rate）
    2. backtest_engine - 回測引擎封裝
    3. visualizer - 視覺化模組（Equity Curve, Drawdown Chart）

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

from .performance_metrics import (
    PerformanceMetrics,
    PerformanceResult,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor,
    calculate_sortino_ratio,
)

from .backtest_engine import (
    BacktestEngine,
    BacktestConfig,
    run_backtest,
)

from .visualizer import (
    Visualizer,
    plot_equity_curve,
    plot_drawdown,
    plot_returns_distribution,
)

__all__ = [
    # Performance Metrics
    "PerformanceMetrics",
    "calculate_sharpe_ratio",
    "calculate_max_drawdown",
    "calculate_win_rate",
    "calculate_profit_factor",
    "calculate_sortino_ratio",
    # Backtest Engine
    "BacktestEngine",
    "BacktestConfig",
    "run_backtest",
    # Visualizer
    "Visualizer",
    "plot_equity_curve",
    "plot_drawdown",
    "plot_returns_distribution",
]