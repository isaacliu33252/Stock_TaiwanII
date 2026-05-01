# ============================================================================
# Portfolio Data Loader - 投資組 合多股票資料下載器
# ============================================================================
"""
下載並整合所有持股的歷史數據，用於多智能體訓練和回測。

功能:
    1. 同時下載 8 檔股票的歷史數據
    2. 對齊交易日 (取交集)
    3. 計算各股票的技術指標
    4. 合併為統一的 DataFrame
"""

import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import warnings
import sys
import os

warnings.filterwarnings('ignore')

# 嘗試導入 config
try:
    PROJECT_ROOT = Path(__file__).parent
    sys.path.insert(0, str(PROJECT_ROOT))
    from portfolio_config import (
        ALL_TICKERS, PORTFOLIO_HOLDINGS,
        BACKTEST_START, BACKTEST_END,
        TRAIN_START, TRAIN_END
    )
    from config import TRAIN_START_DATE, TRAIN_END_DATE, TEST_START_DATE, TEST_END_DATE
except ImportError:
    # fallback
    ALL_TICKERS = ["0050.TW", "0056.TW", "00646.TW", "00679B.TWO",
                   "00713.TW", "00751B.TWO", "00878.TW", "2884.TW"]
    PORTFOLIO_HOLDINGS = {}
    BACKTEST_START = "2021-01-01"
    BACKTEST_END = "2024-12-31"
    TRAIN_START = "2015-01-01"
    TRAIN_END = "2020-12-31"


def download_all_stocks(
    tickers: List[str],
    start_date: str,
    end_date: str,
    interval: str = "1d",
    cache_dir: str = None
) -> Dict[str, pd.DataFrame]:
    """
    下載所有股票的歷史數據

    Args:
        tickers: 股票代碼列表
        start_date: 開始日期
        end_date: 結束日期
        interval: K線週期
        cache_dir: 快取目錄

    Returns:
        dict: {ticker: DataFrame} 的字典
    """
    if cache_dir is None:
        cache_dir = PROJECT_ROOT / "data" / "portfolio_cache"
    else:
        cache_dir = Path(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    print(f"[Portfolio Data Loader] 開始下載 {len(tickers)} 檔股票...")
    print(f"[Portfolio Data Loader] 日期區間: {start_date} ~ {end_date}")

    # TW/TWO mapping for Yahoo Finance
    YF_TICKER_MAP = {
        "00679B.TW": "00679B.TWO",
        "00751B.TW": "00751B.TWO",
    }

    for i, ticker in enumerate(tickers):
        cache_file = cache_dir / f"{ticker.replace('.', '_')}.parquet"

        # 嘗試從快取讀取
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                print(f"  [{i+1}/{len(tickers)}] {ticker} 從快取載入: {len(df)} 筆")
                results[ticker] = df
                continue
            except Exception:
                pass

        # 轉換為 Yahoo Finance ticker
        yf_ticker = YF_TICKER_MAP.get(ticker, ticker)
        
        # 下載
        print(f"  [{i+1}/{len(tickers)}] 下載 {ticker}... (YF: {yf_ticker})", end=" ", flush=True)
        try:
            yf_ticker_obj = yf.Ticker(yf_ticker)
            df = yf_ticker_obj.history(start=start_date, end=end_date, interval=interval)

            if df.empty:
                print("無數據")
                continue

            df = df.reset_index()
            if 'Datetime' in df.columns:
                df['Date'] = df['Datetime'].dt.tz_localize(None)
                df = df.drop(columns=['Datetime'])
            elif 'Date' in df.columns and str(df['Date'].dtype).startswith('datetime'):
                pass  # 已經是正確格式

            df.columns = [c.lower() for c in df.columns]

            # 確保必要欄位
            required = ['date', 'open', 'high', 'low', 'close', 'volume']
            for col in required:
                if col not in df.columns:
                    print(f"缺少欄位 {col}")
                    continue

            # 保存快取
            df.to_parquet(cache_file, index=False)

            print(f"{len(df)} 筆")
            results[ticker] = df

        except Exception as e:
            print(f"失敗: {e}")

    print(f"[Portfolio Data Loader] 完成，共 {len(results)} 檔股票")
    return results


def align_trading_days(stock_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    對齊所有股票的交易日 (取交集)

    這樣確保每個時間點所有股票都有數據。
    """
    # 取得每支股票的交易日
    trading_days_per_stock = {}
    for ticker, df in stock_data.items():
        if 'date' not in df.columns:
            continue
        df['date'] = pd.to_datetime(df['date'])
        trading_days_per_stock[ticker] = set(df['date'])

    # 取交集
    if not trading_days_per_stock:
        raise ValueError("沒有任何股票數據")

    common_days = set.intersection(*trading_days_per_stock.values())
    common_days = sorted(common_days)

    print(f"[align_trading_days] 共同交易日: {len(common_days)} 天")
    print(f"  {common_days[0]} ~ {common_days[-1]}")

    return pd.DataFrame({'date': common_days})


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    為股票數據添加技術指標
    """
    df = df.copy()

    # 收益率
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

    # 移動平均線
    for window in [5, 20, 60]:
        df[f'ma{window}'] = df['close'].rolling(window=window).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Bollinger Bands
    bb_window = 20
    df['bb_middle'] = df['close'].rolling(window=bb_window).mean()
    bb_std = df['close'].rolling(window=bb_window).std(ddof=1)
    df['bb_upper'] = df['bb_middle'] + 2 * bb_std
    df['bb_lower'] = df['bb_middle'] - 2 * bb_std

    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    # KDJ
    low_n = df['low'].rolling(window=9).min()
    high_n = df['high'].rolling(window=9).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-10) * 100
    df['kd_k'] = rsv.ewm(com=2).mean()
    df['kd_d'] = df['kd_k'].ewm(com=2).mean()
    df['kd_j'] = 3 * df['kd_k'] - 2 * df['kd_d']

    # 成交量變化
    df['volume_change'] = df['volume'].pct_change()
    df['volume_ma5'] = df['volume'].rolling(window=5).mean()

    return df


def merge_portfolio_data(
    stock_data: Dict[str, pd.DataFrame],
    add_indicators: bool = True
) -> pd.DataFrame:
    """
    合併所有股票數據為一個 DataFrame

    輸出格式:
        date, ticker, open, high, low, close, volume, turnover,
        returns, log_returns, ma5, ma20, ma60, rsi, macd, ...
    """
    all_dfs = []

    for ticker, df in stock_data.items():
        df = df.copy()
        if 'date' not in df.columns:
            continue

        df['date'] = pd.to_datetime(df['date'])

        if add_indicators:
            df = add_technical_indicators(df)

        df['ticker'] = ticker

        # 重新排列欄位
        cols = ['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']
        other_cols = [c for c in df.columns if c not in cols]
        df = df[cols + other_cols]

        all_dfs.append(df)

    merged = pd.concat(all_dfs, ignore_index=True)
    merged = merged.sort_values(['ticker', 'date']).reset_index(drop=True)

    print(f"[merge_portfolio_data] 合併後總共 {len(merged)} 筆")
    return merged


def calculate_portfolio_weights(current_prices: Dict[str, float]) -> Dict[str, float]:
    """
    根據 current_prices 和持股數計算各股票權重
    """
    holdings = PORTFOLIO_HOLDINGS
    values = {}
    total = 0

    for ticker, info in holdings.items():
        shares = info['shares']
        price = current_prices.get(ticker, 0)
        value = shares * price
        values[ticker] = value
        total += value

    if total == 0:
        return {t: 1.0/len(values) for t in values}

    return {t: v / total for t, v in values.items()}


# =============================================================================
# 主程式：下載並準備資料
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='下載投資組合歷史數據')
    parser.add_argument('--start', type=str, default='2015-01-01')
    parser.add_argument('--end', type=str, default='2024-12-31')
    parser.add_argument('--mode', type=str, default='all',
                        choices=['all', 'train', 'test'])
    args = parser.parse_args()

    if args.mode == 'train':
        start, end = TRAIN_START_DATE, TRAIN_END_DATE
    elif args.mode == 'test':
        start, end = TEST_START_DATE, TEST_END_DATE
    else:
        start, end = args.start, args.end

    print("=" * 60)
    print("投資組合數據下載")
    print("=" * 60)
    print(f"股票: {ALL_TICKERS}")
    print(f"日期: {start} ~ {end}")
    print("=" * 60)

    # 下載
    stock_data = download_all_stocks(ALL_TICKERS, start, end)

    # 合併
    merged = merge_portfolio_data(stock_data)

    # 儲存
    output_file = PROJECT_ROOT / "data" / "portfolio_data.parquet"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(output_file, index=False)
    print(f"\n數據已儲存至: {output_file}")
