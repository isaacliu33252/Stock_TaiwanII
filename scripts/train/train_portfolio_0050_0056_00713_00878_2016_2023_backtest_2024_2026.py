#!/usr/bin/env python3
"""Train one PPO portfolio allocator for 0050/0056/00713/00878."""

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

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics


TICKERS = ["0050.TW", "0056.TW", "00713.TW", "00878.TW"]
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
TIMESTEPS = 100_000
SEED = 42


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

DERIVED_FEATURE_COLUMNS = [
    "0050_trend_score",
    "0050_above_ma120",
    "0050_above_ma240",
    "0050_ma60_above_ma240",
    "0050_drawdown_risk",
    "0050_volatility_63",
    "0050_volatility_rank_252",
    "high_dividend_momentum_avg_63",
    "high_dividend_momentum_avg_126",
    "high_dividend_vs_0050_momentum_63",
    "high_dividend_vs_0050_momentum_126",
    "00878_vs_0050_momentum_63",
    "00713_vs_0050_momentum_63",
    "0056_vs_0050_momentum_63",
    "00878_vs_0056_momentum_126",
    "0050_momentum_rank_63",
    "0050_momentum_rank_126",
    "0050_momentum_rank_252",
    "00878_momentum_rank_126",
    "best_momentum_spread_126",
    "top2_momentum_avg_126",
    "momentum_dispersion_126",
]

ACTIVE_DERIVED_FEATURE_COLUMNS = [
    "0050_trend_score",
    "0050_volatility_rank_252",
    "high_dividend_vs_0050_momentum_126",
    "00878_vs_0050_momentum_63",
    "0050_momentum_rank_126",
]


def _slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def _align_panel(stock_data: dict[str, pd.DataFrame], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in TICKERS:
        df = _slice_by_date(stock_data[ticker], start, end)
        cols = ["date", "close"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")

    panel = panel.sort_values("date").reset_index(drop=True)
    panel = panel.ffill().bfill().fillna(0.0)
    panel = _add_portfolio_features(panel)
    return panel


def _safe_col(panel: pd.DataFrame, ticker: str, feature: str, default: float = 0.0) -> pd.Series:
    col = f"{ticker}_{feature}"
    if col in panel.columns:
        return panel[col].astype(float)
    return pd.Series(default, index=panel.index, dtype=float)


def _rank_desc(values: pd.DataFrame) -> pd.DataFrame:
    return values.rank(axis=1, ascending=False, method="min")


def _add_portfolio_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Features that describe cross-ETF relative strength and market regime."""
    panel = panel.copy()

    ma120 = _safe_col(panel, "0050.TW", "close_ma120_ratio", 1.0)
    ma240 = _safe_col(panel, "0050.TW", "close_ma240_ratio", 1.0)
    ma60_240 = _safe_col(panel, "0050.TW", "ma60_ma240_ratio", 1.0)
    mdd63 = _safe_col(panel, "0050.TW", "rolling_mdd_63", 0.0)
    panel["0050_above_ma120"] = (ma120 > 1.0).astype(float)
    panel["0050_above_ma240"] = (ma240 > 1.0).astype(float)
    panel["0050_ma60_above_ma240"] = (ma60_240 > 1.0).astype(float)
    panel["0050_drawdown_risk"] = mdd63.clip(upper=0.0).abs()
    panel["0050_trend_score"] = (
        panel["0050_above_ma120"] + panel["0050_above_ma240"] + panel["0050_ma60_above_ma240"]
    ) / 3.0

    close_0050 = _safe_col(panel, "0050.TW", "close", np.nan)
    ret_0050 = close_0050.pct_change()
    vol63 = ret_0050.rolling(63, min_periods=20).std().fillna(0.0) * np.sqrt(252)
    panel["0050_volatility_63"] = vol63
    panel["0050_volatility_rank_252"] = vol63.rolling(252, min_periods=63).rank(pct=True).fillna(0.5)

    high_dividend = ["0056.TW", "00713.TW", "00878.TW"]
    for lookback in (63, 126):
        hd_momentum = pd.concat(
            [_safe_col(panel, ticker, f"momentum_{lookback}", 0.0) for ticker in high_dividend],
            axis=1,
        )
        panel[f"high_dividend_momentum_avg_{lookback}"] = hd_momentum.mean(axis=1)
        panel[f"high_dividend_vs_0050_momentum_{lookback}"] = (
            panel[f"high_dividend_momentum_avg_{lookback}"] - _safe_col(panel, "0050.TW", f"momentum_{lookback}", 0.0)
        )

    panel["00878_vs_0050_momentum_63"] = _safe_col(panel, "00878.TW", "momentum_63") - _safe_col(panel, "0050.TW", "momentum_63")
    panel["00713_vs_0050_momentum_63"] = _safe_col(panel, "00713.TW", "momentum_63") - _safe_col(panel, "0050.TW", "momentum_63")
    panel["0056_vs_0050_momentum_63"] = _safe_col(panel, "0056.TW", "momentum_63") - _safe_col(panel, "0050.TW", "momentum_63")
    panel["00878_vs_0056_momentum_126"] = _safe_col(panel, "00878.TW", "momentum_126") - _safe_col(panel, "0056.TW", "momentum_126")

    for lookback in (63, 126, 252):
        momentum = pd.concat(
            [_safe_col(panel, ticker, f"momentum_{lookback}", 0.0).rename(ticker) for ticker in TICKERS],
            axis=1,
        )
        ranks = _rank_desc(momentum)
        panel[f"0050_momentum_rank_{lookback}"] = (ranks["0050.TW"] - 1.0) / (len(TICKERS) - 1)
        if lookback == 126:
            panel["00878_momentum_rank_126"] = (ranks["00878.TW"] - 1.0) / (len(TICKERS) - 1)
            sorted_momentum = np.sort(momentum.to_numpy(dtype=float), axis=1)[:, ::-1]
            panel["best_momentum_spread_126"] = sorted_momentum[:, 0] - sorted_momentum[:, -1]
            panel["top2_momentum_avg_126"] = sorted_momentum[:, :2].mean(axis=1)
            panel["momentum_dispersion_126"] = momentum.std(axis=1)

    panel[DERIVED_FEATURE_COLUMNS] = panel[DERIVED_FEATURE_COLUMNS].replace([np.inf, -np.inf], 0.0)
    panel[DERIVED_FEATURE_COLUMNS] = panel[DERIVED_FEATURE_COLUMNS].fillna(0.0)
    return panel


def _prices(panel: pd.DataFrame) -> np.ndarray:
    return panel[[f"{ticker}_close" for ticker in TICKERS]].to_numpy(dtype=float)


class ETFPortfolioEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        initial_cash: float = 1_000_000,
        commission_rate: float = COMMISSION_RATE,
        tax_rate: float = ETF_TAX_RATE,
        turnover_penalty: float = 0.001,
        benchmark_weight: float = 2.0,
        min_rebalance_days: int = 20,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.tax_rate = float(tax_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.benchmark_weight = float(benchmark_weight)
        self.min_rebalance_days = int(min_rebalance_days)
        self.price_array = _prices(self.panel)
        self.equal_bh_curve = self._benchmark_curve(np.array([0.25, 0.25, 0.25, 0.25], dtype=float))
        self.bh_0050_curve = self._benchmark_curve(np.array([1.0, 0.0, 0.0, 0.0], dtype=float))
        self.feature_cols = []
        for ticker in TICKERS:
            self.feature_cols.extend([f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns])
        self.feature_cols.extend([c for c in ACTIVE_DERIVED_FEATURE_COLUMNS if c in self.panel.columns])

        self.portfolio_state_dim = len(TICKERS) + 6
        obs_dim = len(self.feature_cols) + self.portfolio_state_dim
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(10)
        self.reset()

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = self.initial_cash * weights / self.price_array[0]
        return self.price_array @ shares

    def _target_weights(self, action: int) -> np.ndarray:
        if action == 0:
            return self.weights.copy()
        if action == 1:
            return np.array([0.25, 0.25, 0.25, 0.25], dtype=float)
        if action == 2:
            return np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
        if action == 3:
            return np.array([0.50, 0.30, 0.10, 0.10], dtype=float)
        if action == 4:
            return np.array([0.70, 0.10, 0.10, 0.10], dtype=float)
        if action == 5:
            return np.array([0.80, 0.00, 0.00, 0.20], dtype=float)
        if action == 6:
            return np.array([0.15, 0.25, 0.25, 0.35], dtype=float)
        if action == 7:
            return np.array([0.0, 0.40, 0.30, 0.30], dtype=float)

        momentum = []
        for ticker in TICKERS:
            col = f"{ticker}_momentum_126"
            momentum.append(float(self.panel.iloc[self.step_idx].get(col, 0.0)))
        order = np.argsort(momentum)[::-1]
        weights = np.zeros(len(TICKERS), dtype=float)
        if action == 8:
            weights[order[0]] = 1.0
        else:
            weights[order[:2]] = 0.5
        return weights

    def _get_obs(self) -> np.ndarray:
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        prices = self.price_array[self.step_idx]
        value = max(self._portfolio_value(prices), 1.0)
        weights = self.shares * prices / value
        cash_weight = self.cash / value
        peak = max(self.peak_value, value, 1.0)
        current_drawdown = value / peak - 1.0
        days_since_rebalance = min(max(self.step_idx - self.last_rebalance_idx, 0), 252) / 252.0
        equal_relative = value / max(float(self.equal_bh_curve[self.step_idx]), 1.0) - 1.0
        bh_0050_relative = value / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0
        high_dividend_weight = float(weights[1:].sum())
        state = np.array(
            [
                *weights,
                cash_weight,
                current_drawdown,
                days_since_rebalance,
                equal_relative,
                bh_0050_relative,
                high_dividend_weight,
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
            if delta < 0:
                sell_value = min(-delta, self.shares[i] * prices[i])
                if sell_value <= 0:
                    continue
                fees += sell_value * (self.commission_rate + self.tax_rate)
                self.cash += sell_value - sell_value * (self.commission_rate + self.tax_rate)
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
        self.shares = np.zeros(len(TICKERS), dtype=float)
        self.weights = np.zeros(len(TICKERS), dtype=float)
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
        equal_return = self.equal_bh_curve[self.step_idx] / self.equal_bh_curve[self.step_idx - 1] - 1
        bh_0050_return = self.bh_0050_curve[self.step_idx] / self.bh_0050_curve[self.step_idx - 1] - 1
        benchmark_return = max(float(equal_return), float(bh_0050_return))
        excess_return = daily_return - benchmark_return
        reward = float(
            (daily_return + self.benchmark_weight * excess_return) * 100.0
            - self.turnover_penalty * turnover
            - fees / max(value_before, 1.0)
        )
        terminated = self.step_idx >= len(self.panel) - 1
        info = {
            "portfolio_value": value_after,
            "fees_paid": self.fees_paid,
            "trade_count": self.trade_count,
            "weights": self.weights.copy(),
        }
        return self._get_obs(), reward, terminated, False, info


def _run_model(model: PPO, panel: pd.DataFrame) -> dict:
    env = ETFPortfolioEnv(panel)
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": metrics,
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "final_weights": {ticker: float(w) for ticker, w in zip(TICKERS, info["weights"])},
        "equity_curve": equity,
    }


def _buy_and_hold(panel: pd.DataFrame, weights: np.ndarray) -> dict:
    prices = _prices(panel)
    initial = 1_000_000.0
    shares = initial * weights / prices[0]
    equity = (prices @ shares).astype(float).tolist()
    return {
        "final_value": float(equity[-1]),
        "metrics": calculate_backtest_metrics(equity),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a 4-ETF PPO portfolio allocator.")
    parser.add_argument("--timesteps", type=int, default=TIMESTEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    print("=" * 72)
    print("0050+0056+00713+00878 portfolio PPO training/backtest")
    print(f"Train:    {TRAIN_START} ~ {TRAIN_END}")
    print(f"Backtest: {BACKTEST_START} ~ {BACKTEST_END}")
    print(f"Steps:    {args.timesteps:,}")
    print(f"Seed:     {args.seed}")
    print("=" * 72)

    stock_data = download_all_stocks(TICKERS, TRAIN_START, DOWNLOAD_END)
    missing = [ticker for ticker in TICKERS if ticker not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    train_panel = _align_panel(stock_data, TRAIN_START, TRAIN_END)
    test_panel = _align_panel(stock_data, BACKTEST_START, BACKTEST_END)
    if len(train_panel) < 100 or len(test_panel) < 100:
        raise RuntimeError("Not enough aligned train/backtest rows")

    print(f"Loaded rows: train={len(train_panel)}, backtest={len(test_panel)}")
    print(
        "Actual ranges: "
        f"train={train_panel['date'].min().date()}~{train_panel['date'].max().date()}, "
        f"backtest={test_panel['date'].min().date()}~{test_panel['date'].max().date()}"
    )

    train_env = ETFPortfolioEnv(train_panel)
    model = PPO(
        "MlpPolicy",
        train_env,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=128,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        seed=args.seed,
        verbose=1,
    )
    model.learn(total_timesteps=args.timesteps)

    model_path = PROJECT_ROOT / "models" / "portfolio" / "portfolio_0050_0056_00713_00878_2016_2023_ppo_features_v4_reduced"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))

    train_eval = _run_model(model, train_panel)
    result = _run_model(model, test_panel)
    equal_bh = _buy_and_hold(test_panel, np.array([0.25, 0.25, 0.25, 0.25], dtype=float))
    bh_0050 = _buy_and_hold(test_panel, np.array([1.0, 0.0, 0.0, 0.0], dtype=float))

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
        "feature_config": {
            "base_features_per_ticker": FEATURE_COLUMNS,
            "available_derived_portfolio_features": DERIVED_FEATURE_COLUMNS,
            "active_derived_portfolio_features": ACTIVE_DERIVED_FEATURE_COLUMNS,
            "portfolio_state_features": [
                "current_weights_4",
                "cash_weight",
                "current_drawdown",
                "days_since_rebalance_scaled",
                "relative_value_vs_equal_weight_bh",
                "relative_value_vs_0050_bh",
                "high_dividend_weight",
            ],
            "observation_dim": int(ETFPortfolioEnv(train_panel).observation_space.shape[0]),
        },
        "action_space": {
            "0": "hold current weights",
            "1": "25/25/25/25",
            "2": "100% 0050",
            "3": "50/30/10/10",
            "4": "70/10/10/10 0050 core",
            "5": "80/0/0/20 0050+00878 core",
            "6": "15/25/25/35 high-dividend tilt",
            "7": "0/40/30/30 defensive high-dividend tilt",
            "8": "100% best 6M momentum ETF",
            "9": "50/50 top-2 6M momentum ETFs",
        },
        "reward_note": "daily_return + 2.0 * excess daily return versus max(equal-weight B&H, 0050 B&H); observation includes relative momentum, market regime, and portfolio-vs-benchmark state features",
        "train_eval": train_eval,
        **result,
        "equal_weight_buy_and_hold": equal_bh,
        "buy_and_hold_0050": bh_0050,
        "excess_return_vs_equal_bh": result["rl_metrics"]["total_return"] - equal_bh["metrics"]["total_return"],
        "excess_return_vs_0050_bh": result["rl_metrics"]["total_return"] - bh_0050["metrics"]["total_return"],
    }

    output_file = PROJECT_ROOT / "results" / (
        "training_portfolio_0050_0056_00713_00878_2016_2023_ppo_"
        f"backtest_2024_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print("=" * 72)
    print("Done")
    print(f"Model:  {model_path}")
    print(f"Result: {output_file}")
    print(f"Final value: {result['final_value']:,.0f}")
    print(f"Trades: {result['num_trades']}")
    print(f"Equal B&H final value: {equal_bh['final_value']:,.0f}")
    print(f"0050 B&H final value: {bh_0050['final_value']:,.0f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
