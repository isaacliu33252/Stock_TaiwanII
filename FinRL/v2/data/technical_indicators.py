"""
================================================================================
TechnicalIndicators - 技術指標計算模組 (v2新版)
================================================================================
計算金融技術指標，這些指標將作為 RL 環境的狀態特徵輸入。

指標類別:
    1. 移動平均線 (MA) 系列: MA3, MA5, MA10, MA20, MA60, MA120, MA240
    2. MACD 系列: MACD Line, Signal Line, Histogram
    3. 動量指標: RSI, KDJ, 威廉指標
    4. 波動性指標: Bollinger Bands, ATR
    5. 成交量指標: 量增信號

設計原則:
    - 使用 TA-Lib 加速計算 (若已安裝)
    - 若無 TA-Lib，則使用 Pandas 手工計算
    - 所有輸出為浮點數或 0/1 (binary)
    - 輸出均已標準化或歸一化，適合 RL 訓練

技術指標 → RL State Features 對應:
    MA 系列 → price_features / technical_features
    MACD → technical_features
    RSI → technical_features
    KDJ → technical_features
    Bollinger Bands → technical_features

台股特殊規則:
    - 股票代碼格式: 2330.TW (Yahoo Finance 格式)
    - 交易單位: 1000 股為一張
    - 漲跌停限制: 10%
    - T+2 交割制度

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Tuple, Union
from functools import wraps
import warnings

warnings.filterwarnings('ignore')


# =============================================================================
# TA-Lib 包裝器 (嘗試使用 TA-Lib，若失敗則使用 Pandas)
# =============================================================================

# 嘗試導入 TA-Lib
TALIB_AVAILABLE = False
try:
    import talib
    TALIB_AVAILABLE = True
    print("[TechnicalIndicators] TA-Lib 可用")
except ImportError:
    TALIB_AVAILABLE = False
    print("[TechnicalIndicators] TA-Lib 不可用，將使用 Pandas 計算")


def try_talib(func):
    """
    裝飾器：優先使用 TA-Lib，若失敗則使用 Pandas 實作
    
    用法:
        @try_talib
        def calculate_ma(df, ma_type='sma', timeperiod=20):
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            warnings.warn(f"{func.__name__} 使用 Pandas 計算: {e}")
            return None
    return wrapper


# =============================================================================
# 技術指標計算類別
# =============================================================================

class TechnicalIndicators:
    """
    技術指標計算器
    
    負責計算所有 RL 環境所需的技術指標。
    
    Attributes:
        df: 輸入的股價數據 (必須包含 OHLCV)
        lookback_window: 回看窗口大小 (預設 60)
    
    Example:
        >>> df = pd.read_csv('2330.csv')
        >>> ti = TechnicalIndicators(df)
        >>> df_with_features = ti.calculate_all()
    """
    
    def __init__(
        self,
        df: pd.DataFrame,
        lookback_window: int = 60
    ):
        """
        初始化技術指標計算器
        
        Args:
            df: 股價數據，必須包含 ['open', 'high', 'low', 'close', 'volume']
            lookback_window: 回看窗口大小
        """
        self.df = df.copy()
        self.lookback_window = lookback_window
        
        # 確保必要的欄位存在
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in self.df.columns]
        if missing:
            raise ValueError(f"缺少必要欄位: {missing}")
        
        # 確保按日期排序
        if 'date' in self.df.columns:
            self.df = self.df.sort_values('date').reset_index(drop=True)
    
    # =========================================================================
    # MA (移動平均線) 系列
    # =========================================================================
    
    def calculate_ma(
        self,
        periods: List[int] = [3, 5, 10, 20, 60, 120, 240],
        ma_type: str = 'sma'  # 'sma', 'ema'
    ) -> pd.DataFrame:
        """
        計算移動平均線
        
        移動平均線是技術分析中最基礎的指標，
        用於平滑價格波動，識別趨勢方向。
        
        Args:
            periods: 週期列表，預設 [3, 5, 10, 20, 60, 120, 240]
            ma_type: MA 類型，'sma'=簡單移動平均, 'ema'=指數移動平均
            
        Returns:
            包含 MA 各週期的 DataFrame
            
        備註:
            - MA3, MA5: 短期趨勢
            - MA10, MA20: 中期趨勢
            - MA60, MA120, MA240: 長期趨勢
        """
        
        for period in periods:
            col_name = f'ma{period}'
            
            if TALIB_AVAILABLE:
                try:
                    if ma_type == 'ema':
                        self.df[col_name] = talib.EMA(self.df['close'].values, timeperiod=period)
                    else:
                        self.df[col_name] = talib.SMA(self.df['close'].values, timeperiod=period)
                except Exception as e:
                    # TA-Lib 失敗，使用 Pandas
                    if ma_type == 'ema':
                        self.df[col_name] = self.df['close'].ewm(span=period, adjust=False).mean()
                    else:
                        self.df[col_name] = self.df['close'].rolling(window=period).mean()
            else:
                # 無 TA-Lib，使用 Pandas
                if ma_type == 'ema':
                    self.df[col_name] = self.df['close'].ewm(span=period, adjust=False).mean()
                else:
                    self.df[col_name] = self.df['close'].rolling(window=period).mean()
        
        # 計算 MA 斜率（變化率）
        for period in [3, 20, 60]:
            col_name = f'ma{period}_slope'
            ma_col = f'ma{period}'
            if ma_col in self.df.columns:
                # 計算 MA 的日變化率
                self.df[col_name] = self.df[ma_col].pct_change(periods=1)
        
        # MA 交叉信號
        # 金叉：MA5 > MA20，死叉：MA5 < MA20
        if 'ma5' in self.df.columns and 'ma20' in self.df.columns:
            self.df['ma_cross_signal'] = np.where(
                self.df['ma5'] > self.df['ma20'], 1,  # 金叉
                np.where(self.df['ma5'] < self.df['ma20'], -1, 0)  # 死叉
            )
        
        # 價格與 MA 的比率
        for period in [120, 240]:
            col_name = f'close_ma{period}_ratio'
            ma_col = f'ma{period}'
            if ma_col in self.df.columns:
                self.df[col_name] = self.df['close'] / self.df[ma_col]
        
        # MA60 / MA240 比率（長期趨勢）
        if 'ma60' in self.df.columns and 'ma240' in self.df.columns:
            self.df['ma60_ma240_ratio'] = self.df['ma60'] / self.df['ma240']
        
        return self.df
    
    # =========================================================================
    # MACD (平滑異同移動平均線)
    # =========================================================================
    
    def calculate_macd(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> pd.DataFrame:
        """
        計算 MACD
        
        MACD 是最受歡迎的趨勢指標之一，
        由快線(MACD Line)、慢線(Signal Line)和柱狀圖(Histogram)組成。
        
        公式:
            MACD Line = EMA(close, 12) - EMA(close, 26)
            Signal Line = EMA(MACD Line, 9)
            Histogram = MACD Line - Signal Line
            
        Args:
            fast_period: 快線週期 (預設 12)
            slow_period: 慢線週期 (預設 26)
            signal_period: 信號線週期 (預設 9)
            
        Returns:
            包含 MACD, Signal, Histogram 的 DataFrame
            
        交易信號:
            - MACD > 0: 多頭趨勢
            - MACD < 0: 空頭趨勢
            - MACD 突破 Signal: 買入信號
            - MACD 跌破 Signal: 賣出信號
        """
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            try:
                macd_line, signal_line, hist = talib.MACD(
                    close,
                    fastperiod=fast_period,
                    slowperiod=slow_period,
                    signalperiod=signal_period
                )
                self.df['macd_line'] = macd_line
                self.df['signal_line'] = signal_line
                self.df['histogram'] = hist
            except Exception:
                # TA-Lib 失敗，使用 Pandas
                ema_fast = pd.Series(close).ewm(span=fast_period, adjust=False).mean()
                ema_slow = pd.Series(close).ewm(span=slow_period, adjust=False).mean()
                macd_line = ema_fast - ema_slow
                signal_line = pd.Series(macd_line).ewm(span=signal_period, adjust=False).mean()
                hist = macd_line - signal_line
                
                self.df['macd_line'] = macd_line
                self.df['signal_line'] = signal_line
                self.df['histogram'] = hist
        else:
            # 無 TA-Lib，使用 Pandas
            ema_fast = pd.Series(close).ewm(span=fast_period, adjust=False).mean()
            ema_slow = pd.Series(close).ewm(span=slow_period, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = pd.Series(macd_line).ewm(span=signal_period, adjust=False).mean()
            hist = macd_line - signal_line
            
            self.df['macd_line'] = macd_line
            self.df['signal_line'] = signal_line
            self.df['histogram'] = hist
        
        # MACD 柱狀圖變化（動量）
        self.df['histogram_change'] = self.df['histogram'].diff()
        
        # MACD 由負轉正 / 由正轉負
        self.df['macd_turn_positive'] = np.where(
            (self.df['macd_line'] > 0) & (self.df['macd_line'].shift(1) <= 0), 1, 0
        )
        self.df['macd_turn_negative'] = np.where(
            (self.df['macd_line'] < 0) & (self.df['macd_line'].shift(1) >= 0), 1, 0
        )
        
        return self.df
    
    # =========================================================================
    # RSI (相對強弱指標)
    # =========================================================================
    
    def calculate_rsi(
        self,
        periods: List[int] = [14, 28],
        ma_type: str = 'ema'
    ) -> pd.DataFrame:
        """
        計算 RSI (Relative Strength Index)
        
        RSI 衡量價格變化的速度和幅度，
        取值範圍 0~100，越高表示超買，越低表示超賣。
        
        公式:
            RSI = 100 - (100 / (1 + RS))
            RS = 平均漲幅 / 平均跌幅
            
        Args:
            periods: RSI 週期列表，預設 [14, 28]
            ma_type: 平均計算方式，'ema' 或 'sma'
            
        Returns:
            包含 RSI 的 DataFrame
            
        交易信號:
            - RSI > 70: 超買，可能反轉
            - RSI < 30: 超賣，可能反彈
            - RSI 突破 50: 多頭信號
            - RSI 跌破 50: 空頭信號
        """
        close = self.df['close'].values
        
        for period in periods:
            col_name = f'rsi_{period}'
            
            if TALIB_AVAILABLE:
                try:
                    self.df[col_name] = talib.RSI(close, timeperiod=period)
                except Exception:
                    # TA-Lib 失敗，使用 Pandas
                    delta = pd.Series(close).diff()
                    gain = delta.where(delta > 0, 0)
                    loss = -delta.where(delta < 0, 0)
                    
                    if ma_type == 'ema':
                        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
                        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
                    else:
                        avg_gain = gain.rolling(window=period).mean()
                        avg_loss = loss.rolling(window=period).mean()
                    
                    rs = avg_gain / avg_loss
                    self.df[col_name] = 100 - (100 / (1 + rs))
            else:
                # 無 TA-Lib，使用 Pandas
                delta = pd.Series(close).diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                
                if ma_type == 'ema':
                    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
                    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
                else:
                    avg_gain = gain.rolling(window=period).mean()
                    avg_loss = loss.rolling(window=period).mean()
                
                rs = avg_gain / avg_loss
                self.df[col_name] = 100 - (100 / (1 + rs))
        
        return self.df
    
    # =========================================================================
    # KDJ (隨機指標)
    # =========================================================================
    
    def calculate_kdj(
        self,
        k_period: int = 9,
        d_period: int = 3,
        j_multiplier: float = 3
    ) -> pd.DataFrame:
        """
        計算 KDJ (隨機指標)
        
        KDJ 是一個超買超賣指標，類似於傳統的 KDJ 或 RSV 指標。
        
        公式:
            RSV = (close - lowest_low) / (highest_high - lowest_low) * 100
            K = 2/3 * prev_K + 1/3 * RSV
            D = 2/3 * prev_D + 1/3 * K
            J = 3 * K - 2 * D
            
        Args:
            k_period: K 線週期 (預設 9)
            d_period: D 線週期 (預設 3)
            j_multiplier: J 線倍數 (預設 3)
            
        Returns:
            包含 kdj_k, kdj_d, kdj_j 的 DataFrame
            
        交易信號:
            - K > 80: 超買
            - K < 20: 超賣
            - 金叉 (K > D): 買入
            - 死叉 (K < D): 賣出
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        # 計算 RSV (Raw Stochastic Value)
        lowest_low = pd.Series(low).rolling(window=k_period).min()
        highest_high = pd.Series(high).rolling(window=k_period).max()
        
        # 避免除以零
        denominator = highest_high - lowest_low
        denominator = denominator.replace(0, np.nan)
        
        rsv = (close - lowest_low) / denominator * 100
        
        # 計算 K, D, J（向量化 EMA 實現，替代 for 迴圈）
        # K = (2/3)*prev_K + (1/3)*RSV → EMA(RSV, alpha=1/3)
        # D = (2/3)*prev_D + (1/3)*K   → EMA(K, alpha=1/3)
        rsv_series = pd.Series(rsv)
        k = rsv_series.ewm(alpha=1/3, adjust=False, min_periods=1).mean().values
        d = pd.Series(k).ewm(alpha=1/3, adjust=False, min_periods=1).mean().values
        
        self.df['kdj_k'] = k
        self.df['kdj_d'] = d
        self.df['kdj_j'] = j_multiplier * k - (j_multiplier - 1) * d
        
        return self.df
    
    # =========================================================================
    # Bollinger Bands (布林帶)
    # =========================================================================
    
    def calculate_bollinger_bands(
        self,
        period: int = 20,
        nb_devup: float = 2,
        nb_devdn: float = 2
    ) -> pd.DataFrame:
        """
        計算 Bollinger Bands (布林帶)
        
        布林帶由中軌(MA)和上下兩條軌線組成，
        用於衡量價格的波動性。
        
        公式:
            中軌 = MA(close, period)
            上軌 = 中軌 + nb_devup * STD(close, period)
            下軌 = 中軌 - nb_devdn * STD(close, period)
            
        Args:
            period: 週期 (預設 20)
            nb_devup: 上軌標準差倍數 (預設 2)
            nb_devdn: 下軌標準差倍數 (預設 2)
            
        Returns:
            包含 bb_upper, bb_lower, bb_width 的 DataFrame
            
        交易信號:
            - 價格觸及上軌: 可能超買
            - 價格觸及下軌: 可能超賣
            - 布林帶收窄: 波動性降低，可能突破
        """
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            try:
                upper, middle, lower = talib.BBANDS(
                    close,
                    timeperiod=period,
                    nbdevup=nb_devup,
                    nbdevdn=nb_devdn,
                    matype=0  # SMA
                )
                self.df['bb_upper'] = upper
                self.df['bb_middle'] = middle
                self.df['bb_lower'] = lower
            except Exception:
                # TA-Lib 失敗，使用 Pandas
                middle = pd.Series(close).rolling(window=period).mean()
                std = pd.Series(close).rolling(window=period).std(ddof=1)

                self.df['bb_upper'] = middle + nb_devup * std
                self.df['bb_middle'] = middle
                self.df['bb_lower'] = middle - nb_devdn * std
        else:
            # 無 TA-Lib，使用 Pandas
            middle = pd.Series(close).rolling(window=period).mean()
            std = pd.Series(close).rolling(window=period).std(ddof=1)

            self.df['bb_upper'] = middle + nb_devup * std
            self.df['bb_middle'] = middle
            self.df['bb_lower'] = middle - nb_devdn * std
        
        # 布林帶寬度（波動性指標）
        self.df['bb_width'] = (self.df['bb_upper'] - self.df['bb_lower']) / self.df['bb_middle']
        
        return self.df
    
    # =========================================================================
    # ATR (平均真實波幅)
    # =========================================================================
    
    def calculate_atr(
        self,
        period: int = 14
    ) -> pd.DataFrame:
        """
        計算 ATR (Average True Range)
        
        ATR 衡量價格的波動性，不考慮趨勢方向。
        
        公式:
            True Range = max(
                high - low,
                |high - prev_close|,
                |low - prev_close|
            )
            ATR = MA(True Range, period)
            
        Args:
            period: ATR 週期 (預設 14)
            
        Returns:
            包含 atr_14 的 DataFrame
            
        用途:
            - 停損設定
            - 市場波動性衡量
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            try:
                self.df['atr_14'] = talib.ATR(high, low, close, timeperiod=period)
            except Exception:
                # TA-Lib 失敗，使用 Pandas
                tr1 = high - low
                tr2 = np.abs(high - pd.Series(close).shift(1).values)
                tr3 = np.abs(low - pd.Series(close).shift(1).values)
                tr = np.maximum(tr1, np.maximum(tr2, tr3))
                self.df['atr_14'] = pd.Series(tr).rolling(window=period).mean()
        else:
            # 無 TA-Lib，使用 Pandas
            tr1 = high - low
            tr2 = np.abs(high - pd.Series(close).shift(1).values)
            tr3 = np.abs(low - pd.Series(close).shift(1).values)
            tr = np.maximum(tr1, np.maximum(tr2, tr3))
            self.df['atr_14'] = pd.Series(tr).rolling(window=period).mean()
        
        return self.df
    
    # =========================================================================
    # DMI (方向指標)
    # =========================================================================
    
    def calculate_dmi(
        self,
        period: int = 14
    ) -> pd.DataFrame:
        """
        計算 DMI (Direction Movement Index) / ADX
        
        DMI 衡量趨勢方向，ADX 衡量趨勢強度。
        
        公式:
            +DM = 如果上升動向 > 下降動向，則為上升動向，否則為 0
            -DM = 如果下降動向 > 上升動向，則為下降動向，否則為 0
            +DI = 100 * EMA(+DM, period) / ATR(period)
            -DI = 100 * EMA(-DM, period) / ATR(period)
            DX = 100 * |+DI - -DI| / (+DI + -DI)
            ADX = EMA(DX, period)
            
        Args:
            period: DMI 週期 (預設 14)
            
        Returns:
            包含 dmi_plus, dmi_minus, adx 的 DataFrame
            
        交易信號:
            - ADX > 25: 趨勢明顯
            - +DI > -DI: 多頭趨勢
            - -DI > +DI: 空頭趨勢
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            # TA-Lib 實作（高效）
            try:
                self.df['dmi_plus'] = talib.PLUS_DI(high, low, close, timeperiod=period)
                self.df['dmi_minus'] = talib.MINUS_DI(high, low, close, timeperiod=period)
                self.df['adx'] = talib.ADX(high, low, close, timeperiod=period)
            except Exception:
                # TA-Lib 失敗，使用 Pandas fallback
                self._dmi_pandas_impl(period)
        else:
            # 無 TA-Lib，使用 Pandas 實作
            self._dmi_pandas_impl(period)
        
        return self.df
    
    def _dmi_pandas_impl(self, period: int = 14):
        """
        DMI Pandas 實作（供 TA-Lib fallback 使用）
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        # 計算 +DM, -DM
        high_diff = pd.Series(high).diff()
        low_diff = -pd.Series(low).diff()
        
        plus_dm = high_diff.where(
            (high_diff > low_diff) & (high_diff > 0), 0
        )
        minus_dm = low_diff.where(
            (low_diff > high_diff) & (low_diff > 0), 0
        )
        
        # 計算 ATR
        tr1 = high - low
        tr2 = np.abs(high - pd.Series(close).shift(1).values)
        tr3 = np.abs(low - pd.Series(close).shift(1).values)
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = pd.Series(tr).ewm(span=period, adjust=False).mean()
        
        # 計算 +DI, -DI
        plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr
        
        # 計算 ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=period, adjust=False).mean()
        
        self.df['dmi_plus'] = plus_di
        self.df['dmi_minus'] = minus_di
        self.df['adx'] = adx
    
    # =========================================================================
    # MFI (資金流量指標)
    # =========================================================================
    
    def calculate_mfi(
        self,
        period: int = 14
    ) -> pd.DataFrame:
        """
        計算 MFI (Money Flow Index)
        
        MFI 是量能版本的 RSI，衡量資金流入流出的強度。
        
        公式:
            Typical Price = (high + low + close) / 3
            Raw Money Flow = Typical Price * volume
            Money Flow Ratio = Positive Flow / Negative Flow
            MFI = 100 - (100 / (1 + Money Flow Ratio))
            
        Args:
            period: MFI 週期 (預設 14)
            
        Returns:
            包含 mfi 的 DataFrame
            
        交易信號:
            - MFI > 80: 超買
            - MFI < 20: 超賣
            - MFI 與價格背離: 反轉信號
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        volume = self.df['volume'].values
        
        if TALIB_AVAILABLE:
            # TA-Lib 實作（高效）
            try:
                self.df['mfi'] = talib.MFI(high, low, close, volume, timeperiod=period)
            except Exception:
                # TA-Lib 失敗，使用 Pandas fallback
                self._mfi_pandas_impl(period)
        else:
            # 無 TA-Lib，使用 Pandas 實作
            self._mfi_pandas_impl(period)
        
        return self.df
    
    def _mfi_pandas_impl(self, period: int = 14):
        """
        MFI Pandas 實作（供 TA-Lib fallback 使用）
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        volume = self.df['volume'].values
        
        typical_price = (high + low + close) / 3
        raw_money_flow = typical_price * volume
        
        delta_tp = pd.Series(typical_price).diff()
        positive_flow = pd.Series(raw_money_flow).where(delta_tp > 0, 0)
        negative_flow = pd.Series(raw_money_flow).where(delta_tp < 0, 0)
        
        period_positive = positive_flow.rolling(window=period).sum()
        period_negative = negative_flow.rolling(window=period).sum()
        
        period_negative = period_negative.replace(0, np.nan)
        money_flow_ratio = period_positive / period_negative
        
        self.df['mfi'] = 100 - (100 / (1 + money_flow_ratio))
    
    # =========================================================================
    # Williams %R
    # =========================================================================
    
    def calculate_williams_r(
        self,
        period: int = 14
    ) -> pd.DataFrame:
        """
        計算 Williams %R
        
        Williams %R 是一個動量指標，衡量現價相對於週期內高低範圍的位置。
        
        公式:
            %R = (Highest High - Close) / (Highest High - Lowest Low) * -100
            
        Args:
            period: 週期 (預設 14)
            
        Returns:
            包含 williams_r 的 DataFrame
            
        交易信號:
            - %R > -20: 超買
            - %R < -80: 超賣
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            # TA-Lib 實作（高效）
            try:
                self.df['williams_r'] = talib.WILLR(high, low, close, timeperiod=period)
            except Exception:
                # TA-Lib 失敗，使用 Pandas fallback
                self._williams_r_pandas_impl(period)
        else:
            # 無 TA-Lib，使用 Pandas 實作
            self._williams_r_pandas_impl(period)
        
        return self.df
    
    def _williams_r_pandas_impl(self, period: int = 14):
        """
        Williams %R Pandas 實作（供 TA-Lib fallback 使用）
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        highest_high = pd.Series(high).rolling(window=period).max()
        lowest_low = pd.Series(low).rolling(window=period).min()
        
        denominator = highest_high - lowest_low
        denominator = denominator.replace(0, np.nan)
        
        self.df['williams_r'] = ((highest_high - close) / denominator) * -100
    
    # =========================================================================
    # 動量指標
    # =========================================================================
    
    def calculate_momentum(
        self,
        periods: List[int] = [21, 63, 126, 252]
    ) -> pd.DataFrame:
        """
        計算價格動量
        
        動量衡量價格變化的速度，
        正值表示上漲動能，負值表示下跌動能。
        
        公式:
            Momentum = close - close(n period ago)
            
        Args:
            periods: 動量週期列表，預設 [21, 63, 126, 252]
            
        Returns:
            包含 momentum_n 的 DataFrame
        """
        close = self.df['close'].values
        
        for period in periods:
            col_name = f'momentum_{period}'
            self.df[col_name] = pd.Series(close).diff(periods=period)
        
        return self.df
    
    # =========================================================================
    # 位置指標
    # =========================================================================
    
    def calculate_position_features(
        self,
        period: int = 252
    ) -> pd.DataFrame:
        """
        計算價格位置特徵
        
        這些特徵幫助模型理解當前價格在歷史範圍中的位置。
        
        Args:
            period: 回看週期 (預設 252 = 約一年)
            
        Returns:
            包含 high_252_position, rolling_mdd_63 的 DataFrame
        """
        
        # 252日最高點的位置
        highest_high = self.df['high'].rolling(window=period).max()
        lowest_low = self.df['low'].rolling(window=period).min()
        
        denominator = highest_high - lowest_low
        denominator = denominator.replace(0, np.nan)
        
        self.df['high_252_position'] = (self.df['close'] - lowest_low) / denominator
        
        # 63日滾動最大回撤
        rolling_max = self.df['close'].rolling(window=period).max()
        drawdown = (self.df['close'] - rolling_max) / rolling_max
        self.df['rolling_mdd_63'] = drawdown.rolling(window=63).min()  # 最負的回撤
        
        return self.df
    
    # =========================================================================
    # 型態辨識
    # =========================================================================
    
    def calculate_pattern_features(
        self
    ) -> pd.DataFrame:
        """
        計算型態辨識特徵
        
        這些特徵捕捉重要的價格型態：
        - 突破高點/低點
        - 成交量爆發
        - 連續漲跌天數
        - 跳空缺口
        
        Returns:
            包含多個型態特徵的 DataFrame
        """
        
        # 突破252日高點
        highest_252 = self.df['high'].rolling(window=252).max()
        self.df['highest_breakout'] = np.where(self.df['close'] > highest_252.shift(1), 1, 0)
        
        # 跌破252日低點
        lowest_252 = self.df['low'].rolling(window=252).min()
        self.df['lowest_breakdown'] = np.where(self.df['close'] < lowest_252.shift(1), 1, 0)
        
        # 成交量爆發（超過20日均量的2倍）
        volume_ma20 = self.df['volume'].rolling(window=20).mean()
        self.df['volume_spike'] = np.where(self.df['volume'] > volume_ma20 * 2, 1, 0)
        
        # 價格動量（5日變化率）
        self.df['price_momentum'] = self.df['close'].pct_change(periods=5)
        
        # 波動性（日內波動幅度）
        self.df['volatility'] = (self.df['high'] - self.df['low']) / self.df['close']
        
        # 連續上漲/下跌天數（向量化解法）
        # 簡單 for 迴圈但作用於 numpy array（比 pandas Series 快約 10x）
        close = self.df['close'].values
        n = len(close)
        consecutive_up = np.zeros(n, dtype=np.int_)
        consecutive_down = np.zeros(n, dtype=np.int_)

        for i in range(1, n):
            if close[i] > close[i-1]:
                consecutive_up[i] = consecutive_up[i-1] + 1
                consecutive_down[i] = 0
            elif close[i] < close[i-1]:
                consecutive_down[i] = consecutive_down[i-1] + 1
                consecutive_up[i] = 0
            else:
                consecutive_up[i] = consecutive_up[i-1]
                consecutive_down[i] = consecutive_down[i-1]
        
        self.df['consecutive_up_days'] = consecutive_up.astype(int)
        self.df['consecutive_down_days'] = consecutive_down.astype(int)
        
        # 跳空缺口
        self.df['gap_up_or_down'] = np.where(
            self.df['open'] > self.df['close'].shift(1) * 1.01, 1,  # 跳空上漲
            np.where(self.df['open'] < self.df['close'].shift(1) * 0.99, -1, 0)  # 跳空下跌
        )
        
        return self.df
    
    # =========================================================================
    # 成交量特徵
    # =========================================================================
    
    def calculate_volume_features(
        self
    ) -> pd.DataFrame:
        """
        計算成交量特徵
        
        成交量是技術分析的重要組成部分，
        可以確認價格變化的有效性。
        
        Returns:
            包含 volume_normalized 的 DataFrame
        """
        
        # 成交量標準化（Z-score，相對於20日均值和標準差）
        volume_ma20 = self.df['volume'].rolling(window=20).mean()
        volume_std20 = self.df['volume'].rolling(window=20).std(ddof=1)
        
        denominator = volume_std20.replace(0, np.nan)
        self.df['volume_normalized'] = (self.df['volume'] - volume_ma20) / denominator
        
        return self.df
    
    # =========================================================================
    # 統一計算介面
    # =========================================================================
    
    def calculate_all(
        self,
        include_patterns: bool = True
    ) -> pd.DataFrame:
        """
        計算所有技術指標
        
        這是統一介面，一次計算所有指標。
        推薦使用此函數而非單獨呼叫各指標函數。
        
        Args:
            include_patterns: 是否包含型態辨識特徵
            
        Returns:
            包含所有技術指標的 DataFrame
        """
        
        print("[TechnicalIndicators] 開始計算技術指標...")
        
        # 1. 移動平均線 (MA)
        print("  - 計算 MA...")
        self.calculate_ma()
        
        # 2. MACD
        print("  - 計算 MACD...")
        self.calculate_macd()
        
        # 3. RSI
        print("  - 計算 RSI...")
        self.calculate_rsi()
        
        # 4. KDJ
        print("  - 計算 KDJ...")
        self.calculate_kdj()
        
        # 5. Bollinger Bands
        print("  - 計算 Bollinger Bands...")
        self.calculate_bollinger_bands()
        
        # 6. ATR
        print("  - 計算 ATR...")
        self.calculate_atr()
        
        # 7. DMI/ADX
        print("  - 計算 DMI/ADX...")
        self.calculate_dmi()
        
        # 8. MFI
        print("  - 計算 MFI...")
        self.calculate_mfi()
        
        # 9. Williams %R
        print("  - 計算 Williams %R...")
        self.calculate_williams_r()
        
        # 10. 動量指標
        print("  - 計算動量...")
        self.calculate_momentum()
        
        # 11. 位置特徵
        print("  - 計算位置特徵...")
        self.calculate_position_features()
        
        # 12. 型態辨識（可選）
        if include_patterns:
            print("  - 計算型態特徵...")
            self.calculate_pattern_features()
        
        # 13. 成交量特徵
        print("  - 計算成交量特徵...")
        self.calculate_volume_features()
        
        print(f"[TechnicalIndicators] 完成，共 {len(self.df.columns)} 個欄位")
        
        return self.df
    
    def get_feature_list(self) -> List[str]:
        """
        獲取所有計算的特徵名稱列表
        
        Returns:
            特徵名稱列表
        """
        features = []
        
        # MA 系列
        for period in [3, 5, 10, 20, 60, 120, 240]:
            features.append(f'ma{period}')
        
        # MA 比率和交叉
        features.extend([
            'close_ma120_ratio', 'close_ma240_ratio', 'ma60_ma240_ratio',
            'ma_cross_signal', 'ma3_slope', 'ma20_slope', 'ma60_slope'
        ])
        
        # MACD
        features.extend([
            'macd_line', 'signal_line', 'histogram',
            'histogram_change', 'macd_turn_positive'
        ])
        
        # RSI
        features.extend(['rsi_14', 'rsi_28'])
        
        # KDJ
        features.extend(['kdj_k', 'kdj_d', 'kdj_j'])
        
        # Williams %R
        features.append('williams_r')
        
        # Bollinger Bands
        features.extend(['bb_upper', 'bb_lower', 'bb_width'])
        
        # ATR
        features.append('atr_14')
        
        # DMI
        features.extend(['dmi_plus', 'dmi_minus', 'adx'])
        
        # MFI
        features.append('mfi')
        
        # 動量
        features.extend(['momentum_21', 'momentum_63', 'momentum_126', 'momentum_252'])
        
        # 位置
        features.extend(['high_252_position', 'rolling_mdd_63'])
        
        # 型態
        features.extend([
            'highest_breakout', 'lowest_breakdown', 'volume_spike',
            'price_momentum', 'volatility',
            'consecutive_up_days', 'consecutive_down_days', 'gap_up_or_down'
        ])
        
        # 成交量
        features.append('volume_normalized')
        
        return features


# =============================================================================
# 便捷函數
# =============================================================================

def calculate_ma(df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
    """
    便捷函數：計算移動平均線
    
    Args:
        df: 股價數據
        periods: 週期列表
        
    Returns:
        包含 MA 的 DataFrame
    """
    if periods is None:
        periods = [3, 5, 10, 20, 60, 120, 240]
    ti = TechnicalIndicators(df)
    return ti.calculate_ma(periods)


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> pd.DataFrame:
    """
    便捷函數：計算 MACD
    
    Args:
        df: 股價數據
        fast_period: 快線週期
        slow_period: 慢線週期
        signal_period: 信號線週期
        
    Returns:
        包含 MACD 的 DataFrame
    """
    ti = TechnicalIndicators(df)
    return ti.calculate_macd(fast_period, slow_period, signal_period)


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    便捷函數：計算 RSI
    
    Args:
        df: 股價數據
        period: RSI 週期
        
    Returns:
        包含 RSI 的 DataFrame
    """
    ti = TechnicalIndicators(df)
    return ti.calculate_rsi([period])


def calculate_kdj(df: pd.DataFrame) -> pd.DataFrame:
    """
    便捷函數：計算 KDJ
    
    Args:
        df: 股價數據
        
    Returns:
        包含 KDJ 的 DataFrame
    """
    ti = TechnicalIndicators(df)
    return ti.calculate_kdj()


def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    便捷函數：計算布林帶
    
    Args:
        df: 股價數據
        period: 週期
        
    Returns:
        包含布林帶的 DataFrame
    """
    ti = TechnicalIndicators(df)
    return ti.calculate_bollinger_bands(period)


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    import yfinance as yf
    
    print("=" * 60)
    print("TechnicalIndicators 測試")
    print("=" * 60)
    
    # 獲取測試數據
    print("\n[測試] 下載台積電 (2330) 測試數據...")
    ticker = yf.Ticker("2330.TW")
    df = ticker.history(start='2023-01-01', end='2024-01-01', auto_adjust=False)
    df = df.reset_index()
    
    if df.empty:
        print("無法下載測試數據")
    else:
        print(f"成功獲取 {len(df)} 筆數據")
        
        # 計算技術指標
        print("\n[測試] 計算技術指標...")
        ti = TechnicalIndicators(df)
        df_with_features = ti.calculate_all()
        
        # 顯示結果
        feature_list = ti.get_feature_list()
        print(f"\n共計算 {len(feature_list)} 個技術指標")
        print("\n前10個特徵:")
        for feat in feature_list[:10]:
            if feat in df_with_features.columns:
                print(f"  - {feat}: {df_with_features[feat].iloc[-1]:.4f}")
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)