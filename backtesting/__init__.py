# ============================================================================
# FinRL 台股交易系統 - Backtesting 模組
# ============================================================================
"""
本模組提供回測功能，用於評估交易策略的歷史表現。

功能特色：
- 完整的回測引擎 (BacktestEngine)
- 績效指標計算 (calculate_sharpe_ratio, calculate_max_drawdown 等)
- 台股特殊規則處理（涨跌停、T+2、1000股單位）
- 交易歷史記錄與分析
- PyFolio 整合

使用方式：
    from FinRL.backtesting import BacktestEngine, calculate_all_metrics
    
    # 建立回測引擎
    bt = BacktestEngine(env, agent, initial_balance=1_000_000)
    
    # 執行回測
    result = bt.run(data)
    
    # 取得績效指標
    metrics = result['metrics']

作者: FinRL量化交易專家
"""

# 版本資訊
__version__ = "1.0.0"
__author__ = "FinRL量化交易專家"

# 匯出主要類別
from FinRL.backtesting.backtest import BacktestEngine
from FinRL.backtesting.backtest import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor,
    calculate_calmar_ratio,
    calculate_sortino_ratio,
    calculate_annual_return,
)

# 匯出績效指標模組
from FinRL.backtesting.performance_metrics import (
    calculate_all_metrics,
    format_metrics,
    calculate_volatility,
    calculate_win_loss_stats,
    calculate_max_drawdown_duration,
    calculate_max_consecutive_loss,
    calculate_avg_holding_days,
)

# 方便直接匯入
__all__ = [
    # 主要類別
    "BacktestEngine",
    
    # 績效指標計算函式
    "calculate_sharpe_ratio",
    "calculate_max_drawdown",
    "calculate_win_rate",
    "calculate_profit_factor",
    "calculate_calmar_ratio",
    "calculate_sortino_ratio",
    "calculate_annual_return",
    "calculate_volatility",
    
    # 綜合計算
    "calculate_all_metrics",
    "format_metrics",
    
    # 進階指標
    "calculate_win_loss_stats",
    "calculate_max_drawdown_duration",
    "calculate_max_consecutive_loss",
    "calculate_avg_holding_days",
]