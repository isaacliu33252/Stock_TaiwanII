"""
FeatureEngineer - 特徵工程處理器
================================================================================
負責將原始股價數據轉換為 RL 環境所需的狀態特徵。

主要功能:
    1. 整合股價數據與技術指標
    2. 整合三大法人資料
    3. 添加台股特殊特徵
    4. 數據正規化與清理
    5. 生成完整的狀態特徵矩陣

設計原則:
    - 所有特徵皆為浮點數
    - 連續特徵正規化 (归一化)
    - 類別特徵編碼為 0/1
    - 缺失值向前填補

狀態向量 (52維) 分配:
    1. 價格特徵: 6維 (close, open, high, low, volume, turnover)
    2. 技術指標: 20維 (MA, MACD, RSI, KDJ, BB, ATR...)
    3. 型態特徵: 8維 (突破/跌破信號、量增、動量...)
    4. 基本面特徵: 8維 (法人淨買、殖利率、PE、PB...)
    5. 部位特徵: 6維 (持股、成本、未實現盈虧...)
    6. 市場情緒: 4維 (大盤報酬、波动率...)

作者: FinRL量化交易專家
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Tuple, Any
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')


class FeatureEngineer:
    """
    特徵工程處理器
    
    負責將原始數據轉換為 RL 可用的狀態特徵。
    
    Attributes:
        df: 原始股價數據
        tech_indicators: TechnicalIndicators 實例
    
    Example:
        >>> engineer = FeatureEngineer()
        >>> df = engineer.process(
        ...     price_data=price_df,
        ...     corp_data=corp_df,
        ...     include_corp=True
        ... )
    """
    
    def __init__(
        self,
        lookback_window: int = 60
    ):
        """
        初始化特徵工程處理器
        
        Args:
            lookback_window: 回看窗口大小 (用於計算移動指標)
        """
        self.lookback_window = lookback_window
        self.df = None
        self.tech_indicators = None
        # 修正: 加入 scaler 參數儲存，避免資料洩漏（train fit, test transform）
        self._scaler_params: Dict[str, Any] = {}
        self._scaler_fitted: bool = False
    
    def process(
        self,
        price_data: pd.DataFrame,
        corp_data: Optional[pd.DataFrame] = None,
        include_corp: bool = True,
        include_market: bool = False
    ) -> pd.DataFrame:
        """
        處理數據並生成特徵
        
        Args:
            price_data: 股價數據 (必須包含 OHLCV)
            corp_data: 三大法人數據 (可選)
            include_corp: 是否整合法人數據
            include_market: 是否整合大盤數據
        
        Returns:
            添加了所有特徵的 DataFrame
        """
        print("[FeatureEngineer] 開始處理數據...")
        
        # 複製數據避免修改原始數據
        self.df = price_data.copy()
        
        # =====================================================================
        # Step 1: 數據預處理
        # =====================================================================
        self._preprocess_data()
        
        # =====================================================================
        # Step 2: 計算技術指標
        # =====================================================================
        self._calculate_technical_indicators()
        
        # =====================================================================
        # Step 3: 整合法人數據
        # =====================================================================
        if include_corp and corp_data is not None:
            self._integrate_corp_data(corp_data)
        
        # =====================================================================
        # Step 4: 添加台股特殊特徵
        # =====================================================================
        self._add_taiwan_stock_features()
        
        # =====================================================================
        # Step 5: 清理數據
        # =====================================================================
        self._clean_data()
        
        # =====================================================================
        # Step 6: 標準化
        # =====================================================================
        self._normalize_features()
        # 標記 scaler 已 fit，之後可用 transform() 處理測試資料
        self._scaler_fitted = True
        
        print(f"[FeatureEngineer] 完成，共 {len(self.df)} 筆數據，{len(self.df.columns)} 個欄位")
        
        return self.df
    
    def _preprocess_data(self):
        """
        數據預處理
        
        處理智作:
            1. 確保日期格式正確
            2. 按日期排序
            3. 重新索引
            4. 計算基礎欄位
        """
        print("[FeatureEngineer] Step 1: 數據預處理...")
        
        # 確保日期欄位存在並格式化
        if 'date' in self.df.columns:
            self.df['date'] = pd.to_datetime(self.df['date'])
            self.df = self.df.sort_values('date').reset_index(drop=True)
        elif self.df.index.name == 'date':
            self.df = self.df.reset_index()
            self.df['date'] = pd.to_datetime(self.df['date'])
            self.df = self.df.sort_values('date').reset_index(drop=True)
        
        # 確保價格欄位為 float
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in self.df.columns:
                self.df[col] = self.df[col].astype(float)
        
        # 確保成交量為 numeric
        if 'volume' in self.df.columns:
            self.df['volume'] = pd.to_numeric(self.df['volume'], errors='coerce').fillna(0)
        
        # 計算成交額 (若不存在)
        if 'turnover' not in self.df.columns:
            self.df['turnover'] = self.df['open'] * self.df['volume']
        
        # 處理缺失值 (向前填補再用向後填補覆蓋開頭的 NaN)
        self.df = self.df.ffill().bfill()
        
        # 去除价格为 0 或负数的行
        self.df = self.df[self.df['close'] > 0]
        
        print(f"  - 有效數據筆數: {len(self.df)}")
    
    def _calculate_technical_indicators(self):
        """
        計算技術指標
        
        使用 TechnicalIndicators 類計算所有需要的技術指標。
        計算完成後，指標欄位會添加到 self.df
        """
        print("[FeatureEngineer] Step 2: 計算技術指標...")
        
        from .technical_indicators import TechnicalIndicators
        
        # 建立技術指標計算器
        self.tech_indicators = TechnicalIndicators(self.df, self.lookback_window)
        
        # 計算所有指標
        self.df = self.tech_indicators.calculate_all()
        
        print(f"  - 技術指標計算完成")
    
    def _integrate_corp_data(self, corp_data: pd.DataFrame):
        """
        整合三大法人數據
        
        法人數據是 RL 狀態的重要組成部分，反映機構投資者的行為。
        
        Args:
            corp_data: 三大法人 DataFrame
        """
        print("[FeatureEngineer] Step 3: 整合法人數據...")
        
        # 如果無法整合，跳過
        if corp_data.empty:
            print("  - 法人數據為空，跳過")
            return
        
        # 嘗試匹配日期
        if 'date' in corp_data.columns and 'date' in self.df.columns:
            corp_data['date'] = pd.to_datetime(corp_data['date'])
            
            # 嘗試找到法人凈買欄位
            # 欄位名稱可能因來源而異，嘗試自動識別
            net_buy_cols = [c for c in corp_data.columns if '凈' in c or 'net' in c.lower()]
            
            if net_buy_cols:
                # 與股價數據合併
                self.df = self.df.merge(
                    corp_data[['date'] + net_buy_cols],
                    on='date',
                    how='left'
                )
                
                # 填補缺失值 (使用 ffill + bfill 取代已廢棄的 method 參數)
                for col in net_buy_cols:
                    self.df[col] = self.df[col].ffill().bfill()
                
                print(f"  - 已整合法人欄位: {net_buy_cols}")
    
    def _add_taiwan_stock_features(self):
        """
        添加台股特殊特徵
        
        台股特性:
            1. 涨跌停限制
            2. T+2 交割
            3. 1000 股交易單位
            4. 三大法人交易限制
        
        添加的特徵:
            - daily_return: 日報酬率
            - limit_up: 是否漲停 (0/1)
            - limit_down: 是否跌停 (0/1)
            - amplitude: 振幅
        """
        print("[FeatureEngineer] Step 4: 添加台股特殊特徵...")
        
        # 日報酬率
        self.df['daily_return'] = self.df['close'].pct_change()
        
        # 前一日收盤價
        prev_close = self.df['close'].shift(1)
        
        # 涨跌停判斷
        # 台股涨跌停限制為 10%
        self.df['limit_up'] = 0
        self.df['limit_down'] = 0
        
        # 漲停: 當日最高價達到或超過前一日收盤價的 110%
        limit_up_mask = self.df['high'] >= prev_close * 1.10
        self.df.loc[limit_up_mask, 'limit_up'] = 1
        
        # 跌停: 當日最低價達到或低於前一日收盤價的 90%
        limit_down_mask = self.df['low'] <= prev_close * 0.90
        self.df.loc[limit_down_mask, 'limit_down'] = 1
        
        # 振幅 (最高-最低)/前收盤
        self.df['amplitude'] = (self.df['high'] - self.df['low']) / prev_close
        
        # 開盤跳空幅度
        self.df['gap'] = (self.df['open'] - prev_close) / prev_close
        
        print("  - 台股特徵添加完成")
    
    def _clean_data(self):
        """
        清理數據
        
        處理智作:
            1. 去除包含 NaN 的行 (在 lookback_window 之後)
            2. 確保所有數值為 float
            3. 處理無效值
        """
        print("[FeatureEngineer] Step 5: 清理數據...")
        
        # 去除落後指標造成的 NaN
        # 保留足夠的 lookback_window 數據
        initial_len = len(self.df)
        
        # 找出有 NaN 的行
        nan_rows = self.df.isnull().any(axis=1)
        
        # 從有數據的第一行開始，去除前面的 NaN 行
        first_valid_idx = self.df.dropna().index[0] if not self.df.dropna().empty else 0
        
        # 只保留 first_valid_idx 之後的數據
        if first_valid_idx > 0:
            self.df = self.df.loc[first_valid_idx:].reset_index(drop=True)
        
        # 剩餘的 NaN 用 0 填補
        self.df = self.df.fillna(0)
        
        # 確保數值類型
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        self.df[numeric_cols] = self.df[numeric_cols].astype(np.float32)
        
        final_len = len(self.df)
        print(f"  - 清理前行: {initial_len}, 清理後行: {final_len}")
    
    def _normalize_features(self):
        """
        標準化特徵
        
        對部分特徵進行標準化，使其適合 RL 訓練。
        使用 z-score 標準化或 min-max 正規化。
        
        修正: 若已有 fit 的 scaler 參數，則套用該參數（transform 模式），
        否則直接正規化並儲存參數（向後兼容單一 dataset）。
        """
        print("[FeatureEngineer] Step 6: 特徵標準化...")
        
        # 識別需要標準化的欄位
        # 價格相關欄位 - 使用 min-max 正規化到 [0, 1]
        price_related = ['close', 'open', 'high', 'low']
        
        if self._scaler_fitted and 'price_max' in self._scaler_params:
            # Transform 模式：使用 train fit 的參數
            max_val = self._scaler_params['price_max']
            for col in price_related:
                if col in self.df.columns:
                    self.df[col] = self.df[col] / max_val
        else:
            # Fit 模式（向後兼容）：從 self.df 計算並儲存
            max_val = self.df['close'].max()
            self._scaler_params['price_max'] = max_val
            for col in price_related:
                if col in self.df.columns:
                    if max_val > 0:
                        self.df[col] = self.df[col] / max_val
        
        # 技術指標 - 使用 z-score 標準化
        # (x - mean) / std，使用 expanding window 避免 lookahead bias
        # expanding 只包含到當前時間點之前的數據，不會洩漏未來資訊
        tech_cols = [c for c in self.df.columns if c.startswith(('ma', 'macd', 'rsi', 'kdj', 'atr'))]
        
        for col in tech_cols:
            if col in self.df.columns:
                # 使用 expanding window 計算，只用歷史數據
                expanding_mean = self.df[col].expanding().mean()
                expanding_std = self.df[col].expanding().std()
                self.df[col] = (self.df[col] - expanding_mean) / (expanding_std + 1e-10)
        
        print("  - 特徵標準化完成")

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        在訓練資料上 fit scaler 並 transform
        
        Args:
            df: 訓練資料 DataFrame
        
        Returns:
            標準化後的 DataFrame
        """
        self.df = df.copy()
        self._preprocess_data()
        self._calculate_technical_indicators()
        self._clean_data()
        self._normalize_features()  # 會計算並儲存 scaler params
        self._scaler_fitted = True
        print(f"[FeatureEngineer] fit_transform 完成，共 {len(self.df)} 筆，scaler 已儲存")
        return self.df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        用已 fit 的 scaler 參數 transform 測試/新資料
        
        Args:
            df: 測試或新資料 DataFrame
        
        Returns:
            標準化後的 DataFrame
        """
        if not self._scaler_fitted:
            raise RuntimeError(
                "[FeatureEngineer] scaler 尚未 fit，請先呼叫 fit_transform() "
                "或在同一個 DataFrame 上呼叫 process()"
            )
        self.df = df.copy()
        self._preprocess_data()
        self._calculate_technical_indicators()
        self._clean_data()
        self._normalize_features()  # 會使用已儲存的 scaler params
        print(f"[FeatureEngineer] transform 完成，共 {len(self.df)} 筆")
        return self.df
    
    def get_feature_columns(self) -> List[str]:
        """
        取得所有特徵欄位名稱
        
        Returns:
            特徵欄位名稱列表
        """
        # 基本欄位
        base_cols = ['date', 'close', 'open', 'high', 'low', 'volume', 'turnover']
        
        # 技術指標欄位
        if self.tech_indicators:
            tech_cols = TechnicalIndicators.get_feature_columns()
        else:
            tech_cols = []
        
        # 台股特徵
        taiwan_cols = ['daily_return', 'limit_up', 'limit_down', 'amplitude', 'gap']
        
        # 法人特徵 (如果存在)
        corp_cols = [c for c in self.df.columns if '凈' in c or 'net' in c.lower()]
        
        return base_cols + tech_cols + taiwan_cols + corp_cols
    
    def get_state_feature_names(self) -> Dict[str, List[str]]:
        """
        取得 RL 狀態特徵的分類
        
        Returns:
            Dictionary，按類別分組的特徵名稱
        """
        return {
            'price_features': ['close', 'open', 'high', 'low', 'volume', 'turnover'],
            'technical_features': self.tech_indicators.get_feature_columns() if self.tech_indicators else [],
            'pattern_features': [
                'highest_breakout', 'lowest_breakdown',
                'volume_spike', 'price_momentum', 'volatility',
                'consecutive_up_days', 'consecutive_down_days',
                'gap_up_or_down'
            ],
            'fundamental_features': [
                'foreign_net_buy_1d', 'foreign_net_buy_3d', 'foreign_net_buy_5d',
                'dealer_net_buy_1d', 'investment_trust_net_buy',
                'dividend_yield', 'per', 'pbr'
            ],
            'position_features': [
                'current_position', 'position_value_ratio',
                'unrealized_pnl', 'max_drawdown',
                'days_since_trade', 'cash_ratio'
            ],
            'sentiment_features': [
                'twse_index_return', 'twse_index_volume_change',
                'sector_correlation', 'market_volatility'
            ],
            'taiwan_features': ['daily_return', 'limit_up', 'limit_down', 'amplitude', 'gap']
        }


# =============================================================================
# 便捷函數
# =============================================================================

def engineer_features(
    price_data: pd.DataFrame,
    corp_data: Optional[pd.DataFrame] = None,
    lookback_window: int = 60
) -> pd.DataFrame:
    """
    便捷函數：快速進行特徵工程
    
    Args:
        price_data: 股價數據
        corp_data: 法人數據 (可選)
        lookback_window: 回看窗口
    
    Returns:
        處理後的 DataFrame
    
    Example:
        >>> df = engineer_features(price_df, corp_df)
    """
    engineer = FeatureEngineer(lookback_window=lookback_window)
    return engineer.process(price_data, corp_data)
