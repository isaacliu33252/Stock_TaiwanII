# ============================================================================
# 台灣股票交易環境 (Taiwan Stock Trading Environment)
# ============================================================================
"""
自定義 Gymnasium 交易環境，專為台灣股票市場設計。

功能特色：
- 支援台股交易規則（漲跌停、最小交易單位 1000 股）
- 完整的動作空間（買入、賣出、持有）
- 可自定義 Reward 函數
- 技術指標特徵處理

使用方式：
    import gymnasium as gym
    from FinRL.environments import TaiwanStockEnv
    
    env = TaiwanStockEnv(df=data, initial_cash=1000000)
    observation, info = env.reset()
"""

import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MIN_TRADE_UNIT, PRICE_LIMIT_PERCENT, TRANSACTION_TAX_RATE,
    BROKERAGE_FEE_RATE, MIN_BROKERAGE_FEE, INITIAL_CASH, WINDOW_SIZE
)


class TaiwanStockEnv(gym.Env):
    """
    台灣股票交易環境
    
    這個環境模擬台灣股票的實際交易規則，包括：
    - 漲跌停 10% 限制
    - 最小交易單位 1000 股
    - 交易成本（手續費 + 證交稅）
    
    參數：
        df: DataFrame，必須包含 open, high, low, close, volume 欄位
        initial_cash: 初始資金（預設 1,000,000 元）
        commission_rate: 手續費率（預設 0.001425 = 0.1425%）
        tax_rate: 交易稅率（預設 0.003 = 0.3%，僅賣出時收取）
        max_position: 最大倉位比例（預設 1.0 = 100%）
        window_size: 觀察視窗大小（預設 10 天）
    """
    
    metadata = {"render_modes": ["human"]}
    
    def __init__(
        self,
        df: pd.DataFrame,
        initial_cash: float = INITIAL_CASH,
        commission_rate: float = BROKERAGE_FEE_RATE,
        tax_rate: float = TRANSACTION_TAX_RATE,
        max_position: float = 1.0,
        window_size: int = WINDOW_SIZE,
    ):
        """初始化交易環境"""
        super().__init__()
        
        # 資料驗證
        required_columns = ["open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"資料中缺少必要的欄位: {col}")
        
        self.df = df.reset_index(drop=True)
        self.n_step = len(self.df)
        
        # 交易參數
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.max_position = max_position
        self.window_size = window_size
        
        # 計算漲跌停價格範圍
        self.price_limit = PRICE_LIMIT_PERCENT / 100.0
        
        # 動作空間：-1（賣出）, 0（持有）, 1（買入）
        # 若需要更細緻的控制，可以擴展為連續空間
        self.action_space = spaces.Discrete(3)  # 3 個動作：0=賣, 1=持有, 2=買
        
        # 觀察空間：包含價格資料和帳戶狀態
        # n_features = len(df.columns) + 帳戶狀態（cash, shares, value）
        n_features = len(df.columns) + 3
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(n_features,), dtype=np.float32
        )
        
        # 內部狀態
        self.current_step = 0
        self.cash = initial_cash
        self.shares = 0  # 持有股數（必須是 1000 的倍數）
        self.total_asset = initial_cash
        self.trades = []  # 交易記錄
        
        # 買入/賣出標記（用於計算reward）
        self.buy_price = 0
        self.last_portfolio_value = initial_cash
    
    def reset(self, seed=None, options=None):
        """重置環境到初始狀態"""
        super().reset(seed=seed)
        
        self.current_step = self.window_size
        self.cash = self.initial_cash
        self.shares = 0
        self.total_asset = self.initial_cash
        self.buy_price = 0
        self.last_portfolio_value = self.initial_cash
        self.trades = []
        
        return self._get_observation(), self._get_info()
    
    def _get_observation(self):
        """取得當前觀察值"""
        # 取得視窗內的價格資料
        window_data = self.df.iloc[
            self.current_step - self.window_size : self.current_step
        ].copy()
        
        # 取出收盤價並攤平為 1D 陣列
        price_features = window_data.values.flatten().astype(np.float32)
        
        # 取得最後一天的收盤價（用於計算倉位價值）
        last_close = self.df.iloc[self.current_step - 1]["close"]
        portfolio_value = self.cash + self.shares * last_close
        
        # 帳戶狀態
        account_state = np.array([
            self.cash / self.initial_cash,  # 現金比例（標準化）
            self.shares * last_close / self.initial_cash,  # 倉位價值比例
            portfolio_value / self.initial_cash,  # 總資產比例
        ], dtype=np.float32)
        
        # 合併所有特徵
        observation = np.concatenate([price_features, account_state])
        
        return observation
    
    def _get_info(self):
        """取得額外資訊"""
        last_close = self.df.iloc[self.current_step - 1]["close"]
        return {
            "current_step": self.current_step,
            "cash": self.cash,
            "shares": self.shares,
            "position_value": self.shares * last_close,
            "total_asset": self.cash + self.shares * last_close,
            "last_close": last_close,
        }
    
    def _calculate_portfolio_value(self):
        """計算當前投資組合價值"""
        last_close = self.df.iloc[self.current_step - 1]["close"]
        return self.cash + self.shares * last_close
    
    def step(self, action):
        """執行一步交易"""
        # 取得當前價格
        current_data = self.df.iloc[self.current_step]
        open_price = current_data["open"]
        close_price = current_data["close"]
        high_price = current_data["high"]
        low_price = current_data["low"]
        
        # 計算可交易價格範圍（考慮漲跌停）
        max_price = close_price * (1 + self.price_limit)
        min_price = close_price * (1 - self.price_limit)
        
        # 限制開盤價在漲跌停範圍內
        execution_price = np.clip(open_price, min_price, max_price)
        
        # 執行交易
        self._execute_trade(action, execution_price)
        
        # 移動到下一步
        self.current_step += 1
        
        # 檢查是否結束
        terminated = self.current_step >= self.n_step - 1
        truncated = False
        
        # 計算 reward（資產變化）
        current_portfolio_value = self._calculate_portfolio_value()
        reward = (current_portfolio_value - self.last_portfolio_value) / self.initial_cash
        self.last_portfolio_value = current_portfolio_value
        
        # 更新總資產
        self.total_asset = current_portfolio_value
        
        return self._get_observation(), reward, terminated, truncated, self._get_info()
    
    def _execute_trade(self, action, price):
        """
        執行交易
        
        action: 0=賣出, 1=持有, 2=買入
        """
        if action == 0:  # 賣出
            if self.shares > 0:
                # 賣出全部持股（必須是 1000 的倍數）
                sell_shares = self.shares
                gross_value = sell_shares * price
                
                # 計算交易成本
                commission = max(gross_value * self.commission_rate, MIN_BROKERAGE_FEE)
                tax = gross_value * self.tax_rate
                net_value = gross_value - commission - tax
                
                # 更新現金和持股
                self.cash += net_value
                self.shares = 0
                
                # 記錄交易
                self.trades.append({
                    "step": self.current_step,
                    "action": "sell",
                    "shares": sell_shares,
                    "price": price,
                    "gross_value": gross_value,
                    "commission": commission,
                    "tax": tax,
                    "net_value": net_value,
                })
        
        elif action == 2:  # 買入
            # 計算可買入的最大股數（1000 的倍數）
            max_shares_by_cash = int(self.cash / (price * (1 + self.commission_rate)))
            max_shares_by_position = int(
                self.initial_cash * self.max_position / price
            ) - self.shares
            
            # 取兩者的最小值，並向下取整到 1000 的倍數
            max_shares = min(max_shares_by_cash, max_shares_by_position)
            buy_shares = (max_shares // MIN_TRADE_UNIT) * MIN_TRADE_UNIT
            
            if buy_shares > 0:
                gross_value = buy_shares * price
                commission = max(gross_value * self.commission_rate, MIN_BROKERAGE_FEE)
                total_cost = gross_value + commission
                
                if total_cost <= self.cash:
                    self.cash -= total_cost
                    self.shares += buy_shares
                    self.buy_price = price
                    
                    self.trades.append({
                        "step": self.current_step,
                        "action": "buy",
                        "shares": buy_shares,
                        "price": price,
                        "gross_value": gross_value,
                        "commission": commission,
                        "tax": 0,
                        "net_value": -total_cost,
                    })
    
    def render(self):
        """渲染環境狀態"""
        last_close = self.df.iloc[self.current_step - 1]["close"]
        print(f"步驟: {self.current_step}")
        print(f"  收盤價: {last_close:.2f}")
        print(f"  現金: {self.cash:.2f}")
        print(f"  持股: {self.shares} 股")
        print(f"  倉位價值: {self.shares * last_close:.2f}")
        print(f"  總資產: {self.total_asset:.2f}")
    
    def close(self):
        """關閉環境"""
        pass


# 註冊環境（方便使用 gym.make() 創建）
# gym.register(id="TaiwanStock-v0", entry_point=TaiwanStockEnv)
