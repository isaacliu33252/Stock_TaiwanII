"""
================================================================================
FinRL v2 台股量化交易系統 - 數據層初始化
================================================================================
這個模組包含所有數據處理相關的功能：

主要功能：
    1. data_loader - 台股數據取得（Yahoo Finance / TWSE API）
    2. technical_indicators - TA-Lib 技術指標計算
    3. stock_db - SQLite 數據庫管理

台股特殊規則：
    - 股票代碼格式: 2330.TW (Yahoo Finance 格式)
    - 交易單位: 1000 股為一張
    - 漲跌停限制: 10%
    - T+2 交割制度

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

from .data_loader import (
    TaiwanStockDataLoader,
    fetch_stock_data,
    fetch_institutional_data,
    load_cached_data,
    save_to_cache,
)

from .technical_indicators import (
    TechnicalIndicators,
    calculate_ma,
    calculate_macd,
    calculate_rsi,
    calculate_kdj,
    calculate_bollinger_bands,
)

from .stock_db import (
    StockDatabase,
    init_database,
    query_stock_data,
    save_stock_data,
)

__all__ = [
    # Data Loader
    "TaiwanStockDataLoader",
    "fetch_stock_data",
    "fetch_institutional_data",
    "load_cached_data",
    "save_to_cache",
    # Technical Indicators
    "TechnicalIndicators",
    "calculate_ma",
    "calculate_macd",
    "calculate_rsi",
    "calculate_kdj",
    "calculate_bollinger_bands",
    # Stock Database
    "StockDatabase",
    "init_database",
    "query_stock_data",
    "save_stock_data",
]