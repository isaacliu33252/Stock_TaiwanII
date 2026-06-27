"""
================================================================================
RewardFunction - 複合獎勵函數模組 (v2新版)
================================================================================
定義 RL 訓練的獎勵函數，支援多種獎勵模式。

獎勵組成：
    1. capital_reward: 投資組合市值變化率（主要獎勵）
    2. holding_bonus: 持有獲利部位的 bonus
    3. trade_penalty: 交易懲罰（避免過度交易）
    4. stop_loss_penalty: 停損懲罰
    5. drawdown_penalty: 最大回撒懲罰
    6. win_rate_bonus: 勝率獎勵
    7: limit_up_down_bonus: 涨跌停額外獎勵/懲罰

設計原則：
    - 獎勵應該平滑，避免大幅跳躍
    - 懲罰應該適度，避免模型過於保守
    - 獎勵應該與實際交易績效相關

台股特殊規則：
    - 涨跌停限制: ±10%
    - T+2 交割制度
    - 最小交易單位: 1000 股

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np


# =============================================================================
# 獎勵配置
# =============================================================================

@dataclass
class RewardConfig:
    """
    獎勵函數配置
    
    用於配置各項獎勵權重和參數。
    """
    # 主要獎勵權重
    capital_reward_weight: float = 100.0      # 資本回報獎勵權重
    holding_bonus_weight: float = 0.1        # 持有獲利部位 bonus
    trade_penalty_weight: float = 0.001      # 交易懲罰
    stop_loss_penalty_weight: float = 0.05   # 停損懲罰
    drawdown_penalty_weight: float = 0.5     # 最大回撒懲罰
    win_rate_bonus_weight: float = 0.1       # 勝率獎勵
    limit_up_down_bonus: float = 0.0         # 涨跌停 bonus
    
    # 閾值參數
    stop_loss_threshold: float = -0.05       # 停損門檻（-5%）
    drawdown_threshold: float = 0.2          # 回撒懲罰門檻（20%）
    max_position: int = 40000               # 最大持股數


@dataclass
class TradingMetrics:
    """
    交易指標 dataclass
    
    用於追蹤一段時間內的交易指標。
    """
    portfolio_value: float = 0.0            # 投資組合市值
    cash: float = 0.0                        # 現金
    position: int = 0                        # 持股數
    avg_cost: float = 0.0                    # 平均成本
    total_trades: int = 0                    # 總交易次數
    winning_trades: int = 0                  # 獲利交易次數
    losing_trades: int = 0                   # 虧損交易次數
    peak_value: float = 0.0                  # 歷史最高市值
    trough_value: float = 0.0               # 歷史最低市值
    last_trade_date: Optional[int] = None    # 上次交易時間步
    consecutive_wins: int = 0                # 連續獲利次數
    consecutive_losses: int = 0              # 連續虧損次數


# =============================================================================
# 複合獎勵函數
# =============================================================================

class RewardFunction:
    """
    複合獎勵函數類別
    
    計算 RL 環境的獎勵信號。
    獎勵由多個組件組成，權重可配置。
    
    使用範例:
        >>> config = RewardConfig()
        >>> reward_func = RewardFunction(config)
        >>> 
        >>> # 在 RL step 後計算獎勵
        >>> reward = reward_func.calculate(
        ...     current_metrics=metrics,
        ...     action=action,
        ...     price=price
        ... )
    """
    
    def __init__(self, config: RewardConfig = None):
        """
        初始化獎勵函數
        
        參數:
            config: 獎勵配置，若為 None 則使用預設配置
        """
        self.config = config or RewardConfig()
        self.metrics_history: List[TradingMetrics] = []
    
    def calculate(
        self,
        current_metrics: TradingMetrics,
        action: int = 0,
        prev_metrics: TradingMetrics = None
    ) -> Tuple[float, Dict]:
        """
        計算複合獎勵
        
        參數:
            current_metrics: 當前交易指標
            action: 執行的動作
            prev_metrics: 前一步的交易指標（用於計算變化）
            
        返回:
            (reward, details)
            - reward: 複合獎勵值
            - details: 各獎勵組成的詳細字典
        """
        details = {}
        
        # 初始化前一步指標（如果是第一個時間步）
        if prev_metrics is None:
            prev_metrics = current_metrics
        
        # =========================================================================
        # 1. Capital Reward（資本回報獎勵）- 主要獎勵
        # =========================================================================
        # 計算相對於初始資本的回報率
        initial_capital = 1_000_000
        portfolio_return = (current_metrics.portfolio_value - initial_capital) / initial_capital
        capital_reward = portfolio_return * self.config.capital_reward_weight
        details['capital_reward'] = capital_reward
        
        # =========================================================================
        # 2. Holding Bonus（持有獲利部位的 bonus）
        # =========================================================================
        holding_bonus = 0.0
        if current_metrics.position > 0 and current_metrics.avg_cost > 0:
            unrealized_return = (current_metrics.portfolio_value - current_metrics.position * current_metrics.avg_cost
                               - current_metrics.cash) / (current_metrics.position * current_metrics.avg_cost)
            if unrealized_return > 0:
                # 持有獲利部位，給予小額 bonus
                holding_bonus = self.config.holding_bonus_weight
        details['holding_bonus'] = holding_bonus
        
        # =========================================================================
        # 3. Trade Penalty（交易懲罰）- 避免過度交易
        # =========================================================================
        trade_penalty = 0.0
        if current_metrics.last_trade_date is not None:
            time_since_trade = len(self.metrics_history) - current_metrics.last_trade_date
            if time_since_trade < 5:  # 最近5個時間步內有交易
                trade_penalty = -self.config.trade_penalty_weight
        details['trade_penalty'] = trade_penalty
        
        # =========================================================================
        # 4. Stop Loss Penalty（停損懲罰）
        # =========================================================================
        stop_loss_penalty = 0.0
        if action == 4:  # STOP_LOSS
            stop_loss_penalty = -self.config.stop_loss_penalty_weight
        details['stop_loss_penalty'] = stop_loss_penalty
        
        # =========================================================================
        # 5. Drawdown Penalty（最大回撒懲罰）
        # =========================================================================
        drawdown_penalty = 0.0
        if current_metrics.peak_value > 0:
            current_drawdown = (current_metrics.peak_value - current_metrics.portfolio_value) / current_metrics.peak_value
            if current_drawdown > self.config.drawdown_threshold:
                # 回撤超過門檻，給予懲罰
                drawdown_penalty = -self.config.drawdown_penalty_weight * current_drawdown
        details['drawdown_penalty'] = drawdown_penalty
        
        # =========================================================================
        # 6. Win Rate Bonus（勝率獎勵）
        # =========================================================================
        win_rate_bonus = 0.0
        if current_metrics.total_trades > 0:
            win_rate = current_metrics.winning_trades / current_metrics.total_trades
            if win_rate > 0.5:  # 勝率超過 50%
                win_rate_bonus = self.config.win_rate_bonus_weight * win_rate
        details['win_rate_bonus'] = win_rate_bonus
        
        # =========================================================================
        # 7. Limit Up/Down Bonus（涨跌停 bonus）
        # =========================================================================
        # 這個需要股價數據來判斷是否涨跌停
        # 在實際實現中，可以從 environment 傳入價格數據
        limit_bonus = 0.0
        details['limit_up_down_bonus'] = limit_bonus
        
        # =========================================================================
        # 計算總獎勵
        # =========================================================================
        total_reward = (
            capital_reward
            + holding_bonus
            + trade_penalty
            + stop_loss_penalty
            + drawdown_penalty
            + win_rate_bonus
            + limit_bonus
        )
        
        details['total_reward'] = total_reward
        
        return total_reward, details
    
    def calculate_simple(
        self,
        current_value: float,
        initial_capital: float = 1_000_000
    ) -> float:
        """
        計算簡單獎勵（市值變化率）
        
        這是複合獎勵的簡化版本，只考慮資本回報。
        
        參數:
            current_value: 當前投資組合市值
            initial_capital: 初始資本
            
        返回:
            獎勵值
        """
        return (current_value - initial_capital) / initial_capital
    
    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02
    ) -> float:
        """
        計算夏普比率
        
        這是一個輔助函數，用於計算歷史報酬的夏普比率。
        
        參數:
            returns: 報酬率列表
            risk_free_rate: 無風險利率（年化）
            
        返回:
            夏普比率
        """
        if len(returns) < 2:
            return 0.0
        
        returns = np.array(returns)
        excess_returns = returns - risk_free_rate / 252  # 日無風險利率
        
        mean_return = np.mean(excess_returns)
        std_return = np.std(excess_returns, ddof=1)
        
        if std_return == 0:
            return 0.0
        
        sharpe = mean_return / std_return * np.sqrt(252)  # 年化夏普比率
        return sharpe


def composite_reward(
    current_metrics: TradingMetrics,
    action: int = 0,
    prev_metrics: TradingMetrics = None,
    config: RewardConfig = None
) -> Tuple[float, Dict]:
    """
    便捷函數：計算複合獎勵
    
    這是 RewardFunction.calculate() 的便捷包裝。
    
    參數:
        current_metrics: 當前交易指標
        action: 執行的動作
        prev_metrics: 前一步的交易指標
        config: 獎勵配置
        
    返回:
        (reward, details)
    """
    if config is None:
        config = RewardConfig()
    
    reward_func = RewardFunction(config)
    return reward_func.calculate(current_metrics, action, prev_metrics)


def calculate_portfolio_metrics(
    cash: float,
    position: int,
    avg_cost: float,
    current_price: float,
    total_trades: int = 0,
    winning_trades: int = 0,
    losing_trades: int = 0,
    peak_value: float = None,
    trough_value: float = None,
    last_trade_date: int = None
) -> TradingMetrics:
    """
    便捷函數：從基本參數計算交易指標
    
    參數:
        cash: 現金
        position: 持股數
        avg_cost: 平均成本
        current_price: 當前價格
        total_trades: 總交易次數
        winning_trades: 獲利交易次數
        losing_trades: 虧損交易次數
        peak_value: 歷史最高市值（若為 None，自動計算）
        trough_value: 歷史最低市值（若為 None，自動計算）
        last_trade_date: 上次交易時間步
        
    返回:
        TradingMetrics 物件
    """
    position_value = position * current_price
    portfolio_value = cash + position_value
    
    # 自動計算歷史高/低
    if peak_value is None:
        peak_value = portfolio_value
    if trough_value is None:
        trough_value = portfolio_value
    
    return TradingMetrics(
        portfolio_value=portfolio_value,
        cash=cash,
        position=position,
        avg_cost=avg_cost,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        peak_value=peak_value,
        trough_value=trough_value,
        last_trade_date=last_trade_date,
    )


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("RewardFunction 測試")
    print("=" * 60)
    
    # 測試獎勵配置
    config = RewardConfig()
    print(f"\n預設獎勵配置:")
    print(f"  - Capital Reward Weight: {config.capital_reward_weight}")
    print(f"  - Holding Bonus Weight: {config.holding_bonus_weight}")
    print(f"  - Trade Penalty Weight: {config.trade_penalty_weight}")
    print(f"  - Stop Loss Penalty Weight: {config.stop_loss_penalty_weight}")
    print(f"  - Drawdown Penalty Weight: {config.drawdown_penalty_weight}")
    
    # 測試獎勵計算
    print(f"\n測試複合獎勵計算:")
    
    # 模擬情境1：市值增加
    metrics1 = calculate_portfolio_metrics(
        cash=1_000_000,
        position=0,
        avg_cost=0,
        current_price=100,
        total_trades=0
    )
    
    reward_func = RewardFunction(config)
    reward1, details1 = reward_func.calculate(metrics1)
    print(f"\n情境1（初始狀態）:")
    print(f"  - Portfolio Value: {metrics1.portfolio_value:.2f}")
    print(f"  - Total Reward: {reward1:.4f}")
    print(f"  - Details: {details1}")
    
    # 模擬情境2：持有獲利部位
    metrics2 = calculate_portfolio_metrics(
        cash=950_000,
        position=10000,
        avg_cost=50,  # 成本50元，現價100元
        current_price=100,
        total_trades=1,
        winning_trades=1
    )
    
    reward2, details2 = reward_func.calculate(metrics2)
    print(f"\n情境2（持有獲利部位）:")
    print(f"  - Portfolio Value: {metrics2.portfolio_value:.2f}")
    print(f"  - Unrealized PnL: {metrics2.portfolio_value - metrics2.cash - metrics2.position * metrics2.avg_cost:.2f}")
    print(f"  - Total Reward: {reward2:.4f}")
    print(f"  - Details: {details2}")
    
    # 模擬情境3：停損
    metrics3 = calculate_portfolio_metrics(
        cash=950_000,
        position=10000,
        avg_cost=55,  # 成本55元，現價50元（虧損）
        current_price=50,
        total_trades=2,
        winning_trades=1,
        losing_trades=1
    )
    
    reward3, details3 = reward_func.calculate(metrics3, action=4)  # STOP_LOSS
    print(f"\n情境3（停損）:")
    print(f"  - Portfolio Value: {metrics3.portfolio_value:.2f}")
    print(f"  - Unrealized PnL: {metrics3.portfolio_value - metrics3.cash - metrics3.position * metrics3.avg_cost:.2f}")
    print(f"  - Total Reward: {reward3:.4f}")
    print(f"  - Details: {details3}")
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)