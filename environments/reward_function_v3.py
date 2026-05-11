"""
RewardFunction v3 - Dynamic Reward Shaping
================================================================================
v3.0 新功能：
1. Dynamic Reward Scaling：根據訓練進度自動調整 reward 幅度
   - 初期（exploration phase）：放大信號，幫助模型快速學習
   - 後期（exploitation phase）：精細化，避免過度波動
   
2. Adaptive Signal Amplification：
   - 當 Sharpe/執行品質持續改善 → 逐步放大好信號
   - 當連續虧損或 MDD 擴大 → 收斂信號，避免災難性更新
   
3. Progressive Risk Penalty：
   - 訓練初期：容忍較大回撤，專注學習
   - 訓練後期：嚴格風控，提高生存率
   
4. Momentum-based Reward Scaling：
   - 根據最近 N 步的賺赔趨勢動態調整

作者: FinRL量化交易專家（v3 Dynamic Shaping）
"""

import numpy as np
from typing import Dict, Optional, List, Tuple


class DynamicRewardShaper:
    """
    動態獎勵塑形器
    
    核心概念：
    - training_progress (0→1): 訓練進度，0=剛開始，1=快結束
    - momentum (滾動趨勢): 最近幾步是轉好還是轉差
    - risk_level (0→1): 目前風險程度
    
    調整策略：
    - training_progress < 0.3（探索期）：reward_scale 高，探索為主
    - training_progress 0.3~0.7（學習期）：reward_scale 中，慢慢收斂
    - training_progress > 0.7（收斂期）：reward_scale 低，精細調整
    
    - 當 momentum 為正且風險低：放大正向 reward
    - 當 momentum 為負或風險高：抑制負向 reward，避免過度懲罰
    """
    
    def __init__(
        self,
        # 基本獎勵權重
        trade_penalty: float = 0.0,       # 禁用交易懲罰
        stop_loss_penalty: float = 0.05,
        drawdown_penalty: float = 0.5,
        holding_bonus: float = 0.1,
        win_rate_bonus: float = 0.1,
        risk_free_rate: float = 0.02,

        # Dynamic Shaping 參數
        sortino_weight: float = 0.25,       # Sortino 獎勵權重（加大）
        calmar_weight: float = 0.20,        # Calmar 獎勵權重（加大）
        volatility_penalty: float = 0.1,
        min_trade_reward: float = 0.0,
        trade_reward: float = 0.001,        # 交易獎勵（降低抑制過度交易）
<<<<<<< HEAD
=======
        trend_bull_bonus: float = 0.10,      # 多頭趨勢 bonus（MA5>MA20 且持倉中）
        trend_bear_penalty: float = 0.08,   # 空頭趨勢 penalty（MA5<MA20 且空手）

        benchmark_weight: float = 1.25,
        underperform_penalty: float = 0.35,
        cash_miss_penalty: float = 0.02,
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600

        # 動態調整參數
        init_reward_scale: float = 1.5,     # 初期 reward 放大倍數
        final_reward_scale: float = 0.6,   # 末期 reward 縮小倍數
        momentum_window: int = 20,          # 趨勢計算視窗
        risk_adaptive: bool = True,         # 是否啟用風險自適應
    ):
        # 基本權重
        self.trade_penalty = trade_penalty
        self.stop_loss_penalty = stop_loss_penalty
        self.drawdown_penalty = drawdown_penalty
        self.holding_bonus = holding_bonus
        self.win_rate_bonus = win_rate_bonus
        self.risk_free_rate = risk_free_rate

        # Dynamic Shaping
        self.sortino_weight = sortino_weight
        self.calmar_weight = calmar_weight
        self.volatility_penalty = volatility_penalty
        self.min_trade_reward = min_trade_reward
        self.trade_reward = trade_reward
<<<<<<< HEAD
=======
        self.trend_bull_bonus = trend_bull_bonus
        self.trend_bear_penalty = trend_bear_penalty
        self.benchmark_weight = benchmark_weight
        self.underperform_penalty = underperform_penalty
        self.cash_miss_penalty = cash_miss_penalty
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        self.init_reward_scale = init_reward_scale
        self.final_reward_scale = final_reward_scale
        self.momentum_window = momentum_window
        self.risk_adaptive = risk_adaptive

        # 內部狀態
        self._returns_history: List[float] = []
<<<<<<< HEAD
=======
        self._price_history: List[float] = []   # 用於 MA trend 計算
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        self._portfolio_peak: float = 0.0
        self._rolling_rewards: List[float] = []  # 用於計算 momentum
        self._total_steps: int = 0
        self._current_step: int = 0  # 內部追蹤 step
<<<<<<< HEAD
=======
        self._ma_window_short: int = 5    # MA 短期視窗
        self._ma_window_long: int = 20   # MA 長期視窗
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        
    def reset(self):
        """重置內部狀態"""
        self._returns_history = []
<<<<<<< HEAD
        self._portfolio_peak = 0.0
        self._rolling_rewards = []
        self._total_steps = 0
=======
        self._price_history = []
        self._portfolio_peak = 0.0
        self._rolling_rewards = []
        self._current_step = 0
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
    
    def set_total_steps(self, total_steps: int):
        """設定總訓練步數（用於計算 training_progress）"""
        self._total_steps = total_steps
    
    def _get_reward_scale(self) -> float:
        """
        根據訓練進度計算當前 reward_scale
        - 剛開始：1.5（放大探索信號）
        - 接近尾聲：0.6（精細調整）
        """
        if self._total_steps <= 0:
            return self.init_reward_scale
        
        progress = min(self._current_step / self._total_steps, 1.0)
        
        # 非線性衰減：一開始慢慢降，後期降得快
        # 使用冪函數 shape
        import math
        scale = self.init_reward_scale - (self.init_reward_scale - self.final_reward_scale) * math.pow(progress, 0.7)
        return scale
    
    def _get_momentum(self) -> float:
        """
        計算最近 momentum_window 步的趨勢
        返回：正值=正在好轉，負值=正在變差
        """
        if len(self._rolling_rewards) < self.momentum_window:
            return 0.0
        
        recent = self._rolling_rewards[-self.momentum_window:]
        older = self._rolling_rewards[-self.momentum_window*2:-self.momentum_window] if len(self._rolling_rewards) >= self.momentum_window*2 else recent
        
        if len(older) == 0:
            return 0.0
        
        return (np.mean(recent) - np.mean(older)) / (np.abs(np.mean(older)) + 1e-8)
    
    def _get_risk_level(self, max_drawdown: float) -> float:
        """
        計算當前風險等級 0~1
        0 = 無風險，1 = 極高風險
        """
        if not self.risk_adaptive:
            return 0.5
        
        # MDD 基礎風險
        mdd_risk = min(max_drawdown / 0.30, 1.0)  # 30% MDD 為最高風險
        
        # 波動度風險
        vol_risk = 0.0
        if len(self._returns_history) >= 20:
            vol = np.std(self._returns_history[-20:], ddof=1) * np.sqrt(252)  # Sample std
            vol_risk = min(vol / 0.40, 1.0)  # 40% 年化波動為最高風險
        
        return max(mdd_risk, vol_risk)
    
    def _apply_dynamic_shaping(
        self,
        base_reward: float,
        risk_level: float,
        momentum: float,
    ) -> float:
        """
        根據多個信號對 base_reward 進行動態塑形
        """
        scale = self._get_reward_scale()
        
        # Momentum 調整：好趨勢時放大，壞趨勢時收斂
        if momentum > 0.1:
            # 正在好轉：稍微放大正向 reward
            momentum_factor = 1.0 + min(momentum * 0.3, 0.5)
        elif momentum < -0.1:
            # 正在變差：抑制負向 reward，避免過度反應
            momentum_factor = 1.0 - min(abs(momentum) * 0.3, 0.4)
        else:
            momentum_factor = 1.0
        
        # 風險調整：風除越高，越要抑制負向 reward
        if base_reward < 0 and risk_level > 0.5:
            risk_factor = 1.0 - (risk_level - 0.5) * 0.6  # 最多抑制 30%
        else:
            risk_factor = 1.0
        
        shaped = base_reward * scale * momentum_factor * risk_factor
        return shaped
    
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
        volatility: Optional[float] = None,
    ) -> Tuple[float, Dict]:
        """
        計算動態塑形後的複合獎勵
        """
        rewards = {}
        
        # 更新 peak
        if portfolio_value > self._portfolio_peak:
            self._portfolio_peak = portfolio_value
        
        # =================================================================
        # 1. 資本報酬 (核心獎勵)
        # =================================================================
        value_change = portfolio_value - previous_portfolio_value
        if previous_portfolio_value > 1.0:
            portfolio_return = value_change / previous_portfolio_value
        else:
            portfolio_return = 0.0
        # 放寬 clamp：±20%（比 v2 的 ±10% 更寬）
        portfolio_return = np.clip(portfolio_return, -0.20, 0.20)
<<<<<<< HEAD
        rewards['capital'] = portfolio_return
=======
        if previous_close is not None and previous_close > 0:
            benchmark_return = (close_price - previous_close) / previous_close
        elif daily_return is not None:
            benchmark_return = daily_return
        else:
            benchmark_return = 0.0
        benchmark_return = np.clip(benchmark_return, -0.20, 0.20)

        excess_return = np.clip(portfolio_return - benchmark_return, -0.20, 0.20)
        rewards['capital'] = portfolio_return * 0.25
        rewards['benchmark_excess'] = excess_return * self.benchmark_weight
        rewards['benchmark_underperform'] = min(excess_return, 0.0) * self.underperform_penalty
        rewards['cash_miss'] = 0.0
        if position == 0 and action == 0 and benchmark_return > 0.003:
            rewards['cash_miss'] = -min(benchmark_return * self.cash_miss_penalty * 10.0, 0.02)
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        
        # 記錄歷史
        self._returns_history.append(portfolio_return)
        if len(self._returns_history) > 504:  # 保留兩年
            self._returns_history = self._returns_history[-504:]
        
        self._rolling_rewards.append(portfolio_return)
        if len(self._rolling_rewards) > self.momentum_window * 3:
            self._rolling_rewards = self._rolling_rewards[-self.momentum_window * 3:]
        
        # =================================================================
        # 2. Sortino Ratio 獎勵（動態權重）
        # =================================================================
        rewards['sortino'] = 0.0
        if len(self._returns_history) >= 20:
            sortino = self._calculate_sortino_ratio(np.array(self._returns_history))
            # 動態權重：訓練前期大一點，幫助學習
            sortino_weight_adjusted = self.sortino_weight * self._get_reward_scale()
            rewards['sortino'] = np.clip(sortino * sortino_weight_adjusted * 0.01, -0.15, 0.15)
        
        # =================================================================
        # 3. Calmar Ratio 獎勵（動態權重）
        # =================================================================
        rewards['calmar'] = 0.0
        if max_drawdown > 0 and portfolio_return > 0:
            annual_return = portfolio_return * 252
            calmar = annual_return / max_drawdown
            rewards['calmar'] = np.clip(calmar * self.calmar_weight * 0.01, -0.05, 0.08)
        elif max_drawdown > 0 and portfolio_return < 0:
            rewards['calmar'] = -0.015  # 減輕懲罰
        
        # =================================================================
<<<<<<< HEAD
        # 4. 持有獎勵（降低，避免躺平）
        # =================================================================
        rewards['holding'] = 0.0
        if position > 0 and action == 0 and avg_cost > 0:
            unrealized_pnl = (close_price - avg_cost) / avg_cost
            unrealized_pnl = np.clip(unrealized_pnl, -1.0, 1.0)
            if unrealized_pnl > 0:
                rewards['holding'] = unrealized_pnl * self.holding_bonus
        
        # 現金懲罰：激勵模型不要持有大量現金
        # 當趨勢好轉時，有倉位者應加分
=======
        # 持有獎勵（核心問題修復：平原/小虧也要獎勵，不能只靠 unrealized_pnl）
        rewards['holding'] = 0.0
        if position > 0 and action == 0 and avg_cost > 0:
            unrealized_pnl = (close_price - avg_cost) / avg_cost
            unrealized_pnl_clipped = np.clip(unrealized_pnl, -1.0, 1.0)
            # 主要：根據趨勢方向給予不同的持有獎勵/懲罰
            if len(self._returns_history) >= 10:
                recent_trend = np.mean(self._returns_history[-5:])
                older_trend = np.mean(self._returns_history[-10:-5])
                trend_improving = recent_trend > older_trend
                if unrealized_pnl > 0:
                    # 獲利持仓：強烈獎勵
                    rewards['holding'] = unrealized_pnl_clipped * self.holding_bonus * 2.0
                elif trend_improving:
                    # 趨勢向上但持仓虧損：不要懲罰，維持現有持仓
                    rewards['holding'] = unrealized_pnl_clipped * self.holding_bonus * 0.5
                else:
                    # 趨勢向下且持仓虧損：輕微懲罰
                    rewards['holding'] = unrealized_pnl_clipped * self.holding_bonus * 1.5
            else:
                # 訓練初期：，只要有持仓就給基礎獎勵
                rewards['holding'] = self.holding_bonus * 0.5

        # 現金懲罰：趨勢確認向上的多頭市場，空手要懲罰
>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        if len(self._returns_history) >= 10:
            recent_trend = np.mean(self._returns_history[-5:])
            older_trend = np.mean(self._returns_history[-10:-5])
            trend_improving = recent_trend > older_trend
<<<<<<< HEAD
            
            if trend_improving and position == 0 and action == 0:
                # 趨勢轉多但空手，輕微懲罰
                rewards['holding'] = -0.003
        
=======
            trend_strong = recent_trend > 0.002  # 日報酬均值 > 0.2% 視為明顯多頭

            if trend_strong and position == 0 and action == 0:
                # 明確多頭但空手，大幅懲罰
                rewards['holding'] = -0.01
            elif trend_improving and position == 0 and action == 0:
                # 趨勢轉多但空手，輕微懲罰
                rewards['holding'] = -0.003

        # =================================================================
        # 11. MA 趨勢追蹤 bonus（核心新功能）
        # MA5 > MA20 → 多頭市場 → 持倉者 bonus
        # MA5 < MA20 → 空頭市場 → 空手者 penalty
        # =================================================================
        rewards['ma_trend'] = 0.0
        self._price_history.append(close_price)
        if len(self._price_history) > max(self._ma_window_long, 30):
            self._price_history = self._price_history[-max(self._ma_window_long, 30):]

        if len(self._price_history) >= self._ma_window_long:
            ma_short = np.mean(self._price_history[-self._ma_window_short:])
            ma_long  = np.mean(self._price_history[-self._ma_window_long:])
            if ma_short > ma_long:
                # 多頭格局（MA5 > MA20）
                if position > 0 and action == 0:
                    # 持倉中且未交易 → 趨勢確認，獎勵持有
                    rewards['ma_trend'] = self.trend_bull_bonus
            else:
                # 空頭格局（MA5 < MA20）
                if position == 0 and action == 0:
                    # 空手且未交易 → 空頭確認，獎勵空手
                    rewards['ma_trend'] = -self.trend_bear_penalty

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 5. 交易獎勵（engagement bonus）
        # =================================================================
        rewards['trade'] = 0.0
<<<<<<< HEAD
        if action in [1, 2, 3]:  # BUY, SELL, CLOSE
            rewards['trade'] = self.trade_reward  # 可調整的交易獎勵
        
=======
        if action in [1, 2, 3, 4, 5, 6, 7, 8]:
            rewards['trade'] = self.trade_reward - self.trade_penalty

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 6. 停損懲罰
        # =================================================================
        rewards['stop_loss'] = 0.0
<<<<<<< HEAD
        if action == 4:
            rewards['stop_loss'] = -self.stop_loss_penalty
        
=======

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 7. 勝率獎勵
        # =================================================================
        rewards['win_rate'] = 0.0
        if len(trade_history) > 0:
            wins = sum(1 for t in trade_history if t.get('pnl', 0) > 0)
            win_rate = wins / len(trade_history)
            rewards['win_rate'] = (win_rate - 0.5) * self.win_rate_bonus
<<<<<<< HEAD
        
=======

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 8. 最大回撤懲罰（訓練前期放寬）
        # =================================================================
        rewards['drawdown'] = 0.0
        risk_level = self._get_risk_level(max_drawdown)
        progress = min(self._current_step / max(self._total_steps, 1), 1.0) if self._total_steps > 0 else 0.0
<<<<<<< HEAD
        
        # 訓練前期（<30%）：回撤懲罰減半，專注探索
        dd_penalty_scale = 1.0 if progress > 0.3 else 0.5
        rewards['drawdown'] = -max_drawdown * self.drawdown_penalty * dd_penalty_scale
        
        # 訓練後期（>70%）：若 MDD 超標，加大懲罰
        if progress > 0.7:
            if max_drawdown > 0.20:
                rewards['drawdown'] -= 0.05
            elif max_drawdown > 0.30:
                rewards['drawdown'] -= 0.10
        
=======

        # 訓練前期（<30%）：回撤懲罰減半，專注探索
        dd_penalty_scale = 1.0 if progress > 0.3 else 0.5
        rewards['drawdown'] = -max_drawdown * self.drawdown_penalty * dd_penalty_scale

        # 訓練後期（>70%）：若 MDD 超標，加大懲罰
        if progress > 0.7:
            if max_drawdown > 0.30:
                rewards['drawdown'] -= 0.10
            elif max_drawdown > 0.20:
                rewards['drawdown'] -= 0.05

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 9. 波動度懲罰
        # =================================================================
        rewards['volatility'] = 0.0
        if volatility is not None and volatility > 0:
            if volatility > 0.30:
                rewards['volatility'] = -self.volatility_penalty
            elif len(self._returns_history) >= 20:
                hist_vol = np.std(self._returns_history, ddof=1) * np.sqrt(252)  # Sample std
                if volatility > hist_vol * 1.5:
                    rewards['volatility'] = -self.volatility_penalty * 0.5
<<<<<<< HEAD
        
=======

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 10. 台股涨跌停 Bonus/Penalty
        # =================================================================
        rewards['limit_up_down'] = 0.0
        if previous_close is not None and previous_close > 0 and position > 0:
            daily_change = (close_price - previous_close) / previous_close
            if abs(daily_change) >= 0.095:
                if daily_change > 0:
                    rewards['limit_up_down'] = 0.02
                else:
                    rewards['limit_up_down'] = -0.02
<<<<<<< HEAD
        
=======

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # 計算總獎勵（動態塑形前）
        # =================================================================
        # 內部 step 計數器前進（每次 step 就是下一步）
        self._current_step += 1
        total_reward = sum(rewards.values())
<<<<<<< HEAD
        total_reward = np.clip(total_reward, -1.0, 1.0)
        
=======
        total_reward = np.clip(total_reward, -1.5, 1.5)  # 適度放寬：原 -1~1 太嚴格

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # =================================================================
        # Dynamic Reward Shaping
        # =================================================================
        momentum = self._get_momentum()
        shaped_reward = self._apply_dynamic_shaping(
            total_reward, risk_level, momentum
        )
        shaped_reward = np.clip(shaped_reward, -1.5, 1.5)  # 動態塑形後的 clip
<<<<<<< HEAD
        
=======

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        # 加入診斷資訊
        rewards['_diagnostic'] = {
            'reward_scale': self._get_reward_scale(),
            'momentum': momentum,
            'risk_level': risk_level,
            'progress': progress,
            'shaped': shaped_reward,
<<<<<<< HEAD
        }
        
=======
            'portfolio_return': float(portfolio_return),
            'benchmark_return': float(benchmark_return),
            'excess_return': float(excess_return),
        }

>>>>>>> 639e2d5a2887c27e5f4df627d9ee5f5bec2a6600
        return shaped_reward, rewards
    
    def _calculate_sortino_ratio(self, returns: np.ndarray, target: float = 0.0) -> float:
        """計算 Sortino Ratio"""
        if len(returns) < 2:
            return 0.0
        
        mean_ret = np.mean(returns)
        downside_returns = returns[returns < target]
        
        if len(downside_returns) == 0:
            return 0.0
        
        downside_std = np.std(downside_returns, ddof=1)
        if downside_std == 0:
            return 0.0
        
        sortino = (mean_ret - target) / downside_std
        return sortino * np.sqrt(252)
