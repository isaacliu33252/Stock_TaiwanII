# ============================================================================
# FinRL 台股交易系統 - Data 模組
# ============================================================================
"""
本模組負責資料處理與取得。

功能特色：
- 從 Yahoo Finance 取得台股歷史資料 (data_loader.py)
- 從 TWSE API 取得三大法人資料 (data_loader.py)
- 技術指標計算（使用 TA-Lib 或 Pandas） (technical_indicators.py)
- 資料清洗與標準化 (data_processor.py)
- 52維 RL 狀態特徵工程 (feature_engineering.py)
- 訓練/測試資料分割 (data_processor.py)

使用方式：
    from FinRL.data import DataProcessor, TaiwanStockDataLoader
    
    # 載入資料
    loader = TaiwanStockDataLoader()
    df = loader.download_price_data('2330', '2020-01-01', '2024-12-31')
    
    # 處理資料
    processor = DataProcessor()
    df = processor.clean_data(df)
    df = processor.normalize_features(df)
    
    # 計算技術指標
    from FinRL.data import TechnicalIndicators
    ti = TechnicalIndicators(df)
    df = ti.calculate_all()
    
    # 建立 RL 狀態特徵
    from FinRL.data import FeatureEngineering
    fe = FeatureEngineering()
    state = fe.build_state(df, position_info)
"""

# 匯出版本資訊
__version__ = "1.0.0"

# 匯出主要類別和函數

# data_loader.py - 資料載入
from FinRL.data.data_loader import (
    TaiwanStockDataLoader,
    fetch_stock_data,
    fetch_institutional_data,
    fetch_dividend_data,
    get_trading_dates,
    is_trading_day,
    load_taiwan_stock_data,
)

# data_processor.py - 資料處理
from FinRL.data.data_processor import (
    DataProcessor,
    quick_clean,
    quick_normalize,
)

# technical_indicators.py - 技術指標計算 (完整版)
from FinRL.data.technical_indicators import (
    TechnicalIndicators,
    add_technical_indicators,
)

# technical_analysis.py - 技術指標計算 (簡化版，工廠相容)
from FinRL.data.technical_analysis import (
    TechnicalIndicators as TAIndicators,
    calculate_all_indicators,
)

# feature_engineering.py - 52維狀態特徵工程
from FinRL.data.feature_engineering import (
    FeatureEngineering,
    build_state_vector,
    get_feature_names,
    # 特徵維度常數
    PRICE_FEATURES,
    TECHNICAL_FEATURES,
    PATTERN_FEATURES,
    FUNDAMENTAL_FEATURES,
    POSITION_FEATURES,
    MARKET_SENTIMENT,
)

# 便利直接匯入
__all__ = [
    # 資料載入
    "TaiwanStockDataLoader",
    "fetch_stock_data",
    "fetch_institutional_data",
    "fetch_dividend_data",
    "get_trading_dates",
    "is_trading_day",
    "load_taiwan_stock_data",
    # 資料處理
    "DataProcessor",
    "quick_clean",
    "quick_normalize",
    # 技術指標
    "TechnicalIndicators",
    "add_technical_indicators",
    "TAIndicators",
    "calculate_all_indicators",
    # 特徵工程
    "FeatureEngineering",
    "build_state_vector",
    "get_feature_names",
    # 特徵常數
    "PRICE_FEATURES",
    "TECHNICAL_FEATURES",
    "PATTERN_FEATURES",
    "FUNDAMENTAL_FEATURES",
    "POSITION_FEATURES",
    "MARKET_SENTIMENT",
]