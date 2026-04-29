# ============================================================================
# 資料處理器 (Data Processor)
# ============================================================================
"""
TaiwanStockDataProcessor - 台股資料處理器

負責:
    1. 資料清洗 - 處理缺失值、異常值、重複資料
    2. 格式轉換 - 統一日期格式、數值格式
    3. 資料分割 - 訓練/測試資料分割
    4. 標準化 - 特徵標準化用於 RL 模型輸入

台股特殊處理:
    - 缺失值: 使用前向填補 (ffill)，避免交易日不連續問題
    - 異常值: 檢測並標記漲跌停日 (±10%)
    - 日期格式: 統一使用 datetime，避免字串比較問題

作者: FinRL量化交易專家
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Tuple, Dict, Union
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# 嘗試導入 config
try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import (
        DATA_DIR, TRAIN_DATA_FILE, TEST_DATA_FILE,
        NORMALIZATION_METHOD, FEATURE_COLUMNS
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    DATA_DIR = './data'
    TRAIN_DATA_FILE = 'train_data.csv'
    TEST_DATA_FILE = 'test_data.csv'
    NORMALIZATION_METHOD = 'zscore'
    FEATURE_COLUMNS = []


class DataProcessor:
    """
    台股資料處理器
    
    負責從各種來源取得的金融資料進行清洗和標準化。
    
    屬性:
        data_dir: 資料儲存目錄
        taiwan_stock_codes: 台股代碼對照表 (Yahoo Finance 格式)
    
    使用範例:
        >>> processor = DataProcessor()
        >>> df = processor.clean_data(raw_df)
        >>> df = processor.normalize_features(df)
        >>> train_df, test_df = processor.split_data(df, train_ratio=0.8)
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        """
        初始化資料處理器
        
        Args:
            data_dir: 資料儲存目錄 (預設使用 config.py 中的設定)
        """
        self.data_dir = data_dir if data_dir else DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 台股代碼對照表（Yahoo Finance 格式）
        self.taiwan_stock_codes = {
            "2330": "2330.TW",
            "台積電": "2330.TW",
            "2317": "2317.TW",
            "鴻海": "2317.TW",
            "2303": "2303.TW",
            "聯發科": "2303.TW",
            "0050": "0050.TW",
            "元大台灣50": "0050.TW",
            "0056": "0056.TW",
            "元大高股息": "0056.TW",
        }
    
    def _convert_code(self, stock_code: str) -> str:
        """
        轉換股票代碼為 Yahoo Finance 格式
        
        Args:
            stock_code: 股票代碼（可直接是 Yahoo 格式如 "2330.TW"）
        
        Returns:
            Yahoo Finance 格式的股票代碼
        """
        if stock_code in self.taiwan_stock_codes:
            return self.taiwan_stock_codes[stock_code]
        elif ".TW" in stock_code.upper() or ".TWO" in stock_code.upper():
            return stock_code.upper()
        else:
            # 假設是台股代碼，自動加上 .TW
            return f"{stock_code}.TW"
    
    # =========================================================================
    # 資料清洗方法
    # =========================================================================
    
    def clean_data(
        self,
        df: pd.DataFrame,
        fill_missing: str = 'ffill',
        remove_duplicates: bool = True,
        sort_by_date: bool = True
    ) -> pd.DataFrame:
        """
        清洗資料
        
        處理項目:
            1. 去除重複資料
            2. 排序 (按日期)
            3. 填補缺失值
            4. 異常值檢測與標記
            
        Args:
            df: 原始資料 DataFrame
            fill_missing: 缺失值填補方式 ('ffill', 'bfill', 'interpolate', None)
            remove_duplicates: 是否去除重複資料
            sort_by_date: 是否按日期排序
        
        Returns:
            清洗後的 DataFrame
        
        台股特殊處理:
            - 使用 ffill 填補因為除權息導致的價格缺口
            - 標記漲跌停日 (±10%) 為特殊情況
        """
        df = df.copy()
        
        # === 去除重複資料 ===
        if remove_duplicates and 'date' in df.columns:
            before = len(df)
            df = df.drop_duplicates(subset=['date'], keep='first')
            after = len(df)
            if before > after:
                print(f"[DataProcessor] 移除 {before - after} 筆重複資料")
        
        # === 按日期排序 ===
        if sort_by_date and 'date' in df.columns:
            df = df.sort_values('date').reset_index(drop=True)
        
        # === 填補缺失值 ===
        if fill_missing:
            # 檢查哪些欄位有缺失值
            missing_cols = df.columns[df.isnull().any()].tolist()
            if missing_cols:
                print(f"[DataProcessor] 發現缺失值欄位: {missing_cols}")
                
            if fill_missing == 'ffill':
                # 前向填補 - 適合時間序列
                df = df.ffill()
            elif fill_missing == 'bfill':
                # 後向填補
                df = df.bfill()
            elif fill_missing == 'interpolate':
                # 線性插值
                df = df.interpolate()
            
            # 再次檢查並填補剩餘缺失值 (適用於開頭的 NaN)
            df = df.ffill().bfill()
        
        return df
    
    def detect_anomalies(
        self,
        df: pd.DataFrame,
        price_limit: float = 0.10,
        volume_threshold: float = 5.0
    ) -> pd.DataFrame:
        """
        異常值檢測
        
        檢測項目:
            1. 漲跌停異常 (±10% 在台股)
            2. 成交量異常 (超過平均 N 倍)
            3. 價格異常 (負值或極端值)
        
        Args:
            df: 資料 DataFrame
            price_limit: 價格變動限制 (預設 10% 為台股漲跌停)
            volume_threshold: 成交量異常閾值 (為平均的 N 倍)
        
        Returns:
            添加了異常標記欄位的 DataFrame
        
        新增欄位:
            - is_limit_up: 是否漲停 (1/0)
            - is_limit_down: 是否跌停 (1/0)
            - is_volume_spike: 是否量能異常 (1/0)
        """
        df = df.copy()
        
        # === 漲跌停檢測 ===
        if 'close' in df.columns and 'close' in df.columns:
            # 計算每日價格變化
            prev_close = df['close'].shift(1)
            price_change = (df['close'] - prev_close) / prev_close
            
            # 漲停標記 (+10%)
            df['is_limit_up'] = 0
            df.loc[price_change >= price_limit, 'is_limit_up'] = 1
            
            # 跌停標記 (-10%)
            df['is_limit_down'] = 0
            df.loc[price_change <= -price_limit, 'is_limit_down'] = 1
            
            # 價格劇烈變化 (> 15%，可能為特殊情況)
            df['price_shock'] = 0
            df.loc[abs(price_change) > 0.15, 'price_shock'] = 1
        
        # === 成交量異常檢測 ===
        if 'volume' in df.columns:
            volume_ma = df['volume'].rolling(window=20).mean()
            volume_ratio = df['volume'] / (volume_ma + 1e-10)
            
            df['is_volume_spike'] = 0
            df.loc[volume_ratio > volume_threshold, 'is_volume_spike'] = 1
        
        return df
    
    # =========================================================================
    # 日期處理方法
    # =========================================================================
    
    def normalize_date_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        統一日期格式
        
        確保 'date' 欄位為 datetime 格式:
            - 去除時區資訊
            - 設定為 index 或保持為欄位
        
        Args:
            df: 資料 DataFrame
        
        Returns:
            日期格式統一後的 DataFrame
        """
        df = df.copy()
        
        if 'date' in df.columns:
            # 轉換為 datetime
            df['date'] = pd.to_datetime(df['date'])
            
            # 去除時區資訊
            if df['date'].dt.tz is not None:
                df['date'] = df['date'].dt.tz_localize(None)
        
        return df
    
    def filter_by_date(
        self,
        df: pd.DataFrame,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None
    ) -> pd.DataFrame:
        """
        按日期區間篩選資料
        
        Args:
            df: 資料 DataFrame
            start_date: 開始日期 (包含)
            end_date: 結束日期 (包含)
        
        Returns:
            篩選後的 DataFrame
        """
        df = df.copy()
        
        # 確保日期格式正確
        df = self.normalize_date_format(df)
        
        # 開始日期篩選
        if start_date:
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date)
            df = df[df['date'] >= start_date]
        
        # 結束日期篩選
        if end_date:
            if isinstance(end_date, str):
                end_date = pd.to_datetime(end_date)
            df = df[df['date'] <= end_date]
        
        return df.reset_index(drop=True)
    
    def get_date_range(self, df: pd.DataFrame) -> Tuple[datetime, datetime]:
        """
        取得資料的日期範圍
        
        Args:
            df: 資料 DataFrame
        
        Returns:
            (起始日期, 結束日期) 的元組
        """
        if 'date' not in df.columns:
            raise ValueError("資料中沒有 'date' 欄位")
        
        df = self.normalize_date_format(df)
        return (df['date'].min(), df['date'].max())
    
    # =========================================================================
    # 資料分割方法
    # =========================================================================
    
    def split_data(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.8,
        train_file: Optional[str] = None,
        test_file: Optional[str] = None,
        rebalance: bool = False
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        分割訓練/測試資料
        
        分割方式:
            - 按時間順序 (不做隨機洗牌)
            - 訓練集在前，測試集在後
        
        Args:
            df: 完整資料 DataFrame
            train_ratio: 訓練資料比例 (預設 0.8 = 80%)
            train_file: 訓練資料檔案名稱
            test_file: 測試資料檔案名稱
            rebalance: 是否重新平衡資料 (目前未實作)
        
        Returns:
            (train_df, test_df): 訓練資料和測試資料
        
        台股注意:
            - 不使用隨機洗牌，保持時間序列完整性
            - 訓練/測試分割點通常在 COVID 時間點 (2020初) 或 2021初
        """
        n = len(df)
        train_size = int(n * train_ratio)
        
        train_df = df.iloc[:train_size].copy()
        test_df = df.iloc[train_size:].copy()
        
        print(f"[DataProcessor] 訓練資料：{len(train_df)} 筆")
        print(f"[DataProcessor]   日期區間：{train_df['date'].min()} 至 {train_df['date'].max()}")
        print(f"[DataProcessor] 測試資料：{len(test_df)} 筆")
        print(f"[DataProcessor]   日期區間：{test_df['date'].min()} 至 {test_df['date'].max()}")
        
        # 自動儲存
        if train_file:
            self.save_data(train_df, train_file)
        if test_file:
            self.save_data(test_df, test_file)
        
        return train_df, test_df
    
    def split_by_date(
        self,
        df: pd.DataFrame,
        split_date: Union[str, datetime],
        train_file: Optional[str] = None,
        test_file: Optional[str] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        按指定日期分割資料
        
        適用於已有明確的訓練/測試分割點時使用
        
        Args:
            df: 資料 DataFrame
            split_date: 分割日期 (此日期後為測試集)
            train_file: 訓練資料檔案名稱
            test_file: 測試資料檔案名稱
        
        Returns:
            (train_df, test_df)
        """
        if isinstance(split_date, str):
            split_date = pd.to_datetime(split_date)
        
        train_df = df[df['date'] < split_date].copy()
        test_df = df[df['date'] >= split_date].copy()
        
        print(f"[DataProcessor] 分割日期：{split_date}")
        print(f"[DataProcessor] 訓練資料：{len(train_df)} 筆 ({train_df['date'].min()} ~ {train_df['date'].max()})")
        print(f"[DataProcessor] 測試資料：{len(test_df)} 筆 ({test_df['date'].min()} ~ {test_df['date'].max()})")
        
        if train_file:
            self.save_data(train_df, train_file)
        if test_file:
            self.save_data(test_df, test_file)
        
        return train_df, test_df
    
    # =========================================================================
    # 標準化方法
    # =========================================================================
    
    def normalize_features(
        self,
        df: pd.DataFrame,
        columns: Optional[List[str]] = None,
        method: str = 'zscore'
    ) -> Tuple[pd.DataFrame, Dict[str, object]]:
        """
        特徵標準化
        
        標準化方法:
            1. zscore: (x - mean) / std
            2. minmax: (x - min) / (max - min)
        
        Args:
            df: 資料 DataFrame
            columns: 要標準化的欄位 (None = 所有數值欄位)
            method: 標準化方法 ('zscore' 或 'minmax')
        
        Returns:
            (標準化後的 DataFrame, 標準化參數字典)
        
        台股注意:
            - 價格類特徵可能需要特殊處理 (如漲跌停日)
            - 成交量標準化可能需要對數變換
        """
        df = df.copy()
        
        # 取得要標準化的欄位
        if columns is None:
            # 自動排除非數值和日期欄位
            columns = df.select_dtypes(include=[np.number]).columns.tolist()
            # 排除 date, symbol 等
            exclude_cols = ['date', 'symbol', 'is_limit_up', 'is_limit_down', 
                          'is_volume_spike', 'price_shock']
            columns = [c for c in columns if c not in exclude_cols]
        
        # 儲存標準化參數
        norm_params = {}
        
        for col in columns:
            if col not in df.columns:
                continue
            
            if method == 'zscore':
                mean = df[col].mean()
                std = df[col].std()
                norm_params[col] = {'mean': mean, 'std': std}
                
                # 避免除以零
                if std > 0:
                    df[f'{col}_normalized'] = (df[col] - mean) / std
                else:
                    df[f'{col}_normalized'] = 0
                    
            elif method == 'minmax':
                min_val = df[col].min()
                max_val = df[col].max()
                norm_params[col] = {'min': min_val, 'max': max_val}
                
                # 避免除以零
                if max_val > min_val:
                    df[f'{col}_normalized'] = (df[col] - min_val) / (max_val - min_val)
                else:
                    df[f'{col}_normalized'] = 0
        
        return df, norm_params
    
    def denormalize_features(
        self,
        df: pd.DataFrame,
        norm_params: Dict[str, Dict]
    ) -> pd.DataFrame:
        """
        反向標準化 (將標準化後的資料轉回原始尺度)
        
        Args:
            df: 標準化後的 DataFrame
            norm_params: 標準化參數 (from normalize_features)
        
        Returns:
            還原後的 DataFrame
        """
        df = df.copy()
        
        for col, params in norm_params.items():
            norm_col = f'{col}_normalized'
            if norm_col in df.columns:
                if 'mean' in params and 'std' in params:
                    # zscore 反向
                    df[col] = df[norm_col] * params['std'] + params['mean']
                elif 'min' in params and 'max' in params:
                    # minmax 反向
                    df[col] = df[norm_col] * (params['max'] - params['min']) + params['min']
        
        return df
    
    # =========================================================================
    # 計算收益率
    # =========================================================================
    
    def calculate_returns(
        self,
        df: pd.DataFrame,
        column: str = "close",
        periods: List[int] = [1, 5, 20]
    ) -> pd.DataFrame:
        """
        計算收益率
        
        Args:
            df: 資料 DataFrame
            column: 用於計算的價格欄位
            periods: 計算收益率的期間列表
        
        Returns:
            帶有 returns 相關欄位的 DataFrame
        
        新增欄位:
            - returns: 1日 simple return
            - log_returns: 1日 log return
            - returns_{N}d: N日 simple return
        """
        df = df.copy()
        
        # 簡單收益率
        df['returns'] = df[column].pct_change()
        
        # 對數收益率 (更適合金融分析)
        df['log_returns'] = np.log(df[column] / df[column].shift(1))
        
        # 多期間收益率
        for period in periods:
            df[f'returns_{period}d'] = df[column].pct_change(periods=period)
        
        return df
    
    # =========================================================================
    # 資料儲存與載入
    # =========================================================================
    
    def save_data(self, df: pd.DataFrame, filename: str) -> str:
        """
        儲存資料到 CSV 檔案
        
        Args:
            df: 資料 DataFrame
            filename: 檔案名稱
        
        Returns:
            完整檔案路徑
        """
        import os
        filepath = os.path.join(self.data_dir, filename)
        
        # 確保目錄存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        df.to_csv(filepath, index=False)
        print(f"[DataProcessor] 資料已儲存至：{filepath}")
        return filepath
    
    def load_data(self, filename: str) -> pd.DataFrame:
        """
        從 CSV 載入資料
        
        Args:
            filename: 檔案名稱
        
        Returns:
            DataFrame
        """
        import os
        filepath = os.path.join(self.data_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"找不到檔案：{filepath}")
        
        df = pd.read_csv(filepath)
        df['date'] = pd.to_datetime(df['date'])
        print(f"[DataProcessor] 從 {filepath} 載入 {len(df)} 筆資料")
        return df
    
    # =========================================================================
    # 工廠方法 - 建立完整處理流程
    # =========================================================================
    
    def process_pipeline(
        self,
        df: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        add_returns: bool = True,
        detect_anomalies: bool = True,
        normalize: bool = True,
        norm_method: str = 'zscore'
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        完整處理流程
        
        執行順序:
            1. 日期格式統一
            2. 日期區間篩選
            3. 去除重複/缺失值處理
            4. 異常值檢測
            5. 收益率計算
            6. 特徵標準化
        
        Args:
            df: 原始資料 DataFrame
            start_date: 開始日期
            end_date: 結束日期
            add_returns: 是否計算收益率
            detect_anomalies: 是否檢測異常值
            normalize: 是否標準化
            norm_method: 標準化方法
        
        Returns:
            (處理後的 DataFrame, 處理參數字典)
        """
        pipeline_params = {}
        
        # 1. 日期格式統一
        df = self.normalize_date_format(df)
        pipeline_params['date_normalized'] = True
        
        # 2. 日期區間篩選
        if start_date or end_date:
            df = self.filter_by_date(df, start_date, end_date)
            pipeline_params['date_filter'] = {'start': start_date, 'end': end_date}
        
        # 3. 資料清洗
        df = self.clean_data(df, fill_missing='ffill')
        pipeline_params['cleaned'] = True
        
        # 4. 異常值檢測
        if detect_anomalies:
            df = self.detect_anomalies(df)
            pipeline_params['anomalies_detected'] = True
        
        # 5. 收益率計算
        if add_returns:
            df = self.calculate_returns(df)
            pipeline_params['returns_added'] = True
        
        # 6. 特徵標準化
        if normalize:
            df, norm_params = self.normalize_features(df, method=norm_method)
            pipeline_params['normalized'] = True
            pipeline_params['norm_params'] = norm_params
        else:
            norm_params = {}
        
        print(f"[DataProcessor] 處理流程完成，共 {len(df)} 筆資料")
        
        return df, pipeline_params


# =============================================================================
# 便利函數
# =============================================================================

def quick_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    快速清洗資料 (便利函數)
    
    Example:
        >>> df = quick_clean(raw_df)
    """
    processor = DataProcessor()
    return processor.clean_data(df)


def quick_normalize(df: pd.DataFrame, method: str = 'zscore') -> pd.DataFrame:
    """
    快速標準化資料 (便利函數)
    
    Example:
        >>> df = quick_normalize(df)
    """
    processor = DataProcessor()
    df, _ = processor.normalize_features(df, method=method)
    return df