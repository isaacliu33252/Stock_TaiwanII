# ============================================================================
# FinRL 台股交易系統 - Data 模組
# ============================================================================
"""
本模組負責資料處理與取得。

功能特色：
- 從 Yahoo Finance 取得台股歷史資料 (data_loader.py)
- 從 TWSE API 取得三大法人資料 (data_loader.py)
- 技術指標計算（使用 TA-Lib 或 Pandas） (technical_indicators.py)

使用方式：
    from data.technical_indicators import TechnicalIndicators
    
    ti = TechnicalIndicators(df)
    df = ti.calculate_all()
"""

# 匯出版本資訊
__version__ = "1.0.0"

# 匯出主要類別和函數
from .data_loader import (
    TaiwanStockDataLoader,
    fetch_stock_data,
    fetch_institutional_data,
)

from .technical_indicators import (
    TechnicalIndicators,
    add_technical_indicators,
)

__all__ = [
    "TaiwanStockDataLoader",
    "fetch_stock_data",
    "fetch_institutional_data",
    "TechnicalIndicators",
    "add_technical_indicators",
]