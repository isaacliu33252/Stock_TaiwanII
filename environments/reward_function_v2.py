"""
RewardFunction - 增強版獎勵函數
================================================================================
v2.0 改善：
1. 加入 Sortino Ratio（只計算下行風險）
2. 加入 Calmar Ratio 獎勵
3. 增強 MDD 懲罰
4. 加入波動度懲罰
5. 動態調整懲罰權重

作者: FinRL量化交易專家（改進版）
"""

import numpy as np
from typing import Dict, Optional, List, Tuple


class RewardFunction:
    """
    增強版複合獎勵函數計算器
    
    新增：
    - Sortino Ratio 獎勵
    - Calmar Ratio 獎勵  
    - 市場波動度懲罰
    - 動態權重調整
    """
    
    def __init__(
        self,
        # 基本參數
        trade_penalty: float = 0.001,
        stop_loss_penalty: float = 0.05,
        drawdown_penalty: float = 0.5,
        holding_bonus: float = 0.1,
        win_rate_bonus: float = 0.1,
        risk_free_rate: float = 0.02,
        # 新增參數
        sortino_weight: float = 0.2,      # Sortino 獎勵權重
        calmar_weight: float = 0.15,    # Calmar 獎勵權重
        volatility_penalty: float = 0.1, # 波動度懲罰
        min_trade_reward: float = 0.005, # 最低交易獎勵（避免零交易）
    ):
        self.trade_penalty = trade_penalty
        self.stop_loss_penalty = stop_loss_penalty
        self.drawdown_penalty = drawdown_penalty
        self.holding_bonus = holding_bonus
        self.win_rate_bonus = win_rate_bonus
        self.risk_free_rate = risk_free_rate
        # 新增
        self.sortino_weight = sortino_weight
        self.calmar_weight = calmar_weight
        self.volatility_penalty = volatility_penalty
        self.min_trade_reward = min_trade_reward
        
        # 內部狀態
        self._returns_history: List[float] = []
        self._portfolio_peak: float = 0.0
    
    def reset(self):
        """重置內部狀態"""
        self._returns_history = []
        self._portfolio_peak = 0.0
    
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
        daily_return: Optional[float] = None,
        # 新增參數
        volatility: Optional[float] = None,  # 已實現波動度
        current_step: int = 0,
    ) -> Tuple[float, Dict]:
        """
        計算增強版複合獎勵
        
        新增回傳：
        - sortino_bonus: Sortino Ratio 相關獎勵
        - calmar_bonus: Calmar Ratio 相關獎勵
        - volatility_penalty: 波動度懲罰
        """
        rewards = {}
        
        # =====================================================================
        # 1. 資本報酬 (核心獎勵)
        # =====================================================================
        value_change = portfolio_value - previous_portfolio_value
        if previous_portfolio_value > 1.0:
            portfolio_return = value_change / previous_portfolio_value
        else:
            portfolio_return = 0.0
        # clamp: 單步報酬不超過 ±10%
        portfolio_return = np.clip(portfolio_return, -0.10, 0.10)
        rewards['capital'] = portfolio_return
        
        # 記錄歷史報酬（用於計算 Sortino）
        self._returns_history.append(portfolio_return)
        if len(self._returns_history) > 252:  # 只保留一年
            self._returns_history = self._returns_history[-252:]
        
        # =====================================================================
        # 2. Sortino Ratio 獎勵（新增）
        # =====================================================================
        rewards['sortino'] = 0.0
        if len(self._returns_history) >= 20:
            sortino = self._calculate_sortino_ratio(np.array(self._returns_history))
            # 正向 Sortino 給獎勵，負向給懲罰
            rewards['sortino'] = np.clip(sortino * self.sortino_weight * 0.01, -0.1, 0.1)
        
        # =====================================================================
        # 3. Calmar Ratio 獎勵（新增）
        # =====================================================================
        rewards['calmar'] = 0.0
        if max_drawdown > 0 and portfolio_return > 0:
            # Calmar = 年化報酬 / MDD
            annual_return = portfolio_return * 252
            calmar = annual_return / max_drawdown
            rewards['calmar'] = np.clip(calmar * self.calmar_weight * 0.01, -0.05, 0.05)
        elif max_drawdown > 0 and portfolio_return < 0:
            # 虧損且MDD大，懲罰
            rewards['calmar'] = -0.02
        
        # =====================================================================
        # 4. 持有獎勵
        # =====================================================================
        rewards['holding'] = 0.0
        if position > 0 and action == 0 and avg_cost > 0:
            unrealized_pnl = (close_price - avg_cost) / avg_cost
            unrealized_pnl = np.clip(unrealized_pnl, -1.0, 1.0)
            if unrealized_pnl > 0:
                rewards['holding'] = unrealized_pnl * self.holding_bonus
        
        # =====================================================================
        # 5. 交易懲罰（增強：加入最低獎勵避免不交易）
        # =====================================================================
        rewards['trade'] = 0.0
        if action in [1, 2]:  # BUY or SELL
            rewards['trade'] = -self.trade_penalty
        
        # 檢查是否太久沒交易（超過 20 步）
        if current_step > 20 and len(trade_history) == 0:
            rewards['inactivity'] = -self.min_trade_reward  # 處罰不作為
        
        # =====================================================================
        # 6. 停損懲罰
        # =====================================================================
        rewards['stop_loss'] = 0.0
        if action == 4:  # STOP_LOSS
            rewards['stop_loss'] = -self.stop_loss_penalty
        
        # =====================================================================
        # 7. 勝率獎勵
        # =====================================================================
        rewards['win_rate'] = 0.0
        if len(trade_history) > 0:
            wins = sum(1 for t in trade_history if t.get('pnl', 0) > 0)
            win_rate = wins / len(trade_history)
            rewards['win_rate'] = (win_rate - 0.5) * self.win_rate_bonus
        
        # =====================================================================
        # 8. 最大回撤懲罰（增強）
        # =====================================================================
        rewards['drawdown'] = 0.0
        # 基礎 MDD 懲罰
        rewards['drawdown'] = -max_drawdown * self.drawdown_penalty
        
        # 額外：如果 MDD 超過 20%，加大懲罰
        if max_drawdown > 0.20:
            rewards['drawdown'] -= 0.05  # 額外懲罰
        elif max_drawdown > 0.30:
            rewards['drawdown'] -= 0.10
        
        # =====================================================================
        # 9. 波動度懲罰（新增）
        # =====================================================================
        rewards['volatility'] = 0.0
        if volatility is not None and volatility > 0:
            # 波動度超過 30% 年化認為是高風險
            if volatility > 0.30:
                rewards['volatility'] = -self.volatility_penalty
            # 或者與歷史平均比較
            elif len(self._returns_history) >= 20:
<<<<<<< HEAD
                hist_vol = np.std(self._returns_history) * np.sqrt(252)
=======
                hist_vol = np.std(self._returns_history, ddof=1) * np.sqrt(252)
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
                if volatility > hist_vol * 1.5:
                    rewards['volatility'] = -self.volatility_penalty * 0.5
        
        # =====================================================================
        # 10. 台股涨跌停 Bonus/Penalty
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
        # 計算總獎勵
        # =====================================================================
        total_reward = sum(rewards.values())
        total_reward = np.clip(total_reward, -1.0, 1.0)
        
        return total_reward, rewards
    
    def _calculate_sortino_ratio(self, returns: np.ndarray, target: float = 0.0) -> float:
        """
        計算 Sortino Ratio
        
        Sortino = (平均報酬 - 目標報酬) / 下行標準差
        """
        if len(returns) < 2:
            return 0.0
        
        mean_ret = np.mean(returns)
        downside_returns = returns[returns < target]
        
        if len(downside_returns) == 0:
            return 0.0
        
<<<<<<< HEAD
        downside_std = np.std(downside_returns)
=======
        downside_std = np.std(downside_returns, ddof=1)
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        if downside_std == 0:
            return 0.0
        
        sortino = (mean_ret - target) / downside_std
        # 年化
        return sortino * np.sqrt(252)
    
    def calculate_sharpe(self, returns: np.ndarray, risk_free_rate: Optional[float] = None) -> float:
        """計算 Sharpe Ratio"""
        if risk_free_rate is None:
            risk_free_rate = self.risk_free_rate
        
        if len(returns) < 2:
            return 0.0
        
        daily_rf = risk_free_rate / 252
        excess_return = returns - daily_rf
        mean_excess = np.mean(excess_return)
<<<<<<< HEAD
        std_excess = np.std(excess_return)
=======
        std_excess = np.std(excess_return, ddof=1)
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        
        if std_excess == 0:
            return 0.0
        
        return (mean_excess / std_excess) * np.sqrt(252)
    
    def calculate_sortino(self, returns: np.ndarray, target_return: float = 0.0) -> float:
        """計算 Sortino Ratio（包裝）"""
        return self._calculate_sortino_ratio(np.array(returns), target_return)


# =============================================================================
# 便捷函數
# =============================================================================

def enhanced_reward(
    portfolio_value: float,
    previous_portfolio_value: float,
    max_drawdown: float,
    **kwargs
) -> Tuple[float, Dict]:
    """
    增強版獎勵的便捷調用函數
    """
    reward_func = RewardFunction()
    return reward_func.calculate(
        portfolio_value=portfolio_value,
        previous_portfolio_value=previous_portfolio_value,
        position=kwargs.get('position', 0),
        close_price=kwargs.get('close_price', 0),
        avg_cost=kwargs.get('avg_cost', 0),
        action=kwargs.get('action', 0),
        max_drawdown=max_drawdown,
        trade_history=kwargs.get('trade_history', []),
        previous_close=kwargs.get('previous_close'),
        current_step=kwargs.get('current_step', 0),
    )