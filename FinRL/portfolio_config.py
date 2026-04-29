# ============================================================================
# Portfolio Configuration - 投資組合配置
# ============================================================================
# 用戶持股明細
#
# 更新日期: 2026-04-28
#
# 格式:
#   ticker: Yahoo Finance 格式代碼
#   name: 中文名稱
#   shares: 持有股數
#   cost_basis: 成本價 (可選，填入後可用於計算未實現損益)

PORTFOLIO_HOLDINGS = {
    "0050.TW": {
        "name": "元大台灣50",
        "shares": 1036,
        "cost_basis": None,
        "ticker_yf": "0050.TW",
        "ticker_local": "0050",
    },
    "0056.TW": {
        "name": "元大高股息",
        "shares": 16429,
        "cost_basis": None,
        "ticker_yf": "0056.TW",
        "ticker_local": "0056",
    },
    "00646.TW": {
        "name": "元大S&P500",
        "shares": 32,
        "cost_basis": None,
        "ticker_yf": "00646.TW",
        "ticker_local": "00646",
    },
    # 00679B 元大美債20年 - Yahoo Finance 無法取得資料（可能已下市或改碼）
    "00713.TW": {
        "name": "元大台灣高息低波",
        "shares": 4686,
        "cost_basis": None,
        "ticker_yf": "00713.TW",
        "ticker_local": "00713",
    },
    # 00751B 元大AAA至A公司債 - Yahoo Finance 無法取得資料（可能已下市或改碼）
    "00878.TW": {
        "name": "國泰永續高股息",
        "shares": 13836,
        "cost_basis": None,
        "ticker_yf": "00878.TW",
        "ticker_local": "00878",
    },
    "2884.TW": {
        "name": "玉山金",
        "shares": 20,
        "cost_basis": None,
        "ticker_yf": "2884.TW",
        "ticker_local": "2884",
    },
}

# 所有股票代碼列表
ALL_TICKERS = list(PORTFOLIO_HOLDINGS.keys())

# 等權重初始配置
INITIAL_WEIGHTS = None

# 最小交易單位 (台股 = 1000股/張)
TRADE_UNIT = 1000

# 是否為 ETF
ETF_TICKERS = ["0050.TW", "0056.TW", "00646.TW", "00713.TW", "00878.TW"]
STOCK_TICKERS = ["2884.TW"]

# ============================================================================
# 多智能體訓練設定
# ============================================================================

AGENT_TYPE = "ppo"
PARALLEL_TRAINING = True
LEARNING_RATE = 3e-4
TIMESTEPS_PER_STOCK = 100_000
EVAL_FREQUENCY = 5000
SAVE_FREQUENCY = 10000

# ============================================================================
# 投資組合回測設定
# ============================================================================

BACKTEST_INITIAL_CASH = 1_000_000.0
BACKTEST_START = "2021-01-01"
BACKTEST_END = "2024-12-31"
COMMISSION_RATE = 0.001425
TRANSACTION_TAX_RATE = 0.003
ETF_TAX_RATE = 0.001
RISK_FREE_RATE = 0.02
BENCHMARK_TICKER = "0050.TW"
