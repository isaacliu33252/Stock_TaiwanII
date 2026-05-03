# ============================================================================
# FinRL 台股交易系統 - Results 模組
# ============================================================================
"""
本模組提供結果追蹤和視覺化功能。

功能特色：
- 結果追蹤 (ResultTracker)
- 視覺化繪圖 (TradingPlotter)
- 績效指標儀表板
- PyFolio tearsheet 產生

使用方式：
    from .results import ResultTracker, TradingPlotter
    
    # 追蹤結果
    tracker = ResultTracker()
    tracker.save_result(result, config)
    
    # 繪製圖表
    plotter = TradingPlotter()
    plotter.plot_equity_curve(equity_curve)

作者: FinRL量化交易專家
"""

# 版本資訊
__version__ = "1.0.0"

# 匯出主要類別
from .results.plotter import TradingPlotter, create_plotter
from .results.result_tracker import ResultTracker, create_result_tracker

# 方便直接匯入
__all__ = [
    "TradingPlotter",
    "create_plotter",
    "ResultTracker",
    "create_result_tracker",
]