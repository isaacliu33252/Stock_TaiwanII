"""
================================================================================
StockDatabase - SQLite 資料庫管理 (v2新版)
================================================================================
負責管理台股歷史數據的 SQLite 資料庫。

主要功能：
    1. 初始化資料庫和表格
    2. 儲存和讀取股票數據
    3. 快取管理
    4. 資料清理

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import sqlite3
import pandas as pd
from typing import Optional, List, Tuple, Dict
from pathlib import Path
from datetime import datetime
import warnings


class StockDatabase:
    """
    台股資料庫管理類別
    
    使用 SQLite 作為本地資料庫，儲存股票歷史數據和技術指標。
    
    Attributes:
        db_path: 資料庫路徑
        conn: SQLite 連接
        
    使用範例:
        >>> db = StockDatabase('/path/to/stock_data.db')
        >>> 
        >>> # 儲存數據
        >>> db.save_stock_data(df, '2330.TW')
        >>> 
        >>> # 讀取數據
        >>> df = db.load_stock_data('2330.TW', '2020-01-01', '2024-12-31')
        >>> 
        >>> # 獲取可用股票列表
        >>> symbols = db.get_available_symbols()
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化資料庫
        
        參數:
            db_path: 資料庫路徑，預設使用專案內的 stock_data.db
        """
        if db_path is None:
            self.db_path = Path(__file__).parent / 'stock_data.db'
        else:
            self.db_path = Path(db_path)
        
        # 確保目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化資料庫
        self._init_database()
        
        self.conn = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """獲取資料庫連接"""
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
        return self.conn
    
    def _init_database(self):
        """初始化資料庫表格"""
        conn = self._get_connection()
        
        # 股票日線資料表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                turnover REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)
        
        # 技術指標資料表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_indicators (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                ma3 REAL, ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL, ma120 REAL, ma240 REAL,
                macd_line REAL, signal_line REAL, histogram REAL,
                rsi_14 REAL, rsi_28 REAL,
                kdj_k REAL, kdj_d REAL, kdj_j REAL,
                bb_upper REAL, bb_lower REAL, bb_width REAL,
                atr_14 REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)
        
        # 三大法人資料表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS institutional_data (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                foreign_net_buy REAL,
                investment_trust_net_buy REAL,
                dealer_net_buy REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)
        
        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_symbol_date ON stock_daily (symbol, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_indicator_symbol_date ON stock_indicators (symbol, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_institutional_symbol_date ON institutional_data (symbol, date)")
        
        conn.commit()
        
        print(f"[StockDatabase] 資料庫初始化完成: {self.db_path}")
    
    def save_stock_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        if_exists: str = 'replace'
    ) -> bool:
        """
        儲存股票數據
        
        參數:
            df: 包含 OHLCV 數據的 DataFrame
            symbol: 股票代碼
            if_exists: 'replace'=替換, 'append'=附加
        
        返回:
            True 如果成功
        """
        if df.empty:
            return False
        
        conn = self._get_connection()
        
        try:
            # 準備數據
            df_save = df.copy()
            df_save['symbol'] = symbol
            df_save['date'] = pd.to_datetime(df_save['date']).astype(str)
            
            # 移除時間戳欄位（如果存在）
            if 'created_at' in df_save.columns:
                df_save = df_save.drop(columns=['created_at'])
            
            # 儲存
            df_save.to_sql(
                'stock_daily',
                conn,
                if_exists=if_exists,
                index=False,
                method='REPLACE'
            )
            
            conn.commit()
            
            print(f"[StockDatabase] 已儲存 {symbol}: {len(df)} 筆數據")
            return True
            
        except Exception as e:
            print(f"[StockDatabase] 儲存失敗: {e}")
            return False
    
    def load_stock_data(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        columns: List[str] = None
    ) -> pd.DataFrame:
        """
        讀取股票數據
        
        參數:
            symbol: 股票代碼
            start_date: 開始日期（可選）
            end_date: 結束日期（可選）
            columns: 要讀取的欄位（可選）
        
        返回:
            DataFrame 包含股票數據
        """
        conn = self._get_connection()
        
        # 構建查詢（使用參數化查詢防止 SQL injection）
        col_str = '*' if columns is None else ', '.join(columns)
        
        query = f"""
            SELECT {col_str}
            FROM stock_daily
            WHERE symbol = ?
        """
        params = [symbol]
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY date"
        
        try:
            df = pd.read_sql_query(query, conn, params=params, parse_dates=['date'] if 'date' in col_str else None)
            
            if not df.empty:
                print(f"[StockDatabase] 已載入 {symbol}: {len(df)} 筆數據")
            
            return df
            
        except Exception as e:
            print(f"[StockDatabase] 讀取失敗: {e}")
            return pd.DataFrame()
    
    def get_available_symbols(self) -> List[str]:
        """
        獲取資料庫中所有可用的股票代碼
        
        返回:
            股票代碼列表
        """
        conn = self._get_connection()
        
        query = "SELECT DISTINCT symbol FROM stock_daily ORDER BY symbol"
        
        try:
            df = pd.read_sql_query(query, conn)
            return df['symbol'].tolist()
        except Exception as e:
            print(f"[StockDatabase] 查詢失敗: {e}")
            return []
    
    def delete_stock_data(self, symbol: str) -> bool:
        """
        刪除股票數據
        
        參數:
            symbol: 股票代碼
        
        返回:
            True 如果成功
        """
        conn = self._get_connection()
        
        try:
            conn.execute("DELETE FROM stock_daily WHERE symbol = ?", (symbol,))
            conn.execute("DELETE FROM stock_indicators WHERE symbol = ?", (symbol,))
            conn.execute("DELETE FROM institutional_data WHERE symbol = ?", (symbol,))
            conn.commit()
            
            print(f"[StockDatabase] 已刪除 {symbol} 的所有數據")
            return True
            
        except Exception as e:
            print(f"[StockDatabase] 刪除失敗: {e}")
            return False
    
    def get_database_stats(self) -> Dict:
        """
        獲取資料庫統計資訊
        
        返回:
            統計資訊字典
        """
        conn = self._get_connection()
        
        stats = {}
        
        try:
            # 股票數量
            query = "SELECT COUNT(DISTINCT symbol) as count FROM stock_daily"
            stats['stock_count'] = pd.read_sql_query(query, conn).iloc[0]['count']
            
            # 總記錄數
            query = "SELECT COUNT(*) as count FROM stock_daily"
            stats['total_records'] = pd.read_sql_query(query, conn).iloc[0]['count']
            
            # 日期範圍
            query = "SELECT MIN(date) as min_date, MAX(date) as max_date FROM stock_daily"
            result = pd.read_sql_query(query, conn).iloc[0]
            stats['min_date'] = result['min_date']
            stats['max_date'] = result['max_date']
            
        except Exception as e:
            print(f"[StockDatabase] 統計查詢失敗: {e}")
        
        return stats
    
    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def init_database(db_path: str = None) -> StockDatabase:
    """
    便捷函數：初始化資料庫
    
    參數:
        db_path: 資料庫路徑
        
    返回:
        StockDatabase 實例
    """
    return StockDatabase(db_path)


def query_stock_data(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
    db_path: str = None
) -> pd.DataFrame:
    """
    便捷函數：查詢股票數據
    
    參數:
        symbol: 股票代碼
        start_date: 開始日期
        end_date: 結束日期
        db_path: 資料庫路徑
        
    返回:
        DataFrame
    """
    db = StockDatabase(db_path)
    df = db.load_stock_data(symbol, start_date, end_date)
    db.close()
    return df


def save_stock_data(
    df: pd.DataFrame,
    symbol: str,
    db_path: str = None
) -> bool:
    """
    便捷函數：儲存股票數據
    
    參數:
        df: DataFrame
        symbol: 股票代碼
        db_path: 資料庫路徑
        
    返回:
        True 如果成功
    """
    db = StockDatabase(db_path)
    result = db.save_stock_data(df, symbol)
    db.close()
    return result


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("StockDatabase 測試")
    print("=" * 60)
    
    # 創建資料庫
    print("\n[測試] 創建資料庫...")
    db = StockDatabase('/tmp/test_stock.db')
    
    # 獲取統計
    print("\n[測試] 獲取統計資訊...")
    stats = db.get_database_stats()
    print(f"  股票數量: {stats.get('stock_count', 0)}")
    print(f"  總記錄數: {stats.get('total_records', 0)}")
    
    # 關閉
    db.close()
    
    # 清理測試資料庫
    import os
    if os.path.exists('/tmp/test_stock.db'):
        os.remove('/tmp/test_stock.db')
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)