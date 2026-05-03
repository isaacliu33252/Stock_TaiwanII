"""
data_loader.py - 台股數據載入器 (整合版)
================================================================================
負責從多種來源取得台股數據：
    1. Yahoo Finance API - 主要股價數據來源
    2. TWSE API - 三大法人買賣超資料
    3. 資料庫/本地快取 - 避免重複下載

整合本地 Stock_taiwan2 的 utility_f.py 邏輯。

作者: FinRL量化交易專家
"""

import pandas as pd
import numpy as np
import requests
import json
import yfinance as yf
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple
from datetime import datetime, timedelta
import time
import warnings

warnings.filterwarnings('ignore')


def fetch_stock_data(
    symbol: str,
    start_date: Union[str, datetime],
    end_date: Union[str, datetime],
    interval: str = '1d'
) -> pd.DataFrame:
    """
    fetch_stock_data() - 從 Yahoo Finance 取得台股歷史數據
    
    Args:
        symbol: 股票代碼 (例如 '2330' 或 '2330.TW')
        start_date: 開始日期 (YYYY-MM-DD 格式)
        end_date: 結束日期 (YYYY-MM-DD 格式)
        interval: K線週期 ('1d', '1wk', '1mo')
    
    Returns:
        DataFrame 包含 OHLCV 欄位
    """
    if not symbol.endswith('.TW') and '.' not in symbol:
        yf_symbol = f"{symbol}.TW"
    else:
        yf_symbol = symbol
    
    print(f"[fetch_stock_data] 下載 {yf_symbol} ({start_date} ~ {end_date})...")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            print(f"[fetch_stock_data] {symbol} 無數據")
            return pd.DataFrame()
        
        # 處理 MultiIndex 欄位問題 (yfinance 版本差異)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.reset_index()
        
        # 確保日期欄位統一處理
        date_col = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()][0]
        df = df.rename(columns={date_col: 'date'})
        if 'datetime' in str(df['date'].dtype).lower():
            df['date'] = df['date'].dt.tz_localize(None) if df['date'].dt.tz else df['date']
        
        # 標準化欄位名稱
        col_mapping = {
            'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'volume'
        }
        df = df.rename(columns=col_mapping)
        
        # 只保留必要欄位
        keep_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        df = df[[c for c in keep_cols if c in df.columns]]
        df['turnover'] = ((df['open'] + df['close']) / 2) * df['volume']
        df['symbol'] = symbol
        
        print(f"[fetch_stock_data] 成功取得 {len(df)} 筆資料")
        return df
        
    except Exception as e:
        print(f"[fetch_stock_data] 下載失敗: {e}")
        return pd.DataFrame()


def fetch_institutional_data(
    date: Union[str, datetime],
    retry: int = 3
) -> pd.DataFrame:
    """
    fetch_institutional_data() - 從 TWSE API 取得三大法人買賣資料
    
    Args:
        date: 日期字串 (YYYYMMDD 格式)
        retry: 最大重試次數
    
    Returns:
        DataFrame 包含三大法人資料
    """
    if isinstance(date, datetime):
        date_str = date.strftime('%Y%m%d')
    else:
        date_str = date.replace('-', '').replace('/', '')
    
    url = f'https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999'
    
    print(f"[fetch_institutional_data] 下載三大法人資料: {date_str}")
    
    for attempt in range(retry):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data_json = json.loads(response.text)
            
            if 'data' not in data_json or not data_json['data']:
                print(f"[fetch_institutional_data] {date_str} 無資料 (可能為休市日)")
                return pd.DataFrame()
            
            columns = data_json.get('fields', [])
            df = pd.DataFrame(data_json['data'], columns=columns)
            
            print(f"[fetch_institutional_data] 取得 {len(df)} 筆三大法人資料")
            return df
            
        except Exception as e:
            print(f"[fetch_institutional_data] 嘗試 {attempt + 1}/{retry} 失敗: {e}")
            if attempt < retry - 1:
                time.sleep(1 * (attempt + 1))
    
    return pd.DataFrame()


class TaiwanStockDataLoader:
    """
    台股數據載入器類別
    
    統一管理台股數據的取得和快取。
    
    Attributes:
        cache_dir: 快取目錄
        data_dir: 數據目錄
    
    Example:
        >>> loader = TaiwanStockDataLoader()
        >>> df = loader.download_price_data('2330', '2020-01-01', '2024-12-31')
    """
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        data_dir: Optional[Path] = None
    ):
        """初始化數據載入器"""
        self.cache_dir = cache_dir or Path('./data/cache')
        self.data_dir = data_dir or Path('./data/raw')
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def download_price_data(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """下載股價數據"""
        return fetch_stock_data(symbol, start, end, interval)
    
    def download_institutional_data(
        self,
        date: Union[str, datetime]
    ) -> pd.DataFrame:
        """下載三大法人資料"""
        return fetch_institutional_data(date)
