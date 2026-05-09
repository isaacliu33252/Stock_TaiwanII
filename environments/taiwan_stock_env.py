"""
TaiwanStockTradingEnv - 台股交易環境 (Gym-style)
================================================================================
這是 FinRL 台股系統的核心環境類別，繼承自 gym.Env。

環境設計:
    - State Space: 52維狀態向量
    - Action Space: 9類離散動作
    - Reward Function: 複合獎勵函數

台股特殊規則:
    - 涨跌停 10% 限制
    - T+2 交割制度
    - 最小交易單位 1000 股
    - 最大持有 4000 股

狀態向量結構 (52維):
    1. 價格特徵 (6維): close, open, high, low, volume, turnover
    2. 技術指標 (20維): MA, MACD, RSI, KDJ, BB, ATR
    3. 型態特徵 (8維): 突破/跌破信號、量增、動量等
    4. 基本面特徵 (8維): 三大法人淨買、殖利率、PE、PB
    5. 部位特徵 (6維): 持股數、成本、未實現盈虧等
    6. 市場情緒 (4維): 大盤報酬、成交量變化等

作者: FinRL量化交易專家
"""

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
import pandas as pd


class TaiwanStockTradingEnv(gym.Env):
    """
    台股交易環境 (Gym-style)
    
    本環境模擬台灣股票市場的交易情境，適合用於訓練 RL 交易代理。
    
    台股特殊規則實現:
        1. 涨跌停限制: 單日最大漲跌幅 10%
        2. T+2 交割: 當日買入股票，T+2 日才能賣出
        3. 1000股單位: 最小交易單位為 1000 股
        4. 最大持倉: 最多持有 4000 股 (4個單位)
    
    Attributes:
        df: 股票歷史數據 (包含 OHLCV 和技術指標)
        initial_balance: 初始資金
        max_position: 最大持股數
        trade_unit: 最小交易單位
        price_limit: 涨跌停限制 (0.10 = 10%)
        commission_rate: 券商佣金率
        tax_rate: 證交稅率
    
    Example:
        >>> env = TaiwanStockTradingEnv(df, initial_balance=1_000_000)
        >>> state, info = env.reset()
        >>> action = env.action_space.sample()
        >>> state, reward, done, truncated, info = env.step(action)
    """
    
    # Gym 環境元數據
    metadata = {'render_modes': ['human', 'rgb_array']}
    
    ACTION_NAMES = [
        'HOLD', 'BUY_1000', 'BUY_5000', 'BUY_10000',
        'SELL_1000', 'SELL_5000', 'SELL_10000',
        'TARGET_50_PERCENT', 'TARGET_100_PERCENT',
    ]

    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 1_000_000,
        max_position: int = 40000,
        trade_unit: int = 1000,
        price_limit: float = 0.10,
        commission_rate: float = 0.0015,
        tax_rate: float = 0.003,
        lookback_window: int = 60,
        reward_func=None,
        initial_shares: int = 0,
        initial_avg_cost: float = 0.0,
        enable_risk_manager: bool = True,
        crash_window: int = 15,
        turnover_penalty: float = 0.01,
        min_hold_days: int = 20,
        short_hold_penalty: float = 0.02,
    ):
        """
        初始化交易環境
        
        Args:
            df: 股票數據 DataFrame，必須包含欄位:
                date, open, high, low, close, volume
                以及所有技術指標欄位
            initial_balance: 初始資金 (預設 100萬)
            max_position: 最大持股數 (預設 4000 股)
            trade_unit: 最小交易單位 (預設 1000 股)
            price_limit: 涨跌停限制 (預設 0.10 = 10%)
            commission_rate: 券商佣金 (預設 0.0015 = 0.15%)
            tax_rate: 證交稅 (預設 0.003 = 0.3%，賣出時收取)
            lookback_window: 狀態回看窗口 (預設 60)
            reward_func: 獎勵函數物件 (若為 None，使用預設)
        """
        super().__init__()
        
        # =====================================================================
        # 基本參數
        # =====================================================================
        self.df = df.copy()
        self.initial_balance = initial_balance
        self.max_position = max_position
        self.trade_unit = trade_unit
        self.price_limit = price_limit
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.lookback_window = lookback_window
        self.enable_risk_manager = enable_risk_manager
        self.crash_window = crash_window
        self.turnover_penalty = turnover_penalty
        self.min_hold_days = min_hold_days
        self.short_hold_penalty = short_hold_penalty
        
        # 獎勵函數
        if reward_func is None:
            from .reward_function import RewardFunction
            self.reward_func = RewardFunction()
        else:
            self.reward_func = reward_func
        
        # 現有持股（用於載入真實部位）
        self._initial_shares = initial_shares
        self._initial_avg_cost = initial_avg_cost
        
        # =====================================================================
        # 環境狀態初始化
        # =====================================================================
        self.current_step = 0          # 當前時間步
        self.balance = initial_balance  # 目前現金
        self.position = 0              # 目前持股數 (0-4000)
        self.avg_cost = 0.0            # 平均成本
        self.total_cost = 0.0          # 總投入成本
        
        # 歷史記錄
        self.trade_history = []        # 交易歷史 [{'action': int, 'price': float, 'pnl': float}, ...]
        self.consecutive_idle_days = 0   # crash detection: 連續無交易天數
        self.portfolio_value_history = []  # 投資組合價值歷史
        self.last_buy_step = None
        
        # 計算最大持股所需資金
        # 假設價格上限為 1000 元，4000 股需要約 400萬
        self.max_shares = max_position
        
        # =====================================================================
        # 狀態空間定義 (52維)
        # =====================================================================
        # 狀態維度說明:
        # - 價格特徵: 6維
        # - 技術指標: 20維
        # - 型態特徵: 8維
        # - 基本面特徵: 8維
        # - 部位特徵: 6維
        # - 市場情緒: 4維
        # 總計: 52維
        self.state_dim = 52
        
        # 觀察空間: 連續空間，無邊界
        self.observation_space = spaces.Box(
            low=-np.inf, 
            high=np.inf, 
            shape=(self.state_dim,), 
            dtype=np.float32
        )
        
        # =====================================================================
        # 動作空間定義 (9類離散)
        # =====================================================================
        # 0: HOLD           - 觀望
        # 1: BUY_1000       - 買入 1000 股
        # 2: SELL_1000      - 賣出 1000 股
        # 3: CLOSE_POSITION - 清倉
        # 4: STOP_LOSS      - 停損
        self.action_space = spaces.Discrete(len(self.ACTION_NAMES))
        
        # =====================================================================
        # 預處理數據
        # =====================================================================
        # 確保數據按日期排序
        if 'date' in self.df.columns:
            self.df = self.df.sort_values('date').reset_index(drop=True)
        elif self.df.index.name == 'date':
            self.df = self.df.reset_index()
        
        # 計算數據長度
        self.max_steps = len(self.df) - 1
        
        # 識別特徵欄位
        self._identify_feature_columns()
        self._prepare_sentiment_features()
        
        # =====================================================================
        # 風險指標初始化
        # =====================================================================
        self.peak_value = initial_balance  # 歷史最高點
        self.max_drawdown = 0.0            # 最大回撒
        
        # =====================================================================
        # T+2 交割制度追蹤
        # =====================================================================
        # 台灣股票市場實行 T+2 交割制度：
        # 當日買入的股票，必須等到第 2 個營業日才能賣出
        # 例如：週一買入 → 週三才能賣出
        # self.pending_shares 儲存每個 step 可賣出的股數
        # key: step 編號，value: 可賣出的股數
        self.pending_shares = {}  # T+2 pending shares tracking
        
        print(f"[TaiwanStockTradingEnv] 環境初始化完成")
        print(f"  - 數據筆數: {len(self.df)}")
        print(f"  - 初始資金: {initial_balance:,.0f} TWD")
        print(f"  - 最大持股: {max_position} 股")
        print(f"  - 狀態維度: {self.state_dim}")
        print(f"  - 動作空間: {self.action_space.n} 類離散動作")
    
    def _identify_feature_columns(self):
        """
        識別並分類特徵欄位
        
        將特徵分為:
        - price_features: 價格特徵
        - technical_features: 技術指標
        - pattern_features: 型態特徵
        - fundamental_features: 基本面特徵
        """
        all_cols = self.df.columns.tolist()
        
        # 排除非特徵欄位
        exclude_cols = ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        
        # 技術指標欄位 (預定義)
        self.price_features = ['close', 'open', 'high', 'low', 'volume', 'turnover']
        
        self.technical_features = [
            'close_ma120_ratio', 'close_ma240_ratio', 'ma60_ma240_ratio',
            'momentum_63', 'momentum_126', 'momentum_252',
            'high_252_position', 'rolling_mdd_63',
            'ma3', 'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma240',
            'ma3_slope', 'ma20_slope', 'ma60_slope',
            'ma_cross_signal',
            'macd_line', 'signal_line', 'histogram', 'histogram_change',
            'macd_turn_positive',
            'rsi_14', 'rsi_28',
            'kdj_k', 'kdj_d', 'kdj_j',
            'williams_r',
            'bb_upper', 'bb_lower', 'bb_width',
            'atr_14',
            'dmi_plus', 'dmi_minus', 'adx',  # DMI/ADX 趨勢強度
            'mfi',                             # 金錢流量指標
            'volume_normalized',               # 標準化成交量 (Z-score)
        ]
        
        self.pattern_features = [
            'highest_breakout', 'lowest_breakdown',
            'volume_spike', 'price_momentum', 'volatility',
            'consecutive_up_days', 'consecutive_down_days',
            'gap_up_or_down',
        ]
        
        self.fundamental_features = [
            'foreign_net_buy_1d', 'foreign_net_buy_3d', 'foreign_net_buy_5d',
            'dealer_net_buy_1d', 'investment_trust_net_buy',
            'dividend_yield', 'per', 'pbr',
        ]
        
        self.position_features = [
            'current_position',  # 持股狀態 (0-4)
            'position_value_ratio',  # 持股價值/總資產
            'unrealized_pnl',    # 未實現盈虧
            'max_drawdown',      # 最大回撒
            'days_since_trade',  # 距上次交易天數
            'cash_ratio',        # 現金比例
        ]
        
        self.sentiment_features = [
            'twse_index_return',
            'twse_index_volume_change',
            'sector_correlation',
            'market_volatility',
        ]
        
        # 驗證欄位是否存在於數據中
        available_cols = [c for c in all_cols if c not in exclude_cols]
        
        # 過濾技術指標 (只保留存在的)
        self.tech_features_available = [c for c in self.technical_features if c in available_cols]
        self.pattern_features_available = [c for c in self.pattern_features if c in available_cols]
        self.fund_features_available = [c for c in self.fundamental_features if c in available_cols]
        self.sentiment_features_available = [c for c in self.sentiment_features if c in available_cols]

    def _prepare_sentiment_features(self) -> None:
        """Ensure the last 4 state slots contain market/sentiment signals."""
        if len(self.sentiment_features_available) == len(self.sentiment_features):
            return

        close = pd.to_numeric(self.df["close"], errors="coerce")
        if "volume" in self.df:
            volume = pd.to_numeric(self.df["volume"], errors="coerce")
        else:
            volume = pd.Series(0.0, index=self.df.index)
        returns = close.pct_change()

        if "twse_index_return" not in self.df:
            self.df["twse_index_return"] = returns.fillna(0.0).clip(-0.2, 0.2)

        if "twse_index_volume_change" not in self.df:
            vol_change = volume.pct_change()
            self.df["twse_index_volume_change"] = (
                vol_change.replace([np.inf, -np.inf], 0.0).fillna(0.0).clip(-5.0, 5.0)
            )

        if "sector_correlation" not in self.df:
            rolling_corr = returns.rolling(20, min_periods=5).corr(
                returns.rolling(5, min_periods=2).mean()
            )
            self.df["sector_correlation"] = (
                rolling_corr.replace([np.inf, -np.inf], 0.0).fillna(0.0).clip(-1.0, 1.0)
            )

        if "market_volatility" not in self.df:
            self.df["market_volatility"] = (
                returns.rolling(20, min_periods=5).std().fillna(0.0).clip(0.0, 1.0)
            )

        self.sentiment_features_available = self.sentiment_features.copy()
    
    def _create_state(self) -> np.ndarray:
        """
        建立 52 維狀態向量
        
        狀態向量結構:
            [價格特徵(6) | 技術指標(20) | 型態(8) | 基本面(8) | 部位(6) | 情緒(4)] = 52
        
        Returns:
            numpy array，52維狀態向量
        """
        state_list = []
        
        # =====================================================================
        # 1. 價格特徵 (6維)
        # =====================================================================
        row = self.df.iloc[self.current_step]
        
        # 標準化價格特徵 (除以收盤價，變成比例)
        close = row['close']
        state_list.extend([
            row['close'] / close if close != 0 else 0,   # close (normalized)
            row['open'] / close if close != 0 else 0,     # open
            row['high'] / close if close != 0 else 0,     # high
            row['low'] / close if close != 0 else 0,      # low
            np.log1p(row['volume']) / 20,                  # volume (log scaled)
            np.log1p(row.get('turnover', 0)) / 25,        # turnover (log scaled)
        ])
        
        # =====================================================================
        # 2. 技術指標特徵 (20維)
        # 優先使用長週期、比例化特徵，讓 ETF 策略更容易學會長抱/少交易。
        # =====================================================================
        for feature in self.tech_features_available[:20]:  # 最多20個
            value = row.get(feature, 0)
            if pd.isna(value):
                value = 0
            state_list.append(float(value))
        
        # 如果不足20個，用0填充
        while len(state_list) < 6 + 20:
            state_list.append(0.0)
        
        # =====================================================================
        # 3. 型態特徵 (8維)
        # =====================================================================
        for feature in self.pattern_features_available[:8]:
            value = row.get(feature, 0)
            if pd.isna(value):
                value = 0
            state_list.append(float(value))
        
        while len(state_list) < 6 + 20 + 8:
            state_list.append(0.0)
        
        # =====================================================================
        # 4. 基本面特徵 (8維) - 填充0因為可能沒有
        # =====================================================================
        for feature in self.fund_features_available[:8]:
            value = row.get(feature, 0)
            if pd.isna(value):
                value = 0
            state_list.append(float(value))
        
        while len(state_list) < 6 + 20 + 8 + 8:
            state_list.append(0.0)
        
        # =====================================================================
        # 5. 部位特徵 (6維)
        # =====================================================================
        portfolio_value = self.balance + self.position * close
        
        # 持股狀態 (0-4)
        position_level = self.position // self.trade_unit  # 0, 1, 2, 3, 4
        state_list.append(float(position_level))
        
        # 持股價值/總資產
        position_value_ratio = (self.position * close) / portfolio_value if portfolio_value > 0 else 0
        state_list.append(position_value_ratio)
        
        # 未實現盈虧
        unrealized_pnl = 0.0
        if self.position > 0 and self.avg_cost > 0:
            unrealized_pnl = (close - self.avg_cost) / self.avg_cost
        state_list.append(unrealized_pnl)
        
        # 最大回撒
        state_list.append(self.max_drawdown)
        
        # 距上次交易天數
        days_since_trade = 0
        if self.trade_history:
            last_trade_step = self.trade_history[-1].get('step', 0)
            days_since_trade = self.current_step - last_trade_step
        state_list.append(float(days_since_trade) / 60)  # 正規化
        
        # 現金比例
        cash_ratio = self.balance / portfolio_value if portfolio_value > 0 else 1.0
        state_list.append(cash_ratio)
        
        # =====================================================================
        # 6. 市場情緒特徵 (4維) - 填充0或計算
        # =====================================================================
        # 如果有加權指數數據，可以計算這些特徵
        # 這裡先用0填充
        for feature in self.sentiment_features[:4]:
            value = row.get(feature, 0.0)
            if pd.isna(value):
                value = 0.0
            state_list.append(float(value))
        
        # 確保長度為52
        state_array = np.array(state_list[:52], dtype=np.float32)
        
        # 如果長度不足，填充0
        if len(state_array) < 52:
            state_array = np.pad(state_array, (0, 52 - len(state_array)), 'constant')
        
        return state_array
    
    def _get_trade_price(self, action: int) -> Tuple[float, bool]:
        """
        取得交易價格並檢查涨跌停
        
        Args:
            action: 動作
        
        Returns:
            (price, is_valid)
            - price: 交易價格
            - is_valid: 價格是否有效 (未涨跌停)
        """
        row = self.df.iloc[self.current_step]
        close = row['close']
        prev_close = self.df.iloc[self.current_step - 1]['close'] if self.current_step > 0 else close
        
        # 根據動作決定交易價格
        if action in [1, 4]:  # BUY, STOP_LOSS - 用 ask (略高於 close)
            trade_price = close * 1.001  # 假設有 0.1% 滑價
        elif action in [2, 3]:  # SELL, SELL_1000 - 用 bid (略低於 close)
            trade_price = close * 0.999
        else:  # HOLD
            trade_price = close
        
        # 檢查涨跌停
        price_change = abs(trade_price - prev_close) / prev_close
        is_valid = price_change < self.price_limit
        
        return trade_price, is_valid

    def _get_side_trade_price(self, side: str) -> Tuple[float, bool]:
        row = self.df.iloc[self.current_step]
        close = row['close']
        prev_close = self.df.iloc[self.current_step - 1]['close'] if self.current_step > 0 else close
        trade_price = close * 1.001 if side == 'buy' else close * 0.999
        price_change = abs(trade_price - prev_close) / prev_close if prev_close else 0.0
        return trade_price, price_change < self.price_limit

    def _buy_shares(self, shares: int, action: int, label: str) -> Tuple[bool, str]:
        shares = int(shares // self.trade_unit * self.trade_unit)
        if shares <= 0:
            return False, "BUY size too small"
        if self.position >= self.max_position:
            return False, "max position reached"

        trade_price, is_valid = self._get_side_trade_price('buy')
        if not is_valid:
            return False, "price limit"

        shares = min(shares, self.max_position - self.position)
        max_affordable = int((self.balance / (trade_price * (1 + self.commission_rate))) // self.trade_unit) * self.trade_unit
        shares = min(shares, max_affordable)
        if shares <= 0:
            return False, "insufficient cash"

        cost = trade_price * shares
        self.balance -= cost * (1 + self.commission_rate)
        total_cost_new = self.position * self.avg_cost + cost
        self.position += shares
        self.avg_cost = total_cost_new / self.position if self.position > 0 else 0.0

        settlement_step = self.current_step + 2
        self.pending_shares[settlement_step] = self.pending_shares.get(settlement_step, 0) + shares
        self.trade_history.append({
            'step': self.current_step,
            'action': action,
            'price': trade_price,
            'shares': shares,
            'position': self.position,
            'pnl': 0,
            'type': label,
            'settlement_step': settlement_step,
        })
        self.consecutive_idle_days = 0
        self.last_buy_step = self.current_step
        return True, f"{label} {shares}@{trade_price:.2f}"

    def _sell_shares(self, shares: int, action: int, label: str) -> Tuple[bool, str]:
        shares = int(shares // self.trade_unit * self.trade_unit)
        if shares <= 0:
            return False, "SELL size too small"

        locked_shares = sum(count for step, count in self.pending_shares.items() if step > self.current_step)
        sellable_shares = max(0, self.position - locked_shares)
        shares = min(shares, sellable_shares)
        shares = int(shares // self.trade_unit * self.trade_unit)
        if shares <= 0:
            return False, f"T+2 locked ({locked_shares} shares)"

        trade_price, is_valid = self._get_side_trade_price('sell')
        if not is_valid:
            return False, "price limit"

        proceeds = trade_price * shares
        commission = proceeds * self.commission_rate
        tax = proceeds * self.tax_rate
        net_proceeds = proceeds - commission - tax
        pnl = net_proceeds - (shares * self.avg_cost)
        self.balance += net_proceeds
        self.position -= shares
        if self.position == 0:
            self.avg_cost = 0.0

        self.trade_history.append({
            'step': self.current_step,
            'action': action,
            'price': trade_price,
            'shares': shares,
            'position': self.position,
            'pnl': pnl,
            'type': label,
        })
        self.consecutive_idle_days = 0
        return True, f"{label} {shares}@{trade_price:.2f}, PnL={pnl:.0f}"
    
    def _execute_trade(self, action: int) -> Tuple[bool, str]:
        """
        執行交易
        
        Args:
            action: 動作 (0-4)
        
        Returns:
            (executed, message)
            - executed: 是否執行成功
            - message: 交易訊息
        """
        action = int(np.asarray(action).item())
        if not 0 <= action < self.action_space.n:
            raise ValueError(f"Invalid action {action}; expected 0-{self.action_space.n - 1}")
        if action == 0:  # HOLD
            return False, "HOLD"

        if action in (1, 2, 3):
            shares = {1: 1000, 2: 5000, 3: 10000}[action]
            return self._buy_shares(shares, action, f"BUY_{shares}")
        if action in (4, 5, 6):
            shares = {4: 1000, 5: 5000, 6: 10000}[action]
            return self._sell_shares(shares, action, f"SELL_{shares}")
        if action in (7, 8):
            row = self.df.iloc[self.current_step]
            close = float(row['close'])
            target_ratio = 0.5 if action == 7 else 1.0
            portfolio_value = self.balance + self.position * close
            target_shares = int((portfolio_value * target_ratio / close) // self.trade_unit) * self.trade_unit
            target_shares = min(target_shares, self.max_position)
            delta = target_shares - self.position
            if delta >= self.trade_unit:
                return self._buy_shares(delta, action, f"TARGET_{int(target_ratio * 100)}_BUY")
            if delta <= -self.trade_unit:
                return self._sell_shares(-delta, action, f"TARGET_{int(target_ratio * 100)}_SELL")
            return False, f"TARGET_{int(target_ratio * 100)}_HOLD"

        return False, "Unknown action"
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        執行一個時間步
        
        Args:
            action: 動作 (0-4)
                0: HOLD
                1: BUY_1000
                2: SELL_1000
                3: CLOSE_POSITION
                4: STOP_LOSS
        
        Returns:
            (state, reward, terminated, truncated, info)
            - state: 下一狀態 (52維向量)
            - reward: 獎勵值
            - terminated: 是否結束 (所有數據走完)
            - truncated: 是否截斷 (人為中斷)
            - info: 額外資訊字典
        """
        action = int(np.asarray(action).item())

        # 取得前一日收盤價 (用於涨跌停計算)
        prev_close = self.df.iloc[self.current_step - 1]['close'] if self.current_step > 0 else 0

        # 取得目前投資組合價值 (交易前用前一步收盤價)
        prev_step_price = prev_close if prev_close != 0 else self.df.iloc[0]['close']
        previous_portfolio_value = self.balance + self.position * prev_step_price
        
        # 執行交易
        executed, message = self._execute_trade(action)
        
        # 更新 step
        self.current_step += 1
        
        # =====================================================================
        # T+2 交割解鎖處理
        # =====================================================================
        # 當 step 前進時，檢查是否有 T+2 鎖定的股票可以解鎖
        # 例如：在 step 5 買入的股票，在 step 7 (5+2) 可以賣出
        unlocked_shares = 0
        settlement_steps_to_remove = []
        for settlement_step, locked_count in self.pending_shares.items():
            if settlement_step <= self.current_step:
                # 這些股票已達 T+2，可以解除鎖定
                unlocked_shares += locked_count
                settlement_steps_to_remove.append(settlement_step)
        
        # 移除已解鎖的記錄
        for step in settlement_steps_to_remove:
            del self.pending_shares[step]
        
        if unlocked_shares > 0:
            pass  # silenced
        
        # 計算新的收盤價投資組合價值
        new_price = self.df.iloc[min(self.current_step, len(self.df) - 1)]['close']
        portfolio_value = self.balance + self.position * new_price
        
        # =====================================================================
        # 計算獎勵
        # =====================================================================
        reward, reward_breakdown = self.reward_func.calculate(
            portfolio_value=portfolio_value,
            previous_portfolio_value=previous_portfolio_value,
            position=self.position,
            close_price=new_price,
            avg_cost=self.avg_cost,
            action=action,
            max_drawdown=self.max_drawdown,
            trade_history=self.trade_history,
            previous_close=prev_close
        )

        if executed and action != 0:
            reward -= self.turnover_penalty
            reward_breakdown['turnover_penalty'] = -self.turnover_penalty

        if executed and action in (4, 5, 6, 7, 8) and self.last_buy_step is not None:
            held_days = self.current_step - self.last_buy_step
            if held_days < self.min_hold_days:
                penalty = self.short_hold_penalty * (1.0 - held_days / max(self.min_hold_days, 1))
                reward -= penalty
                reward_breakdown['short_hold_penalty'] = -penalty
        
        # 更新風險指標
        if portfolio_value > self.peak_value:
            self.peak_value = portfolio_value
        
        drawdown = (self.peak_value - portfolio_value) / self.peak_value
        self.max_drawdown = max(self.max_drawdown, drawdown)
        
        # 記錄歷史
        self.portfolio_value_history.append(portfolio_value)
        
        # =====================================================================
        # 判斷是否結束
        # =====================================================================
        terminated = self.current_step >= self.max_steps
        
        # 額外結束條件
        # 1. 資金歸零或為負
        # 2. 虧損超過 50%
        if self.balance <= 0 or portfolio_value < self.initial_balance * 0.5:
            terminated = True
        
        # =====================================================================
        # 構建 info
        # =====================================================================
        info = {
            'step': self.current_step,
            'action': action,
            'action_name': self.ACTION_NAMES[action],
            'message': message,
            'trade_executed': executed,
            'balance': self.balance,
            'position': self.position,
            'avg_cost': self.avg_cost,
            'portfolio_value': portfolio_value,
            'portfolio_return': (portfolio_value / previous_portfolio_value - 1) if previous_portfolio_value > 0 else 0.0,
            'reward_breakdown': reward_breakdown,
            'max_drawdown': self.max_drawdown,
        }
        
        # =====================================================================
        # 返回下一狀態
        # =====================================================================
        # ── Crash Detection（Soft Penalty）────────────────────────────────
        # 漸進式懲罰：每次 CLOSE/idle position 後結算，idle N 天則罰 -0.003*N
        # 不再是固定 -0.05，避免模型完全停擺
        self.consecutive_idle_days += 1
        if (self.consecutive_idle_days >= self.crash_window
                and self.position > 0
                and self.enable_risk_manager):
            # 漸進式 penalty：罰額與 idle 天數成正比（1天=-0.003, 15天=-0.045）
            idle_days = min(self.consecutive_idle_days, 15)
            soft_penalty = -0.003 * idle_days
            reward = reward + soft_penalty  # 加負值 = 減 reward
            self.consecutive_idle_days = 0   # reset after penalty
        # ── End Crash Detection ───────────────────────────────────────

        if terminated:
            state = np.zeros(self.state_dim, dtype=np.float32)
        else:
            state = self._create_state()

        return state, reward, terminated, False, info
    
    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[np.ndarray, Dict]:
        """
        重置環境
        
        Args:
            seed: 隨機種子 (Gymnasium API)
            options: 額外選項
        
        Returns:
            (state, info)
        """
        super().reset(seed=seed)

        # 重置狀態
        self.current_step = 0
        self.balance = self.initial_balance
        self.position = self._initial_shares
        self.avg_cost = self._initial_avg_cost if self._initial_shares > 0 else 0.0
        self.total_cost = self.position * self.avg_cost if self.position > 0 else 0.0
        
        # 重置風險指標
        self.peak_value = self.initial_balance + self.position * self.df.iloc[0]['close']
        self.max_drawdown = 0.0
        
        # 重置 T+2 交割追蹤
        self.pending_shares = {}
        
        # 清空歷史
        self.trade_history = []
        self.portfolio_value_history = [self.initial_balance]
        self.last_buy_step = None

        if self.reward_func is not None and hasattr(self.reward_func, 'reset'):
            self.reward_func.reset()
        
        # 創建初始狀態
        state = self._create_state()
        
        info = {
            'initial_balance': self.initial_balance,
            'max_position': self.max_position,
            'trade_unit': self.trade_unit,
        }
        
        return state, info
    
    def render(self, mode: str = 'human'):
        """
        渲染環境 (用於除錯)
        
        Args:
            mode: 渲染模式 ('human' 或 'rgb_array')
        """
        if mode == 'human':
            portfolio_value = self.balance + self.position * self.df.iloc[self.current_step]['close']
            
            print(f"\n{'='*60}")
            print(f"Step: {self.current_step}")
            print(f"Date: {self.df.iloc[self.current_step].get('date', 'N/A')}")
            print(f"Price: {self.df.iloc[self.current_step]['close']:.2f}")
            print(f"Balance: {self.balance:,.0f}")
            print(f"Position: {self.position} 股")
            print(f"Avg Cost: {self.avg_cost:.2f}")
            print(f"Portfolio Value: {portfolio_value:,.0f}")
            print(f"Max Drawdown: {self.max_drawdown:.2%}")
            print(f"{'='*60}\n")
    
    def get_info(self) -> Dict[str, Any]:
        """
        取得環境當前資訊
        
        Returns:
            環境狀態資訊字典
        """
        current_price = self.df.iloc[min(self.current_step, len(self.df) - 1)]['close']
        portfolio_value = self.balance + self.position * current_price
        
        return {
            'step': self.current_step,
            'date': self.df.iloc[self.current_step].get('date', 'N/A'),
            'price': current_price,
            'balance': self.balance,
            'position': self.position,
            'avg_cost': self.avg_cost,
            'portfolio_value': portfolio_value,
            'unrealized_pnl': (current_price - self.avg_cost) / self.avg_cost if self.avg_cost > 0 else 0,
            'realized_pnl': sum(t.get('pnl', 0) for t in self.trade_history),
            'max_drawdown': self.max_drawdown,
            'total_trades': len(self.trade_history),
        }
