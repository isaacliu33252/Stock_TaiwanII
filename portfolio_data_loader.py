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
    BACKTEST_START = "2000-01-01"
    BACKTEST_END = "2010-12-31"
    TRAIN_START = "1990-01-01"
    TRAIN_END = "2000-12-31"


MARKET_TICKER = "^TWII"
MARKET_FEATURE_COLUMNS = [
    "twse_index_return",
    "twse_index_volume_change",
    "sector_correlation",
    "market_volatility",
]
MARKET_RAW_COLUMNS = [
    "twse_index_return_raw",
    "twse_index_volume_change_raw",
    "market_volatility_raw",
]


def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "datetime" in df.columns and "date" not in df.columns:
        df["date"] = df["datetime"]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        if getattr(df["date"].dt, "tz", None) is not None:
            df["date"] = df["date"].dt.tz_localize(None)
        df["date"] = df["date"].dt.normalize()
    return df


def _rolling_zscore(series: pd.Series, window: int = 60, min_periods: int = 20) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std().replace(0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def download_market_features(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    cache_dir: str = None,
) -> Optional[pd.DataFrame]:
    """Download TWSE index data and derive market features."""
    if cache_dir is None:
        cache_dir = PROJECT_ROOT / "data" / "portfolio_cache"
    else:
        cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    safe_start = start_date.replace("-", "")
    safe_end = end_date.replace("-", "")
    cache_file = cache_dir / f"TWII_{safe_start}_{safe_end}_{interval}_market_v2.parquet"

    if cache_file.exists():
        try:
            market = pd.read_parquet(cache_file)
            return _normalize_date_column(market)
        except Exception:
            pass

    print(f"[Portfolio Data Loader] 下載大盤 {MARKET_TICKER}...", end=" ", flush=True)
    try:
        market = yf.Ticker(MARKET_TICKER).history(start=start_date, end=end_date, interval=interval)
        if market.empty:
            print("無數據")
            return None

        market = market.reset_index()
        market.columns = [c.lower() for c in market.columns]
        market = _normalize_date_column(market)
        market = market.rename(columns={"close": "twse_close", "volume": "twse_volume"})

        market["twse_index_return_raw"] = (
            pd.to_numeric(market["twse_close"], errors="coerce").pct_change().fillna(0.0).clip(-0.2, 0.2)
        )
        vol_change = pd.to_numeric(market["twse_volume"], errors="coerce").pct_change()
        market["twse_index_volume_change_raw"] = (
            vol_change.replace([np.inf, -np.inf], 0.0).fillna(0.0).clip(-5.0, 5.0)
        )
        market["market_volatility_raw"] = (
            market["twse_index_return_raw"].rolling(20, min_periods=5).std().fillna(0.0).clip(0.0, 1.0)
        )

        market["twse_index_return"] = (market["twse_index_return_raw"] * 10.0).clip(-2.0, 2.0)
        market["twse_index_volume_change"] = market["twse_index_volume_change_raw"].clip(-2.0, 2.0)
        market["market_volatility"] = _rolling_zscore(market["market_volatility_raw"]).clip(-3.0, 3.0)

        out = market[["date"] + MARKET_RAW_COLUMNS + [
            "twse_index_return",
            "twse_index_volume_change",
            "market_volatility",
        ]].copy()
        out.to_parquet(cache_file, index=False)
        print(f"{len(out)} 筆")
        return out
    except Exception as e:
        print(f"失敗: {e}")
        return None


def add_market_features(df: pd.DataFrame, market: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Merge market features into one stock dataframe."""
    out = _normalize_date_column(df)
    if market is None or market.empty:
        return out

    drop_cols = [c for c in MARKET_FEATURE_COLUMNS + MARKET_RAW_COLUMNS if c in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols)

    market_cols = ["date"] + MARKET_RAW_COLUMNS + [
        "twse_index_return",
        "twse_index_volume_change",
        "market_volatility",
    ]
    out = out.merge(market[market_cols], on="date", how="left")
    for col in market_cols[1:]:
        out[col] = pd.to_numeric(out[col], errors="coerce").ffill().fillna(0.0)

    stock_return = pd.to_numeric(out["close"], errors="coerce").pct_change()
    out["sector_correlation"] = (
        stock_return.rolling(20, min_periods=5)
        .corr(out["twse_index_return_raw"])
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
        .clip(-1.0, 1.0)
    )
    return out


def add_long_horizon_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add slow trend/risk features that help ETF holding decisions."""
    out = _normalize_date_column(df)
    if "close" not in out.columns:
        return out

    close = pd.to_numeric(out["close"], errors="coerce")
    for window in (60, 120, 240):
        ma_col = f"ma{window}"
        if ma_col not in out.columns:
            out[ma_col] = close.rolling(window, min_periods=max(5, window // 4)).mean()

    out["close_ma120_ratio"] = (close / out["ma120"] - 1.0).replace([np.inf, -np.inf], 0.0)
    out["close_ma240_ratio"] = (close / out["ma240"] - 1.0).replace([np.inf, -np.inf], 0.0)
    out["ma60_ma240_ratio"] = (out["ma60"] / out["ma240"] - 1.0).replace([np.inf, -np.inf], 0.0)
    out["momentum_63"] = close.pct_change(63)
    out["momentum_126"] = close.pct_change(126)
    out["momentum_252"] = close.pct_change(252)

    rolling_high = close.rolling(252, min_periods=60).max()
    rolling_low = close.rolling(252, min_periods=60).min()
    out["high_252_position"] = ((close - rolling_low) / (rolling_high - rolling_low)).replace([np.inf, -np.inf], 0.0)

    rolling_peak_63 = close.rolling(63, min_periods=20).max()
    out["rolling_mdd_63"] = (close / rolling_peak_63 - 1.0).replace([np.inf, -np.inf], 0.0)

    long_cols = [
        "close_ma120_ratio",
        "close_ma240_ratio",
        "ma60_ma240_ratio",
        "momentum_63",
        "momentum_126",
        "momentum_252",
        "high_252_position",
        "rolling_mdd_63",
    ]
    for col in long_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).clip(-3.0, 3.0)

    return out


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

    market = download_market_features(start_date, end_date, interval=interval, cache_dir=str(cache_dir))

    for i, ticker in enumerate(tickers):
        safe_ticker = ticker.replace('.', '_')
        safe_start = start_date.replace('-', '')
        safe_end = end_date.replace('-', '')
        cache_file = cache_dir / f"{safe_ticker}_{safe_start}_{safe_end}_{interval}.parquet"

        # 嘗試從快取讀取
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                print(f"  [{i+1}/{len(tickers)}] {ticker} 從快取載入: {len(df)} 筆")
                results[ticker] = add_long_horizon_features(add_market_features(df, market))
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
            results[ticker] = add_long_horizon_features(add_market_features(df, market))

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
    為股票數據添加技術指標。
    
    統一使用 data/technical_indicators.py 的 TechnicalIndicators 類別，
    確保計算邏輯一致，避免重複代碼。
    """
    from data.technical_indicators import TechnicalIndicators
    ti = TechnicalIndicators(df)
    return ti.calculate_all()


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
    parser.add_argument('--start', type=str, default='2000-01-01')
    parser.add_argument('--end', type=str, default='2010-12-31')
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
