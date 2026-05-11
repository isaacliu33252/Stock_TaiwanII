"""
台股交易規則設定 (Taiwan Stock Trading Configuration)
================================================================================
定義台股特有的交易規則和系統預設值。

台股特殊規則:
    - 涨跌停 10%: 個股單日最大漲跌幅不得超過 10%
    - T+2 交割: 當日買入的股票需於第二個交易日完成交割
    - 最小交易單位: 1000 股 (一張 = 1000 股)
    - 交易時間: 09:00 - 13:30 (午間不休市)
    - 主力成本計算: 三大法人買賣資訊
"""

# === 台股交易規則設定 (不改動) ===
TAIWAN_STOCK_CONFIG = {
    # --- 基本規則 ---
    'trade_unit': 1000,              # 最小交易單位: 1000 股 (一張)
    'max_position': 4000,            # 最大持有股數: 4000 股 (4 張)
    'price_limit': 0.10,             # 涨跌停限制: 10% (0.10)
    
    # --- 交易成本 ---
    'commission_rate': 0.0015,        # 券商佣金: 0.15% (0.0015)
    'tax_rate': 0.003,               # 證交稅: 0.3% (0.003) (賣出時收取)
    'slippage': 0.001,               # 滑價: 0.1% (0.001) 預估
    
    # --- 風險控制 ---
    'stop_loss_threshold': 0.10,     # 停損門檻: 虧損 10% 強制停損
    'daily_loss_limit': 0.15,       # 單日最大虧損: 15% 停止交易
    'max_trades_per_day': 3,         # 每日最大交易次數
    
    # --- T+2 交割設定 ---
    'settlement_days': 2,            # T+2 交割制度
    
    # --- 交易時間 ---
    'trading_hours': {
        'open': '09:00',            # 開盤時間
        'close': '13:30',           # 收盤時間
    },
    
    # --- 市場代碼 ---
    'market': 'TWSE',               # 台灣證券交易所
    'currency': 'TWD',              # 新台幣
    
    # --- 初始資金 ---
    'initial_balance': 1_000_000,    # 初始資金: 100 萬 TWD
}

# === 狀態空間維度設定 ===
STATE_CONFIG = {
    # 狀態向量總維度
    'state_dim': 52,
    
    # 各類特徵維度 (合計 52)
    'price_features_dim': 6,        # 價格特徵
    'technical_features_dim': 20,   # 技術指標特徵
    'pattern_features_dim': 8,      # 型態特徵
    'fundamental_features_dim': 8,  # 基本面/法人特徵
    'position_features_dim': 6,     # 部位特徵
    'sentiment_features_dim': 4,    # 市場情緒特徵
}

# === 動作空間設定 ===
ACTION_CONFIG = {
    'num_actions': 5,               # 離散動作數量
    'action_names': {
        0: 'HOLD',                  # 觀望，不動作
        1: 'BUY_1000',              # 買入 1000 股
        2: 'SELL_1000',             # 賣出 1000 股
        3: 'CLOSE_POSITION',        # 清倉 (全部賣出)
        4: 'STOP_LOSS',             # 停損賣出
    },
}

# === 資料路徑設定 ===
DATA_CONFIG = {
    # 資料目錄
    'data_dir': './data',
    'cache_dir': './data/cache',
    'raw_dir': './data/raw',
    'processed_dir': './data/processed',
    
    # 現有 Stock_taiwan2 資料路徑 (用於整合)
    'stock_taiwan2_path': '../python-and-Taiwan-stock-market-main/Trading',
    
    # 休市日檔案
    'holiday_file': '../python-and-Taiwan-stock-market-main/Trading/holiday.xlsx',
    
    # 輸出目錄
    'output_dir': './results',
    'model_dir': './results/models',
    'log_dir': './results/logs',
    'plot_dir': './results/plots',
}

# === 回測設定 ===
BACKTEST_CONFIG = {
    'start_date': '2000-01-01',     # 回測開始日期
    'end_date': '2010-12-31',       # 回測結束日期
    
    # 測試集比例
    'test_ratio': 0.2,             # 20% 作為測試集
    
    # 基準設定
    'benchmark': '0050.TW',        # 台灣50作為基準 (元大台灣50 ETF)
}

# === 技術指標預設參數 ===
INDICATOR_CONFIG = {
    # MA 均線期間設定
    'ma_periods': [3, 5, 10, 20, 60, 120, 240],
    
    # MACD 參數
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    
    # RSI 期間
    'rsi_period': 14,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    
    # KDJ 期間
    'kdj_period': 9,
    'kdj_smooth_k': 3,
    'kdj_smooth_d': 3,
    
    # Bollinger Bands
    'bb_period': 20,
    'bb_std': 2,
    
    # ATR 期間
    'atr_period': 14,
    
    # 威廉指標
    'williams_period': 14,
}

# === 資料來源設定 ===
DATA_SOURCE_CONFIG = {
    # Yahoo Finance (主要來源)
    'yahoo': {
        'base_url': 'https://query1.finance.yahoo.com/v8/finance',
        'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',
        'timeout': 30,
    },
    
    # TWSE (台灣證券交易所)
    'twse': {
        'base_url': 'https://www.twse.com.tw',
        'corp_url': 'https://www.twse.com.tw/fund/T86',  # 三大法人
        'timeout': 30,
    },
    
    # TWSE 股票代碼格式
    # 台股代碼: 2330 (台積電) -> Yahoo Finance: 2330.TW
    'symbol_suffix': '.TW',
    
    # 快取設定
    'cache_expiry_days': 1,         # 數據快取過期天數
    'max_retries': 3,              # 最大重試次數
}
