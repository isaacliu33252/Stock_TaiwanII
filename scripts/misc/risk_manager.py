# ============================================================================
# Risk Manager - 風險管理模組
# ============================================================================
"""
提供停損停利、倉位管理、Kelly Criterion 等風險控制機制。
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple


class RiskManager:
    """
    風險管理員
    
    功能：
        1. 停損 / 停利偵測
        2. Kelly Criterion 動態倉位計算
        3. 最大回測監控
        4. 交易頻率控制（避免過度交易）
    """

    def __init__(
        self,
        stop_loss_pct: float = -0.10,      # 停損：虧損 10% 賣出
        take_profit_pct: float = 0.20,     # 停利：獲利 20% 賣出
        kelly_fraction: float = 0.25,       # Kelly 比例（預設 1/4 Kelly）
        max_drawdown_limit: float = 0.20,  # 整體最大回測限制
        trade_cooldown: int = 5,           # 交易冷卻期（天）
        max_trades_per_week: int = 3,      # 每週最多交易次數
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.kelly_fraction = kelly_fraction
        self.max_drawdown_limit = max_drawdown_limit
        self.trade_cooldown = trade_cooldown
        self.max_trades_per_week = max_trades_per_week

        # 內部狀態
        self._peak_value: float = 0.0
        self._last_trade_step: int = 0
        self._weekly_trades: list = []  # [(step, date), ...]
        self._consecutive_loss_days: int = 0
        self._last_outcome: str = "none"  # "profit" | "loss" | "none"

    def reset(self, initial_value: float):
        """重置風險管理員狀態"""
        self._peak_value = initial_value
        self._last_trade_step = 0
        self._weekly_trades = []
        self._consecutive_loss_days = 0
        self._last_outcome = "none"

    # ─────────────────────────────────────────────────────────────────────
    # 停損 / 停利
    # ─────────────────────────────────────────────────────────────────────

    def check_stop_loss(
        self,
        current_price: float,
        avg_cost: float,
        position: int
    ) -> Tuple[bool, str]:
        """
        檢查是否觸發停損。
        
        Returns:
            (triggered, reason)
        """
        if position <= 0 or avg_cost <= 0:
            return False, ""

        pnl_pct = (current_price - avg_cost) / avg_cost

        if pnl_pct <= self.stop_loss_pct:
            return True, f"停損觸發：現價 {current_price:.2f} / 成本 {avg_cost:.2f} = {pnl_pct*100:.1f}%"

        return False, ""

    def check_take_profit(
        self,
        current_price: float,
        avg_cost: float,
        position: int,
        days_held: int = 0
    ) -> Tuple[bool, str]:
        """
        檢查是否觸發停利。
        
        加入時間因素：持倉越久，停利標準越寬鬆。
        """
        if position <= 0 or avg_cost <= 0:
            return False, ""

        pnl_pct = (current_price - avg_cost) / avg_cost

        # 持倉超過 60 天後，調高停利標準（避免過早退出）
        if days_held > 60:
            threshold = self.take_profit_pct * 1.5  # 30%
        elif days_held > 30:
            threshold = self.take_profit_pct * 1.2  # 24%
        else:
            threshold = self.take_profit_pct

        if pnl_pct >= threshold:
            return True, f"停利觸發：{pnl_pct*100:.1f}% (threshold={threshold*100:.0f}%, held={days_held}d)"

        return False, ""

    # ─────────────────────────────────────────────────────────────────────
    # Kelly Criterion
    # ─────────────────────────────────────────────────────────────────────

    def calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_portfolio_value: float,
    ) -> float:
        """
        計算 Kelly Criterion 比例。
        
        Kelly % = W - (1-W)/R
        其中 W = 勝率, R = avg_win/avg_loss
        
        最後再乘以 kelly_fraction（建議用 0.25，半 Kelly）降低波動。
        
        Returns:
            建議投入資金比例 (0.0 ~ 1.0)
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        win_loss_ratio = avg_win / abs(avg_loss)
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        # 限制範圍
        kelly = max(0.0, min(kelly, 0.25))  # 最大不超過 25%
        
        # 半 Kelly（降低波動）
        return kelly * self.kelly_fraction

    def suggest_position_size(
        self,
        current_portfolio_value: float,
        historical_returns: pd.Series,
        current_drawdown: float = 0.0,
    ) -> float:
        """
        根據歷史報酬分佈動態建議倉位。
        
        結合：
            1. Kelly Criterion（根據滾動勝率）
            2. 當前回測（回測越大，倉位越小）
        """
        if len(historical_returns) < 20:
            return 1.0  # 數據不足，全倉

        # 滾動勝率（過去 60 天）
        rolling_returns = historical_returns.tail(60)
        win_rate = (rolling_returns > 0).mean()

        # 平均獲利 / 平均虧損
        wins = rolling_returns[rolling_returns > 0]
        losses = rolling_returns[rolling_returns < 0]
        avg_win = wins.mean() if len(wins) > 0 else 0.01
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0.01

        kelly = self.calculate_kelly_fraction(
            win_rate, avg_win, avg_loss, current_portfolio_value
        )

        # 回測抑制：MDD 越大，倉位越小
        if current_drawdown > self.max_drawdown_limit * 0.5:
            kelly *= 0.5  # 回測超過一半限制，減半倉
        elif current_drawdown > self.max_drawdown_limit:
            kelly *= 0.25  # 接近限制，降至 1/4

        return max(0.0, min(kelly, 1.0))

    # ─────────────────────────────────────────────────────────────────────
    # 交易頻率控制
    # ─────────────────────────────────────────────────────────────────────

    def can_trade(self, current_step: int) -> Tuple[bool, str]:
        """
        檢查是否可以交易（冷卻期）。
        """
        if current_step - self._last_trade_step < self.trade_cooldown:
            remaining = self.trade_cooldown - (current_step - self._last_trade_step)
            return False, f"冷卻期，{remaining} 天後才能交易"
        return True, ""

    def record_trade(self, step: int, date=None):
        """記錄已執行交易"""
        self._last_trade_step = step
        self._weekly_trades.append((step, date))

        # 清理超過一週的交易記錄
        if len(self._weekly_trades) > self.max_trades_per_week * 4:
            self._weekly_trades = self._weekly_trades[-self.max_trades_per_week * 2:]

    def check_weekly_limit(self, current_step: int) -> Tuple[bool, str]:
        """
        檢查本週是否已達交易上限。
        """
        # 簡化：每 5 步 = 一週
        current_week = current_step // 5
        recent_weeks = [(s // 5, s) for s, _ in self._weekly_trades]
        trades_this_week = sum(1 for w, _ in recent_weeks if w == current_week)

        if trades_this_week >= self.max_trades_per_week:
            return False, f"本週已交易 {trades_this_week} 次（上限 {self.max_trades_per_week}）"
        return True, ""

    # ─────────────────────────────────────────────────────────────────────
    # 最大回測管理
    # ─────────────────────────────────────────────────────────────────────

    def update_peak(self, portfolio_value: float) -> float:
        """
        更新歷史高點，返回當前回測。
        """
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value

        if self._peak_value > 0:
            drawdown = (self._peak_value - portfolio_value) / self._peak_value
        else:
            drawdown = 0.0

        return drawdown

    def check_drawdown_limit(self, current_drawdown: float) -> Tuple[bool, str]:
        """
        檢查是否觸發整體回測限制（減倉或清倉信號）。
        """
        if current_drawdown >= self.max_drawdown_limit:
            return True, f"最大回測 {current_drawdown*100:.1f}% 已達上限 {self.max_drawdown_limit*100:.0f}%，建議減倉"

        if current_drawdown >= self.max_drawdown_limit * 0.75:
            return True, f"最大回測 {current_drawdown*100:.1f}% 接近限制，謹慎交易"

        return False, ""

    # ─────────────────────────────────────────────────────────────────────
    # 綜合風控決策
    # ─────────────────────────────────────────────────────────────────────

    def get_risk_signal(
        self,
        current_price: float,
        avg_cost: float,
        position: int,
        current_step: int,
        days_held: int = 0,
        current_drawdown: float = 0.0,
    ) -> dict:
        """
        綜合所有風控規則，回傳交易信號。
        
        Returns:
            dict: {
                "action": "hold" | "stop_loss" | "take_profit" | "reduce" | "buy",
                "reason": str,
                "kelly_fraction": float,
                "can_trade": bool,
            }
        """
        signals = []

        # 1. 停損檢查
        triggered, reason = self.check_stop_loss(current_price, avg_cost, position)
        if triggered:
            return {
                "action": "stop_loss",
                "reason": reason,
                "can_trade": True,
            }

        # 2. 停利檢查
        triggered, reason = self.check_take_profit(current_price, avg_cost, position, days_held)
        if triggered:
            signals.append(("take_profit", reason))

        # 3. 回測限制檢查
        triggered, reason = self.check_drawdown_limit(current_drawdown)
        if triggered:
            if position > 0:
                signals.append(("reduce", reason))

        # 4. 冷卻期檢查
        can_trade, reason = self.can_trade(current_step)
        if not can_trade:
            return {
                "action": "hold",
                "reason": reason,
                "can_trade": False,
            }

        # 5. 每週上限檢查
        can_trade, reason = self.check_weekly_limit(current_step)
        if not can_trade:
            return {
                "action": "hold",
                "reason": reason,
                "can_trade": False,
            }

        if signals:
            # 取最緊急的信號
            action, reason = signals[0]
            return {
                "action": action,
                "reason": reason,
                "can_trade": True,
            }

        return {
            "action": "hold",
            "reason": "無風控信號",
            "can_trade": True,
        }
