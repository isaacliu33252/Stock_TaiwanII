# ============================================================================
# 技術指標計算模組 (Technical Analysis)
# ============================================================================
"""
計算各種技術指標，支援 TA-Lib 和手動實現。

支援指標：
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- 移動平均線 (MA)
- ATR (Average True Range)
- KD 指標

使用方式：
    from FinRL.data import TechnicalIndicators
    
    ta = TechnicalIndicators()
    data = ta.calculate_all(df)
"""

import pandas as pd
import numpy as np

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_PERIOD, BB_STD,
    MA_SHORT, MA_MEDIUM, MA_LONG,
    ATR_PERIOD,
    KD_PERIOD, KD_SMOOTH_K, KD_SMOOTH_D,
)


class TechnicalIndicators:
    """
    技術指標計算類別
    
    提供各種技術指標的計算方法，支援 TA-Lib 和純 Python 實現。
    """
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
        """
        計算 RSI (Relative Strength Index)
        
        公式：RSI = 100 - (100 / (1 + RS))
        其中 RS = 平均漲幅 / 平均跌幅
        
        參數：
            df: 包含 close 價格的 DataFrame
            period: 計算週期（預設 14 天）
        
        返回：
            帶有 RSI 欄位的 DataFrame
        """
        df = df.copy()
        
        # 計算價格變化
        delta = df["close"].diff()
        
        # 分離漲跌
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        # 計算平均漲跌（使用指數移動平均）
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        
        # 計算 RS 和 RSI
        rs = avg_gain / avg_loss
        df["RSI"] = 100 - (100 / (1 + rs))
        
        return df
    
    @staticmethod
    def calculate_macd(
        df: pd.DataFrame,
        fast: int = MACD_FAST,
        slow: int = MACD_SLOW,
        signal: int = MACD_SIGNAL,
    ) -> pd.DataFrame:
        """
        計算 MACD (Moving Average Convergence Divergence)
        
        公式：
        - DIF = EMA(fast) - EMA(slow)
        - MACD = EMA(DIF, signal)
        - Histogram = DIF - MACD
        
        參數：
            df: 包含 close 價格的 DataFrame
            fast: 快速 EMA 週期（預設 12）
            slow: 慢速 EMA 週期（預設 26）
            signal: Signal 線週期（預設 9）
        
        返回：
            帶有 MACD 相關欄位的 DataFrame
        """
        df = df.copy()
        
        # 計算快速和慢速 EMA
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        
        # 計算 DIF 和 MACD
        df["MACD"] = ema_fast - ema_slow
        df["MACD_signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
        
        return df
    
    @staticmethod
    def calculate_bollinger_bands(
        df: pd.DataFrame,
        period: int = BB_PERIOD,
        std: int = BB_STD,
    ) -> pd.DataFrame:
        """
        計算 Bollinger Bands
        
        公式：
        - 中軌 = MA(close, period)
        - 上軌 = 中軌 + (std * 標準差)
        - 下軌 = 中軌 - (std * 標準差)
        
        參數：
            df: 包含 close 價格的 DataFrame
            period: 計算週期（預設 20 天）
            std: 標準差倍數（預設 2）
        
        返回：
            帶有 BB_upper, BB_middle, BB_lower 欄位的 DataFrame
        """
        df = df.copy()
        
        # 計算移動平均和標準差
        df["BB_middle"] = df["close"].rolling(window=period).mean()
        df["BB_std"] = df["close"].rolling(window=period).std()
        
        # 計算上下軌
        df["BB_upper"] = df["BB_middle"] + (std * df["BB_std"])
        df["BB_lower"] = df["BB_middle"] - (std * df["BB_std"])
        
        # 去除多餘的標準差欄位
        df = df.drop("BB_std", axis=1)
        
        return df
    
    @staticmethod
    def calculate_ma(
        df: pd.DataFrame,
        short: int = MA_SHORT,
        medium: int = MA_MEDIUM,
        long: int = MA_LONG,
    ) -> pd.DataFrame:
        """
        計算移動平均線
        
        參數：
            df: 包含 close 價格的 DataFrame
            short: 短期均線週期（預設 5 天）
            medium: 中期均線週期（預設 20 天）
            long: 長期均線週期（預設 60 天）
        
        返回：
            帶有 MA_short, MA_medium, MA_long 欄位的 DataFrame
        """
        df = df.copy()
        
        df["MA_short"] = df["close"].rolling(window=short).mean()
        df["MA_medium"] = df["close"].rolling(window=medium).mean()
        df["MA_long"] = df["close"].rolling(window=long).mean()
        
        return df
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
        """
        計算 ATR (Average True Range)
        
        True Range = max(H - L, |H - PC|, |L - PC|)
        其中 PC 為前一日收盤價
        
        參數：
            df: 包含 high, low, close 價格的 DataFrame
            period: 計算週期（預設 14 天）
        
        返回：
            帶有 ATR 欄位的 DataFrame
        """
        df = df.copy()
        
        # 取得前一日收盤價
        prev_close = df["close"].shift(1)
        
        # 計算 True Range
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - prev_close)
        low_close = abs(df["low"] - prev_close)
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 計算 ATR（使用平滑移動平均）
        df["ATR"] = true_range.rolling(window=period).mean()
        
        return df
    
    @staticmethod
    def calculate_kd(
        df: pd.DataFrame,
        period: int = KD_PERIOD,
        smooth_k: int = KD_SMOOTH_K,
        smooth_d: int = KD_SMOOTH_D,
    ) -> pd.DataFrame:
        """
        計算 KD 指標（隨機指標）
        
        公式：
        - RSV = (close - LLV(low, period)) / (HHV(high, period) - LLV(low, period)) * 100
        - K = SMA(RSV, smooth_k)
        - D = SMA(K, smooth_d)
        
        參數：
            df: 包含 high, low, close 價格的 DataFrame
            period: 計算週期（預設 9 天）
            smooth_k: K 值平滑週期（預設 3）
            smooth_d: D 值平滑週期（預設 3）
        
        返回：
            帶有 KD_K, KD_D 欄位的 DataFrame
        """
        df = df.copy()
        
        # 計算週期內最低價和最高價
        low_min = df["low"].rolling(window=period).min()
        high_max = df["high"].rolling(window=period).max()
        
        # 計算 RSV
        rsv = (df["close"] - low_min) / (high_max - low_min) * 100
        rsv = rsv.fillna(50)  # 處理除零情況
        
        # 計算 K 和 D
        df["KD_K"] = rsv.rolling(window=smooth_k).mean()
        df["KD_D"] = df["KD_K"].rolling(window=smooth_d).mean()
        
        return df
    
    @classmethod
    def calculate_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算所有技術指標
        
        參數：
            df: 包含 OHLCV 資料的 DataFrame
        
        返回：
            帶有所有技術指標的 DataFrame
        """
        result = df.copy()
        
        # 依序計算各指標
        result = cls.calculate_returns(result)
        result = cls.calculate_rsi(result)
        result = cls.calculate_macd(result)
        result = cls.calculate_bollinger_bands(result)
        result = cls.calculate_ma(result)
        result = cls.calculate_atr(result)
        result = cls.calculate_kd(result)
        
        # 填補 NaN 值 (使用 ffill + bfill 取代已廢棄的 method 參數)
        result = result.ffill().bfill()
        
        return result


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    便捷函數：計算所有技術指標
    
    這是 TechnicalIndicators.calculate_all 的簡化介面。
    """
    return TechnicalIndicators.calculate_all(df)
