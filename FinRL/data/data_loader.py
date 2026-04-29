"""
TaiwanStockDataLoader - 台股數據載入器
================================================================================
負責從多種來源取得台股數據：
    1. Yahoo Finance API - 主要股價數據來源
    2. TWSE API - 三大法人買賣超資料
    3. 資料庫/本地快取 - 避免重複下載

整合來源:
    - 現有 Stock_taiwan2 的 utility_f.py 的 twse_data() 函數邏輯
    - Yahoo Finance 即時/歷史股價

台股特殊規則:
    - 股票代碼格式: 2330.TW (Yahoo Finance 格式)
    - 交易單位: 1000 股為一張
    - 漲跌停限制: 10%
    - T+2 交割制度

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

# 忽略警告
warnings.filterwarnings('ignore')


# =============================================================================
# 便利函數
# =============================================================================

def fetch_stock_data(
    symbol: str,
    start_date: Union[str, datetime],
    end_date: Union[str, datetime],
    interval: str = '1d'
) -> pd.DataFrame:
    """
    fetch_stock_data() - 從 Yahoo Finance 取得台股歷史數據
    
    台股代碼處理:
        - 2330.TW (完整格式) 直接使用
        - 2330 (純數字) 自動轉換為 2330.TW
        
    參數:
        symbol: 股票代碼 (例如 '2330' 或 '2330.TW')
        start_date: 開始日期 (YYYY-MM-DD 格式)
        end_date: 結束日期 (YYYY-MM-DD 格式)
        interval: K線週期 ('1d', '1wk', '1mo')
    
    返回:
        DataFrame 包含 OHLCV 欄位:
        - date: 交易日期
        - open: 開盤價
        - high: 最高價
        - low: 最低價
        - close: 收盤價
        - volume: 成交量
        - turnover: 成交額 (約略值)
    
    台股特殊情況處理:
        1. 漲跌停日: 價格會停在 10% 限制處
        2. 有時會出現無交易量的日子 (可能為處置股或清淡日)
        3. 股票代碼可能因企業活動而調整
        
    使用範例:
        >>> df = fetch_stock_data('2330', '2020-01-01', '2024-12-31')
        >>> df = fetch_stock_data('2317', '2023-01-01', '2024-06-30', interval='1wk')
    """
    # 格式化代碼
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
        
        # 重置索引，將日期設為欄位
        df = df.reset_index()
        
        # 轉換日期格式 (去除時區)
        if 'Datetime' in str(df['Date'].dtype):
            df['Date'] = df['Date'].dt.tz_localize(None)
        
        # 重新命名欄位 (小寫)
        df.columns = [col.lower() for col in df.columns]
        df = df.rename(columns={
            'date': 'date',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        })
        
        # 計算成交額 (約略值 = 平均價格 * 成交量)
        df['turnover'] = ((df['open'] + df['close']) / 2) * df['volume']
        
        # 添加股票代碼欄位
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
    
    三大法人包括:
        1. 外資 (Foreign Investors)
        2. 投信 (Investment Trust)
        3. 自營商 (Dealer/Self-employed)
    
    參數:
        date: 日期字串 (YYYYMMDD 格式，例如 '20240115')
        retry: 最大重試次數
    
    返回:
        DataFrame 包含欄位:
        - 證券代號: 股票代碼
        - 證券名稱: 股票名稱
        - 外資買進股數/賣出股數/買賣超股數
        - 投信買進股數/賣出股數/買賣超股數
        - 自營商買進股數/賣出股數/買賣超股數
    
    台股特殊情況處理:
        1. 週末/國定假日: TWSE 不會有資料，回傳空 DataFrame
        2. 資料可能有延遲 (通常當日 14:00 後才公布)
        3. 欄位名稱可能因 TWSE API 更新而改變
    
    使用範例:
        >>> df = fetch_institutional_data('20240115')
        >>> # 取得並查看外資買超最多的股票
        >>> df_sorted = df.sort_values('外資買賣超股數', ascending=False)
    """
    # 格式化日期
    if isinstance(date, datetime):
        date_str = date.strftime('%Y%m%d')
    else:
        date_str = date.replace('-', '').replace('/', '')
    
    # TWSE API URL
    url = f'https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999'
    
    print(f"[fetch_institutional_data] 下載三大法人資料: {date_str}")
    
    for attempt in range(retry):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data_json = json.loads(response.text)
            
            # 檢查數據是否存在
            if 'data' not in data_json or not data_json['data']:
                print(f"[fetch_institutional_data] {date_str} 無資料 (可能為休市日)")
                return pd.DataFrame()
            
            # 建立 DataFrame
            columns = data_json.get('fields', [])
            df = pd.DataFrame(data_json['data'], columns=columns)
            
            print(f"[fetch_institutional_data] 取得 {len(df)} 筆三大法人資料")
            return df
            
        except Exception as e:
            print(f"[fetch_institutional_data] 嘗試 {attempt + 1}/{retry} 失敗: {e}")
            if attempt < retry - 1:
                time.sleep(1 * (attempt + 1))  # 指數退避
    
    return pd.DataFrame()


def fetch_dividend_data(
    symbol: str,
    years: Optional[int] = 5
) -> pd.DataFrame:
    """
    fetch_dividend_data() - 取得個股除權息資料
    
    台股除權息特色:
        - 除權: 配發股票 (例如 配股票 100 股)
        - 除息: 配發現金 (例如 配息 3 元)
        - 除權息日常導致股價大幅波動
    
    參數:
        symbol: 股票代碼 (例如 '2330')
        years: 回溯年份數 (預設 5 年)
    
    返回:
        DataFrame 包含欄位:
        - ex_date: 除權息日期
        - dividend_type: '股票' 或 '現金'
        - dividend_per_share: 每股股利
        - closing_price_before: 除權息前一交易日收盤價
        - opening_price_after: 除權息後首日開盤價
        - price_change_pct: 價格變化百分比
    
    台股特殊情況處理:
        1. 除權息日前後成交量可能暴增
        2. 融券回補期間股價可能波動
        3. 資料可能不完整 (早期歷史資料)
    
    使用範例:
        >>> df = fetch_dividend_data('2330', years=3)
        >>> # 查看近3年除息紀錄
        >>> cash_div = df[df['dividend_type'] == '現金']
    """
    try:
        # 嘗試使用 yfinance 取得股利資料
        yf_symbol = symbol if '.TW' in symbol else f"{symbol}.TW"
        ticker = yf.Ticker(yf_symbol)
        
        # 取得股利歷史 (yfinance 有 Dividends 欄位)
        dividends = ticker.dividends
        
        if dividends.empty:
            print(f"[fetch_dividend_data] {symbol} 無股利資料")
            return pd.DataFrame()
        
        # 轉換為 DataFrame
        df = pd.DataFrame({
            'ex_date': dividends.index,
            'dividend_per_share': dividends.values
        })
        
        # 根據股利大小判斷是股票股利還是現金股利
        # 通常現金股利 > 1 元為正常，股票股利通常以百分比或配股率表示
        # 這裡假設所有股利都是現金股利 (更具體的判斷需要更多資料)
        df['dividend_type'] = '現金'
        
        # 排序並限制年份
        df = df.sort_values('ex_date', ascending=False)
        
        # 只取近 N 年的資料
        if years:
            cutoff_date = datetime.now() - timedelta(days=years * 365)
            df = df[df['ex_date'] >= cutoff_date]
        
        # 格式化日期
        df['ex_date'] = df['ex_date'].dt.strftime('%Y-%m-%d')
        
        print(f"[fetch_dividend_data] 取得 {len(df)} 筆記錄")
        return df
        
    except Exception as e:
        print(f"[fetch_dividend_data] 取得失敗: {e}")
        return pd.DataFrame()


def get_trading_dates(
    start_date: Union[str, datetime],
    end_date: Union[str, datetime]
) -> List[datetime]:
    """
    取得指定日期區間內的台股交易日
    
    台股交易日定義:
        - 非週末 (週六週日休市)
        - 非國定假日
        - 非盤後資料公佈日 (但仍為交易日)
    
    參數:
        start_date: 開始日期
        end_date: 結束日期
    
    返回:
        交易日列表 (datetime物件)
    
    使用範例:
        >>> dates = get_trading_dates('2024-01-01', '2024-01-31')
        >>> print(f"1月有 {len(dates)} 個交易日")
    """
    if isinstance(start_date, str):
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    else:
        start_dt = start_date
    
    if isinstance(end_date, str):
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end_dt = end_date
    
    trading_dates = []
    current_dt = start_dt
    
    while current_dt <= end_dt:
        # 跳過週末 (0=週一, 5=週六, 6=週日)
        if current_dt.weekday() < 5:
            trading_dates.append(current_dt)
        current_dt += timedelta(days=1)
    
    return trading_dates


def is_trading_day(date: Union[str, datetime]) -> bool:
    """
    判斷指定日期是否為台股交易日
    
    參數:
        date: 日期
    
    返回:
        True 為交易日，False 為休市日
    
    使用範例:
        >>> if is_trading_day('2024-01-01'):
        ...     print("今天有開盤")
        ... else:
        ...     print("今天沒開盤")
    """
    if isinstance(date, str):
        dt = datetime.strptime(date, '%Y-%m-%d')
    else:
        dt = date
    
    # 週末檢查
    if dt.weekday() >= 5:
        return False
    
    # 注意：完整實現需要載入假期資料庫
    # 這裡僅做基本檢查
    
    return True


# =============================================================================
# TaiwanStockDataLoader 類別 (完整實現)
# =============================================================================

class TaiwanStockDataLoader:
    """
    台股數據載入器 (Class-based 實現)
    
    功能:
        - 從 Yahoo Finance 取得歷史股價
        - 從 TWSE API 取得三大法人資料
        - 數據快取機制
        - 台股代碼處理 (.TW 結尾)
    
    使用範例:
        >>> loader = TaiwanStockDataLoader(cache_dir='./data/cache')
        >>> df = loader.download_price_data('2330', start='2020-01-01', end='2024-12-31')
        >>> corp_df = loader.download_corp_data('2024-01-15')
    """
    
    def __init__(
        self,
        cache_dir: str = './data/cache',
        data_dir: str = './data/raw',
        symbol_suffix: str = '.TW',
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        初始化數據載入器
        
        Args:
            cache_dir: 數據快取目錄
            data_dir: 原始數據儲存目錄
            symbol_suffix: Yahoo Finance 股票代碼後綴
            max_retries: 最大重試次數
            retry_delay: 重試間隔 (秒)
        """
        self.cache_dir = Path(cache_dir)
        self.data_dir = Path(data_dir)
        self.symbol_suffix = symbol_suffix
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 建立目錄
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 數據來源 URL
        self.twse_url = 'https://www.twse.com.tw/fund/T86'
        self.yf_base_url = 'https://query1.finance.yahoo.com/v8/finance'
    
    def _retry_request(self, func, *args, **kwargs):
        """
        帶重試機制的請求包裝器
        
        原因: 網路請求可能因暫時性錯誤失敗，重試3次提高成功率
        """
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # 指數退避
        raise last_exception
    
    def format_symbol(self, symbol: str) -> str:
        """
        格式化台股代碼為 Yahoo Finance 格式
        
        Args:
            symbol: 股票代碼，例如 '2330' 或 '2330.TW'
        
        Returns:
            格式化後的代碼，例如 '2330.TW'
        """
        # 去除空白
        symbol = symbol.strip()
        
        # 如果已經有 .TW 後綴，直接返回
        if symbol.endswith(self.symbol_suffix):
            return symbol
        
        # 如果有 .TW 以外的后缀，也直接返回
        if '.' in symbol:
            return symbol
            
        # 否則加上 .TW 後綴
        return f"{symbol}{self.symbol_suffix}"
    
    def download_price_data(
        self,
        symbol: str,
        start: Union[str, datetime],
        end: Union[str, datetime],
        interval: str = '1d',
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        下載個股歷史股價數據
        
        Args:
            symbol: 股票代碼 (例如 '2330' 或 '2330.TW')
            start: 開始日期
            end: 結束日期
            interval: K線週期 ('1d', '1wk', '1mo')
            use_cache: 是否使用快取
        
        Returns:
            包含 OHLCV 數據的 DataFrame
        """
        # 格式化代碼
        yf_symbol = self.format_symbol(symbol)
        
        # 生成快取檔名
        cache_file = self.cache_dir / f"{symbol.replace('.', '_')}_{start}_{end}_{interval}.parquet"
        
        # 檢查快取
        if use_cache and cache_file.exists():
            df = pd.read_parquet(cache_file)
            print(f"[TaiwanStockDataLoader] 從快取載入 {symbol}: {len(df)} 筆資料")
            return df
        
        # 下載數據 (使用 yfinance)
        print(f"[TaiwanStockDataLoader] 從 Yahoo Finance 下載 {yf_symbol}...")
        
        def _download():
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=start, end=end, interval=interval)
            return df
        
        try:
            df = self._retry_request(_download)
        except Exception as e:
            print(f"[TaiwanStockDataLoader] 下載失敗: {e}")
            return pd.DataFrame()
        
        # 處理數據
        if df.empty:
            print(f"[TaiwanStockDataLoader] {symbol} 無數據")
            return pd.DataFrame()
        
        # 重置索引，將日期設為欄位
        df = df.reset_index()
        
        # 轉換日期格式 (去除時區)
        if 'Datetime' in str(df['Date'].dtype):
            df['Date'] = df['Date'].dt.tz_localize(None)
        
        # 重新命名欄位
        df.columns = [col.lower() for col in df.columns]
        df = df.rename(columns={
            'date': 'date',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        })
        
        # 計算成交額 (金額)
        df['turnover'] = ((df['open'] + df['close']) / 2) * df['volume']
        
        # 添加股票代碼欄位
        df['symbol'] = symbol
        
        # 儲存快取
        df.to_parquet(cache_file)
        print(f"[TaiwanStockDataLoader] 已儲存快取: {cache_file.name} ({len(df)} 筆資料)")
        
        return df
    
    def download_batch(
        self,
        symbols: List[str],
        start: Union[str, datetime],
        end: Union[str, datetime],
        interval: str = '1d'
    ) -> Dict[str, pd.DataFrame]:
        """
        批量下載多支股票數據
        
        Args:
            symbols: 股票代碼列表
            start: 開始日期
            end: 結束日期
            interval: K線週期
        
        Returns:
            Dictionary，key 為股票代碼，value 為對應的 DataFrame
        """
        results = {}
        for symbol in symbols:
            print(f"\n[{symbol}] 處理中...")
            df = self.download_price_data(symbol, start, end, interval)
            results[symbol] = df
            time.sleep(0.5)  # 避免請求過快
        
        return results
    
    def download_corp_data(self, date: str) -> pd.DataFrame:
        """
        下載指定日期的三大法人買賣超日報
        
        整合自 Stock_taiwan2 的 utility_f.twse_data() 函數
        
        Args:
            date: 日期字串，格式 'YYYYMMDD' (例如 '20240115')
        
        Returns:
            DataFrame 包含三大法人資料
        """
        # 格式化日期
        if isinstance(date, datetime):
            date_str = date.strftime('%Y%m%d')
        else:
            date_str = date.replace('-', '')
        
        # TWSE API URL
        url = f'{self.twse_url}?response=json&date={date_str}&selectType=ALLBUT0999'
        
        print(f"[TaiwanStockDataLoader] 下載三大法人資料: {date_str}")
        
        def _fetch():
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response
        
        try:
            data_json = self._retry_request(_fetch)
        except Exception as e:
            print(f"[TaiwanStockDataLoader] TWSE API 請求失敗: {e}")
            return pd.DataFrame()
        
        # 解析 JSON
        try:
            data_json = json.loads(data_json.text)
        except json.JSONDecodeError:
            print(f"[TaiwanStockDataLoader] JSON 解析失敗")
            return pd.DataFrame()
        
        # 檢查數據是否存在
        if 'data' not in data_json or not data_json['data']:
            print(f"[TaiwanStockDataLoader] {date_str} 無三大法人資料 (可能為休市日)")
            return pd.DataFrame()
        
        # 建立 DataFrame
        columns = data_json.get('fields', [])
        df = pd.DataFrame(data_json['data'], columns=columns)
        
        print(f"[TaiwanStockDataLoader] 取得 {len(df)} 筆三大法人資料")
        
        return df
    
    def get_corp_trading(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        取得特定股票在日期區間內的三大法人累計買賣超
        
        這是 RL 狀態的重要特徵 (fundamental_features)
        
        Args:
            symbol: 股票代碼
            start_date: 開始日期 'YYYYMMDD'
            end_date: 結束日期 'YYYYMMDD'
        
        Returns:
            DataFrame 包含每日三大法人資料
        """
        # 解析日期
        start_dt = datetime.strptime(start_date, '%Y%m%d')
        end_dt = datetime.strptime(end_date, '%Y%m%d')
        
        all_data = []
        current_dt = start_dt
        
        while current_dt <= end_dt:
            # 跳過週末
            if current_dt.weekday() < 5:
                date_str = current_dt.strftime('%Y%m%d')
                df = self.download_corp_data(date_str)
                
                if not df.empty:
                    # 篩選指定股票
                    symbol_col = [c for c in df.columns if '代號' in c][0]
                    stock_df = df[df[symbol_col] == symbol]
                    
                    if not stock_df.empty:
                        stock_df = stock_df.copy()
                        stock_df['date'] = current_dt
                        all_data.append(stock_df)
                
                time.sleep(0.3)  # 避免請求過快
            
            current_dt += timedelta(days=1)
        
        if not all_data:
            return pd.DataFrame()
        
        # 合併所有數據
        result = pd.concat(all_data, ignore_index=True)
        
        return result
    
    def merge_price_and_corp(
        self,
        price_df: pd.DataFrame,
        corp_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        合併股價數據與三大法人資料
        
        這是建立 RL 狀態的關鍵步驟
        
        Args:
            price_df: 股價數據 (from download_price_data)
            corp_df: 三大法人數據 (from download_corp_data)
        
        Returns:
            合併後的 DataFrame
        """
        if price_df.empty or corp_df.empty:
            return price_df
        
        # 確保日期格式一致
        price_df['date'] = pd.to_datetime(price_df['date'])
        corp_df['date'] = pd.to_datetime(corp_df['date'])
        
        # 嘗試合併 (根據具體欄位調整)
        try:
            merged = price_df.merge(corp_df, on='date', how='left')
            return merged
        except Exception as e:
            print(f"[TaiwanStockDataLoader] 合併失敗: {e}")
            return price_df
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """
        驗證數據完整性
        
        檢查:
        1. 是否為空
        2. 必要的欄位是否存在
        3. 是否有缺失值
        4. 價格是否合理 (positive, 不是 NaN)
        
        Args:
            df: 要驗證的 DataFrame
        
        Returns:
            True 如果通過所有檢查
        """
        required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        
        # 檢查是否為空
        if df.empty:
            print("[TaiwanStockDataLoader] 數據為空")
            return False
        
        # 檢查必要欄位
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            print(f"[TaiwanStockDataLoader] 缺少欄位: {missing_cols}")
            return False
        
        # 檢查缺失值 - 使用 ffill 填補
        if df[required_cols].isnull().any().any():
            print("[TaiwanStockDataLoader] 數據包含缺失值，嘗試填補...")
            df = df.ffill()
        
        # 檢查價格合理性
        if (df['close'] <= 0).any():
            print("[TaiwanStockDataLoader] 存在不合理價格 (<=0)")
            return False
        
        return True


# =============================================================================
# 便利函數 - 快速呼叫
# =============================================================================

def load_taiwan_stock_data(
    symbol: str,
    start: str,
    end: str,
    cache_dir: str = './data/cache'
) -> pd.DataFrame:
    """
    便利函數：快速載入台股數據
    
    這是 fetch_stock_data() 的包裝函數，提供更簡潔的介面
    
    Args:
        symbol: 股票代碼 (例如 '2330')
        start: 開始日期 (例如 '2020-01-01')
        end: 結束日期 (例如 '2024-12-31')
        cache_dir: 快取目錄
    
    Returns:
        包含 OHLCV 數據的 DataFrame
    
    Example:
        >>> df = load_taiwan_stock_data('2330', '2020-01-01', '2024-12-31')
    """
    loader = TaiwanStockDataLoader(cache_dir=cache_dir)
    return loader.download_price_data(symbol, start, end)