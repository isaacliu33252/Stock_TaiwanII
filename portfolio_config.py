# ============================================================================
# Portfolio Configuration - 投資組合配置
# ============================================================================
# 自動從 taiwan_stock_.xlsx 讀取持股資料
# ============================================================================

import pandas as pd
from pathlib import Path

_EXCEL_PATH = Path(__file__).parent / "taiwan_stock_.xlsx"

# 代碼對照表（Excel 欄位名 → Yahoo Finance 代碼）
_TICKER_MAP = {
    "0050":  "0050.TW",
    "0056":  "0056.TW",
    "00646": "00646.TW",
    "00679B": "00679B.TWO",
    "00713": "00713.TW",
    "00751B": "00751B.TWO",
    "00878": "00878.TW",
    "2884":  "2884.TW",
}

# 名字對照表
_NAME_MAP = {
    "0050":  "元大台灣50",
    "0056":  "元大高股息",
    "00646": "元大S&P500",
    "00679B": "元大美債20年",
    "00713": "元大台灣高息低波",
    "00751B": "元大AAA至A公司債",
    "00878": "國泰永續高股息",
    "2884":  "玉山金",
}

def _load_holdings() -> dict:
    """從 Excel 檔讀取持股資料，自動對應 Yahoo Finance 代碼。"""
    df = pd.read_excel(_EXCEL_PATH, header=0)
    row = df.iloc[0]

    holdings = {}
    for col in df.columns[1:]:  # 跳過第一欄（標籤欄）
        # 從欄位名解析代碼（如 "元大台灣50 \n0050" → "0050"）
        code = col.split("\n")[-1].strip()
        shares = int(row[col])

        yf_ticker = _TICKER_MAP.get(code, code + ".TW")
        holdings[yf_ticker] = {
            "name":         _NAME_MAP.get(code, code),
            "shares":       shares,
            "cost_basis":   None,
            "ticker_yf":    yf_ticker,
            "ticker_local": code,
        }
    return holdings

PORTFOLIO_HOLDINGS = _load_holdings()

# 所有股票代碼列表
ALL_TICKERS = list(PORTFOLIO_HOLDINGS.keys())

# 等權重初始配置
INITIAL_WEIGHTS = None

# 最小交易單位 (台股 = 1000股/張)
TRADE_UNIT = 1000

# 是否為 ETF
ETF_TICKERS = [t for t in ALL_TICKERS if t != "2884.TW"]
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
