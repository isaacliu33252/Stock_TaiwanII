"""
TaiwanStockTradingEnv - 台股交易環境 (Gym-style)
================================================================================
這是 FinRL 台股系統的核心環境類別，繼承自 gym.Env。

環境設計:
    - State Space: 57維狀態向量
    - Action Space: 9類離散動作 / 連續目標持倉
    - Reward Function: 複合獎勵函數

台股特殊規則:
    - 涨跌停 10% 限制
    - T+2 交割制度
    - 最小交易單位 1000 股
    - 最大持有 4000 股
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, List

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from .action_space import (
    ActionMode,
    ContinuousActionSpec,
    build_action_space,
    continuous_action_to_target_ratio,
    format_continuous_action,
)


class TaiwanStockTradingEnv(gym.Env):
    """
    台股交易環境 (Gym-style)

    本環境模擬台灣股票市場的交易情境，適合用於訓練 RL 交易代理。
    """

    metadata = {"render_modes": ["human", "rgb_array"]}

    ACTION_NAMES = [
        "HOLD", "BUY_1000", "BUY_5000", "BUY_10000",
        "SELL_1000", "SELL_5000", "SELL_10000",
        "TARGET_50_PERCENT", "TARGET_100_PERCENT",
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
        include_dividends: bool = False,
        action_mode: str = "discrete",
        continuous_action_low: float = -1.0,
        continuous_action_high: float = 1.0,
    ):
        super().__init__()

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
        self.include_dividends = include_dividends
        self.action_mode = ActionMode.from_value(action_mode)
        self.continuous_action_spec = ContinuousActionSpec(
            low=continuous_action_low,
            high=continuous_action_high,
            shape=(1,),
            long_only=True,
        )

        if reward_func is None:
            from .reward_function import RewardFunction
            self.reward_func = RewardFunction()
        else:
            self.reward_func = reward_func

        self._initial_shares = initial_shares
        self._initial_avg_cost = initial_avg_cost

        self.current_step = 0
        self.balance = initial_balance
        self.position = 0
        self.avg_cost = 0.0
        self.total_cost = 0.0

        self.trade_history = []
        self.dividend_history = []
        self.dividend_cash_received = 0.0
        self.consecutive_idle_days = 0
        self.portfolio_value_history = []
        self.last_buy_step = None
        self.last_target_ratio = 0.0

        self.max_shares = max_position

        self.state_dim = 57
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(self.state_dim,),
            dtype=np.float32,
        )
        self.action_space = build_action_space(
            self.action_mode,
            discrete_size=len(self.ACTION_NAMES),
            continuous_spec=self.continuous_action_spec,
        )

        if "date" in self.df.columns:
            self.df = self.df.sort_values("date").reset_index(drop=True)
        elif self.df.index.name == "date":
            self.df = self.df.reset_index()

        self.max_steps = len(self.df) - 1

        self._identify_feature_columns()
        self._prepare_sentiment_features()

        self.peak_value = initial_balance
        self.max_drawdown = 0.0
        self.pending_shares = {}

        print("[TaiwanStockTradingEnv] 環境初始化完成")
        print(f"  - 數據筆數: {len(self.df)}")
        print(f"  - 初始資金: {initial_balance:,.0f} TWD")
        print(f"  - 最大持股: {max_position} 股")
        print(f"  - 狀態維度: {self.state_dim}")
        if self.action_mode == ActionMode.DISCRETE:
            print(f"  - 動作空間: {self.action_space.n} 類離散動作")
        else:
            print(
                f"  - 動作空間: 連續控制 {self.continuous_action_spec.low:.1f}"
                f" ~ {self.continuous_action_spec.high:.1f}"
            )

    def _identify_feature_columns(self):
        all_cols = self.df.columns.tolist()
        exclude_cols = ["date", "symbol", "open", "high", "low", "close", "volume", "turnover"]

        self.price_features = ["close", "open", "high", "low", "volume", "turnover"]
        self.technical_features = [
            "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
            "momentum_21", "momentum_63", "momentum_126", "momentum_252",
            "high_252_position", "rolling_mdd_63",
            "ma3", "ma5", "ma10", "ma20", "ma60", "ma120", "ma240",
            "ma3_slope", "ma20_slope", "ma60_slope",
            "ma_cross_signal",
            "macd_line", "signal_line", "histogram", "histogram_change",
            "macd_turn_positive",
            "macd_turn_negative",
            "rsi_14", "rsi_28",
            "kdj_k", "kdj_d", "kdj_j",
            "williams_r",
            "bb_upper", "bb_lower", "bb_width",
            "atr_14",
            "dmi_plus", "dmi_minus", "adx",
            "mfi",
            "volume_normalized",
        ]
        self.pattern_features = [
            "highest_breakout", "lowest_breakdown",
            "volume_spike", "price_momentum", "volatility",
            "consecutive_up_days", "consecutive_down_days",
            "gap_up_or_down",
        ]
        self.fundamental_features = [
            "foreign_net_buy_1d", "foreign_net_buy_3d", "foreign_net_buy_5d",
            "dealer_net_buy_1d", "investment_trust_net_buy",
            "dividend_yield", "per", "pbr",
        ]
        self.position_features = [
            "current_position",
            "position_value_ratio",
            "unrealized_pnl",
            "max_drawdown",
            "days_since_trade",
            "cash_ratio",
        ]
        self.sentiment_features = [
            "twse_index_return",
            "twse_index_volume_change",
            "sector_correlation",
            "market_volatility",
            "dji_return_1d_lag1",
            "dji_return_5d_lag1",
            "dji_volatility_20d_lag1",
            "dji_ma60_ratio_lag1",
            "dji_drawdown_60d_lag1",
        ]

        available_cols = [c for c in all_cols if c not in exclude_cols]
        self.tech_features_available = [c for c in self.technical_features if c in available_cols]
        self.pattern_features_available = [c for c in self.pattern_features if c in available_cols]
        self.fund_features_available = [c for c in self.fundamental_features if c in available_cols]
        self.sentiment_features_available = [c for c in self.sentiment_features if c in available_cols]

    def _prepare_sentiment_features(self) -> None:
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
                returns.rolling(20, min_periods=5).std(ddof=1).fillna(0.0).clip(0.0, 1.0)
            )

        for col in [
            "dji_return_1d_lag1",
            "dji_return_5d_lag1",
            "dji_volatility_20d_lag1",
            "dji_ma60_ratio_lag1",
            "dji_drawdown_60d_lag1",
        ]:
            if col not in self.df:
                self.df[col] = 0.0

        self.sentiment_features_available = self.sentiment_features.copy()

    def _create_state(self) -> np.ndarray:
        state_list = []
        row = self.df.iloc[self.current_step]

        close = row["close"]
        state_list.extend([
            row["close"] / close if close != 0 else 0,
            row["open"] / close if close != 0 else 0,
            row["high"] / close if close != 0 else 0,
            row["low"] / close if close != 0 else 0,
            np.log1p(row["volume"]) / 20,
            np.log1p(row.get("turnover", 0)) / 25,
        ])

        for feature in self.tech_features_available[:20]:
            value = row.get(feature, 0)
            if pd.isna(value):
                value = 0
            state_list.append(float(value))
        while len(state_list) < 6 + 20:
            state_list.append(0.0)

        for feature in self.pattern_features_available[:8]:
            value = row.get(feature, 0)
            if pd.isna(value):
                value = 0
            state_list.append(float(value))
        while len(state_list) < 6 + 20 + 8:
            state_list.append(0.0)

        for feature in self.fund_features_available[:8]:
            value = row.get(feature, 0)
            if pd.isna(value):
                value = 0
            state_list.append(float(value))
        while len(state_list) < 6 + 20 + 8 + 8:
            state_list.append(0.0)

        portfolio_value = self.balance + self.position * close
        position_level = self.position // self.trade_unit
        state_list.append(float(position_level))

        position_value_ratio = (self.position * close) / portfolio_value if portfolio_value > 0 else 0
        state_list.append(position_value_ratio)

        unrealized_pnl = 0.0
        if self.position > 0 and self.avg_cost > 0:
            unrealized_pnl = (close - self.avg_cost) / self.avg_cost
        state_list.append(unrealized_pnl)

        state_list.append(self.max_drawdown)

        days_since_trade = 0
        if self.trade_history:
            last_trade_step = self.trade_history[-1].get("step", 0)
            days_since_trade = self.current_step - last_trade_step
        state_list.append(float(days_since_trade) / 60)

        cash_ratio = self.balance / portfolio_value if portfolio_value > 0 else 1.0
        state_list.append(cash_ratio)

        for feature in self.sentiment_features[:9]:
            value = row.get(feature, 0.0)
            if pd.isna(value):
                value = 0.0
            state_list.append(float(value))

        state_array = np.array(state_list[:self.state_dim], dtype=np.float32)
        if len(state_array) < self.state_dim:
            state_array = np.pad(state_array, (0, self.state_dim - len(state_array)), "constant")
        return state_array

    def _get_trade_price(self, action: int) -> Tuple[float, bool]:
        row = self.df.iloc[self.current_step]
        close = row["close"]
        prev_close = self.df.iloc[self.current_step - 1]["close"] if self.current_step > 0 else close

        if action in [1, 4]:
            trade_price = close * 1.001
        elif action in [2, 3]:
            trade_price = close * 0.999
        else:
            trade_price = close

        price_change = abs(trade_price - prev_close) / prev_close
        return trade_price, price_change < self.price_limit

    def _get_side_trade_price(self, side: str) -> Tuple[float, bool]:
        row = self.df.iloc[self.current_step]
        close = row["close"]
        prev_close = self.df.iloc[self.current_step - 1]["close"] if self.current_step > 0 else close
        trade_price = close * 1.001 if side == "buy" else close * 0.999
        price_change = abs(trade_price - prev_close) / prev_close if prev_close else 0.0
        return trade_price, price_change < self.price_limit

    def _portfolio_value(self, price: Optional[float] = None) -> float:
        if price is None:
            price = float(self.df.iloc[min(self.current_step, len(self.df) - 1)]["close"])
        return float(self.balance + self.position * price)

    def _position_weight(self, price: Optional[float] = None) -> float:
        portfolio_value = self._portfolio_value(price)
        if portfolio_value <= 0:
            return 0.0
        if price is None:
            price = float(self.df.iloc[min(self.current_step, len(self.df) - 1)]["close"])
        return float((self.position * price) / portfolio_value)

    def _continuous_target_ratio(self, action: Any) -> float:
        return continuous_action_to_target_ratio(action, self.continuous_action_spec)

    def _continuous_action_name(self, action: Any) -> str:
        return format_continuous_action(action, self.continuous_action_spec)

    def _buy_shares(self, shares: int, action: Any, label: str) -> Tuple[bool, str]:
        shares = int(shares // self.trade_unit * self.trade_unit)
        if shares <= 0:
            return False, "BUY size too small"
        if self.position >= self.max_position:
            return False, "max position reached"

        trade_price, is_valid = self._get_side_trade_price("buy")
        if not is_valid:
            return False, "price limit"

        shares = min(shares, self.max_position - self.position)
        max_affordable = int(
            (self.balance / (trade_price * (1 + self.commission_rate))) // self.trade_unit
        ) * self.trade_unit
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
            "step": self.current_step,
            "action": action,
            "price": trade_price,
            "shares": shares,
            "position": self.position,
            "pnl": 0,
            "type": label,
            "settlement_step": settlement_step,
        })
        self.consecutive_idle_days = 0
        self.last_buy_step = self.current_step
        return True, f"{label} {shares}@{trade_price:.2f}"

    def _sell_shares(self, shares: int, action: Any, label: str) -> Tuple[bool, str]:
        shares = int(shares // self.trade_unit * self.trade_unit)
        if shares <= 0:
            return False, "SELL size too small"

        locked_shares = sum(count for step, count in self.pending_shares.items() if step > self.current_step)
        sellable_shares = max(0, self.position - locked_shares)
        shares = min(shares, sellable_shares)
        shares = int(shares // self.trade_unit * self.trade_unit)
        if shares <= 0:
            return False, f"T+2 locked ({locked_shares} shares)"

        trade_price, is_valid = self._get_side_trade_price("sell")
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
            "step": self.current_step,
            "action": action,
            "price": trade_price,
            "shares": shares,
            "position": self.position,
            "pnl": pnl,
            "type": label,
        })
        self.consecutive_idle_days = 0
        return True, f"{label} {shares}@{trade_price:.2f}, PnL={pnl:.0f}"

    def _execute_continuous_trade(
        self,
        action: Any,
    ) -> Tuple[bool, str, int, str, float]:
        target_ratio = self._continuous_target_ratio(action)
        self.last_target_ratio = target_ratio

        close = float(self.df.iloc[self.current_step]["close"])
        portfolio_value = self._portfolio_value(close)
        target_shares = int((portfolio_value * target_ratio / close) // self.trade_unit) * self.trade_unit
        target_shares = min(target_shares, self.max_position)
        delta = target_shares - self.position
        action_name = self._continuous_action_name(action)

        if delta >= self.trade_unit:
            executed, message = self._buy_shares(
                delta,
                action,
                f"TARGET_{target_ratio * 100:.1f}_BUY",
            )
            return executed, message, 1 if executed else 0, action_name, target_ratio
        if delta <= -self.trade_unit:
            executed, message = self._sell_shares(
                -delta,
                action,
                f"TARGET_{target_ratio * 100:.1f}_SELL",
            )
            return executed, message, 4 if executed else 0, action_name, target_ratio
        return False, f"TARGET_{target_ratio * 100:.1f}_HOLD", 0, action_name, target_ratio

    def _execute_trade(self, action: Any) -> Tuple[bool, str, int, str, Optional[float]]:
        if self.action_mode == ActionMode.CONTINUOUS:
            return self._execute_continuous_trade(action)

        action = int(np.asarray(action).item())
        if not 0 <= action < self.action_space.n:
            raise ValueError(f"Invalid action {action}; expected 0-{self.action_space.n - 1}")
        if action == 0:
            return False, "HOLD", 0, self.ACTION_NAMES[action], None

        if action in (1, 2, 3):
            shares = {1: 1000, 2: 5000, 3: 10000}[action]
            executed, message = self._buy_shares(shares, action, f"BUY_{shares}")
            return executed, message, action if executed else 0, self.ACTION_NAMES[action], None
        if action in (4, 5, 6):
            shares = {4: 1000, 5: 5000, 6: 10000}[action]
            executed, message = self._sell_shares(shares, action, f"SELL_{shares}")
            return executed, message, action if executed else 0, self.ACTION_NAMES[action], None
        if action in (7, 8):
            close = float(self.df.iloc[self.current_step]["close"])
            target_ratio = 0.5 if action == 7 else 1.0
            portfolio_value = self._portfolio_value(close)
            target_shares = int((portfolio_value * target_ratio / close) // self.trade_unit) * self.trade_unit
            target_shares = min(target_shares, self.max_position)
            delta = target_shares - self.position
            if delta >= self.trade_unit:
                executed, message = self._buy_shares(delta, action, f"TARGET_{int(target_ratio * 100)}_BUY")
                return executed, message, action if executed else 0, self.ACTION_NAMES[action], target_ratio
            if delta <= -self.trade_unit:
                executed, message = self._sell_shares(-delta, action, f"TARGET_{int(target_ratio * 100)}_SELL")
                return executed, message, action if executed else 0, self.ACTION_NAMES[action], target_ratio
            return False, f"TARGET_{int(target_ratio * 100)}_HOLD", 0, self.ACTION_NAMES[action], target_ratio

        return False, "Unknown action", 0, "UNKNOWN", None

    def _apply_dividend_cashflow(self) -> float:
        if not self.include_dividends or self.position <= 0 or self.current_step >= len(self.df):
            return 0.0

        row = self.df.iloc[self.current_step]
        dividend = row.get("dividends", row.get("dividend", 0.0))
        if pd.isna(dividend):
            dividend = 0.0
        dividend = float(dividend)
        if dividend <= 0:
            return 0.0

        cash = self.position * dividend
        self.balance += cash
        self.dividend_cash_received += cash
        self.dividend_history.append({
            "step": self.current_step,
            "date": row.get("date", None),
            "shares": int(self.position),
            "dividend_per_share": dividend,
            "cash": cash,
        })
        return cash

    def step(self, action: Any) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        prev_close = self.df.iloc[self.current_step - 1]["close"] if self.current_step > 0 else 0
        prev_step_price = prev_close if prev_close != 0 else self.df.iloc[0]["close"]
        previous_portfolio_value = self._portfolio_value(prev_step_price)

        executed, message, reward_action, action_name, target_ratio = self._execute_trade(action)
        self.current_step += 1

        dividend_cash = self._apply_dividend_cashflow()

        settlement_steps_to_remove = []
        for settlement_step in self.pending_shares:
            if settlement_step <= self.current_step:
                settlement_steps_to_remove.append(settlement_step)
        for step in settlement_steps_to_remove:
            del self.pending_shares[step]

        row_idx = min(self.current_step, len(self.df) - 1)
        new_price = self.df.iloc[row_idx]["close"]
        portfolio_value = self.balance + self.position * new_price
        self.last_target_ratio = float(target_ratio) if target_ratio is not None else self._position_weight(new_price)

        reward, reward_breakdown = self.reward_func.calculate(
            portfolio_value=portfolio_value,
            previous_portfolio_value=previous_portfolio_value,
            position=self.position,
            close_price=new_price,
            avg_cost=self.avg_cost,
            action=reward_action,
            max_drawdown=self.max_drawdown,
            trade_history=self.trade_history,
            previous_close=prev_close,
        )

        if executed and reward_action != 0:
            reward -= self.turnover_penalty
            reward_breakdown["turnover_penalty"] = -self.turnover_penalty

        if executed and reward_action in (4, 5, 6, 7, 8) and self.last_buy_step is not None:
            held_days = self.current_step - self.last_buy_step
            if held_days < self.min_hold_days:
                penalty = self.short_hold_penalty * (1.0 - held_days / max(self.min_hold_days, 1))
                reward -= penalty
                reward_breakdown["short_hold_penalty"] = -penalty

        if portfolio_value > self.peak_value:
            self.peak_value = portfolio_value
        drawdown = (self.peak_value - portfolio_value) / self.peak_value
        self.max_drawdown = max(self.max_drawdown, drawdown)

        self.portfolio_value_history.append(portfolio_value)
        terminated = self.current_step >= self.max_steps
        if self.balance <= 0 or portfolio_value < self.initial_balance * 0.5:
            terminated = True

        info = {
            "step": self.current_step,
            "date": self.df.iloc[row_idx].get("date", "N/A"),
            "action": reward_action,
            "action_raw": (
                float(np.asarray(action).reshape(-1)[0])
                if self.action_mode == ActionMode.CONTINUOUS
                else int(np.asarray(action).item())
            ),
            "action_name": action_name,
            "action_mode": self.action_mode.value,
            "message": message,
            "trade_executed": executed,
            "balance": self.balance,
            "position": self.position,
            "avg_cost": self.avg_cost,
            "portfolio_value": portfolio_value,
            "position_weight": self._position_weight(new_price),
            "target_ratio": target_ratio,
            "portfolio_return": (
                portfolio_value / previous_portfolio_value - 1
            ) if previous_portfolio_value > 0 else 0.0,
            "dividend_cash": dividend_cash,
            "dividend_cash_received": self.dividend_cash_received,
            "reward_breakdown": reward_breakdown,
            "max_drawdown": self.max_drawdown,
        }

        self.consecutive_idle_days += 1
        if (
            self.consecutive_idle_days >= self.crash_window
            and self.position > 0
            and self.enable_risk_manager
        ):
            idle_days = min(self.consecutive_idle_days, 15)
            reward = reward - 0.003 * idle_days
            self.consecutive_idle_days = 0

        if terminated:
            state = np.zeros(self.state_dim, dtype=np.float32)
        else:
            state = self._create_state()
        return state, reward, terminated, False, info

    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[np.ndarray, Dict]:
        super().reset(seed=seed)

        self.current_step = 0
        self.balance = self.initial_balance
        self.position = self._initial_shares
        self.avg_cost = self._initial_avg_cost if self._initial_shares > 0 else 0.0
        self.total_cost = self.position * self.avg_cost if self.position > 0 else 0.0

        self.peak_value = self.initial_balance + self.position * self.df.iloc[0]["close"]
        self.max_drawdown = 0.0
        self.pending_shares = {}

        self.trade_history = []
        self.dividend_history = []
        self.dividend_cash_received = 0.0
        initial_value = self.initial_balance + self.position * self.df.iloc[0]["close"]
        self.portfolio_value_history = [initial_value]
        self.last_buy_step = None
        self.last_target_ratio = self._position_weight(float(self.df.iloc[0]["close"]))

        if self.reward_func is not None and hasattr(self.reward_func, "reset"):
            self.reward_func.reset()

        state = self._create_state()
        info = {
            "initial_balance": self.initial_balance,
            "max_position": self.max_position,
            "trade_unit": self.trade_unit,
            "action_mode": self.action_mode.value,
        }
        return state, info

    def render(self, mode: str = "human"):
        if mode == "human":
            row_idx = min(self.current_step, len(self.df) - 1)
            portfolio_value = self.balance + self.position * self.df.iloc[row_idx]["close"]
            print(f"\n{'=' * 60}")
            print(f"Step: {self.current_step}")
            print(f"Date: {self.df.iloc[row_idx].get('date', 'N/A')}")
            print(f"Price: {self.df.iloc[row_idx]['close']:.2f}")
            print(f"Balance: {self.balance:,.0f}")
            print(f"Position: {self.position} 股")
            print(f"Avg Cost: {self.avg_cost:.2f}")
            print(f"Portfolio Value: {portfolio_value:,.0f}")
            print(f"Max Drawdown: {self.max_drawdown:.2%}")
            print(f"{'=' * 60}\n")

    def get_info(self) -> Dict[str, Any]:
        row_idx = min(self.current_step, len(self.df) - 1)
        current_price = self.df.iloc[row_idx]["close"]
        portfolio_value = self._portfolio_value(current_price)
        return {
            "step": self.current_step,
            "date": self.df.iloc[row_idx].get("date", "N/A"),
            "price": current_price,
            "balance": self.balance,
            "position": self.position,
            "avg_cost": self.avg_cost,
            "portfolio_value": portfolio_value,
            "position_weight": self._position_weight(current_price),
            "action_mode": self.action_mode.value,
            "target_ratio": self.last_target_ratio,
            "unrealized_pnl": (current_price - self.avg_cost) / self.avg_cost if self.avg_cost > 0 else 0,
            "realized_pnl": sum(t.get("pnl", 0) for t in self.trade_history),
            "max_drawdown": self.max_drawdown,
            "total_trades": len(self.trade_history),
        }
