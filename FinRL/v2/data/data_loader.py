"""
================================================================================
TaiwanStockDataLoader - 台股數據載入器 (v2新版)
================================================================================
負責從多種來源取得台股數據：

主要數據來源：
    1. Yahoo Finance API - 主要股價數據來源
       - 速度快、免費、數據完整性高
       - 代碼格式: 2330.TW, 0050.TW
       
    2. TWSE API - 三大法人買賣超資料
       - 提供外資、投信、自營商買賣資訊
       - 對於 RL 狀態特徵非常重要

    3. 資料庫/本地快取 - 避免重複下載
       - SQLite 資料庫加速訓練時的數據載入
       - Parquet 格式快取

台股特殊規則：
    - 股票代碼格式: 2330.TW (Yahoo Finance 格式)
    - 交易單位: 1000 股為一張（最小交易單位）
    - 漲跌停限制: ±10%
    - T+2 交割制度（買入後第2個交易日完成交割）

功能：
    - 自動快取：首次下載後自動儲存到本地資料庫
    - 批量下載：支援多檔股票同時下載
    - 技術指標整合：計算完成後自動計算技術指標
    - 法人數據整合：三大法人買賣超資料

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
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
import sqlite3
from pathlib import Path

# 忽略警告
warnings.filterwarnings('ignore')


# =============================================================================
# 台股代碼工具函數
# =============================================================================

def normalize_taiwan_stock_symbol(symbol: str) -> str:
    """
    標準化台股代碼格式
    
    台股代碼在 Yahoo Finance 的格式通常是 `2330.TW` 或 `0050.TW`。
    本函數將純數字代碼轉換為 Yahoo Finance 格式。
    
    參數:
        symbol: 股票代碼，可以是 '2330', '2330.TW', '0050.TW' 等
        
    返回:
        標準化後的代碼，例如 '2330.TW'
        
    範例:
        >>> normalize_taiwan_stock_symbol('2330')
        '2330.TW'
        >>> normalize_taiwan_stock_symbol('2330.TW')
        '2330.TW'
        >>> normalize_taiwan_stock_symbol('0050.TW')
        '0050.TW'
    """
    # 已經是完整格式，直接返回
    if symbol.endswith('.TW') or symbol.endswith('.TWO'):
        return symbol
    
    # 純數字代碼，添加 .TW 後綴
    if symbol.isdigit():
        return f"{symbol}.TW"
    
    # 其他格式，直接返回
    return symbol


def is_valid_trading_date(date: pd.Timestamp, market: str = 'Taiwan') -> bool:
    """
    檢查是否為有效交易日
    
    台股交易時間：
    - 平日：周一至周五
    - 休市日：周末、台灣國定假日、颱風假等
    
    注意：此函數僅做基本檢查，不含完整的國定假日列表
    如需完整檢查，可結合 TWSE API 或 openpyxl 讀取期交所休市日
    
    參數:
        date: 要檢查的日期
        market: 市場類型，預設 'Taiwan'
        
    返回:
        True 如果是交易日，False 否則
    """
    # 周末
    if date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    
    return True


# =============================================================================
# 數據獲取函數
# =============================================================================

def fetch_stock_data(
    symbol: str,
    start_date: Union[str, datetime],
    end_date: Union[str, datetime],
    interval: str = '1d',
    adjust: str = 'pre'  # 'pre'=前復權, 'post'=後復權, False=不平滑
) -> pd.DataFrame:
    """
    fetch_stock_data() - 從 Yahoo Finance 取得台股歷史數據
    
    這是獲取台股數據的主要函數，使用 Yahoo Finance 作為數據源。
    Yahoo Finance 提供高質量、免費的歷史數據，適合 ML/RL 訓練。
    
    台股代碼處理:
        - 2330.TW (完整格式) 直接使用
        - 2330 (純數字) 自動轉換為 2330.TW
        
    參數:
        symbol: 股票代碼 (例如 '2330' 或 '2330.TW')
        start_date: 開始日期 (YYYY-MM-DD 格式)
        end_date: 結束日期 (YYYY-MM-DD 格式)
        interval: K線週期 ('1d', '1wk', '1mo')
        adjust: 復權方式 ('pre'=前復權, 'post'=後復權, False=不平滑)
    
    返回:
        DataFrame 包含 OHLCV 欄位:
        - date: 交易日期
        - open: 開盤價
        - high: 最高價
        - low: 最低價
        - close: 收盤價
        - volume: 成交量
        - turnover: 成交額
    
    台股特殊情況處理:
        1. 漲跌停日: 價格會停在 10% 限制處
        2. 有時會出現無交易量的日子 (可能為處置股或清淡日)
        3. 股票代碼可能因企業活動而調整
        
    使用範例:
        >>> df = fetch_stock_data('2330', '2020-01-01', '2024-12-31')
        >>> df = fetch_stock_data('2317', '2023-01-01', '2024-06-30', interval='1wk')
    """
    # 格式化代碼
    yf_symbol = normalize_taiwan_stock_symbol(symbol)
    
    try:
        # 下載數據
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(
            start=start_date,
            end=end_date,
            interval=interval,
            auto_adjust=False,  # 我們自己處理復權
            back_adjust=adjust == 'pre',
            repair=False
        )
        
        if df.empty:
            warnings.warn(f"無數據返回: {yf_symbol} ({start_date} ~ {end_date})")
            return pd.DataFrame()
        
        # 重置索引，將日期變為欄位
        df = df.reset_index()
        
        # 轉換日期格式（如果有 datetime64 類型）
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.rename(columns={'Date': 'date'})
        elif 'Datetime' in df.columns:
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            df = df.rename(columns={'Datetime': 'date'})
        
        # 計算成交額 (turnover = close * volume)
        # 這是一個約略值，因為 Yahoo 的 volume 是股數
        if 'Turnover' not in df.columns:
            df['turnover'] = df['Close'] * df['Volume']
        else:
            df['turnover'] = df['Turnover']
        
        # 欄位名稱標準化（小寫）
        df.columns = [c.lower() for c in df.columns]
        
        # 確保必要的欄位存在
        required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                warnings.warn(f"缺少欄位: {col}")
                return pd.DataFrame()
        
        # 排序
        df = df.sort_values('date').reset_index(drop=True)
        
        return df
        
    except Exception as e:
        warnings.warn(f"下載失敗: {yf_symbol}, 錯誤: {e}")
        return pd.DataFrame()


def fetch_institutional_data(
    symbol: str,
    start_date: Union[str, datetime],
    end_date: Union[str, datetime]
) -> pd.DataFrame:
    """
    取得三大法人買賣超資料
    
    三大法人是台股市場的重要指標：
    - 外資 (Foreign): 外國機構投資人，通常為長線資金
    - 投信 (Investment Trust): 境內投信基金
    - 自營商 (Dealer): 券商自營部位
    
    這些數據對於 RL 模型的狀態特徵非常重要，可以幫助模型
    理解機構投資人的行為模式。
    
    參數:
        symbol: 股票代碼 (例如 '2330')
        start_date: 開始日期
        end_date: 結束日期
        
    返回:
        DataFrame 包含:
        - date: 交易日期
        - foreign_net_buy: 外資淨買超（正值=買超，負值=賣超）
        - investment_trust_net_buy: 投信淨買超
        - dealer_net_buy: 自營商淨買超
        - total_net_buy: 總淨買超
        
    TWSE API 文件: https://www.twse.com.tw/rwd/zh/fund/T86
    """
    # 轉換股票代碼為 6 碼格式（補零）
    if isinstance(symbol, str):
        symbol = symbol.replace('.TW', '').replace('.TWO', '')
    code_6digit = str(int(symbol)).zfill(6)
    
    # 轉換日期格式為 YYYYMMDD
    if isinstance(start_date, str):
        start_dt = pd.to_datetime(start_date)
    else:
        start_dt = start_date
    if isinstance(end_date, str):
        end_dt = pd.to_datetime(end_date)
    else:
        end_dt = end_date
    
    start_str = start_dt.strftime('%Y%m%d')
    end_str = end_dt.strftime('%Y%m%d')
    
    # TWSE API 端點
    url = 'https://www.twse.com.tw/rwd/zh/fund/T86'
    
    all_data = []
    current_start = start_dt
    
    # 分段下載（每次最多 3 個月，避免 URL 過長）
    chunk_months = 3
    
    while current_start <= end_dt:
        chunk_end = min(current_start + pd.DateOffset(months=chunk_months), end_dt)
        chunk_start_str = current_start.strftime('%Y%m%d')
        chunk_end_str = chunk_end.strftime('%Y%m%d')
        
        params = {
            'response': 'json',
            'code': code_6digit,
            'start_date': chunk_start_str,
            'end_date': chunk_end_str,
        }
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            json_data = resp.json()
            
            if json_data.get('stat') == 'OK':
                data = json_data.get('data', [])
                for row in data:
                    # 欄位: 日期, 外資買進, 外資賣出, 外資淨買賣, 
                    #       投信買進, 投信賣出, 投信淨買賣,
                    #       自營商買進, 自營商賣出, 自營商淨買賣
                    if len(row) >= 10:
                        date_str = str(row[0])
                        # 轉換民國年為西元年
                        parts = date_str.split('/')
                        if len(parts) == 3:
                            year = int(parts[0]) + 1911
                            month = int(parts[1])
                            day = int(parts[2])
                            date = f"{year:04d}-{month:02d}-{day:02d}"
                        else:
                            continue
                        
                        # 解析數值（移除逗號）
                        def parse_num(val):
                            if isinstance(val, str):
                                val = val.replace(',', '').replace('--', '0')
                            try:
                                return float(val) if val else 0.0
                            except:
                                return 0.0
                        
                        foreign_net = parse_num(row[3])
                        it_net = parse_num(row[6])
                        dealer_net = parse_num(row[9])
                        
                        all_data.append({
                            'date': date,
                            'foreign_net_buy': foreign_net,
                            'investment_trust_net_buy': it_net,
                            'dealer_net_buy': dealer_net,
                            'total_net_buy': foreign_net + it_net + dealer_net,
                        })
            else:
                # API 返回錯誤，可能是股票代碼格式不對
                warnings.warn(f"TWSE API: {json_data.get('stat', 'Unknown error')}")
                break
                
        except requests.exceptions.RequestException as e:
            warnings.warn(f"TWSE API request failed: {e}")
            break
        except Exception as e:
            warnings.warn(f"Failed to parse TWSE response: {e}")
            break
        
        # 移動到下一段
        current_start = chunk_end + pd.DateOffset(days=1)
        
        # 避免請求過快
        time.sleep(0.5)
    
    if all_data:
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df
    else:
        warnings.warn(f"fetch_institutional_data() 無法取得 {symbol} 的法人數據")
        return pd.DataFrame()


def load_cached_data(
    symbol: str,
    start_date: str,
    end_date: str,
    db_path: str = None
) -> Optional[pd.DataFrame]:
    """
    從本地 SQLite 資料庫載入快取數據
    
    使用快取可以大幅加速訓練時的數據載入，特別是在：
    1. 反覆訓練相同股票時
    2. 使用walk-forward validation時
    3. 大量股票同時訓練時
    
    參數:
        symbol: 股票代碼 (例如 '2330.TW')
        start_date: 開始日期
        end_date: 結束日期
        db_path: 資料庫路徑，預設使用專案內的 stock_data.db
        
    返回:
        DataFrame 如果找到快取，None 如果無快取
        
    使用範例:
        >>> df = load_cached_data('2330', '2020-01-01', '2024-12-31')
        >>> if df is not None:
        ...     print(f"Loaded {len(df)} rows from cache")
    """
    if db_path is None:
        # 使用預設資料庫路徑
        db_path = Path(__file__).parent / 'stock_data.db'
    
    # 轉換為完整代碼格式
    full_symbol = normalize_taiwan_stock_symbol(symbol)
    
    try:
        conn = sqlite3.connect(db_path)
        
        # 查詢快取（使用參數化查詢避免 SQL injection）
        query = """
            SELECT date, open, high, low, close, volume, turnover
            FROM stock_daily
            WHERE symbol = ?
            AND date >= ?
            AND date <= ?
            ORDER BY date
        """
        
        df = pd.read_sql_query(query, conn, params=[full_symbol, start_date, end_date], parse_dates=['date'])
        conn.close()
        
        if not df.empty:
            print(f"[Cache Hit] {full_symbol}: {len(df)} rows")
            return df
        else:
            print(f"[Cache Miss] {full_symbol}")
            return None
            
    except Exception as e:
        # 可能資料庫不存在或表尚未建立
        return None


def save_to_cache(
    df: pd.DataFrame,
    symbol: str,
    db_path: str = None
) -> bool:
    """
    將下載的數據儲存到 SQLite 快取資料庫
    
    參數:
        df: 包含 OHLCV 數據的 DataFrame
        symbol: 股票代碼
        db_path: 資料庫路徑，預設使用專案內的 stock_data.db
        
    返回:
        True 如果儲存成功，False 否則
    """
    if df.empty:
        return False
    
    if db_path is None:
        db_path = Path(__file__).parent / 'stock_data.db'
    else:
        db_path = Path(db_path)
    
    # 確保目錄存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 轉換為完整代碼格式
    full_symbol = normalize_taiwan_stock_symbol(symbol)
    
    try:
        conn = sqlite3.connect(db_path)
        
        # 確保表存在
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily (
                symbol TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                turnover REAL,
                PRIMARY KEY (symbol, date)
            )
        """)
        
        # 準備數據
        df_save = df.copy()
        df_save['symbol'] = full_symbol
        df_save['date'] = df_save['date'].astype(str)
        
        # 使用 REPLACE 避免重複
        df_save.to_sql('stock_daily', conn, if_exists='append', index=False)
        
        conn.commit()
        conn.close()
        
        print(f"[Cache Saved] {full_symbol}: {len(df)} rows")
        return True
        
    except Exception as e:
        print(f"[Cache Error] {full_symbol}: {e}")
        return False


# =============================================================================
# TaiwanStockDataLoader 類別
# =============================================================================

class TaiwanStockDataLoader:
    """
    台股數據載入器類別
    
    這個類別提供統一的介面來獲取和處理台股數據，
    支援多種數據源、快取機制和技術指標計算。
    
    屬性:
        cache_dir: 快取目錄路徑
        db_path: SQLite 資料庫路徑
        default_interval: 預設K線週期
        default_adjust: 預設復權方式
        
    使用範例:
        >>> loader = TaiwanStockDataLoader()
        >>> 
        >>> # 單檔股票
        >>> df = loader.load('2330', '2020-01-01', '2024-12-31')
        >>> 
        >>> # 多檔股票
        >>> dfs = loader.load_batch(['2330', '0050', '2317'], '2020-01-01', '2024-12-31')
        >>> 
        >>> # 帶技術指標
        >>> df_with_indicators = loader.load_with_indicators('2330', '2020-01-01', '2024-12-31')
    """
    
    def __init__(
        self,
        cache_dir: str = None,
        db_path: str = None,
        default_interval: str = '1d',
        default_adjust: str = 'pre'
    ):
        """
        初始化數據載入器
        
        參數:
            cache_dir: 快取目錄路徑，預設 './cache'
            db_path: SQLite 資料庫路徑，預設 './stock_data.db'
            default_interval: 預設K線週期 ('1d', '1wk', '1mo')
            default_adjust: 預設復權方式 ('pre'=前復權, 'post'=後復權)
        """
        # 設定快取目錄
        if cache_dir is None:
            self.cache_dir = Path(__file__).parent / 'cache'
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 設定資料庫路徑
        if db_path is None:
            self.db_path = Path(__file__).parent / 'stock_data.db'
        else:
            self.db_path = Path(db_path)
        
        self.default_interval = default_interval
        self.default_adjust = default_adjust
        
        # 初始化技術指標計算器
        from .technical_indicators import TechnicalIndicators
        self.indicator_calculator = TechnicalIndicators
        
        print(f"[TaiwanStockDataLoader] 初始化完成")
        print(f"  - 快取目錄: {self.cache_dir}")
        print(f"  - 資料庫: {self.db_path}")
    
    def load(
        self,
        symbol: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        interval: str = None,
        adjust: str = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        載入單一股票的歷史數據
        
        優先順序：
        1. 記憶體快取（未來擴展）
        2. SQLite 快取
        3. Yahoo Finance API
        
        參數:
            symbol: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            interval: K線週期，預設使用 default_interval
            adjust: 復權方式，預設使用 default_adjust
            use_cache: 是否使用快取
            
        返回:
            DataFrame 包含 OHLCV 數據
        """
        interval = interval or self.default_interval
        adjust = adjust or self.default_adjust
        
        # 嘗試從快取載入
        if use_cache:
            cached_df = load_cached_data(
                symbol, start_date, end_date, self.db_path
            )
            if cached_df is not None:
                return cached_df
        
        # 從 Yahoo Finance 下載
        df = fetch_stock_data(
            symbol, start_date, end_date, interval, adjust
        )
        
        # 儲存到快取
        if not df.empty and use_cache:
            save_to_cache(df, symbol, self.db_path)
        
        return df
    
    def load_batch(
        self,
        symbols: List[str],
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        interval: str = None,
        adjust: str = None,
        use_cache: bool = True,
        delay: float = 0.5  # 下載間隔，避免被限制
    ) -> Dict[str, pd.DataFrame]:
        """
        批量載入多檔股票的歷史數據
        
        參數:
            symbols: 股票代碼列表
            start_date: 開始日期
            end_date: 結束日期
            interval: K線週期
            adjust: 復權方式
            use_cache: 是否使用快取
            delay: 下載間隔（秒），避免對 Yahoo Finance 請求過於頻繁
            
        返回:
            Dictionary，key 為股票代碼，value 為對應的 DataFrame
        """
        results = {}
        
        for i, symbol in enumerate(symbols):
            print(f"[Batch] ({i+1}/{len(symbols)}) {symbol}")
            
            try:
                df = self.load(
                    symbol, start_date, end_date,
                    interval, adjust, use_cache
                )
                results[symbol] = df
                
                # 下載間隔
                if i < len(symbols) - 1:
                    time.sleep(delay)
                    
            except Exception as e:
                print(f"[Batch Error] {symbol}: {e}")
                results[symbol] = pd.DataFrame()
        
        return results
    
    def load_with_indicators(
        self,
        symbol: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        interval: str = None,
        adjust: str = None,
        use_cache: bool = True,
        indicator_config: Dict = None
    ) -> pd.DataFrame:
        """
        載入股票數據並計算技術指標
        
        技術指標是 RL 狀態特徵的重要組成部分。
        預設計算的指標包括：
        - MA (移動平均線): 3, 5, 10, 20, 60, 120, 240 日
        - MACD: 12, 26, 9
        - RSI: 14, 28 日
        - KDJ: 9, 3, 3
        - Bollinger Bands: 20, 2
        - ATR: 14 日
        
        參數:
            symbol: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            interval: K線週期
            adjust: 復權方式
            use_cache: 是否使用快取
            indicator_config: 技術指標配置，覆蓋預設值
            
        返回:
            DataFrame 包含 OHLCV + 技術指標
        """
        # 載入基礎數據
        df = self.load(symbol, start_date, end_date, interval, adjust, use_cache)
        
        if df.empty:
            return df
        
        # 計算技術指標
        indicator_config = indicator_config or {}
        ti = self.indicator_calculator(df, **indicator_config)
        df_indicators = ti.calculate_all()
        
        # 整合三大法人數據（增強 RL 狀態特徵）
        try:
            df_inst = fetch_institutional_data(symbol, start_date, end_date)
            if not df_inst.empty and 'date' in df_inst.columns:
                # 將法人數據與價格數據合併
                df_inst['date'] = pd.to_datetime(df_inst['date'])
                df_indicators['date'] = pd.to_datetime(df_indicators['date'])
                df_indicators = df_indicators.merge(df_inst, on='date', how='left')
                # 填補缺失值為 0（無法人交易資料時）
                for col in ['foreign_net_buy', 'investment_trust_net_buy', 'dealer_net_buy', 'total_net_buy']:
                    if col in df_indicators.columns:
                        df_indicators[col] = df_indicators[col].fillna(0)
        except Exception:
            pass  # 法人數據為可選增強，不影響主要功能
        
        return df_indicators
    
    def get_available_cache(self) -> List[str]:
        """
        獲取快取資料庫中所有可用的股票代碼
        
        返回:
            股票代碼列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            query = "SELECT DISTINCT symbol FROM stock_daily ORDER BY symbol"
            df = pd.read_sql_query(query, conn)
            
            conn.close()
            
            return df['symbol'].tolist()
            
        except Exception as e:
            print(f"[Cache Query Error]: {e}")
            return []
    
    def clear_cache(self, symbol: str = None):
        """
        清除快取
        
        參數:
            symbol: 要清除的股票代碼，None 表示清除所有
        """
        try:
            if symbol is None:
                # 清除所有
                if self.db_path.exists():
                    self.db_path.unlink()
                    print(f"[Cache Cleared] All cache deleted")
            else:
                # 清除特定股票
                full_symbol = normalize_taiwan_stock_symbol(symbol)
                conn = sqlite3.connect(self.db_path)
                conn.execute("DELETE FROM stock_daily WHERE symbol = ?", (full_symbol,))
                conn.commit()
                conn.close()
                print(f"[Cache Cleared] {full_symbol}")
                
        except Exception as e:
            print(f"[Cache Clear Error]: {e}")


# =============================================================================
# 便捷函數
# =============================================================================

def load_stock_data(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str = '1d',
    use_cache: bool = True
) -> pd.DataFrame:
    """
    便捷函數：載入單一股票數據
    
    這是一個簡化介面，適用於快速載入數據。
    如需更精細的控制，請使用 TaiwanStockDataLoader 類別。
    
    參數:
        symbol: 股票代碼
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        interval: K線週期
        use_cache: 是否使用快取
        
    返回:
        DataFrame 包含 OHLCV 數據
    """
    loader = TaiwanStockDataLoader()
    return loader.load(symbol, start_date, end_date, interval, use_cache=use_cache)


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("TaiwanStockDataLoader 測試")
    print("=" * 60)
    
    # 測試台積電 (2330) 數據載入
    print("\n[測試] 載入台積電 (2330) 2023-01-01 ~ 2024-01-01")
    df = load_stock_data('2330', '2023-01-01', '2024-01-01')
    
    if not df.empty:
        print(f"成功載入 {len(df)} 筆數據")
        print(f"日期範圍: {df['date'].min()} ~ {df['date'].max()}")
        print(f"價格範圍: {df['close'].min():.2f} ~ {df['close'].max():.2f}")
    else:
        print("數據載入失敗")
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)