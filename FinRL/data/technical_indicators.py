"""
TechnicalIndicators - 技術指標計算模組
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

作者: FinRL量化交易專家
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Tuple
from functools import wraps
import warnings

warnings.filterwarnings('ignore')

# =============================================================================
# TA-Lib 包裝器 (嘗試使用 TA-Lib，若失敗則使用 Pandas)
# =============================================================================

# 嘗試導入 TA-Lib
try:
    import talib
    TALIB_AVAILABLE = True
    print("[TechnicalIndicators] TA-Lib 可用")
except ImportError:
    TALIB_AVAILABLE = False
    print("[TechnicalIndicators] TA-Lib 不可用，將使用 Pandas 計算")
    try:
        import talib
        TALIB_AVAILABLE = True
    except ImportError:
        pass

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
    
    # =========================================================================
    # MA (移動平均線) 系列
    # =========================================================================
    
    def calculate_ma(self, periods: List[int] = [3, 5, 10, 20, 60, 120, 240]) -> pd.DataFrame:
        """
        計算移動平均線
        
        MA 是最基本也最常用的技術指標：
        - MA3, MA5: 短期趨勢
        - MA10, MA20: 中期趨勢
        - MA60, MA120, MA240: 長期趨勢
        
        MA 交叉信號:
        - 黃金交叉: 短期 MA 上穿長期 MA → 買入信號
        - 死亡交叉: 短期 MA 下穿長期 MA → 賣出信號
        
        Args:
            periods: MA 週期列表
        
        Returns:
            添加了 MA 欄位的 DataFrame
        
        新增欄位:
            - ma3, ma5, ma10, ma20, ma60, ma120, ma240
            - ma_cross_signal: (ma3 - ma20) / ma20
        """
        close = self.df['close'].values
        
        for period in periods:
            col_name = f'ma{period}'
            
            if TALIB_AVAILABLE:
                # 使用 TA-Lib 計算 (更快速)
                self.df[col_name] = talib.SMA(close, timeperiod=period)
            else:
                # 使用 Pandas 計算 (備選方案)
                self.df[col_name] = self.df['close'].rolling(window=period).mean()
        
        # === 計算 MA 斜率 ===
        # MA 斜率反映趨勢強度，正值=上升趨勢，負值=下降趨勢
        self.df['ma3_slope'] = self.df['ma3'].pct_change(periods=5)  # 5日變化率
        self.df['ma20_slope'] = self.df['ma20'].pct_change(periods=5)
        self.df['ma60_slope'] = self.df['ma60'].pct_change(periods=5)
        
        # === 計算 MA 交叉信號 ===
        # 這是 RL 狀態的重要特徵
        # (ma3 - ma20) / ma20: 正值表示多頭排列
        self.df['ma_cross_signal'] = (self.df['ma3'] - self.df['ma20']) / self.df['ma20']
        
        return self.df
    
    # =========================================================================
    # MACD (指數平滑異同移動平均線)
    # =========================================================================
    
    def calculate_macd(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> pd.DataFrame:
        """
        計算 MACD 指標
        
        MACD 是動量指標，用於判斷趨勢方向和強度：
        - MACD Line = EMA(12) - EMA(26)
        - Signal Line = EMA(MACD Line, 9)
        - Histogram = MACD Line - Signal Line
        
        MACD 交易信號:
        - Histogram 由負轉正 → 買入時機
        - Histogram 由正轉負 → 賣出時機
        - MACD Line 上穿 Signal Line → 黃金交叉
        - MACD Line 下穿 Signal Line → 死亡交叉
        
        為什麼 MACD 有效:
        1. 結合了趨勢和動量
        2. 過濾了短期噪音
        3. 信號明確易於執行
        
        Args:
            fast_period: 快線 EMA 週期 (預設 12)
            slow_period: 慢線 EMA 週期 (預設 26)
            signal_period: Signal Line 週期 (預設 9)
        
        Returns:
            添加了 MACD 相關欄位的 DataFrame
        
        新增欄位:
            - macd_line: MACD 主線
            - signal_line: Signal 線
            - histogram: 柱狀圖
            - histogram_change: 柱狀圖變化
            - macd_turn_positive: 是否由負轉正 (0/1)
        """
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            macd_line, signal_line, hist = talib.MACD(
                close,
                fastperiod=fast_period,
                slowperiod=slow_period,
                signalperiod=signal_period
            )
            self.df['macd_line'] = macd_line
            self.df['signal_line'] = signal_line
            self.df['histogram'] = hist
        else:
            # 手動計算 EMA
            ema_fast = self.df['close'].ewm(span=fast_period, adjust=False).mean()
            ema_slow = self.df['close'].ewm(span=slow_period, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
            histogram = macd_line - signal_line
            
            self.df['macd_line'] = macd_line
            self.df['signal_line'] = signal_line
            self.df['histogram'] = histogram
        
        # === 計算 Histogram 變化 ===
        # Histogram 變化反映動量加速/減速
        self.df['histogram_change'] = self.df['histogram'].diff()
        
        # === 判斷是否由負轉正 ===
        # 這是經典的買入信號：Histogram 前一根為負，當前為正
        # 轉換為 0/1 變量便於 RL 學習 (向量化實現，避免 Python 迴圈)
        prev_histogram = self.df['histogram'].shift(1)
        self.df['macd_turn_positive'] = (
            (prev_histogram < 0) & (self.df['histogram'] >= 0)
        ).astype(int)
        
        return self.df
    
    # =========================================================================
    # RSI (相對強弱指標)
    # =========================================================================
    
    def calculate_rsi(self, periods: List[int] = [14, 28]) -> pd.DataFrame:
        """
        計算 RSI 指標
        
        RSI 衡量價格變動的速度和幅度：
        - RSI > 70: 過買 (可能反轉下跌)
        - RSI < 30: 過賣 (可能反彈上漲)
        - RSI 50: 多空平衡點
        
        設計考量:
        - 使用多個週期 RSI 捕捉不同時間維度的動量
        - RSI 對價格變化敏感，適合短期交易
        
        Args:
            periods: RSI 週期列表 (預設 [14, 28])
        
        Returns:
            添加了 RSI 欄位的 DataFrame
        
        新增欄位:
            - rsi_14: 14日 RSI
            - rsi_28: 28日 RSI
        """
        close = self.df['close'].values
        
        for period in periods:
            col_name = f'rsi_{period}'
            
            if TALIB_AVAILABLE:
                self.df[col_name] = talib.RSI(close, timeperiod=period)
            else:
                # 手動計算 RSI
                delta = self.df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / (loss + 1e-10)
                self.df[col_name] = 100 - (100 / (1 + rs))
        
        return self.df
    
    # =========================================================================
    # KDJ (隨機指標)
    # =========================================================================
    
    def calculate_kdj(
        self,
        period: int = 9,
        smooth_k: int = 3,
        smooth_d: int = 3
    ) -> pd.DataFrame:
        """
        計算 KDJ 指標 (隨機指標)
        
        KDJ 是一個超買超賣指標：
        - K 線: 快速確認線 (平滑後的 RSV)
        - D 線: 慢速確認線 (K 線的移動平均)
        - J 線: 3*K - 2*D (領先指標)
        
        交易信號:
        - K 上穿 D → 買入
        - K 下穿 D → 賣出
        - KDJ > 80 → 超買
        - KDJ < 20 → 超賣
        
        為什麼 KDJ 適合台股:
        - 台股波動性大，KDJ 能捕捉短期超買超賣
        - J 線的領先特性有助於提前判斷反轉
        
        Args:
            period: RSV 計算週期 (預設 9)
            smooth_k: K 線平滑次數 (預設 3)
            smooth_d: D 線平滑次數 (預設 3)
        
        Returns:
            添加了 KDJ 相關欄位的 DataFrame
        
        新增欄位:
            - kdj_k: K 值
            - kdj_d: D 值
            - kdj_j: J 值
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            k_value, d_value = talib.STOCH(
                high, low, close,
                fastk_period=period,
                slowk_period=smooth_k,
                slowk_matype=0,
                slowd_period=smooth_d,
                slowd_matype=0
            )
            j_value = 3 * k_value - 2 * d_value
        else:
            # 手動計算 KDJ
            lowest_low = self.df['low'].rolling(window=period).min()
            highest_high = self.df['high'].rolling(window=period).max()
            rsv = (close - lowest_low) / (highest_high - lowest_low + 1e-10) * 100
            
            k_value = rsv.rolling(window=smooth_k).mean()
            d_value = k_value.rolling(window=smooth_d).mean()
            j_value = 3 * k_value - 2 * d_value
        
        self.df['kdj_k'] = k_value
        self.df['kdj_d'] = d_value
        self.df['kdj_j'] = j_value
        
        return self.df
    
    # =========================================================================
    # 威廉指標 (Williams %R)
    # =========================================================================
    
    def calculate_williams_r(self, period: int = 14) -> pd.DataFrame:
        """
        計算威廉指標
        
        威廉指標與 KDJ 類似，但計算方式不同：
        - 值域: -100 到 0
        - > -20: 超買
        - < -80: 超賣
        
        Args:
            period: 計算週期 (預設 14)
        
        Returns:
            添加了 williams_r 欄位的 DataFrame
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            self.df['williams_r'] = talib.WILLR(high, low, close, timeperiod=period)
        else:
            highest_high = self.df['high'].rolling(window=period).max()
            lowest_low = self.df['low'].rolling(window=period).min()
            self.df['williams_r'] = -100 * (highest_high - close) / (highest_high - lowest_low + 1e-10)
        
        return self.df
    
    # =========================================================================
    # Bollinger Bands (布林通道)
    # =========================================================================
    
    def calculate_bollinger_bands(
        self,
        period: int = 20,
        std_dev: float = 2.0
    ) -> pd.DataFrame:
        """
        計算布林通道
        
        布林通道由三條線組成：
        - 中軌: MA(close, period)
        - 上軌: 中軌 + 2*std
        - 下軌: 中軌 - 2*std
        
        交易信號:
        - 價格觸及上軌 → 可能回調
        - 價格觸及下軌 → 可能反彈
        - 通道收窄 → 波動率低，可能突破
        - 通道擴張 → 波動率高
        
        Args:
            period: 計算週期 (預設 20)
            std_dev: 標準差倍數 (預設 2.0)
        
        Returns:
            添加了 BB 相關欄位的 DataFrame
        
        新增欄位:
            - bb_upper: 上軌
            - bb_middle: 中軌
            - bb_lower: 下軌
            - bb_width: (上軌 - 下軌) / 中軌 (標準化)
        """
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            upper, middle, lower = talib.BBANDS(
                close,
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev,
                matype=0  # Simple Moving Average
            )
            self.df['bb_upper'] = upper
            self.df['bb_middle'] = middle
            self.df['bb_lower'] = lower
        else:
            middle = self.df['close'].rolling(window=period).mean()
            std = self.df['close'].rolling(window=period).std(ddof=1)
            self.df['bb_upper'] = middle + std_dev * std
            self.df['bb_middle'] = middle
            self.df['bb_lower'] = middle - std_dev * std
        
        # === 計算布林通道寬度 (標準化) ===
        # 寬度越大表示波動率越高
        # 避免除以零：用 + 1e-10
        self.df['bb_width'] = (self.df['bb_upper'] - self.df['bb_lower']) / (self.df['bb_middle'] + 1e-10)

        return self.df
    
    # =========================================================================
    # ATR (平均真實波動幅度)
    # =========================================================================
    
    def calculate_atr(self, period: int = 14) -> pd.DataFrame:
        """
        計算 ATR (平均真實波動幅度)
        
        ATR 衡量價格的波動程度：
        - ATR 越高 → 波動越大，風險越高
        - ATR 越低 → 波動越小，風險越低
        
        應用:
        - 設定停損點: 1.5 * ATR
        - 判斷進場時機: 低 ATR 時進場突破
        - 倉位管理: ATR 高時減少倉位
        
        Args:
            period: 計算週期 (預設 14)
        
        Returns:
            添加了 atr_14 欄位的 DataFrame
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        
        if TALIB_AVAILABLE:
            self.df['atr_14'] = talib.ATR(high, low, close, timeperiod=period)
        else:
            # 手動計算 True Range
            tr1 = self.df['high'] - self.df['low']
            tr2 = abs(self.df['high'] - self.df['close'].shift())
            tr3 = abs(self.df['low'] - self.df['close'].shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            self.df['atr_14'] = tr.rolling(window=period).mean()
        
        return self.df

    # =========================================================================
    # DMI/ADX (趨向指標)
    # =========================================================================

    def calculate_dmi_adx(self, period: int = 14) -> pd.DataFrame:
        """
        計算 DMI (Directional Movement Index) 和 ADX (Average Directional Index)

        DMI 判斷趨勢方向：
        - +DI > -DI → 多頭趨勢
        - -DI > +DI → 空頭趨勢
        - ADX > 25 → 趨勢明確（可用順勢策略）
        - ADX < 20 → 盤整（適用逆勢策略）

        新增欄位:
            - dmi_plus: +DI 趨向指標
            - dmi_minus: -DI 趨向指標
            - adx: ADX 平均趨向指標
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values

        if TALIB_AVAILABLE:
            self.df['dmi_plus'] = talib.PLUS_DM(high, low, timeperiod=period)
            self.df['dmi_minus'] = talib.MINUS_DM(high, low, timeperiod=period)
            self.df['adx'] = talib.ADX(high, low, close, timeperiod=period)
        else:
            # 手動計算 DMI
            high_diff = self.df['high'].diff()
            low_diff = -self.df['low'].diff()

            # +DM: 僅在順向移動時取正向值
            plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
            # -DM: 僅在負向移動時取正向值
            minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

            # 標準化（使用 ATR）
            atr = self.df['atr_14'] if 'atr_14' in self.df.columns else self.calculate_atr(period).df['atr_14']
            self.df['dmi_plus'] = 100 * plus_dm.rolling(window=period).sum() / (atr + 1e-10)
            self.df['dmi_minus'] = 100 * minus_dm.rolling(window=period).sum() / (atr + 1e-10)

            # ADX: (|+/−DI| 之間的差) / (總和) * 100
            di_sum = self.df['dmi_plus'] + self.df['dmi_minus']
            dx = 100 * abs(self.df['dmi_plus'] - self.df['dmi_minus']) / (di_sum + 1e-10)
            self.df['adx'] = dx.rolling(window=period).mean()

        return self.df

    # =========================================================================
    # MFI (金錢流量指標)
    # =========================================================================

    def calculate_mfi(self, period: int = 14) -> pd.DataFrame:
        """
        計算 MFI (Money Flow Index)

        MFI 類似 RSI，但使用成交量加權：
        - MFI > 80 → 過熱（可能回調）
        - MFI < 20 → 賣超（可能反彈）
        - MFI 與價格背離 → 反轉信號

        新增欄位:
            - mfi: 金錢流量指標
        """
        high = self.df['high'].values
        low = self.df['low'].values
        close = self.df['close'].values
        volume = self.df['volume'].values

        if TALIB_AVAILABLE:
            self.df['mfi'] = talib.MFI(high, low, close, volume, timeperiod=period)
        else:
            # 典型價格
            typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3.0
            # 原始金錢流量
            money_flow = typical_price * self.df['volume']
            # 正/負金錢流量
            positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0.0)
            negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0.0)
            # 比率
            positive_sum = positive_flow.rolling(window=period).sum()
            negative_sum = negative_flow.rolling(window=period).sum()
            mfi_ratio = positive_sum / (negative_sum + 1e-10)
            self.df['mfi'] = 100 - (100 / (1 + mfi_ratio))

        return self.df

    # =========================================================================
    # 成交量指標
    # =========================================================================
    
    def calculate_volume_indicators(self) -> pd.DataFrame:
        """
        計算成交量相關指標
        
        成交量是技術分析的重要輔助指標：
        - 量增價漲 → 確認趨勢
        - 量增價跌 → 趨勢可能反轉
        - 量縮 → 趨勢可能停頓
        
        新增欄位:
            - volume_ma5: 5日均量
            - volume_spike: 當日成交量 / 5日均量
            - volume_ratio: 量比
        """
        # 5日均量
        self.df['volume_ma5'] = self.df['volume'].rolling(window=5).mean()
        
        # 量增信號: 當日成交量明顯超過均量
        # 這是 RL 狀態的重要特徵 (pattern_features)
        self.df['volume_spike'] = self.df['volume'] / (self.df['volume_ma5'] + 1e-10)
        
        # 標準化成交量 (z-score)
        self.df['volume_normalized'] = (
            self.df['volume'] - self.df['volume'].rolling(window=20).mean()
        ) / (self.df['volume'].rolling(window=20).std(ddof=1) + 1e-10)
        
        return self.df
    
    # =========================================================================
    # 價格型態特徵
    # =========================================================================
    
    def calculate_pattern_features(self) -> pd.DataFrame:
        """
        計算價格型態特徵
        
        這些特徵捕捉市場的價格行為模式：
        
        新增欄位:
            - highest_breakout: 是否突破N日高 (1/0)
            - lowest_breakdown: 是否跌破N日低 (1/0)
            - consecutive_up_days: 連續上漲天數
            - consecutive_down_days: 連續下跌天數
            - gap_up_or_down: 跳空幅度
            - price_momentum: 價格動量
            - volatility: 波動率 (20日標準差)
        """
        close = self.df['close']
        high = self.df['high']
        low = self.df['low']
        
        # === 突破前期高點信號 ===
        # 這是 tech2_highest 策略的核心
        period = 5
        self.df['highest_high'] = high.rolling(window=period).max().shift(1)
        self.df['highest_breakout'] = 0
        breakout_mask = high > self.df['highest_high']
        self.df.loc[breakout_mask, 'highest_breakout'] = 1
        
        # === 跌破前期低點信號 ===
        self.df['lowest_low'] = low.rolling(window=period).min().shift(1)
        self.df['lowest_breakdown'] = 0
        breakdown_mask = low < self.df['lowest_low']
        self.df.loc[breakdown_mask, 'lowest_breakdown'] = 1
        
        # === 連續漲跌天數 ===
        # 計算每日漲跌
        price_change = close.diff()
        is_up = price_change > 0
        is_down = price_change < 0
        
        # 連續上漲天數
        self.df['consecutive_up_days'] = 0
        up_groups = (~is_up).cumsum()
        self.df['consecutive_up_days'] = is_up.groupby(up_groups).cumsum()
        
        # 連續下跌天數
        self.df['consecutive_down_days'] = 0
        down_groups = (~is_down).cumsum()
        self.df['consecutive_down_days'] = is_down.groupby(down_groups).cumsum()
        
        # === 跳空信號 ===
        # 跳空幅度 = (當日開盤 - 前日收盤) / 前日收盤
        open_price = self.df['open']
        prev_close = close.shift(1)
        self.df['gap_up_or_down'] = (open_price - prev_close) / (prev_close + 1e-10)
        
        # === 價格動量 ===
        # 5日報酬率
        self.df['price_momentum'] = close.pct_change(periods=5)
        
        # === 波動率 ===
        # 20日標準差 (標準化)
        self.df['volatility'] = close.rolling(window=20).std(ddof=1) / (close.rolling(window=20).mean() + 1e-10)
        
        return self.df
    
    # =========================================================================
    # 一次性計算所有指標
    # =========================================================================
    
    def calculate_all(self) -> pd.DataFrame:
        """
        計算所有技術指標
        
        這是主要接口，用於一次計算所有指標並添加到 DataFrame
        
        Returns:
            添加了所有技術指標欄位的 DataFrame
        
        計算順序:
            1. MA 系列
            2. MACD
            3. RSI
            4. KDJ
            5. 威廉指標
            6. Bollinger Bands
            7. ATR
            8. DMI/ADX
            9. MFI
            10. 成交量指標
            11. 價格型態特徵
        
        Note:
            某些指標需要前面的指標結果，所以必須按順序計算
        """
        print("[TechnicalIndicators] 開始計算所有技術指標...")
        
        # 1. MA 系列
        self.calculate_ma()
        print("  - MA 系列完成")
        
        # 2. MACD
        self.calculate_macd()
        print("  - MACD 完成")
        
        # 3. RSI
        self.calculate_rsi([14, 28])
        print("  - RSI 完成")
        
        # 4. KDJ
        self.calculate_kdj()
        print("  - KDJ 完成")
        
        # 5. 威廉指標
        self.calculate_williams_r()
        print("  - 威廉指標完成")
        
        # 6. Bollinger Bands
        self.calculate_bollinger_bands()
        print("  - Bollinger Bands 完成")
        
        # 7. ATR
        self.calculate_atr()
        print("  - ATR 完成")

        # 8. DMI/ADX
        self.calculate_dmi_adx()
        print("  - DMI/ADX 完成")

        # 9. MFI
        self.calculate_mfi()
        print("  - MFI 完成")

        # 10. 成交量指標
        self.calculate_volume_indicators()
        print("  - 成交量指標完成")

        # 11. 價格型態特徵
        self.calculate_pattern_features()
        print("  - 價格型態特徵完成")
        
        # 去除前 N 筆 NaN 數據
        self.df = self.df.dropna()
        
        print(f"[TechnicalIndicators] 完成，共 {len(self.df)} 筆有效數據")
        print(f"[TechnicalIndicators] 總欄位數: {len(self.df.columns)}")
        
        return self.df
    
    # =========================================================================
    # 取得特徵欄位列表
    # =========================================================================
    
    @staticmethod
    def get_feature_columns() -> List[str]:
        """
        取得所有技術指標欄位名稱
        
        Returns:
            技術指標欄位名稱列表
        """
        features = []
        
        # MA 系列
        features.extend([
            'ma3', 'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma240',
            'ma3_slope', 'ma20_slope', 'ma60_slope',
            'ma_cross_signal'
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
        
        # 威廉指標
        features.append('williams_r')
        
        # Bollinger Bands
        features.extend(['bb_upper', 'bb_lower', 'bb_width'])
        
        # ATR
        features.append('atr_14')

        # DMI/ADX
        features.extend(['dmi_plus', 'dmi_minus', 'adx'])

        # MFI
        features.append('mfi')

        # 成交量
        features.extend(['volume_ma5', 'volume_spike', 'volume_normalized'])
        
        # 價格型態
        features.extend([
            'highest_breakout', 'lowest_breakdown',
            'consecutive_up_days', 'consecutive_down_days',
            'gap_up_or_down', 'price_momentum', 'volatility'
        ])
        
        return features


# =============================================================================
# 便利函數
# =============================================================================

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    便利函數：為 DataFrame 添加所有技術指標
    
    Args:
        df: 股價數據
    
    Returns:
        添加了技術指標的 DataFrame
    
    Example:
        >>> df = pd.read_csv('2330.csv')
        >>> df = add_technical_indicators(df)
    """
    ti = TechnicalIndicators(df)
    return ti.calculate_all()
