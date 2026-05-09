"""
RewardFunction - 複合獎勵函數
================================================================================
定義 RL 環境的獎勵計算邏輯。

獎勵函數設計原則:
1. 資本報酬: 核心獎勵信號，反映策略的獲利能力
2. 風險懲罰: 惩罚过度交易、最大回撤等不良行为
3. 持有獎勵: 鼓勵適當持有，避免過度交易
4. 台股特殊: 涨跌停 bonus/penalty

複合獎勵公式:
    total_reward = capital_reward + holding_bonus + trade_penalty 
                 + stop_loss_penalty + drawdown_penalty + win_rate_bonus
                 + limit_up_down_bonus

作者: FinRL量化交易專家
"""

import numpy as np
from typing import Dict, Optional, List, Tuple


class RewardFunction:
    """
    複合獎勵函數計算器
    
    Attributes:
        trade_penalty: 交易懲罰係數 (避免過度交易)
        stop_loss_penalty: 停損懲罰係數
        drawdown_penalty: 回撤懲罰係數
        holding_bonus: 持有獎勵係數
        risk_free_rate: 無風險利率 (年化)
    
    Example:
        >>> reward_func = RewardFunction()
        >>> reward = reward_func.calculate(
        ...     portfolio_value=1_050_000,
        ...     previous_portfolio_value=1_000_000,
        ...     position=2000,
        ...     close_price=650.0,
        ...     avg_cost=640.0,
        ...     action=0,
        ...     trade_history=[]
        ... )
    """
    
    def __init__(
        self,
        trade_penalty: float = 0.001,
        stop_loss_penalty: float = 0.05,
        drawdown_penalty: float = 0.5,
        holding_bonus: float = 0.1,
        win_rate_bonus: float = 0.1,
        risk_free_rate: float = 0.02
    ):
        """
        初始化獎勵函數
        
        Args:
            trade_penalty: 每次交易懲罰 (避免過度交易)
            stop_loss_penalty: 停損懲罰係數
            drawdown_penalty: 最大回撒懲罰係數
            holding_bonus: 持有獲利獎勵係數
            win_rate_bonus: 勝率獎勵係數
            risk_free_rate: 年化無風險利率 (用於 Sharpe Ratio)
        """
        self.trade_penalty = trade_penalty
        self.stop_loss_penalty = stop_loss_penalty
        self.drawdown_penalty = drawdown_penalty
        self.holding_bonus = holding_bonus
        self.win_rate_bonus = win_rate_bonus
        self.risk_free_rate = risk_free_rate
    
    def calculate(
        self,
        portfolio_value: float,
        previous_portfolio_value: float,
        position: int,
        close_price: float,
        avg_cost: float,
        action: int,
        max_drawdown: float,
        trade_history: List[Dict],
        previous_close: Optional[float] = None,
        daily_return: Optional[float] = None
    ) -> Tuple[float, Dict]:
        """
        計算複合獎勵
        
        Args:
            portfolio_value: 目前投資組合總值
            previous_portfolio_value: 前一日投資組合總值
            position: 目前持股數量
            close_price: 收盤價
            avg_cost: 平均成本
            action: 執行的動作 (0-4)
            max_drawdown: 目前最大回撒
            trade_history: 交易歷史 [{'pnl': float, 'date': str}, ...]
            previous_close: 前日收盤價 (用於涨跌停計算)
            daily_return: 日報酬率
        
        Returns:
            (total_reward, reward_breakdown)
            - total_reward: 總獎勵值
            - reward_breakdown: 各項獎勵分解字典
        """
        rewards = {}
        
        # =====================================================================
        # 1. 資本報酬 (核心獎勵) — 關鍵：安全計算 + clamp
        # =====================================================================
        value_change = portfolio_value - previous_portfolio_value
        # 預防除零或初始 value 極小
        if previous_portfolio_value > 1.0:
            portfolio_return = value_change / previous_portfolio_value
        else:
            portfolio_return = 0.0
        # clamp: 單步報酬不超過 ±10%，避免 NaN/inf 傳播
        portfolio_return = max(-0.10, min(0.10, portfolio_return))
        rewards['capital'] = portfolio_return  # 不再 *100，直接用小幅值
        
        # =====================================================================
        # 2. 持有獎勵 (減少過度交易)
        # =====================================================================
        rewards['holding'] = 0.0
        if position > 0 and action == 0 and avg_cost > 0:
            unrealized_pnl = (close_price - avg_cost) / avg_cost
            # clamp unrealized pnl
            unrealized_pnl = max(-1.0, min(1.0, unrealized_pnl))
            if unrealized_pnl > 0:
                rewards['holding'] = unrealized_pnl * self.holding_bonus
        
        # =====================================================================
        # 3. 交易懲罰 (避免過度交易)
        # =====================================================================
        rewards['trade'] = 0.0
        if action in [1, 2]:  # BUY or SELL
            rewards['trade'] = -self.trade_penalty
        
        # =====================================================================
        # 4. 停損懲罰 (控制風險)
        # =====================================================================
        rewards['stop_loss'] = 0.0
        if action == 4:  # STOP_LOSS
            rewards['stop_loss'] = -self.stop_loss_penalty
        
        # =====================================================================
        # 5. 勝率獎勵 (鼓勵正向期望策略)
        # =====================================================================
        rewards['win_rate'] = 0.0
        if len(trade_history) > 0:
            wins = sum(1 for t in trade_history if t.get('pnl', 0) > 0)
            win_rate = wins / len(trade_history)
            rewards['win_rate'] = (win_rate - 0.5) * self.win_rate_bonus
        
        # =====================================================================
        # 6. 最大回撒懲罰 (風險控制)
        # =====================================================================
        rewards['drawdown'] = -max_drawdown * self.drawdown_penalty
        
        # =====================================================================
        # 7. 台股涨跌停 Bonus/Penalty
        # =====================================================================
        rewards['limit_up_down'] = 0.0
        if previous_close is not None and previous_close > 0 and position > 0:
            daily_change = (close_price - previous_close) / previous_close
            if abs(daily_change) >= 0.095:
                if daily_change > 0:
                    rewards['limit_up_down'] = 0.02
                else:
                    rewards['limit_up_down'] = -0.02
        
        # =====================================================================
        # 計算總獎勵 — clamp 最終輸出
        # =====================================================================
        total_reward = sum(rewards.values())
        # clamp 總獎勵，避免單步 reward 太大/太小導致梯度爆炸
        total_reward = max(-1.0, min(1.0, total_reward))
        
        return total_reward, rewards
    
    def calculate_sharpe(
        self,
        returns: np.ndarray,
        risk_free_rate: Optional[float] = None
    ) -> float:
        """
        計算 Sharpe Ratio (用於評估)
        
        Sharpe Ratio = (平均報酬 - 無風險利率) / 報酬標準差
        
        Args:
            returns: 報酬率陣列
            risk_free_rate: 無風險利率 (若為 None，使用預設值)
        
        Returns:
            Sharpe Ratio
        """
        if risk_free_rate is None:
            risk_free_rate = self.risk_free_rate
        
        if len(returns) < 2:
            return 0.0
        
        # 日化無風險利率
        daily_rf = risk_free_rate / 252
        
        # 計算 excess return
        excess_return = returns - daily_rf
        
        # 計算 Sharpe Ratio (使用 sample std, ddof=1)
        mean_excess = np.mean(excess_return)
        std_excess = np.std(excess_return, ddof=1)
        
        if std_excess == 0:
            return 0.0
        
        sharpe = mean_excess / std_excess
        
        # 年化 Sharpe Ratio
        sharpe_annualized = sharpe * np.sqrt(252)
        
        return sharpe_annualized
    
    def calculate_sortino(
        self,
        returns: np.ndarray,
        target_return: float = 0.0
    ) -> float:
        """
        計算 Sortino Ratio (只用於下行風險)
        
        Sortino Ratio = (平均報酬 - 目標報酬) / 下行標準差
        
        Args:
            returns: 報酬率陣列
            target_return: 目標報酬率
        
        Returns:
            Sortino Ratio
        """
        if len(returns) < 2:
            return 0.0
        
        # 計算下行偏離
        downside_returns = returns[returns < target_return]
        
        if len(downside_returns) == 0:
            return 0.0
        
        mean_return = np.mean(returns)
        downside_std = np.std(downside_returns, ddof=1)
        
        if downside_std == 0:
            return 0.0
        
        sortino = (mean_return - target_return) / downside_std
        
        # 年化
        sortino_annualized = sortino * np.sqrt(252)
        
        return sortino_annualized


# =============================================================================
# 便捷函數
# =============================================================================

def simple_reward(
    portfolio_value: float,
    previous_portfolio_value: float
) -> float:
    """
    簡單獎勵函數 (只用於快速測試)
    
    僅使用資本報酬作為獎勵
    
    Args:
        portfolio_value: 目前投資組合總值
        previous_portfolio_value: 前一日投資組合總值
    
    Returns:
        簡單獎勵值
    """
    return (portfolio_value - previous_portfolio_value) / previous_portfolio_value


def sharpe_based_reward(
    returns: np.ndarray,
    risk_free_rate: float = 0.02
) -> float:
    """
    Sharpe Ratio 基於的獎勵 (用於 Portfolio 任務)
    
    Args:
        returns: 歷史報酬率陣列
        risk_free_rate: 年化無風險利率
    
    Returns:
        複合 Sharpe Ratio 獎勵
    """
    reward_func = RewardFunction(risk_free_rate=risk_free_rate)
    return reward_func.calculate_sharpe(returns, risk_free_rate)
