"""
Risk Manager v2 - 與訓練流程整合
================================================================================
v2.0 改善：
1. 與 TaiwanStockTradingEnv 直接整合
2. 支援 Early Stopping（根據 Sharpe/MDD）
3. 動態調整倉位
4. 更完整的風控報告

作者: FinRL量化交易專家（整合版）
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, Dict


class RiskManager:
    """
    增強版風險管理員 - 與 RL 環境整合
    
    新增功能：
    - Early Stopping 觸發
    - 動態 Kelly 倉位建議
    - 交易成本優化
    - 完整的風控信號
    """

    def __init__(
        self,
        # 停損停利
        stop_loss_pct: float = -0.10,      # 停損：虧損 10% 賣出
        take_profit_pct: float = 0.20,     # 停利：獲利 20% 賣出
        
        # 倉位管理
        kelly_fraction: float = 0.25,       # Kelly 比例（預設 1/4 Kelly）
        min_position_pct: float = 0.0,     # 最低持倉比例
        
        # 回測控制
        max_drawdown_limit: float = 0.20,  # 整體最大回測限制
        max_daily_loss: float = 0.05,     # 單日最大虧損
        
        # 交易頻率
        trade_cooldown: int = 5,           # 交易冷卻期（天）
        max_trades_per_week: int = 3,      # 每週最多交易次數
        
        # Early Stopping（新增）
        early_stop_patience: int = 30,     # 連續多少步沒有改善就停止
        early_stop_sharpe_threshold: float = 0.0,  # Sharpe 低於此值就停止
        
        # 風險評估
        risk_free_rate: float = 0.02,
    ):
        # 停損停利
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.kelly_fraction = kelly_fraction
        self.min_position_pct = min_position_pct
        
        # 回測控制
        self.max_drawdown_limit = max_drawdown_limit
        self.max_daily_loss = max_daily_loss
        
        # 交易頻率
        self.trade_cooldown = trade_cooldown
        self.max_trades_per_week = max_trades_per_week
        
        # Early Stopping
        self.early_stop_patience = early_stop_patience
        self.early_stop_sharpe_threshold = early_stop_sharpe_threshold
        
        # 風險評估
        self.risk_free_rate = risk_free_rate
        
        # 內部狀態
        self._peak_value: float = 0.0
        self._last_trade_step: int = 0
        self._weekly_trades: list = []
        
        # Early Stopping 追蹤
        self._best_sharpe: float = -999.0
        self._no_improve_steps: int = 0
        self._history_returns: list = []
        
        # 連續虧損追蹤
        self._consecutive_loss_days: int = 0
        
    def reset(self, initial_value: float):
        """重置風險管理員狀態"""
        self._peak_value = initial_value
        self._last_trade_step = 0
        self._weekly_trades = []
        self._best_sharpe = -999.0
        self._no_improve_steps = 0
        self._history_returns = []
        self._consecutive_loss_days = 0
    
    def record_return(self, portfolio_return: float):
        """記錄每日的報酬，用於計算 Sharpe"""
        self._history_returns.append(portfolio_return)
        if len(self._history_returns) > 252:
            self._history_returns = self._history_returns[-252:]
    
    # ─────────────────────────────────────────────────────────────────────
    # 風控檢查
    # ─────────────────────────────────────────────────────────────────────
    
    def check_all(
        self,
        current_price: float,
        avg_cost: float,
        position: int,
        current_step: int,
        days_held: int = 0,
        portfolio_value: float = None,
        previous_portfolio_value: float = None,
    ) -> dict:
        """
        綜合所有風控規則，回傳交易信號。
        
        Returns:
            dict: {
                "action": "hold" | "buy" | "sell" | "stop_loss" | "take_profit" | "reduce" | "early_stop",
                "reason": str,
                "risk_level": "low" | "medium" | "high" | "critical",
                "position_size": float (0-1),
                "can_trade": bool,
            }
        """
        result = {
            "action": "hold",
            "reason": "無風控信號",
            "risk_level": "low",
            "position_size": 1.0,
            "can_trade": True,
        }
        
        # === 1. 停損檢查 ===
        if position > 0 and avg_cost > 0:
            pnl_pct = (current_price - avg_cost) / avg_cost
            
            if pnl_pct <= self.stop_loss_pct:
                return {
                    "action": "stop_loss",
                    "reason": f"停損觸發：{pnl_pct*100:.1f}% <= {self.stop_loss_pct*100:.0f}%",
                    "risk_level": "high",
                    "position_size": 0.0,
                    "can_trade": True,
                }
            
            # === 2. 停利檢查 ===
            threshold = self._get_take_profit_threshold(days_held)
            if pnl_pct >= threshold:
                return {
                    "action": "take_profit",
                    "reason": f"停利觸發：{pnl_pct*100:.1f}% >= {threshold*100:.0f}%",
                    "risk_level": "medium",
                    "position_size": 0.5,  # 建議減半
                    "can_trade": True,
                }
            
            # === 3. 回測檢查 ===
            drawdown = self.update_peak(portfolio_value)
            if drawdown >= self.max_drawdown_limit:
                return {
                    "action": "stop_loss",
                    "reason": f"MDD 觸發：{drawdown*100:.1f}% >= {self.max_drawdown_limit*100:.0f}%",
                    "risk_level": "critical",
                    "position_size": 0.0,
                    "can_trade": True,
                }
            elif drawdown >= self.max_drawdown_limit * 0.75:
                result["risk_level"] = "high"
        
        # === 4. 單日虧損檢查 ===
        if previous_portfolio_value and portfolio_value:
            daily_loss = (portfolio_value - previous_portfolio_value) / previous_portfolio_value
            if daily_loss <= -self.max_daily_loss:
                return {
                    "action": "reduce",
                    "reason": f"單日虧損過大：{daily_loss*100:.1f}%",
                    "risk_level": "critical",
                    "position_size": 0.3,
                    "can_trade": True,
                }
        
        # === 5. 交易頻率檢查 ===
        if not self.can_trade(current_step):
            return {
                "action": "hold",
                "reason": f"冷卻期，{self.trade_cooldown} 天後才能交易",
                "risk_level": result["risk_level"],
                "position_size": 1.0,
                "can_trade": False,
            }
        
        if not self.check_weekly_limit(current_step):
            return {
                "action": "hold",
                "reason": f"本週已達交易上限 ({self.max_trades_per_week}次)",
                "risk_level": result["risk_level"],
                "position_size": 1.0,
                "can_trade": False,
            }
        
        # === 6. Early Stopping 檢查 ===
        if len(self._history_returns) >= 20:
            sharpe = self.calculate_sharpe()
            if sharpe < self.early_stop_sharpe_threshold:
                self._no_improve_steps += 1
                if self._no_improve_steps >= self.early_stop_patience:
                    return {
                        "action": "early_stop",
                        "reason": f"Sharpe 持續低迷 ({sharpe:.3f})，觸發 Early Stopping",
                        "risk_level": "high",
                        "position_size": 0.0,
                        "can_trade": True,
                    }
            else:
                self._no_improve_steps = 0
                if sharpe > self._best_sharpe:
                    self._best_sharpe = sharpe
        
        # === 7. 動態倉位建議 ===
        if portfolio_value:
            kelly = self.get_kelly_fraction()
            result["position_size"] = kelly
        
        return result
    
    def _get_take_profit_threshold(self, days_held: int) -> float:
        """根據持倉時間調整停利標準"""
        if days_held > 60:
            return self.take_profit_pct * 1.5  # 30%
        elif days_held > 30:
            return self.take_profit_pct * 1.2  # 24%
        return self.take_profit_pct
    
    def get_kelly_fraction(self) -> float:
        """計算 Kelly Criterion 倉位建議"""
        if len(self._history_returns) < 20:
            return 1.0
        
        returns = np.array(self._history_returns)
        win_rate = (returns > 0).mean()
        
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return 0.5
        
        avg_win = wins.mean()
        avg_loss = abs(losses.mean())
        
        if avg_loss == 0:
            return 0.5
        
        win_loss_ratio = avg_win / avg_loss
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # 限制範圍，半 Kelly
        kelly = max(0.0, min(kelly * self.kelly_fraction, 0.25))
        
        return kelly
    
    def can_trade(self, current_step: int) -> bool:
        """檢查是否在冷卻期"""
        return (current_step - self._last_trade_step) >= self.trade_cooldown
    
    def check_weekly_limit(self, current_step: int) -> bool:
        """檢查是否達到每週交易上限"""
        current_week = current_step // 5
        recent_weeks = [s // 5 for s, _ in self._weekly_trades]
        trades_this_week = recent_weeks.count(current_week)
        return trades_this_week < self.max_trades_per_week
    
    def record_trade(self, step: int, date=None):
        """記錄已執行交易"""
        self._last_trade_step = step
        self._weekly_trades.append((step, date))
        if len(self._weekly_trades) > self.max_trades_per_week * 4:
            self._weekly_trades = self._weekly_trades[-self.max_trades_per_week * 2:]
    
    def update_peak(self, portfolio_value: float) -> float:
        """更新歷史高點，返回當前回測"""
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value
        
        if self._peak_value > 0:
            return (self._peak_value - portfolio_value) / self._peak_value
        return 0.0
    
    def calculate_sharpe(self) -> float:
        """計算 Sharpe Ratio"""
        if len(self._history_returns) < 2:
            return 0.0
        
        returns = np.array(self._history_returns)
        daily_rf = self.risk_free_rate / 252
        excess = returns - daily_rf
        
        if np.std(excess, ddof=1) == 0:
            return 0.0
        
        return (np.mean(excess) / np.std(excess, ddof=1)) * np.sqrt(252)
    
    def calculate_sortino(self) -> float:
        """計算 Sortino Ratio"""
        if len(self._history_returns) < 2:
            return 0.0
        
        returns = np.array(self._history_returns)
        downside = returns[returns < 0]
        
        if len(downside) == 0 or np.std(downside, ddof=1) == 0:
            return 0.0
        
        return (np.mean(returns) / np.std(downside, ddof=1)) * np.sqrt(252)
    
    def get_summary(self) -> dict:
        """取得風控摘要"""
        return {
            "total_trades": len(self._weekly_trades),
            "best_sharpe": self._best_sharpe,
            "current_sharpe": self.calculate_sharpe(),
            "current_sortino": self.calculate_sortino(),
            "peak_value": self._peak_value,
            "no_improve_steps": self._no_improve_steps,
        }