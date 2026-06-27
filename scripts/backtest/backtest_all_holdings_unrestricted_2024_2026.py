#!/usr/bin/env python3
"""Backtest the unrestricted all-holdings PPO model on 2024-2026 and plot comparisons."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import gymnasium as gym
import matplotlib
import numpy as np
import pandas as pd
from gymnasium import spaces
from stable_baselines3 import PPO

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import (
    ALL_TICKERS,
    COMMISSION_RATE,
    ETF_TAX_RATE,
    PORTFOLIO_HOLDINGS,
    TRANSACTION_TAX_RATE,
)
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics


BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_START = "2020-01-01"
DOWNLOAD_END = "2026-05-09"
BENCHMARK_TICKER = "0050.TW"
MODEL_PATH = PROJECT_ROOT / "models" / "portfolio" / "portfolio_all_holdings_2020_2023_ppo"

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
    return panel.sort_values("date").reset_index(drop=True).ffill().bfill().fillna(0.0)


def _prices(panel: pd.DataFrame, tickers: list[str]) -> np.ndarray:
    return panel[[f"{ticker}_close" for ticker in tickers]].to_numpy(dtype=float)


def _weights_for_existing(tickers: list[str], weights_by_ticker: dict[str, float]) -> np.ndarray:
    weights = np.array([weights_by_ticker.get(ticker, 0.0) for ticker in tickers], dtype=float)
    total = weights.sum()
    if total <= 0:
        return np.ones(len(tickers), dtype=float) / len(tickers)
    return weights / total


def _actual_holdings_weights(tickers: list[str], first_prices: np.ndarray) -> np.ndarray:
    values = []
    for ticker, price in zip(tickers, first_prices):
        shares = float(PORTFOLIO_HOLDINGS.get(ticker, {}).get("shares", 0))
        values.append(shares * float(price))
    values = np.array(values, dtype=float)
    total = values.sum()
    if total <= 0:
        return np.ones(len(tickers), dtype=float) / len(tickers)
    return values / total


class UnrestrictedAllHoldingsEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        tickers: list[str],
        initial_cash: float = 1_000_000,
        commission_rate: float = COMMISSION_RATE,
        turnover_penalty: float = 0.001,
        benchmark_weight: float = 2.0,
        min_rebalance_days: int = 20,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.tickers = tickers
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.benchmark_weight = float(benchmark_weight)
        self.min_rebalance_days = int(min_rebalance_days)
        self.price_array = _prices(self.panel, self.tickers)
        self.tax_rates = np.array(
            [TRANSACTION_TAX_RATE if ticker == "2884.TW" else ETF_TAX_RATE for ticker in self.tickers],
            dtype=float,
        )
        self.actual_weights = _actual_holdings_weights(self.tickers, self.price_array[0])
        self.equal_bh_curve = self._benchmark_curve(np.ones(len(self.tickers)) / len(self.tickers))
        self.actual_bh_curve = self._benchmark_curve(self.actual_weights)
        self.bh_0050_curve = self._benchmark_curve(_weights_for_existing(self.tickers, {BENCHMARK_TICKER: 1.0}))

        self.feature_cols = []
        for ticker in self.tickers:
            self.feature_cols.extend([f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns])

        obs_dim = len(self.feature_cols) + len(self.tickers) + 6
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(11)
        self.reset()

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = self.initial_cash * weights / self.price_array[0]
        return self.price_array @ shares

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _target_weights(self, action: int) -> np.ndarray:
        n = len(self.tickers)
        if action == 0:
            return self.weights.copy()
        if action == 1:
            return np.ones(n, dtype=float) / n
        if action == 2:
            return self.actual_weights.copy()
        if action == 3:
            return _weights_for_existing(self.tickers, {"0050.TW": 1.0})
        if action == 4:
            base = {ticker: 0.30 / max(n - 1, 1) for ticker in self.tickers if ticker != "0050.TW"}
            base["0050.TW"] = 0.70
            return _weights_for_existing(self.tickers, base)
        if action == 5:
            return _weights_for_existing(self.tickers, {"0050.TW": 0.80, "00878.TW": 0.20})
        if action == 6:
            return _weights_for_existing(self.tickers, {"00679B.TWO": 0.25, "00751B.TWO": 0.25, "0050.TW": 0.50})
        if action == 7:
            return _weights_for_existing(self.tickers, {"0056.TW": 1.0, "00713.TW": 1.0, "00878.TW": 1.0})

        momentum = np.array(
            [float(self.panel.iloc[self.step_idx].get(f"{ticker}_momentum_126", 0.0)) for ticker in self.tickers],
            dtype=float,
        )
        order = np.argsort(momentum)[::-1]
        weights = np.zeros(n, dtype=float)
        if action == 8:
            weights[order[0]] = 1.0
        elif action == 9:
            weights[order[: min(2, n)]] = 1.0 / min(2, n)
        else:
            weights[order[: min(3, n)]] = 1.0 / min(3, n)
        return weights

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
                value / max(float(self.actual_bh_curve[self.step_idx]), 1.0) - 1.0,
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
        self.weights = np.zeros(len(self.tickers), dtype=float)
        self.last_rebalance_idx = -10**9
        self.trade_count = 0
        self.fees_paid = 0.0
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        self.action_history = []
        self.weights_history = []
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

        self.action_history.append(int(action))
        self.weights_history.append(self.weights.copy())
        self.step_idx += 1
        next_prices = self.price_array[self.step_idx]
        value_after = self._portfolio_value(next_prices)
        self.peak_value = max(self.peak_value, value_after)
        self.equity_curve.append(value_after)

        daily_return = value_after / max(value_before, 1.0) - 1
        equal_return = self.equal_bh_curve[self.step_idx] / self.equal_bh_curve[self.step_idx - 1] - 1
        actual_return = self.actual_bh_curve[self.step_idx] / self.actual_bh_curve[self.step_idx - 1] - 1
        bh_0050_return = self.bh_0050_curve[self.step_idx] / self.bh_0050_curve[self.step_idx - 1] - 1
        benchmark_return = max(float(equal_return), float(actual_return), float(bh_0050_return))
        excess_return = daily_return - benchmark_return
        reward = float(
            (daily_return + self.benchmark_weight * excess_return) * 100.0
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


def _buy_and_hold(panel: pd.DataFrame, tickers: list[str], weights: np.ndarray) -> dict:
    prices = _prices(panel, tickers)
    shares = 1_000_000.0 * weights / prices[0]
    equity = (prices @ shares).astype(float).tolist()
    return {
        "final_value": float(equity[-1]),
        "metrics": calculate_backtest_metrics(equity),
        "equity_curve": equity,
    }


def _run_model(model: PPO, panel: pd.DataFrame, tickers: list[str]) -> dict:
    env = UnrestrictedAllHoldingsEnv(panel, tickers)
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
        "action_history": env.action_history,
        "weights_history": [[float(x) for x in row] for row in env.weights_history],
    }


def _plot_comparison(dates: pd.Series, curves: dict[str, list[float]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(13, 7))
    for label, values in curves.items():
        plt.plot(dates.iloc[: len(values)], values, label=label, linewidth=2)
    plt.title("All Holdings Unrestricted Backtest: 2024-2026")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value (TWD)")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()


def _plot_drawdown(dates: pd.Series, curves: dict[str, list[float]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(13, 6))
    for label, values in curves.items():
        arr = np.array(values, dtype=float)
        dd = arr / np.maximum.accumulate(arr) - 1
        plt.plot(dates.iloc[: len(values)], dd * 100, label=label, linewidth=2)
    plt.title("Drawdown Comparison: 2024-2026")
    plt.xlabel("Date")
    plt.ylabel("Drawdown (%)")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest unrestricted all-holdings PPO on 2024-2026.")
    parser.add_argument("--model", default=str(MODEL_PATH))
    parser.add_argument("--start", default=BACKTEST_START)
    parser.add_argument("--end", default=BACKTEST_END)
    args = parser.parse_args()

    tickers = list(ALL_TICKERS)
    stock_data = download_all_stocks(tickers, DOWNLOAD_START, DOWNLOAD_END)
    missing = [ticker for ticker in tickers if ticker not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    panel = _align_panel(stock_data, tickers, args.start, args.end)
    if len(panel) < 100:
        raise RuntimeError("Not enough backtest rows")

    model_path = Path(args.model)
    model = PPO.load(str(model_path))
    result = _run_model(model, panel, tickers)

    env_for_weights = UnrestrictedAllHoldingsEnv(panel, tickers)
    equal_bh = _buy_and_hold(panel, tickers, np.ones(len(tickers)) / len(tickers))
    actual_bh = _buy_and_hold(panel, tickers, env_for_weights.actual_weights)
    bh_0050 = _buy_and_hold(panel, tickers, _weights_for_existing(tickers, {BENCHMARK_TICKER: 1.0}))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    period_slug = f"{args.start}_{args.end}".replace("-", "")
    chart_file = PROJECT_ROOT / "results" / f"all_holdings_unrestricted_backtest_{period_slug}_{timestamp}.png"
    drawdown_file = PROJECT_ROOT / "results" / f"all_holdings_unrestricted_drawdown_{period_slug}_{timestamp}.png"
    curves = {
        "RL unrestricted": result["equity_curve"],
        "Equal B&H": equal_bh["equity_curve"],
        "Actual Holdings B&H": actual_bh["equity_curve"],
        "0050 B&H": bh_0050["equity_curve"],
    }
    _plot_comparison(panel["date"], curves, chart_file)
    _plot_drawdown(panel["date"], curves, drawdown_file)

    payload = {
        "tickers": tickers,
        "model_path": str(model_path),
        "backtest_start": args.start,
        "backtest_end": args.end,
        "actual_backtest_start": str(panel["date"].min().date()),
        "actual_backtest_end": str(panel["date"].max().date()),
        "backtest_rows": int(len(panel)),
        "observation_dim": int(env_for_weights.observation_space.shape[0]),
        "action_space": {
            "0": "hold current weights",
            "1": "equal weight all holdings",
            "2": "actual current holding weights",
            "3": "100% 0050",
            "4": "70% 0050, rest equal",
            "5": "80% 0050 / 20% 00878",
            "6": "50% 0050 / 25% 00679B / 25% 00751B",
            "7": "0056/00713/00878 equal high-dividend basket",
            "8": "100% best 6M momentum",
            "9": "top-2 6M momentum equal",
            "10": "top-3 6M momentum equal",
        },
        **result,
        "equal_weight_buy_and_hold": {k: v for k, v in equal_bh.items() if k != "equity_curve"},
        "actual_holdings_buy_and_hold": {k: v for k, v in actual_bh.items() if k != "equity_curve"},
        "buy_and_hold_0050": {k: v for k, v in bh_0050.items() if k != "equity_curve"},
        "excess_return_vs_equal_bh": result["rl_metrics"]["total_return"] - equal_bh["metrics"]["total_return"],
        "excess_return_vs_actual_bh": result["rl_metrics"]["total_return"] - actual_bh["metrics"]["total_return"],
        "excess_return_vs_0050_bh": result["rl_metrics"]["total_return"] - bh_0050["metrics"]["total_return"],
        "chart_file": str(chart_file),
        "drawdown_file": str(drawdown_file),
    }

    output_file = PROJECT_ROOT / "results" / f"backtest_all_holdings_unrestricted_{period_slug}_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print("=" * 72)
    print("Unrestricted all-holdings backtest done")
    print(f"Model:    {model_path}")
    print(f"Result:   {output_file}")
    print(f"Chart:    {chart_file}")
    print(f"Drawdown: {drawdown_file}")
    print(f"Final value: {result['final_value']:,.0f}")
    print(f"Trades: {result['num_trades']}")
    print(f"Equal B&H final value: {equal_bh['final_value']:,.0f}")
    print(f"Actual holdings B&H final value: {actual_bh['final_value']:,.0f}")
    print(f"0050 B&H final value: {bh_0050['final_value']:,.0f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
