# ============================================================================
# Feature Engineer - 技術指標與特徵工程
# ============================================================================
"""
專門的技術指標計算模組，提供乾淨、可測試的指標函式。
"""

import numpy as np
import pandas as pd
from typing import Optional


def add_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    為 DataFrame 添加完整技術指標特徵。
    
    加入的特徵群組：
        1. 價格特徵（標準化）
        2. 移動平均線（MA3/5/10/20/60/120/240）
        3. 動量指標（RSI, KDJ, Williams%R, CCI, ROC）
        4. MACD 系列
        5. 布林帶（帶寬 %B）
        6. ATR  波動率
        7. 滾動動量與斜率
        8. 成交量特徵
        9. 價格型態信號
    """
    df = df.copy()
    close = df['close']

    # ─── 移動平均線 ───────────────────────────────────────────────────────
    for w in [3, 5, 10, 20, 60, 120, 240]:
        if len(df) >= w:
            df[f'ma{w}'] = close.rolling(window=w).mean()
            # MA 斜率（正規化）
            df[f'ma{w}_slope'] = df[f'ma{w}'].pct_change(periods=5)

    # ─── 指數移動平均線 ───────────────────────────────────────────────────
    for span in [12, 26]:
        df[f'ema{span}'] = close.ewm(span=span, adjust=False).mean()

    # ─── MACD ─────────────────────────────────────────────────────────────
    ema12 = df['ema12']
    ema26 = df['ema26']
    df['macd_line'] = ema12 - ema26
    df['signal_line'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd_line'] - df['signal_line']
    df['macd_histogram_change'] = df['macd_histogram'].diff()

    # MACD 轉多/空信號
    df['macd_turn_positive'] = (
        (df['macd_line'] > 0) & (df['macd_line'].shift(1) <= 0)
    ).astype(int)
    df['macd_turn_negative'] = (
        (df['macd_line'] < 0) & (df['macd_line'].shift(1) >= 0)
    ).astype(int)

    # ─── RSI ──────────────────────────────────────────────────────────────
    for period in [7, 14, 28]:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window=period).mean()
        loss = (-delta.clip(upper=0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # RSI 均線（過濾假信號）
    df['rsi_ma5'] = df['rsi_14'].rolling(5).mean()

    # ─── KDJ ──────────────────────────────────────────────────────────────
    low_n = df['low'].rolling(window=9).min()
    high_n = df['high'].rolling(window=9).max()
    rsv = (close - low_n) / (high_n - low_n + 1e-10) * 100
    df['kdj_k'] = rsv.ewm(com=2).mean()
    df['kdj_d'] = df['kdj_k'].ewm(com=2).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    df['kdj_golden_cross'] = (
        (df['kdj_k'] > df['kdj_d']) &
        (df['kdj_k'].shift(1) <= df['kdj_d'].shift(1))
    ).astype(int)

    # ─── Williams %R ────────────────────────────────────────────────────
    period_wr = 14
    highest_high = df['high'].rolling(window=period_wr).max()
    lowest_low = df['low'].rolling(window=period_wr).min()
    df['williams_r'] = -100 * (highest_high - close) / (highest_high - lowest_low + 1e-10)

    # ─── CCI ──────────────────────────────────────────────────────────────
    period_cci = 14
    tp = (df['high'] + df['low'] + close) / 3
    sma_tp = tp.rolling(window=period_cci).mean()
    mad = tp.rolling(window=period_cci).apply(lambda x: np.abs(x - x.mean()).mean())
    df['cci'] = (tp - sma_tp) / (0.015 * mad + 1e-10)

    # ─── 布林帶 ───────────────────────────────────────────────────────────
    bb_window = 20
    df['bb_middle'] = close.rolling(window=bb_window).mean()
    bb_std = close.rolling(window=bb_window).std()
    df['bb_upper'] = df['bb_middle'] + 2 * bb_std
    df['bb_lower'] = df['bb_middle'] - 2 * bb_std
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['bb_position'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

    # 布林帶突破（收盤價穿越上/下軌）
    df['bb_upper_breakout'] = (close > df['bb_upper']).astype(int)
    df['bb_lower_breakout'] = (close < df['bb_lower']).astype(int)

    # ─── ATR（Average True Range） ───────────────────────────────────────
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - close.shift())
    low_close = np.abs(df['low'] - close.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(window=14).mean()

    # ATR% （相對波動率）
    df['atr_pct'] = df['atr_14'] / close * 100

    # ─── 價格動量 ────────────────────────────────────────────────────────
    for period in [5, 10, 20]:
        df[f'momentum_{period}'] = close.pct_change(periods=period)
        df[f'momentum_{period}_slope'] = df[f'momentum_{period}'].diff()

    # 滾動收益率標準差（市場波動度）
    df['rolling_vol_5'] = df['momentum_5'].rolling(5).std()
    df['rolling_vol_20'] = df['momentum_20'].rolling(20).std()

    # ─── 成交量特徵 ──────────────────────────────────────────────────────
    vol = df['volume']
    df['volume_ma5'] = vol.rolling(5).mean()
    df['volume_ma20'] = vol.rolling(20).mean()
    df['volume_ratio'] = vol / (df['volume_ma20'] + 1e-10)
    df['volume_spike'] = (vol > df['volume_ma5'] * 1.5).astype(int)

    # OBV（能量潮）
    obv = (np.sign(df['close'].diff()) * vol).fillna(0).cumsum()
    df['obv'] = obv
    df['obv_ma10'] = obv.rolling(10).mean()

    # ─── 價格型態特徵 ───────────────────────────────────────────────────
    # 價格相對於均線的位置
    for w in [5, 20, 60]:
        if f'ma{w}' in df.columns:
            df[f'price_vs_ma{w}'] = (close - df[f'ma{w}']) / (df[f'ma{w}'] + 1e-10)

    # 是否在近期高/低點
    df['highest_20d'] = close.rolling(20).max()
    df['lowest_20d'] = close.rolling(20).min()
    df['near_high'] = close / df['highest_20d']
    df['near_low'] = close / df['lowest_20d']

    # 突破近期高點
    df['breakout_20d'] = (close >= df['highest_20d']).astype(int)

    # ─── 漲跌連續性 ─────────────────────────────────────────────────────
    daily_return = close.pct_change()
    df['consecutive_up'] = 0
    df['consecutive_down'] = 0
    current_up = 0
    current_down = 0
    for i, ret in enumerate(daily_return):
        if ret > 0:
            current_up += 1
            current_down = 0
        elif ret < 0:
            current_down += 1
            current_up = 0
        else:
            current_up = 0
            current_down = 0
        df.iloc[i, df.columns.get_loc('consecutive_up')] = current_up
        df.iloc[i, df.columns.get_loc('consecutive_down')] = current_down

    # ─── Gap（跳空） ─────────────────────────────────────────────────────
    prev_close = close.shift(1)
    df['gap_pct'] = (close - prev_close) / (prev_close + 1e-10)
    df['gap_up'] = (df['gap_pct'] > 0.01).astype(int)
    df['gap_down'] = (df['gap_pct'] < -0.01).astype(int)

    # ─── 高/低盤特徵 ────────────────────────────────────────────────────
    df['high_low_range'] = (df['high'] - df['low']) / (close + 1e-10)
    df['close_position'] = (close - df['low']) / (df['high'] - df['low'] + 1e-10)

    return df


def get_feature_list() -> list:
    """
    返回所有計算出來的特徵名稱列表（不含原始 OHLCV 欄位）。
    """
    features = []

    # MA
    for w in [3, 5, 10, 20, 60, 120, 240]:
        features.append(f'ma{w}')
        features.append(f'ma{w}_slope')
    for span in [12, 26]:
        features.append(f'ema{span}')

    # MACD
    features += [
        'macd_line', 'signal_line', 'macd_histogram',
        'macd_histogram_change', 'macd_turn_positive', 'macd_turn_negative'
    ]

    # RSI
    for p in [7, 14, 28]:
        features.append(f'rsi_{p}')
    features.append('rsi_ma5')

    # KDJ
    features += ['kdj_k', 'kdj_d', 'kdj_j', 'kdj_golden_cross']

    # Others
    features += [
        'williams_r', 'cci',
        'bb_middle', 'bb_upper', 'bb_lower', 'bb_width',
        'bb_position', 'bb_upper_breakout', 'bb_lower_breakout',
        'atr_14', 'atr_pct',
        'momentum_5', 'momentum_10', 'momentum_20',
        'momentum_5_slope', 'momentum_10_slope', 'momentum_20_slope',
        'rolling_vol_5', 'rolling_vol_20',
        'volume_ma5', 'volume_ma20', 'volume_ratio', 'volume_spike',
        'obv', 'obv_ma10',
        'price_vs_ma5', 'price_vs_ma20', 'price_vs_ma60',
        'highest_20d', 'lowest_20d', 'near_high', 'near_low', 'breakout_20d',
        'consecutive_up', 'consecutive_down',
        'gap_pct', 'gap_up', 'gap_down',
        'high_low_range', 'close_position',
    ]

    return features
