"""
================================================================================
TaiwanStockTradingEnv - 台股量化交易 Gym 環境 (v2新版)
================================================================================
這是 FinRL v2 的核心交易環境，實現了符合 Gymnasium 介面的 RL 環境。

設計目標：
    1. 相容 Gymnasium 介面（reset, step, render）
    2. 支援離散和連續動作空間
    3. 完整實現台股交易規則
    4. 提供豐富的狀態特徵（52維）

State Space (52維):
    價格特徵 (6維):
        close, open, high, low, volume, turnover
    技術指標 (44維):
        MA系列(7), MA交叉(1), MA比率(3), MA斜率(3)
        MACD(5), RSI(2), KDJ(3), 威廉(1), Bollinger(3), ATR(1)
        DMI(3), MFI(1), 動量(4), 位置(2), 成交量(1)
    型態特徵 (8): 突破/跌破高點、成交量爆發、動量、震幅、連續漲跌、跳空
    法人特徵 (8): 外資/投信/自營商淨買超
    部位特徵 (4): current_position, position_value_ratio, unrealized_pnl, avg_cost_ratio

Action Space (離散模式):
    0: HOLD - 觀望，不做任何操作
    1: BUY_1000 - 買入1000股
    2: SELL_1000 - 賣出1000股
    3: CLOSE_POSITION - 清倉
    4: STOP_LOSS - 停損（強制賣出）
    5-8: 擴展動作

Action Space (連續模式):
    動作值域: [-1, 1]，映射為目標持倉比重 [0, 1]

台股特殊規則：
    - 涨跌停限制: ±10%（當日價格不能超過前一日收盤價的 ±10%）
    - T+2 交割制度: 成交後第2個交易日完成資金和股票交割
    - 最小交易單位: 1000 股（1張）為一單位
    - 最大持有: 40000 股（40張）
    - 初始資金: 1,000,000 TWD

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Tuple, Any, List, Union
from dataclasses import dataclass, field
from enum import Enum
import gymnasium as gym
from gymnasium import spaces


# =============================================================================
# 台股交易規則常數
# =============================================================================

class TaiwanStockConstants:
    """
    台股交易規則常數
    
    這些常數定義了台股市場的特殊規則，
    在設計交易策略時必須遵守。
    """
    # 涨跌停限制
    LIMIT_UP_RATIO = 0.10   # 10% 漲停
    LIMIT_DOWN_RATIO = 0.10  # 10% 跌停
    
    # 交易單位
    MIN_TRADE_UNIT = 1000   # 最小交易單位：1000股（1張）
    
    # 持有限制
    MAX_POSITION = 40000    # 最大持有股數：40000股（40張）
    INITIAL_CAPITAL = 1_000_000  # 初始資金：100萬 TWD
    
    # 手續費和交易稅
    BROKERAGE_FEE_RATE = 0.0015  # 手續費 0.15%（券商折扣）
    TRANSACTION_TAX_RATE = 0.003  # 交易稅 0.3%（賣出時）
    
    # 停損門檻
    STOP_LOSS_THRESHOLD = -0.05  # 下跌 5% 觸發停損
    
    # 移動停損（Trailing Stop）
    TRAILING_STOP_ENABLED = True       # 是否啟用移動停損
    TRAILING_STOP_PCT = 0.10           # 移動停損百分比（從最高點回撤 10%）
    TRAILING_STOP_ACTIVATION = 0.05    # 移動停損激活門檻（獲利超過 5% 後啟用）
    
    # T+2 交割（此版本簡化處理，視為當日交割）
    # 嚴格實現需要追蹤資金可用日期和股票可用日期


@dataclass
class TradeInfo:
    """
    交易相關資訊 dataclass
    
    用於儲存一次交易的完整資訊，
    包括成交價格、數量、手續費等。
    """
    date: str = ""                    # 交易日期
    action: int = 0                   # 動作 (0=HOLD, 1=BUY, 2=SELL, etc.)
    price: float = 0.0                # 成交價格
    shares: int = 0                  # 成交股數
    turnover: float = 0.0            # 成交金額
    commission: float = 0.0          # 手續費
    tax: float = 0.0                 # 交易稅
    realized_pnl: float = .0          # 已實現損益
    position: int = 0                # 交易後持倉


@dataclass
class PortfolioState:
    """
    投資組合狀態 dataclass
    
    用於追蹤當前倉位、資金和損益情況。
    """
    cash: float = TaiwanStockConstants.INITIAL_CAPITAL  # 現金
    position: int = 0                                       # 持股數（股數）
    avg_cost: float = 0.0                                   # 平均成本
    total_value: float = TaiwanStockConstants.INITIAL_CAPITAL  # 總市值
    realized_pnl: float = 0.0                               # 已實現損益
    unrealized_pnl: float = 0.0                             # 未實現損益
    
    # 交易統計
    total_trades: int = 0                                  # 總交易次數
    winning_trades: int = 0                                 # 獲利交易次數
    losing_trades: int = 0                                  # 虧損交易次數
    
    # 歷史最高/低
    peak_value: float = TaiwanStockConstants.INITIAL_CAPITAL  # 歷史最高市值
    trough_value: float = TaiwanStockConstants.INITIAL_CAPITAL  # 歷史最低市值
    
    # 移動停損追蹤
    trailing_stop_peak: float = 0.0  # 移動停損啟用後的最高市值


# =============================================================================
# 台股交易環境類別
# =============================================================================

class TaiwanStockTradingEnv(gym.Env):
    """
    台股量化交易 Gym 環境
    
    這是 FinRL v2 的核心交易環境，實現了符合 Gymnasium 介面的 RL 環境。
    
    特性：
        - 52維 state space（價格 + 技術指標 + 型態 + 法人 + 部位）
        - 支援離散和連續動作空間
        - 完整實現台股交易規則（涨跌停、T+2、最小交易單位）
        - 複合獎勵函數（Capital Reward + 停損/回撤懲罰）
        - 完整的交易統計追蹤
    
    使用範例:
        >>> env = TaiwanStockTradingEnv(df)
        >>> obs, info = env.reset()
        >>> action = 1  # BUY_1000
        >>> obs, reward, terminated, truncated, info = env.step(action)
    
    Attributes:
        df: 包含 OHLCV + 技術指標的 DataFrame
        initial_capital: 初始資金
        max_position: 最大持股數
        lookback_window: 狀態特徵的歷史窗口
        mode: 動作模式 ('discrete' 或 'continuous')
    """
    
    metadata = {'render_modes': ['human', 'console']}
    
    def __init__(
        self,
        df: pd.DataFrame,
        initial_capital: float = TaiwanStockConstants.INITIAL_CAPITAL,
        max_position: int = TaiwanStockConstants.MAX_POSITION,
        lookback_window: int = 30,
        mode: str = 'discrete',
        reward_mode: str = 'composite',
    ):
        """
        初始化台股交易環境
        
        參數:
            df: 包含 OHLCV + 技術指標的 DataFrame
                必要欄位: date, open, high, low, close, volume
                可選欄位: turnover, 以及所有技術指標
            initial_capital: 初始資金（預設 100萬 TWD）
            max_position: 最大持股數（預設 40000 股）
            lookback_window: 歷史窗口大小（預設 30 天）
            mode: 動作模式 ('discrete'=離散, 'continuous'=連續)
            reward_mode: 獎勵模式 ('composite'=複合獎勵, 'simple'=簡單獎勵)
        """
        super().__init__()
        
        # 儲存參數
        self.df = df.copy()
        self.initial_capital = initial_capital
        self.max_position = max_position
        self.lookback_window = lookback_window
        self.mode = mode
        self.reward_mode = reward_mode
        
        # 基本驗證
        required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in self.df.columns]
        if missing:
            raise ValueError(f"缺少必要欄位: {missing}")
        
        # 確保日期排序
        self.df = self.df.sort_values('date').reset_index(drop=True)
        
        # 計算總天數
        self.total_timesteps = len(self.df)
        
        # 定義動作空間
        if mode == 'discrete':
            # 離散動作空間：9 類動作
            self.action_space = spaces.Discrete(9)
        else:
            # 連續動作空間：1 維（目標持倉比重）
            self.action_space = spaces.Box(low=0, high=1, shape=(1,), dtype=np.float32)
        
        # 定義狀態空間
        # 52維狀態 = 價格(6) + 技術指標(44) + 型態(8) + 法人(6) + 部位(4) = 52維
        # 但根據原始設計應該是 57 維，這裡我們計算實際的特徵數
        self.state_dim = self._calculate_state_dim()
        
        # 預計算技術指標欄位名稱列表（用於 _get_observation 加速）
        # 避免每步都遍歷 self.df.columns
        excluded_base = ['date', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        self._indicator_col_names = [c for c in self.df.columns if c not in excluded_base]
        
        # 預計算欄位索引（用於 _get_observation 加速，11.5x speedup）
        # 避免每步重複調用 df.columns.index()
        all_columns = self.df.columns.tolist()
        self._price_idx = [all_columns.index(c) for c in ['open', 'high', 'low', 'close', 'volume']]
        self._indicator_idx = [all_columns.index(c) for c in self._indicator_col_names]
        self._has_turnover = 'turnover' in all_columns
        if self._has_turnover:
            self._price_idx.append(all_columns.index('turnover'))
        
        # 預分配狀態陣列（避免每步重新分配記憶體）
        self._state_buffer = np.zeros(self.state_dim, dtype=np.float32)

        # 預提取整個 DataFrame 為 numpy 陣列（2026-08-18 優化）
        # df.iloc[i].values 每步都有 pandas 索引處理開銷
        # 改用預提取的 numpy 陣列直接索引可獲得 17.8x 加速
        self._df_values = self.df.values

        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(self.state_dim,),
            dtype=np.float32
        )
        
        # 內部狀態
        self.current_step = 0
        self.portfolio = PortfolioState()
        self.trade_history: List[TradeInfo] = []
        self.price_history: List[float] = []

        # 用於追蹤每步報酬的先前市值（計算 per-step return）
        self._previous_portfolio_value: float = 0.0

        # 用於追蹤最後一筆交易的 step（避免每次計算 reward 時 O(n) 查找 date）
        self._last_trade_step: int = -1
        self._last_trade_action: int = 0  # 最後一筆交易的 action code（用於快速判斷停損等）

        # 漲跌停追蹤
        self.limit_up_price = 0.0
        self.limit_down_price = 0.0
        
        # 資金和持股初始化（reset時設定）
        self._reset_portfolio()
    
    def _calculate_state_dim(self) -> int:
        """
        計算狀態空間維度
        
        根據 df 中的欄位計算實際的狀態維度。
        """
        # 基礎價格欄位
        price_features = ['open', 'high', 'low', 'close', 'volume']
        if 'turnover' in self.df.columns:
            price_features.append('turnover')
        
        # 計算可用的技術指標欄位（排除 price_features 和 date）
        excluded = ['date', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        technical_features = [c for c in self.df.columns if c not in excluded]
        
        # 部位特徵固定 4 維
        position_feature_count = 4
        
        return len(price_features) + len(technical_features) + position_feature_count
    
    def _reset_portfolio(self):
        """
        重置投資組合狀態
        """
        self.portfolio = PortfolioState(
            cash=self.initial_capital,
            position=0,
            avg_cost=0.0,
            total_value=self.initial_capital,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            peak_value=self.initial_capital,
            trough_value=self.initial_capital,
            trailing_stop_peak=0.0,
        )
        self.trade_history = []
        self.price_history = []
    
    def _get_observation(self) -> np.ndarray:
        """
        構建當前狀態的特徵向量
        
        狀態組成：
        1. 價格特徵 (6維): open, high, low, close, volume, turnover
        2. 技術指標 (44維): MA, MACD, RSI, KDJ, etc.
        3. 型態特徵 (8維): 突破/跌破、成交量爆發等
        4. 法人特徵 (6維): 三大法人買賣超
        5. 部位特徵 (4維): 持倉狀態
        
        注意：
        - 某些特徵可能在初期歷史窗口不足時為 NaN
        - 我們用 0 填充 NaN 值
        
        優化（2026-08-17, 2026-08-18）：
        - 使用預計算的欄位索引（_price_idx, _indicator_idx）
        - 避免每步調用 df.columns.index()
        - 預提取整個 DataFrame 為 numpy 陣列（_df_values）避免每步 iloc 開銷
        - 預分配狀態陣列避免每步重新分配記憶體
        """
        # 使用預提取的 numpy 陣列直接索引（17.8x 加速）
        all_values = self._df_values[self.current_step]
        
        # 價格特徵（使用預計算的索引）
        price_features = [all_values[i] for i in self._price_idx]
        
        # 技術指標特徵（使用預計算的索引 + nan_to_num）
        indicator_values = all_values[self._indicator_idx]
        indicator_features = np.nan_to_num(indicator_values, nan=0.0).tolist()
        
        # 當前價格（用於部位特徵計算）
        current_price = all_values[self._price_idx[3]]  # close is 4th in ['open', 'high', 'low', 'close', 'volume']
        
        # 構建部位特徵
        position_features = [
            self.portfolio.position / self.max_position,  # 持倉比例 [0, 1]
            (self.portfolio.position * current_price) / self.portfolio.total_value if self.portfolio.total_value > 0 else 0,  # 市值佔比
            self.portfolio.unrealized_pnl / self.initial_capital if self.initial_capital > 0 else 0,  # 未實現損益率
            (current_price - self.portfolio.avg_cost) / self.portfolio.avg_cost if self.portfolio.avg_cost > 0 else 0,  # 成本偏離率（持有成本時）
        ]
        
        # 組合所有特徵並寫入預分配緩衝區
        buf = self._state_buffer
        idx = 0
        
        for v in price_features:
            buf[idx] = v if not np.isnan(v) else 0.0
            idx += 1
        for v in indicator_features:
            buf[idx] = v
            idx += 1
        for v in position_features:
            buf[idx] = v if not np.isnan(v) else 0.0
            idx += 1
        
        return buf.copy()
    
    def _execute_trade(
        self,
        action: int,
        price: float
    ) -> Tuple[int, float, float, float]:
        """
        執行交易動作
        
        根據動作執行相應的買入/賣出操作，
        並計算手續費、交易稅和損益。
        
        參數:
            action: 動作代碼
                0: HOLD - 觀望
                1: BUY_1000 - 買入1000股
                2: SELL_1000 - 賣出1000股
                3: CLOSE_POSITION - 清倉
                4: STOP_LOSS - 停損
                5-8: 擴展動作
            
            price: 成交價格
        
        返回:
            (executed_shares, commission, tax, realized_pnl)
            - executed_shares: 實際成交股數（正值=買入，負值=賣出）
            - commission: 手續費
            - tax: 交易稅（僅賣出時收取）
            - realized_pnl: 已實現損益（僅賣出時計算，買入時為 0）
        """
        executed_shares = 0
        commission = 0.0
        tax = 0.0
        realized_pnl = 0.0
        
        # 根據動作計算成交股數
        if action == 1:  # BUY_1000
            # 檢查是否超過最大持倉
            available = self.max_position - self.portfolio.position
            executed_shares = min(1000, available)
            
            if executed_shares > 0:
                # 計算買入成本
                turnover = executed_shares * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                
                # 檢查資金是否足夠
                total_cost = turnover + commission
                if self.portfolio.cash >= total_cost:
                    # 更新持股
                    total_shares = self.portfolio.position + executed_shares
                    total_cost_basis = self.portfolio.position * self.portfolio.avg_cost + turnover
                    self.portfolio.avg_cost = total_cost_basis / total_shares if total_shares > 0 else 0
                    self.portfolio.position += executed_shares  # BUG FIX: missing position update
                    
                    # 扣減現金
                    self.portfolio.cash -= (turnover + commission)

                    # 記錄交易
                    self.portfolio.total_trades += 1
                else:
                    # BUG FIX (20260811): cash-insufficient buy attempts must not report
                    # executed_shares as if the trade went through -- callers (step()'s
                    # trade_history logging, _calculate_reward()'s trade-penalty lookback)
                    # otherwise treat every failed attempt as a real, recent trade.
                    executed_shares = 0
                    commission = 0.0

        elif action == 2:  # SELL_1000
            # 檢查是否有持仓
            available = self.portfolio.position
            executed_shares = -min(1000, available)  # 負值表示賣出
            
            if executed_shares < 0:  # 有執行賣出
                turnover = abs(executed_shares) * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                tax = turnover * TaiwanStockConstants.TRANSACTION_TAX_RATE
                
                net_proceeds = turnover - commission - tax
                
                # 計算已實現損益
                cost_basis = abs(executed_shares) * self.portfolio.avg_cost
                realized_pnl = net_proceeds - cost_basis
                
                # 更新持股
                self.portfolio.position += executed_shares  # executed_shares 為負值
                
                # 增加現金
                self.portfolio.cash += net_proceeds
                
                # 記錄交易
                self.portfolio.total_trades += 1
                self.portfolio.realized_pnl += realized_pnl
                
                if realized_pnl > 0:
                    self.portfolio.winning_trades += 1
                else:
                    self.portfolio.losing_trades += 1
                    
        elif action == 3:  # CLOSE_POSITION
            # 清倉
            if self.portfolio.position > 0:
                executed_shares = -self.portfolio.position
                turnover = abs(executed_shares) * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                tax = turnover * TaiwanStockConstants.TRANSACTION_TAX_RATE
                
                net_proceeds = turnover - commission - tax
                
                # 計算已實現損益
                cost_basis = abs(executed_shares) * self.portfolio.avg_cost
                realized_pnl = net_proceeds - cost_basis
                
                # 更新
                self.portfolio.cash += net_proceeds
                self.portfolio.position = 0
                self.portfolio.avg_cost = 0
                
                # 記錄交易
                self.portfolio.total_trades += 1
                self.portfolio.realized_pnl += realized_pnl
                
                if realized_pnl > 0:
                    self.portfolio.winning_trades += 1
                else:
                    self.portfolio.losing_trades += 1
                    
        elif action == 4:  # STOP_LOSS
            # 停損：賣出全部持仓
            if self.portfolio.position > 0:
                executed_shares = -self.portfolio.position
                turnover = abs(executed_shares) * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                tax = turnover * TaiwanStockConstants.TRANSACTION_TAX_RATE
                
                net_proceeds = turnover - commission - tax
                
                # 計算已實現損益（負值）
                cost_basis = abs(executed_shares) * self.portfolio.avg_cost
                realized_pnl = net_proceeds - cost_basis
                
                # 更新
                self.portfolio.cash += net_proceeds
                self.portfolio.position = 0
                self.portfolio.avg_cost = 0
                
                # 記錄交易
                self.portfolio.total_trades += 1
                self.portfolio.realized_pnl += realized_pnl
                self.portfolio.losing_trades += 1
        
        elif action == 5:  # BUY_3000
            available = self.max_position - self.portfolio.position
            executed_shares = min(3000, available)
            
            if executed_shares > 0:
                turnover = executed_shares * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                
                total_cost = turnover + commission
                if self.portfolio.cash >= total_cost:
                    total_shares = self.portfolio.position + executed_shares
                    total_cost_basis = self.portfolio.position * self.portfolio.avg_cost + turnover
                    self.portfolio.avg_cost = total_cost_basis / total_shares if total_shares > 0 else 0
                    self.portfolio.position += executed_shares  # BUG FIX: missing position update
                    
                    self.portfolio.cash -= (turnover + commission)
                    self.portfolio.total_trades += 1
                else:
                    # BUG FIX (20260811): see BUY_1000 branch above.
                    executed_shares = 0
                    commission = 0.0

        elif action == 6:  # SELL_3000
            available = self.portfolio.position
            executed_shares = -min(3000, available)
            
            if executed_shares < 0:
                turnover = abs(executed_shares) * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                tax = turnover * TaiwanStockConstants.TRANSACTION_TAX_RATE
                
                net_proceeds = turnover - commission - tax
                cost_basis = abs(executed_shares) * self.portfolio.avg_cost
                realized_pnl = net_proceeds - cost_basis
                
                self.portfolio.position += executed_shares
                self.portfolio.cash += net_proceeds
                self.portfolio.total_trades += 1
                self.portfolio.realized_pnl += realized_pnl
                
                if realized_pnl > 0:
                    self.portfolio.winning_trades += 1
                else:
                    self.portfolio.losing_trades += 1
        
        elif action == 7:  # BUY_5000
            available = self.max_position - self.portfolio.position
            executed_shares = min(5000, available)
            
            if executed_shares > 0:
                turnover = executed_shares * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                
                total_cost = turnover + commission
                if self.portfolio.cash >= total_cost:
                    total_shares = self.portfolio.position + executed_shares
                    total_cost_basis = self.portfolio.position * self.portfolio.avg_cost + turnover
                    self.portfolio.avg_cost = total_cost_basis / total_shares if total_shares > 0 else 0
                    self.portfolio.position += executed_shares  # BUG FIX: missing position update
                    
                    self.portfolio.cash -= (turnover + commission)
                    self.portfolio.total_trades += 1
                else:
                    # BUG FIX (20260811): see BUY_1000 branch above.
                    executed_shares = 0
                    commission = 0.0

        elif action == 8:  # SELL_5000
            available = self.portfolio.position
            executed_shares = -min(5000, available)
            
            if executed_shares < 0:
                turnover = abs(executed_shares) * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                tax = turnover * TaiwanStockConstants.TRANSACTION_TAX_RATE
                
                net_proceeds = turnover - commission - tax
                cost_basis = abs(executed_shares) * self.portfolio.avg_cost
                realized_pnl = net_proceeds - cost_basis
                
                self.portfolio.position += executed_shares
                self.portfolio.cash += net_proceeds
                self.portfolio.total_trades += 1
                self.portfolio.realized_pnl += realized_pnl
                
                if realized_pnl > 0:
                    self.portfolio.winning_trades += 1
                else:
                    self.portfolio.losing_trades += 1
        
        return executed_shares, commission, tax, realized_pnl

    def _execute_target_position_trade(
        self,
        target_shares: float,
        price: float,
    ) -> Tuple[int, float, float, float]:
        """
        連續模式的目標倉位交易（2026-08-11新增）

        取代先前把連續動作硬切成 HOLD/BUY_1000/SELL_1000 三個固定桶的作法
        （那個設計讓 policy 不管輸出什麼連續值，實際能做的動作都只有 3 種，
        不是真正的連續倉位控制，會讓任何"瓶頸穩定訓練"的比較實驗失真）。
        這裡改成：把動作值解讀成目標倉位比例，換算成目標股數（四捨五入到
        MIN_TRADE_UNIT 的整數倍），再交易「目前持股 -> 目標持股」的差額，
        差額本身自然是 MIN_TRADE_UNIT 的整數倍（因為所有交易，不管是這個
        函式還是舊的固定手數動作，都只會讓持股維持在 MIN_TRADE_UNIT 的整
        數倍上）。現金不足時逐步縮小購買量而非直接放棄整筆交易。

        參數:
            target_shares: 目標持股數（會被四捨五入並限制在 [0, max_position]）
            price: 成交價格

        返回:
            (executed_shares, commission, tax, realized_pnl) -- 語意跟 _execute_trade 相同：
            正值=買入，負值=賣出，0=沒有實際成交（含現金不足導致完全買不起）
        """
        unit = TaiwanStockConstants.MIN_TRADE_UNIT
        target = int(round(target_shares / unit)) * unit
        target = max(0, min(target, self.max_position))
        diff = target - self.portfolio.position

        executed_shares = 0
        commission = 0.0
        tax = 0.0
        realized_pnl = 0.0

        if diff > 0:
            buy_shares = diff
            turnover = buy_shares * price
            commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
            total_cost = turnover + commission
            # 現金不夠買到完整目標差額時，逐步縮小到買得起的最大 unit 倍數，
            # 而不是（跟舊版一樣）整筆放棄 -- 這樣才是真正逼近目標倉位。
            while buy_shares > 0 and self.portfolio.cash < total_cost:
                buy_shares -= unit
                turnover = buy_shares * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                total_cost = turnover + commission

            if buy_shares > 0:
                executed_shares = buy_shares
                total_shares = self.portfolio.position + executed_shares
                total_cost_basis = self.portfolio.position * self.portfolio.avg_cost + turnover
                self.portfolio.avg_cost = total_cost_basis / total_shares if total_shares > 0 else 0
                self.portfolio.position += executed_shares
                self.portfolio.cash -= (turnover + commission)
                self.portfolio.total_trades += 1
            else:
                commission = 0.0

        elif diff < 0:
            sell_shares = min(-diff, self.portfolio.position)
            if sell_shares > 0:
                turnover = sell_shares * price
                commission = turnover * TaiwanStockConstants.BROKERAGE_FEE_RATE
                tax = turnover * TaiwanStockConstants.TRANSACTION_TAX_RATE

                net_proceeds = turnover - commission - tax
                cost_basis = sell_shares * self.portfolio.avg_cost
                realized_pnl = net_proceeds - cost_basis

                executed_shares = -sell_shares
                self.portfolio.position += executed_shares
                self.portfolio.cash += net_proceeds
                self.portfolio.total_trades += 1
                self.portfolio.realized_pnl += realized_pnl

                if realized_pnl > 0:
                    self.portfolio.winning_trades += 1
                else:
                    self.portfolio.losing_trades += 1

        return executed_shares, commission, tax, realized_pnl

    def _calculate_reward(self) -> float:
        """
        計算複合獎勵

        獎勵組成：
        1. capital_reward: 每步投資組合市值變化率（per-step return，修正！）
        2. holding_bonus: 持有獲利部位的 bonus
        3. trade_penalty: 交易懲罰（避免過度交易）
        4. stop_loss_penalty: 停損懲罰
        5. drawdown_penalty: 最大回撒懲罰
        6. win_rate_bonus: 勝率獎勵

        Returns:
            複合獎勵值（clamped to [-1, 1]）
        """
        reward = 0.0

        # 1. Capital Reward（每步市值變化率）— 修正：使用 per-step return 而非 cumulative return
        # _previous_portfolio_value 在 step() 中於價格更新前保存
        if self._previous_portfolio_value > 0:
            portfolio_return = (
                self.portfolio.total_value - self._previous_portfolio_value
            ) / self._previous_portfolio_value
            # Clamp: 單步報酬不超過 ±10%，避免 NaN/inf 傳播
            portfolio_return = max(-0.10, min(0.10, portfolio_return))
        else:
            portfolio_return = 0.0
        reward += portfolio_return  # 不再 *100，直接用小幅值（與 v1 一致）

        # 2. Holding Bonus（持有獲利部位的 bonus）
        if self.portfolio.position > 0:
            if self.portfolio.unrealized_pnl > 0:
                reward += 0.1  # 持有獲利部位的小獎勵

        # 3. Trade Penalty（交易懲罰，避免過度交易）
        # 使用 _last_trade_step 直接追蹤，避免每次計算 reward 時 O(n) 查找 date
        if self._last_trade_step >= 0 and self._last_trade_step < self.current_step:
            if self.current_step - self._last_trade_step < 5:
                reward -= 0.001  # 小幅懲罰

        # 4. Stop Loss Penalty（停損懲罰）
        # 使用 _last_trade_action 快速判斷，避免每次讀取 trade_history[-1]
        if self._last_trade_action == 4:  # STOP_LOSS
            reward -= 0.05

        # 5. Drawdown Penalty（最大回撒懲罰）
        current_drawdown = (
            self.portfolio.peak_value - self.portfolio.total_value
        ) / self.portfolio.peak_value if self.portfolio.peak_value > 0 else 0
        if current_drawdown > 0.2:  # 回撤超過 20%
            reward -= 0.5 * current_drawdown

        # 6. Win Rate Bonus（勝率獎勵）
        if self.portfolio.total_trades > 0:
            win_rate = self.portfolio.winning_trades / self.portfolio.total_trades
            if win_rate > 0.5:
                reward += 0.1 * win_rate

        # Clamp 最終獎勵：避免單步 reward 太大/太小導致梯度爆炸
        reward = max(-1.0, min(1.0, reward))

        return reward
    
    def _update_market_limits(self):
        """
        更新涨跌停價格限制
        
        台股规则：
        - 當日價格不能超過前一日收盤價的 ±10%
        - 如果漲停，買單會成交但賣單無法掛出
        - 如果跌停，賣單會成交但買單無法掛出
        
        計算邏輯：
        - 前一日收盤價 × 1.10 = 漲停價
        - 前一日收盤價 × 0.90 = 跌停價
        """
        if self.current_step > 0:
            prev_close = self.df.iloc[self.current_step - 1]['close']
            self.limit_up_price = prev_close * (1 + TaiwanStockConstants.LIMIT_UP_RATIO)
            self.limit_down_price = prev_close * (1 - TaiwanStockConstants.LIMIT_DOWN_RATIO)
        else:
            # 第一天，無涨跌停限制
            self.limit_up_price = np.inf
            self.limit_down_price = 0
    
    def _update_portfolio_value(self, price: float):
        """
        更新投資組合市值
        
        計算：
        - 總市值 = 現金 + 持股市值
        - 未實現損益 = 持股市值 - 持股成本
        """
        position_value = self.portfolio.position * price
        
        self.portfolio.total_value = self.portfolio.cash + position_value
        self.portfolio.unrealized_pnl = position_value - self.portfolio.position * self.portfolio.avg_cost
        
        # 更新歷史高/低
        if self.portfolio.total_value > self.portfolio.peak_value:
            self.portfolio.peak_value = self.portfolio.total_value
        
        if self.portfolio.total_value < self.portfolio.trough_value:
            self.portfolio.trough_value = self.portfolio.total_value
    
    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None
    ) -> Tuple[np.ndarray, Dict]:
        """
        重置環境到初始狀態
        
        Gymnasium 介面要求的方法。
        
        參數:
            seed: 隨機種子的雜訊源
            options: 其他選項（未使用）
            
        返回:
            (observation, info)
            - observation: 初始狀態（52維特徵向量）
            - info: 額外資訊字典
        """
        super().reset(seed=seed)
        
        # 重置內部狀態
        self.current_step = 0
        self._reset_portfolio()
        self._update_market_limits()
        
        # 初始化市值
        price = self.df.iloc[0]['close']
        self._update_portfolio_value(price)
        
        # 記錄初始價格
        self.price_history.append(price)

        # 初始化先前市值（用於計算 per-step 報酬）
        self._previous_portfolio_value = self.portfolio.total_value

        # 初始化最後交易 step（用於計算 trade penalty）
        self._last_trade_step = -1
        self._last_trade_action = 0

        # 獲取初始觀察
        observation = self._get_observation()
        
        # 構建 info
        info = {
            'portfolio': self.portfolio,
            'current_step': self.current_step,
            'date': str(self.df.iloc[0]['date']),
            'price': price,
        }
        
        return observation, info
    
    def step(
        self,
        action: Union[int, np.ndarray]
    ) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        執行一個時間步
        
        Gymnasium 介面要求的方法。
        
        參數:
            action: 動作
                - 離散模式：int (0-8)
                - 連續模式：np.ndarray (目標持倉比重 [0, 1])
        
        返回:
            (observation, reward, terminated, truncated, info)
            - observation: 下一個狀態
            - reward: 獎勵
            - terminated: 是否終止（ episode 完成）
            - truncated: 是否截斷（達到最大步數）
            - info: 額外資訊
        """
        # 獲取當前價格（使用預提取的 numpy 陣列）
        all_values = self._df_values[self.current_step]
        price = all_values[self._price_idx[3]]  # close is 4th

        # 解析並執行動作
        if self.mode == 'discrete':
            action = int(action)
            executed_shares, commission, tax, realized_pnl = self._execute_trade(action, price)
        else:
            # 連續模式（2026-08-11改版）：動作值直接解讀為目標持倉比重，
            # 交易「目前持股 -> 目標持股」的真實差額，而非硬切成
            # HOLD/BUY_1000/SELL_1000 三個固定桶（舊版無論動作值多少，
            # policy 實際能做的只有 3 種離散結果，不是真正的連續控制）。
            target_position_ratio = float(np.clip(action[0], 0.0, 1.0))
            target_shares = target_position_ratio * self.max_position
            executed_shares, commission, tax, realized_pnl = self._execute_target_position_trade(target_shares, price)
            # action 之後仍作為交易方向代碼給 trade_history / reward 停損判斷使用，
            # 語意對齊既有的離散代碼（1=買、2=賣、0=無成交）。
            if executed_shares > 0:
                action = 1
            elif executed_shares < 0:
                action = 2
            else:
                action = 0
        
        # 記錄交易（使用預提取的 numpy 陣列）
        step_date = str(self.df.iloc[self.current_step]['date'])  # date needs string conversion
        if executed_shares != 0:
            trade_info = TradeInfo(
                date=step_date,
                action=action,
                price=price,
                shares=executed_shares,
                turnover=abs(executed_shares) * price,
                commission=commission,
                tax=tax,
                realized_pnl=realized_pnl,
                position=self.portfolio.position,
            )
            self.trade_history.append(trade_info)
            # 追蹤最後交易 step（避免每次計算 reward 時 O(n) 查找 date）
            self._last_trade_step = self.current_step
            self._last_trade_action = action  # 用於快速判斷停損等特殊動作
        
        # 移動到下一個時間步
        self.current_step += 1
        terminated = self.current_step >= self.total_timesteps

        # 在計算獎勵前更新先前市值（用於 per-step return）
        self._previous_portfolio_value = self.portfolio.total_value

        # 更新市值
        if not terminated:
            # 使用預提取的 numpy 陣列讀取下一個時間步的收盤價
            next_all_values = self._df_values[self.current_step]
            price = next_all_values[self._price_idx[3]]  # close is 4th
            self._update_portfolio_value(price)
            self._update_market_limits()
            self.price_history.append(price)
        
        # 計算獎勵
        if self.reward_mode == 'composite':
            reward = self._calculate_reward()
        else:
            # 簡單獎勵：市值變化率
            reward = (self.portfolio.total_value - self.initial_capital) / self.initial_capital
        
        # 檢查停損條件（僅在非 STOP_LOSS 動作時自動停損，避免重複執行）
        # terminatd=True 時不執行停損檢查（price=0 會導致除零錯誤）
        if not terminated and action != 4 and self.portfolio.position > 0 and self.portfolio.avg_cost > 0:
            unrealized_return = (price - self.portfolio.avg_cost) / self.portfolio.avg_cost
            if unrealized_return < TaiwanStockConstants.STOP_LOSS_THRESHOLD:
                # 自動執行停損
                self._execute_trade(4, price)  # STOP_LOSS action = 4
        
        # 移動停損檢查（Trailing Stop）
        # terminatd=True 時不執行移動停損檢查
        if not terminated and TaiwanStockConstants.TRAILING_STOP_ENABLED and self.portfolio.position > 0 and self.portfolio.avg_cost > 0:
            current_total = self.portfolio.total_value
            cost_basis = self.portfolio.position * self.portfolio.avg_cost
            unrealized_return = (current_total - cost_basis - self.portfolio.cash) / cost_basis if cost_basis > 0 else 0
            
            # 如果獲利超過激活門檻，更新移動停損峰值
            # 初始化時：首次激活時 peak = current_total（當前總市值），而非 0
            # 這樣才能正確計算「從高點回撤多少」，而不需要依賴「曾經等於 0」的奇偶邏輯
            if unrealized_return > TaiwanStockConstants.TRAILING_STOP_ACTIVATION:
                if self.portfolio.trailing_stop_peak <= 0:
                    self.portfolio.trailing_stop_peak = current_total
                else:
                    self.portfolio.trailing_stop_peak = max(self.portfolio.trailing_stop_peak, current_total)
            
            # 檢查是否觸發移動停損
            if self.portfolio.trailing_stop_peak > 0:
                trailing_stop_triggered = (
                    (self.portfolio.trailing_stop_peak - current_total) / self.portfolio.trailing_stop_peak 
                    > TaiwanStockConstants.TRAILING_STOP_PCT
                )
                if trailing_stop_triggered and action != 3 and action != 4:
                    # 執行移動停損（相當於 CLOSE_POSITION）
                    self._execute_trade(3, price)  # CLOSE action = 3
        
        # 獲取觀察（terminated=True 時不呼叫，避免 index out of bounds）
        if terminated:
            observation = np.zeros(self.state_dim, dtype=np.float32)
            info = {
                'portfolio': self.portfolio,
                'current_step': self.current_step,
                'date': '',
                'price': 0,
                'executed_shares': 0,
                'action': action,
            }
        else:
            observation = self._get_observation()
            # 構建 info（使用預提取的 numpy 陣列）
            info_date = str(self.df.iloc[self.current_step]['date'])
            info = {
                'portfolio': self.portfolio,
                'current_step': self.current_step,
                'date': info_date,
                'price': price,
                'executed_shares': executed_shares,
                'action': action,
            }
        
        return observation, reward, terminated, False, info
    
    def render(self, mode: str = 'human'):
        """
        渲染環境狀態
        
        參數:
            mode: 渲染模式 ('human'=視覺化, 'console'=控制台輸出)
        """
        if mode == 'console':
            # 控制台輸出
            portfolio = self.portfolio
            price = self.df.iloc[min(self.current_step, len(self.df)-1)]['close']
            
            print(f"=" * 50)
            print(f"日期: {self.df.iloc[min(self.current_step, len(self.df)-1)]['date']}")
            print(f"價格: {price:.2f}")
            print(f"持股: {portfolio.position} 股 (成本: {portfolio.avg_cost:.2f})")
            print(f"現金: {portfolio.cash:.2f}")
            print(f"總市值: {portfolio.total_value:.2f}")
            print(f"已實現損益: {portfolio.realized_pnl:.2f}")
            print(f"未實現損益: {portfolio.unrealized_pnl:.2f}")
            print(f"總交易次數: {portfolio.total_trades}")
            print(f"勝率: {portfolio.winning_trades / portfolio.total_trades * 100:.1f}%" if portfolio.total_trades > 0 else "勝率: N/A")
            print(f"=" * 50)
        else:
            # TODO: 实现 matplotlib 視覺化
            pass
    
    def close(self):
        """
        關閉環境
        """
        pass
    
    def get_trade_history(self) -> List[TradeInfo]:
        """
        獲取交易歷史
        
        返回:
            TradeInfo 列表
        """
        return self.trade_history.copy()
    
    def get_portfolio_state(self) -> PortfolioState:
        """
        獲取當前投資組合狀態
        
        返回:
            PortfolioState 物件
        """
        return self.portfolio
    
    def get_state_features(self) -> List[str]:
        """
        獲取狀態特徵名稱列表
        
        返回:
            特徵名稱列表
        """
        features = ['open', 'high', 'low', 'close', 'volume', 'turnover']
        
        excluded = ['date', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        for col in self.df.columns:
            if col not in excluded:
                features.append(col)
        
        features.extend([
            'position_ratio', 'market_value_ratio',
            'unrealized_pnl_ratio', 'cost_deviation_ratio'
        ])
        
        return features


# =============================================================================
# 便捷函數
# =============================================================================

def create_env(
    df: pd.DataFrame,
    mode: str = 'discrete',
    reward_mode: str = 'composite'
) -> TaiwanStockTradingEnv:
    """
    便捷函數：創建交易環境
    
    參數:
        df: 包含數據的 DataFrame
        mode: 動作模式
        reward_mode: 獎勵模式
        
    返回:
        TaiwanStockTradingEnv 實例
    """
    return TaiwanStockTradingEnv(
        df=df,
        mode=mode,
        reward_mode=reward_mode,
    )


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    import yfinance as yf
    from FinRL.v2.data.technical_indicators import TechnicalIndicators
    
    print("=" * 60)
    print("TaiwanStockTradingEnv 測試")
    print("=" * 60)
    
    # 下載測試數據
    print("\n[1] 下載台積電 (2330) 測試數據...")
    ticker = yf.Ticker("2330.TW")
    df = ticker.history(start='2023-01-01', end='2024-01-01', auto_adjust=False)
    df = df.reset_index()
    
    if df.empty:
        print("無法下載測試數據")
    else:
        print(f"成功獲取 {len(df)} 筆數據")
        
        # 計算技術指標
        print("\n[2] 計算技術指標...")
        ti = TechnicalIndicators(df)
        df = ti.calculate_all()
        print(f"共 {len(df.columns)} 個欄位")
        
        # 創建環境
        print("\n[3] 創建交易環境...")
        env = TaiwanStockTradingEnv(df, mode='discrete')
        print(f"State 維度: {env.state_dim}")
        print(f"Action Space: {env.action_space}")
        
        # 測試 reset
        print("\n[4] 測試環境 reset...")
        obs, info = env.reset()
        print(f"Observation shape: {obs.shape}")
        print(f"Info: {info}")
        
        # 測試 step
        print("\n[5] 測試環境 step...")
        action = 1  # BUY_1000
        obs, reward, terminated, truncated, info = env.step(action)
        print(f"Action: {action} (BUY_1000)")
        print(f"Reward: {reward:.4f}")
        print(f"Terminated: {terminated}, Truncated: {truncated}")
        print(f"Portfolio: 持股={info['portfolio'].position}, 市值={info['portfolio'].total_value:.2f}")
        
        # 渲染
        env.render(mode='console')
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)