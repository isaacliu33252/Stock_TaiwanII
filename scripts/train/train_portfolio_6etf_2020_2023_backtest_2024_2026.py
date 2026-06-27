#!/usr/bin/env python3
"""6-ETF 投資組合訓練：0050 + 00631L 正二 + 00632R 反一 + 三檔高股息/債."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE, TRANSACTION_TAX_RATE
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics


TRAIN_START = "2020-01-01"
TRAIN_END = "2024-12-31"
BACKTEST_START = "2025-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
TIMESTEPS = 400_000
SEED = 42

# 5 檔 ETF（移除 00632R）
TICKERS = [
    "0050.TW",   # 元大台灣50（核心）
    "0056.TW",   # 元大高股息（高息）
    "00631L.TW", # 元大台灣50正二（多頭槓桿）
    "00713.TW",  # 元大巴菲特（高息低波）
    "00878.TW",  # 國泰永續高股息
]

FEATURE_COLUMNS = [
    "close_ma120_ratio",
    "close_ma240_ratio",
    "ma60_ma240_ratio",
    "momentum_21",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "rolling_mdd_63",
]


def _slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def _align_panel(stock_data: dict[str, pd.DataFrame], tickers: list[str], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        df = _slice_by_date(stock_data[ticker], start, end)
        cols = ["date", "close"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")
    panel = panel.sort_values("date").reset_index(drop=True)
    return panel.ffill().bfill().fillna(0.0)


def _prices(panel: pd.DataFrame, tickers: list[str]) -> np.ndarray:
    return panel[[f"{ticker}_close" for ticker in tickers]].to_numpy(dtype=float)


def _weights_for(tickers: list[str], w: dict[str, float]) -> np.ndarray:
    arr = np.array([w.get(t, 0.0) for t in tickers], dtype=float)
    s = arr.sum()
    return arr / s if s > 0 else np.ones(len(tickers)) / len(tickers)


class SixETFEnv(gym.Env):
    """6 ETF 投資組合環境，12 個動作，明確包含正二 / 反一策略。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        tickers: list[str],
        initial_cash: float = 1_000_000,
        commission_rate: float = COMMISSION_RATE,
        turnover_penalty: float = 0.0005,
        equal_benchmark_weight: float = 1.5,
        underperform_0050_weight: float = 0.5,
        drawdown_penalty_weight: float = 0.3,
        min_rebalance_days: int = 5,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.tickers = tickers
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.equal_benchmark_weight = float(equal_benchmark_weight)
        self.underperform_0050_weight = float(underperform_0050_weight)
        self.drawdown_penalty_weight = float(drawdown_penalty_weight)
        self.min_rebalance_days = int(min_rebalance_days)
        self.price_array = _prices(self.panel, self.tickers)
        self.tax_rates = np.array([ETF_TAX_RATE] * len(tickers), dtype=float)

        # benchmark
        self.equal_bh_curve = self._benchmark_curve(np.ones(len(tickers)) / len(tickers))
        self.bh_0050_curve = self._benchmark_curve(_weights_for(self.tickers, {"0050.TW": 1.0}))
        self.bh_00631l_curve = self._benchmark_curve(_weights_for(self.tickers, {"00631L.TW": 1.0}))
        # 50/50 Blend benchmark（00631L + 0050）
        self.blend50_bh_curve = self._benchmark_curve(_weights_for(self.tickers, {"0050.TW": 0.5, "00631L.TW": 0.5}))

        # observation
        self.feature_cols = []
        for ticker in self.tickers:
            self.feature_cols.extend(
                [f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns]
            )
        obs_dim = len(self.feature_cols) + len(self.tickers) + 5
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(5)
        self.reset()

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = self.initial_cash * weights / self.price_array[0]
        return self.price_array @ shares

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    # ------------------------------------------------------------------
    # 12 個動作策略（明確定義 00631L / 00632R 的使用情境）
    # ------------------------------------------------------------------
    def _target_weights(self, action: int) -> np.ndarray:
        t = self.tickers
        w = lambda d: _weights_for(t, d)

        if action == 0:  # 持有不動
            return self.weights.copy()

        # --- 動作 1: 50% 0050 / 50% 00631L（平衡槓桿 = 最強 B&H）---
        if action == 1:
            return w({"0050.TW": 0.50, "00631L.TW": 0.50})

        # --- 動作 2: 40% 0050 / 60% 00631L（適度槓桿）---
        if action == 2:
            return w({"0050.TW": 0.40, "00631L.TW": 0.60})

        # --- 動作 3: 高股息：40% 0050 / 35% 00713 / 25% 00878 ---
        if action == 3:
            return w({"0050.TW": 0.40, "00713.TW": 0.35, "00878.TW": 0.25})

        # --- 動作 4: 等權 5 檔 ---
        if action == 4:
            return np.ones(len(t), dtype=float) / len(t)

        return w({"0050.TW": 1.0})

    def _get_obs(self) -> np.ndarray:
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        prices = self.price_array[self.step_idx]
        value = max(self._portfolio_value(prices), 1.0)
        weights = self.shares * prices / value
        peak = max(self.peak_value, value, 1.0)
        days_since_rebalance = min(max(self.step_idx - self.last_rebalance_idx, 0), 252) / 252.0
        state = np.array(
            [
                *weights,
                self.cash / value,
                value / peak - 1.0,
                days_since_rebalance,
                value / max(float(self.equal_bh_curve[self.step_idx]), 1.0) - 1.0,
                value / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0,
            ],
            dtype=float,
        )
        obs = np.concatenate([features, state])
        obs = np.nan_to_num(obs, nan=0.0, posinf=10.0, neginf=-10.0)
        return np.clip(obs, -10.0, 10.0).astype(np.float32)

    def _rebalance(self, target_weights: np.ndarray, prices: np.ndarray) -> float:
        value_before = self._portfolio_value(prices)
        current_values = self.shares * prices
        target_values = value_before * target_weights
        deltas = target_values - current_values
        fees = 0.0

        for i, delta in enumerate(deltas):
            if delta >= 0:
                continue
            sell_value = min(-delta, self.shares[i] * prices[i])
            if sell_value <= 0:
                continue
            fee_rate = self.commission_rate + self.tax_rates[i]
            fees += sell_value * fee_rate
            self.cash += sell_value * (1 - fee_rate)
            self.shares[i] -= sell_value / prices[i]

        for i, delta in enumerate(deltas):
            if delta <= 0:
                continue
            buy_value = min(delta, self.cash / (1 + self.commission_rate))
            if buy_value <= 0:
                continue
            fees += buy_value * self.commission_rate
            self.cash -= buy_value * (1 + self.commission_rate)
            self.shares[i] += buy_value / prices[i]

        value_after = max(self._portfolio_value(prices), 1.0)
        self.weights = self.shares * prices / value_after
        return float(fees)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = np.zeros(len(self.tickers), dtype=float)
        self.weights = _weights_for(self.tickers, {"0050.TW": 0.50, "00631L.TW": 0.50})
        self.last_rebalance_idx = -10**9
        self.trade_count = 0
        self.fees_paid = 0.0
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        return self._get_obs(), {}

    def step(self, action):
        prices = self.price_array[self.step_idx]
        value_before = self._portfolio_value(prices)
        target_weights = self._target_weights(int(action))
        fees = 0.0
        turnover = float(np.abs(target_weights - self.weights).sum())

        if int(action) != 0 and self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days:
            fees = self._rebalance(target_weights, prices)
            if fees > 0:
                self.trade_count += 1
                self.last_rebalance_idx = self.step_idx
                self.fees_paid += fees

        self.step_idx += 1
        next_prices = self.price_array[self.step_idx]
        value_after = self._portfolio_value(next_prices)
        self.peak_value = max(self.peak_value, value_after)
        self.equity_curve.append(value_after)

        daily_return = value_after / max(value_before, 1.0) - 1
        equal_return = float(self.equal_bh_curve[self.step_idx] / max(self.equal_bh_curve[self.step_idx - 1], 1.0) - 1)
        bh_0050_return = float(self.bh_0050_curve[self.step_idx] / max(self.bh_0050_curve[self.step_idx - 1], 1.0) - 1)
        blend50_return = float(self.blend50_bh_curve[self.step_idx] / max(self.blend50_bh_curve[self.step_idx - 1], 1.0) - 1)
        excess_equal = daily_return - equal_return
        excess_vs_blend50 = daily_return - blend50_return
        underperform_0050 = max(0.0, bh_0050_return - daily_return)
        current_drawdown = min(0.0, value_after / max(self.peak_value, 1.0) - 1.0)
        # HHI 集中度懲罰（HHI>0.65 才罰，逼模型分散到 00632R）
        hhi = float(np.sum(self.weights**2))
        concentration_penalty = max(0.0, hhi - 0.65) * 0.3
        reward = float(
            (
                daily_return
                + 0.3 * excess_equal                      # 極低 equal B&H 權重
                + 3.0 * excess_vs_blend50                 # 全力打敗 50/50 Blend
                - 0.1 * underperform_0050
                - 0.2 * abs(current_drawdown)
                - concentration_penalty
            )
            * 100.0
            - self.turnover_penalty * turnover
            - fees / max(value_before, 1.0)
        )
        terminated = self.step_idx >= len(self.panel) - 1
        return self._get_obs(), reward, terminated, False, {
            "portfolio_value": value_after,
            "fees_paid": self.fees_paid,
            "trade_count": self.trade_count,
            "weights": self.weights.copy(),
        }


ACTION_LABELS = {
    "0": "持有（不動）",
    "1": "50% 0050 / 50% 00631L（平衡槓桿）",
    "2": "40% 0050 / 60% 00631L（適度槓桿）",
    "3": "40% 0050 / 35% 00713 / 25% 00878（高股息）",
    "4": "等權 5 檔",
}


def _run_model(model: PPO, panel: pd.DataFrame, tickers: list[str]) -> dict:
    env = SixETFEnv(panel, tickers)
    obs, _ = env.reset()
    done = False
    info = {"weights": np.zeros(len(tickers))}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "final_weights": {ticker: float(w) for ticker, w in zip(tickers, info["weights"])},
        "equity_curve": equity,
    }


def _buy_and_hold(panel: pd.DataFrame, tickers: list[str], weights: np.ndarray) -> dict:
    prices = _prices(panel, tickers)
    shares = 1_000_000.0 * weights / prices[0]
    equity = (prices @ shares).astype(float).tolist()
    return {"final_value": float(equity[-1]), "metrics": calculate_backtest_metrics(equity)}


def main() -> None:
    parser = argparse.ArgumentParser(description="6-ETF 投資組合訓練（含正二 00631L + 反一 00632R）")
    parser.add_argument("--timesteps", type=int, default=TIMESTEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--agent", type=str, default="ppo", choices=["ppo", "a2c"])
    parser.add_argument("--min-rebalance-days", type=int, default=5)
    args = parser.parse_args()

    print("=" * 72)
    print("5-ETF Portfolio PPO (移除 00632R)")
    print(f"Train:    {TRAIN_START} ~ {TRAIN_END}")
    print(f"Backtest: {BACKTEST_START} ~ {BACKTEST_END}")
    print("=" * 72)

    stock_data = download_all_stocks(TICKERS, TRAIN_START, DOWNLOAD_END)
    missing = [t for t in TICKERS if t not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    train_panel = _align_panel(stock_data, TICKERS, TRAIN_START, TRAIN_END)
    test_panel = _align_panel(stock_data, TICKERS, BACKTEST_START, BACKTEST_END)
    if len(train_panel) < 100 or len(test_panel) < 100:
        raise RuntimeError("Not enough aligned train/backtest rows")

    print(f"Loaded rows: train={len(train_panel)}, backtest={len(test_panel)}")
    print(
        "Actual ranges: "
        f"train={train_panel['date'].min().date()}~{train_panel['date'].max().date()}, "
        f"backtest={test_panel['date'].min().date()}~{test_panel['date'].max().date()}"
    )

    train_env = SixETFEnv(train_panel, TICKERS)
    from stable_baselines3 import PPO as SB3PPO, A2C as SB3A2C
    AgentCls = SB3PPO if args.agent == "ppo" else SB3A2C
    agent_name = "PPO" if args.agent == "ppo" else "A2C"
    print(f"Agent:     {agent_name}  lr={args.lr}")
    model = AgentCls(
        "MlpPolicy",
        train_env,
        learning_rate=args.lr,
        n_steps=1024,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.08,
        seed=args.seed,
        verbose=1,
    )
    model.learn(total_timesteps=args.timesteps)

    model_path = PROJECT_ROOT / "models" / "portfolio" / "portfolio_5etf_2020_2024_v1_ppo"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))

    result = _run_model(model, test_panel, TICKERS)
    train_eval = _run_model(model, train_panel, TICKERS)

    equal_bh = _buy_and_hold(test_panel, TICKERS, np.ones(len(TICKERS)) / len(TICKERS))
    bh_0050 = _buy_and_hold(
        test_panel, TICKERS, _weights_for(TICKERS, {"0050.TW": 1.0})
    )
    bh_00631l = _buy_and_hold(
        test_panel, TICKERS, _weights_for(TICKERS, {"00631L.TW": 1.0})
    )
    bh_blended = _buy_and_hold(
        test_panel, TICKERS, _weights_for(TICKERS, {"0050.TW": 0.5, "00631L.TW": 0.5})
    )
    bh_56_78 = _buy_and_hold(
        test_panel, TICKERS, _weights_for(TICKERS, {"0056.TW": 0.5, "00878.TW": 0.5})
    )
    bh_56 = _buy_and_hold(
        test_panel, TICKERS, _weights_for(TICKERS, {"0056.TW": 1.0})
    )
    bh_78 = _buy_and_hold(
        test_panel, TICKERS, _weights_for(TICKERS, {"00878.TW": 1.0})
    )

    payload = {
        "tickers": TICKERS,
        "train_start": TRAIN_START,
        "train_end": TRAIN_END,
        "backtest_start": BACKTEST_START,
        "backtest_end": BACKTEST_END,
        "actual_train_start": str(train_panel["date"].min().date()),
        "actual_train_end": str(train_panel["date"].max().date()),
        "actual_backtest_start": str(test_panel["date"].min().date()),
        "actual_backtest_end": str(test_panel["date"].max().date()),
        "train_rows": int(len(train_panel)),
        "backtest_rows": int(len(test_panel)),
        "model_path": str(model_path),
        "seed": args.seed,
        "requested_timesteps": args.timesteps,
        "agent_type": "ppo",
        "observation_dim": int(train_env.observation_space.shape[0]),
        "reward_note": (
            "daily return + 1.5*excess vs equal B&H - 0.5*underperform vs 0050 B&H "
            "- 0.3*drawdown - turnover penalty"
        ),
        "action_space": ACTION_LABELS,
        "train_eval": train_eval,
        **result,
        "equal_weight_buy_and_hold": equal_bh,
        "buy_and_hold_0050": bh_0050,
        "buy_and_hold_00631l": bh_00631l,
        "buy_and_hold_50_50_blend": bh_blended,
        "buy_and_hold_56_78": bh_56_78,
        "buy_and_hold_0056": bh_56,
        "buy_and_hold_00878": bh_78,
        "excess_return_vs_equal_bh": result["rl_metrics"]["total_return"] - equal_bh["metrics"]["total_return"],
        "excess_return_vs_0050_bh": result["rl_metrics"]["total_return"] - bh_0050["metrics"]["total_return"],
    }

    output_file = PROJECT_ROOT / "results" / (
        "training_portfolio_5etf_2020_2024_ppo_"
        f"backtest_2025_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print("=" * 72)
    print("Done")
    print(f"Model:  {model_path}")
    print(f"Result: {output_file}")
    print(f"RL Final value:  {result['final_value']:,.0f}")
    print(f"Equal B&H:       {equal_bh['final_value']:,.0f}  Sharpe={equal_bh['metrics']['sharpe']:.3f}")
    print(f"0050 B&H:        {bh_0050['final_value']:,.0f}  Sharpe={bh_0050['metrics']['sharpe']:.3f}")
    print(f"00631L B&H:      {bh_00631l['final_value']:,.0f}  Sharpe={bh_00631l['metrics']['sharpe']:.3f}")
    print(f"50/50 Blend B&H: {bh_blended['final_value']:,.0f}  Sharpe={bh_blended['metrics']['sharpe']:.3f}")
    print(f"0056 B&H:        {bh_56['final_value']:,.0f}  Sharpe={bh_56['metrics']['sharpe']:.3f}")
    print(f"00878 B&H:       {bh_78['final_value']:,.0f}  Sharpe={bh_78['metrics']['sharpe']:.3f}")
    print(f"56/78 Blend B&H: {bh_56_78['final_value']:,.0f}  Sharpe={bh_56_78['metrics']['sharpe']:.3f}")
    print(f"RL Sharpe:       {result['rl_metrics']['sharpe']:.3f}  Trades: {result['num_trades']}")
    print("=" * 72)


if __name__ == "__main__":
    main()
