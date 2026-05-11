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
    from FinRL.data import FeatureEngineer
    fe = FeatureEngineer()
    state = fe.build_state(df, position_info)
"""

# 匯出版本資訊
__version__ = "1.0.0"

# ─────────────────────────────────────────────────────────────────────────────
# 匯出主要類別和函數
# 注意：我們使用相對 import 或直接 import，避免 FinRL. 前綴的路徑問題
# ─────────────────────────────────────────────────────────────────────────────

# data_loader.py - 資料載入（使用相對 import 或 try/except 避免失敗）
try:
    from .data_loader import (
        TaiwanStockDataLoader,
        fetch_stock_data,
        fetch_institutional_data,
        fetch_dividend_data,
        get_trading_dates,
        is_trading_day,
        load_taiwan_stock_data,
    )
except ImportError:
    # 當 FinRL 未安裝時（直接執行 script），使用本地匯入
    from data.data_loader import (
        TaiwanStockDataLoader,
        fetch_stock_data,
        fetch_institutional_data,
        fetch_dividend_data,
        get_trading_dates,
        is_trading_day,
        load_taiwan_stock_data,
    )

# data_processor.py - 資料處理
try:
    from .data_processor import (
        DataProcessor,
        quick_clean,
        quick_normalize,
    )
except ImportError:
    try:
        from data.data_processor import (
            DataProcessor,
            quick_clean,
            quick_normalize,
        )
    except ImportError:
        DataProcessor = None
        quick_clean = None
        quick_normalize = None

# technical_indicators.py - 技術指標計算 (完整版)
try:
    from .technical_indicators import (
        TechnicalIndicators,
        add_technical_indicators,
    )
except ImportError:
    try:
        from data.technical_indicators import (
            TechnicalIndicators,
            add_technical_indicators,
        )
    except ImportError:
        TechnicalIndicators = None
        add_technical_indicators = None

# technical_analysis.py - 技術指標計算 (簡化版，工廠相容)
try:
    from .technical_analysis import (
        TechnicalIndicators as TAIndicators,
        calculate_all_indicators,
    )
except ImportError:
    try:
        from data.technical_analysis import (
            TechnicalIndicators as TAIndicators,
            calculate_all_indicators,
        )
    except ImportError:
        TAIndicators = None
        calculate_all_indicators = None

# feature_engineering.py - 52維狀態特徵工程
try:
    from .feature_engineering import (
        FeatureEngineer,
        engineer_features,
    )
except ImportError:
    try:
        from data.feature_engineering import (
            FeatureEngineer,
            engineer_features,
        )
    except ImportError:
        FeatureEngineer = None
        engineer_features = None

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
    "FeatureEngineer",
    "engineer_features",
]