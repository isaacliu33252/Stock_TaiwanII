#!/usr/bin/env python3
"""MVO baseline and continuous-weight SAC/TD3 portfolio training."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import gymnasium as gym
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from gymnasium import spaces
from stable_baselines3 import SAC, TD3
from stable_baselines3.common.noise import NormalActionNoise

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics


TICKERS = ["0050.TW", "0056.TW", "00713.TW", "00878.TW"]
TRAIN_START = "2009-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
INITIAL_CASH = 1_000_000
SEED = 42

FEATURE_COLUMNS = [
    "close_ma120_ratio",
    "close_ma240_ratio",
    "ma60_ma240_ratio",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "rolling_mdd_63",
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


def _slug(date: str) -> str:
    return date.replace("-", "")


def _clean_slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if getattr(out["date"].dt, "tz", None) is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    out = out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()
    return out.sort_values("date").reset_index(drop=True)


def align_panel(stock_data: dict[str, pd.DataFrame], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in TICKERS:
        df = _clean_slice(stock_data[ticker], start, end)
        cols = ["date", "close", "dividends"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        part = df[cols].copy()
        rename = {c: f"{ticker}_{c}" for c in cols if c != "date"}
        frames.append(part.rename(columns=rename))

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")
    panel = panel.sort_values("date").reset_index(drop=True)
    return panel.ffill().bfill().fillna(0.0)


def prices(panel: pd.DataFrame) -> np.ndarray:
    return panel[[f"{ticker}_close" for ticker in TICKERS]].to_numpy(dtype=float)


def dividends(panel: pd.DataFrame) -> np.ndarray:
    cols = []
    for ticker in TICKERS:
        col = f"{ticker}_dividends"
        cols.append(panel[col] if col in panel else pd.Series(0.0, index=panel.index))
    return pd.concat(cols, axis=1).to_numpy(dtype=float)


def _holding_segments(mask: np.ndarray) -> list[int]:
    segments = []
    current = 0
    for held in mask.astype(bool):
        if held:
            current += 1
        elif current > 0:
            segments.append(current)
            current = 0
    if current > 0:
        segments.append(current)
    return segments


def calculate_holding_time_stats(
    panel: pd.DataFrame,
    weight_history: list[list[float]],
    rebalance_indices: list[int],
    threshold: float = 0.01,
) -> dict:
    dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
    weights = np.asarray(weight_history, dtype=float)
    if len(weights) == 0:
        weights = np.zeros((len(panel), len(TICKERS)), dtype=float)
    weights = weights[: len(panel)]

    clean_rebalances = sorted({int(i) for i in rebalance_indices if 0 <= int(i) < len(panel)})
    intervals = np.diff(clean_rebalances).astype(int).tolist() if len(clean_rebalances) >= 2 else []

    asset_stats = {}
    for idx, ticker in enumerate(TICKERS):
        mask = weights[:, idx] > threshold
        segments = _holding_segments(mask)
        asset_stats[ticker] = {
            "holding_days": int(mask.sum()),
            "holding_ratio": float(mask.mean()) if len(mask) else 0.0,
            "avg_continuous_holding_days": float(np.mean(segments)) if segments else 0.0,
            "max_continuous_holding_days": int(max(segments)) if segments else 0,
            "holding_period_count": int(len(segments)),
        }

    return {
        "threshold": float(threshold),
        "calendar_start": str(dates.iloc[0].date()) if len(dates) else None,
        "calendar_end": str(dates.iloc[-1].date()) if len(dates) else None,
        "total_trading_days": int(len(weights)),
        "rebalance_indices": clean_rebalances,
        "rebalance_dates": [str(dates.iloc[i].date()) for i in clean_rebalances],
        "rebalance_interval_days": {
            "intervals": intervals,
            "avg": float(np.mean(intervals)) if intervals else 0.0,
            "min": int(min(intervals)) if intervals else 0,
            "max": int(max(intervals)) if intervals else 0,
        },
        "asset_holding_days": asset_stats,
    }


def total_return_matrix(panel: pd.DataFrame) -> np.ndarray:
    px = prices(panel)
    div = dividends(panel)
    rets = np.zeros_like(px, dtype=float)
    rets[1:] = (px[1:] + div[1:]) / px[:-1] - 1.0
    return np.nan_to_num(rets, nan=0.0, posinf=0.0, neginf=0.0)


def normalize_weights(weights: np.ndarray) -> np.ndarray:
    w = np.asarray(weights, dtype=float)
    w = np.clip(w, 0.0, None)
    total = float(w.sum())
    if total <= 0:
        return np.ones(len(TICKERS), dtype=float) / len(TICKERS)
    return w / total


def enforce_min_weight(weights: np.ndarray, min_weight: float) -> np.ndarray:
    """Long-only weights with a per-asset minimum, then renormalized."""
    min_weight = float(min_weight)
    if min_weight <= 0:
        return normalize_weights(weights)
    n_assets = len(weights)
    if min_weight * n_assets >= 1.0:
        return np.ones(n_assets, dtype=float) / n_assets
    w = normalize_weights(weights)
    w = np.maximum(w, min_weight)
    return w / w.sum()


def buy_and_hold_curve(panel: pd.DataFrame, weights: np.ndarray, include_dividends: bool = True) -> list[float]:
    px = prices(panel)
    div = dividends(panel)
    w = normalize_weights(weights)
    shares = INITIAL_CASH * w / px[0]
    cash = 0.0
    curve = []
    for i in range(len(panel)):
        if include_dividends:
            cash += float(np.dot(shares, div[i]))
        curve.append(float(cash + np.dot(shares, px[i])))
    return curve


def estimate_mvo_weights(train_panel: pd.DataFrame, risk_free_rate: float = 0.02, max_weight: float = 0.80) -> dict:
    """Long-only random-search MVO, robust enough without scipy dependency."""
    rng = np.random.default_rng(SEED)
    returns = total_return_matrix(train_panel)[1:]
    mu = returns.mean(axis=0) * 252.0
    cov = np.cov(returns.T) * 252.0
    cov = np.nan_to_num(cov, nan=0.0, posinf=0.0, neginf=0.0)
    cov += np.eye(len(TICKERS)) * 1e-8

    candidates = [
        np.ones(len(TICKERS)) / len(TICKERS),
        np.array([1.0, 0.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 0.0, 1.0]),
    ]
    candidates.extend(rng.dirichlet(np.ones(len(TICKERS)), size=25_000))

    best_w = candidates[0]
    best_sharpe = -np.inf
    for weights in candidates:
        weights = normalize_weights(np.minimum(weights, max_weight))
        ret = float(weights @ mu)
        vol = float(np.sqrt(weights @ cov @ weights))
        sharpe = (ret - risk_free_rate) / vol if vol > 0 else -np.inf
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_w = weights

    return {
        "weights": {ticker: float(weight) for ticker, weight in zip(TICKERS, best_w)},
        "expected_annual_return": float(best_w @ mu),
        "expected_annual_volatility": float(np.sqrt(best_w @ cov @ best_w)),
        "expected_sharpe": float(best_sharpe),
        "max_weight": float(max_weight),
    }


class ContinuousPortfolioEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        initial_cash: float = INITIAL_CASH,
        commission_rate: float = COMMISSION_RATE,
        tax_rate: float = ETF_TAX_RATE,
        turnover_penalty: float = 0.02,
        benchmark_weight: float = 1.0,
        drawdown_penalty: float = 0.25,
        min_rebalance_days: int = 20,
        min_weight: float = 0.0,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.tax_rate = float(tax_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.benchmark_weight = float(benchmark_weight)
        self.drawdown_penalty = float(drawdown_penalty)
        self.min_rebalance_days = int(min_rebalance_days)
        self.min_weight = float(min_weight)
        self.price_array = prices(self.panel)
        self.dividend_array = dividends(self.panel)
        self.equal_curve = np.asarray(buy_and_hold_curve(self.panel, np.ones(len(TICKERS)) / len(TICKERS)))
        self.bh_0050_curve = np.asarray(buy_and_hold_curve(self.panel, np.array([1.0, 0.0, 0.0, 0.0])))
        self.feature_cols = []
        for ticker in TICKERS:
            self.feature_cols.extend([f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns])
        obs_dim = len(self.feature_cols) + len(TICKERS) + 6
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(len(TICKERS),), dtype=np.float32)

    def _portfolio_value(self, idx: int) -> float:
        return float(self.cash + np.dot(self.shares, self.price_array[idx]))

    def _weights(self, idx: int) -> np.ndarray:
        value = max(self._portfolio_value(idx), 1.0)
        return self.shares * self.price_array[idx] / value

    def _get_obs(self) -> np.ndarray:
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        value = max(self._portfolio_value(self.step_idx), 1.0)
        peak = max(self.peak_value, value, 1.0)
        state = np.array(
            [
                *self._weights(self.step_idx),
                self.cash / value,
                value / peak - 1.0,
                min(max(self.step_idx - self.last_rebalance_idx, 0), 252) / 252.0,
                value / max(float(self.equal_curve[self.step_idx]), 1.0) - 1.0,
                value / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0,
                self.turnover_ema,
            ],
            dtype=float,
        )
        obs = np.concatenate([features, state])
        return np.clip(np.nan_to_num(obs, nan=0.0, posinf=10.0, neginf=-10.0), -10.0, 10.0).astype(np.float32)

    def _action_to_weights(self, action: np.ndarray) -> np.ndarray:
        raw = (np.asarray(action, dtype=float) + 1.0) / 2.0
        raw = np.clip(raw, 0.0, 1.0)
        return enforce_min_weight(raw, self.min_weight)

    def _rebalance(self, target_weights: np.ndarray, idx: int) -> float:
        px = self.price_array[idx]
        value_before = self._portfolio_value(idx)
        current_values = self.shares * px
        target_values = value_before * target_weights
        deltas = target_values - current_values
        fees = 0.0

        for i, delta in enumerate(deltas):
            if delta >= 0:
                continue
            sell_value = min(-delta, self.shares[i] * px[i])
            if sell_value <= 0:
                continue
            fee_rate = self.commission_rate + self.tax_rate
            fees += sell_value * fee_rate
            self.cash += sell_value * (1.0 - fee_rate)
            self.shares[i] -= sell_value / px[i]

        for i, delta in enumerate(deltas):
            if delta <= 0:
                continue
            buy_value = min(delta, self.cash / (1.0 + self.commission_rate))
            if buy_value <= 0:
                continue
            fees += buy_value * self.commission_rate
            self.cash -= buy_value * (1.0 + self.commission_rate)
            self.shares[i] += buy_value / px[i]

        self.fees_paid += fees
        return float(fees)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = np.zeros(len(TICKERS), dtype=float)
        self.last_rebalance_idx = -10**9
        self.trade_count = 0
        self.fees_paid = 0.0
        self.dividend_cash_received = 0.0
        self.turnover_ema = 0.0
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        self.weight_history = []
        self.rebalance_indices = []
        self._rebalance(enforce_min_weight(np.ones(len(TICKERS)) / len(TICKERS), self.min_weight), self.step_idx)
        self.weight_history.append(self._weights(self.step_idx).tolist())
        self.rebalance_indices.append(int(self.step_idx))
        return self._get_obs(), {}

    def step(self, action):
        previous_value = self._portfolio_value(self.step_idx)
        current_weights = self._weights(self.step_idx)
        target_weights = self._action_to_weights(action)
        turnover = float(np.abs(target_weights - current_weights).sum())
        fees = 0.0
        if self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days and turnover > 0.05:
            fees = self._rebalance(target_weights, self.step_idx)
            self.last_rebalance_idx = self.step_idx
            self.trade_count += 1
            self.rebalance_indices.append(int(self.step_idx))
        self.turnover_ema = 0.95 * self.turnover_ema + 0.05 * turnover

        self.step_idx += 1
        self.dividend_cash_received += float(np.dot(self.shares, self.dividend_array[self.step_idx]))
        self.cash += float(np.dot(self.shares, self.dividend_array[self.step_idx]))

        if self.min_weight > 0:
            post_move_weights = self._weights(self.step_idx)
            if np.any(post_move_weights < self.min_weight * 0.999):
                floor_target = enforce_min_weight(post_move_weights, self.min_weight)
                floor_fees = self._rebalance(floor_target, self.step_idx)
                if floor_fees > 0:
                    fees += floor_fees
                    self.trade_count += 1
                    self.rebalance_indices.append(int(self.step_idx))

        value = self._portfolio_value(self.step_idx)
        self.peak_value = max(self.peak_value, value)
        self.equity_curve.append(float(value))
        self.weight_history.append(self._weights(self.step_idx).tolist())

        daily_return = value / max(previous_value, 1.0) - 1.0
        benchmark_return = self.equal_curve[self.step_idx] / max(self.equal_curve[self.step_idx - 1], 1.0) - 1.0
        drawdown = value / max(self.peak_value, 1.0) - 1.0
        reward = (
            daily_return * 100.0
            + self.benchmark_weight * (daily_return - benchmark_return) * 100.0
            - self.turnover_penalty * turnover
            - self.drawdown_penalty * abs(drawdown)
            - fees / max(previous_value, 1.0)
        )

        terminated = self.step_idx >= len(self.panel) - 1
        info = {
            "portfolio_value": float(value),
            "weights": self.weight_history[-1],
            "trade_executed": fees > 0,
            "fees": fees,
            "turnover": turnover,
            "dividend_cash_received": self.dividend_cash_received,
        }
        return self._get_obs() if not terminated else np.zeros(self.observation_space.shape, dtype=np.float32), float(reward), terminated, False, info


def run_policy(model, env: ContinuousPortfolioEnv) -> dict:
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
    return env_result(env)


def env_result(env: ContinuousPortfolioEnv) -> dict:
    metrics = calculate_backtest_metrics(env.equity_curve, initial_value=INITIAL_CASH)
    final_weights = {ticker: float(weight) for ticker, weight in zip(TICKERS, env.weight_history[-1])}
    return {
        "final_value": float(env.equity_curve[-1]),
        "metrics": metrics,
        "equity_curve": env.equity_curve,
        "weight_history": env.weight_history,
        "holding_time_stats": calculate_holding_time_stats(env.panel, env.weight_history, env.rebalance_indices),
        "final_weights": final_weights,
        "num_rebalances": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "dividend_cash_received": float(env.dividend_cash_received),
    }


def make_chart(payload: dict, output_prefix: Path) -> tuple[str, str]:
    dates = pd.to_datetime(payload["dates"])
    curves = payload["curves"]

    value_path = output_prefix.with_suffix(".png")
    drawdown_path = output_prefix.parent / f"{output_prefix.name}_drawdown.png"

    plt.figure(figsize=(12, 6))
    for name, curve in curves.items():
        plt.plot(dates[: len(curve)], curve, label=name, linewidth=2)
    plt.title(payload["title"])
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(value_path, dpi=150)
    plt.close()

    plt.figure(figsize=(12, 5))
    for name, curve in curves.items():
        arr = np.asarray(curve, dtype=float)
        dd = arr / np.maximum.accumulate(arr) - 1.0
        plt.plot(dates[: len(curve)], dd, label=name, linewidth=2)
    plt.title(f"{payload['title']} Drawdown")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(drawdown_path, dpi=150)
    plt.close()

    return str(value_path), str(drawdown_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="MVO baseline and SAC/TD3 continuous portfolio training.")
    parser.add_argument("--mode", choices=["mvo", "sac", "td3", "all"], default="mvo")
    parser.add_argument("--train-start", default=TRAIN_START)
    parser.add_argument("--train-end", default=TRAIN_END)
    parser.add_argument("--backtest-start", default=BACKTEST_START)
    parser.add_argument("--backtest-end", default=BACKTEST_END)
    parser.add_argument("--download-end", default=DOWNLOAD_END)
    parser.add_argument("--timesteps", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--max-mvo-weight", type=float, default=0.80)
    parser.add_argument("--turnover-penalty", type=float, default=0.02)
    parser.add_argument("--min-rebalance-days", type=int, default=20)
    parser.add_argument("--min-weight", type=float, default=0.0)
    args = parser.parse_args()

    np.random.seed(args.seed)
    stock_data = download_all_stocks(TICKERS, args.train_start, args.download_end)
    train_panel = align_panel(stock_data, args.train_start, args.train_end)
    test_panel = align_panel(stock_data, args.backtest_start, args.backtest_end)
    if len(train_panel) < 200 or len(test_panel) < 60:
        raise RuntimeError(f"Not enough rows: train={len(train_panel)}, backtest={len(test_panel)}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = PROJECT_ROOT / "results"
    model_dir = PROJECT_ROOT / "models" / "portfolio"
    result_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    mvo = estimate_mvo_weights(train_panel, max_weight=args.max_mvo_weight)
    mvo_weights = np.array([mvo["weights"][ticker] for ticker in TICKERS], dtype=float)
    mvo_curve = buy_and_hold_curve(test_panel, mvo_weights, include_dividends=True)
    equal_curve = buy_and_hold_curve(test_panel, np.ones(len(TICKERS)) / len(TICKERS), include_dividends=True)
    bh_0050_curve = buy_and_hold_curve(test_panel, np.array([1.0, 0.0, 0.0, 0.0]), include_dividends=True)
    mvo_payload = {
        "weights": mvo["weights"],
        "train_estimates": mvo,
        "final_value": float(mvo_curve[-1]),
        "metrics": calculate_backtest_metrics(mvo_curve, initial_value=INITIAL_CASH),
        "equity_curve": mvo_curve,
    }

    outputs = {"mvo": mvo_payload}

    if args.mode in ("sac", "td3", "all"):
        for algo_name, algo_cls in (("sac", SAC), ("td3", TD3)):
            if args.mode not in (algo_name, "all"):
                continue
            train_env = ContinuousPortfolioEnv(
                train_panel,
                turnover_penalty=args.turnover_penalty,
                min_rebalance_days=args.min_rebalance_days,
                min_weight=args.min_weight,
            )
            if algo_name == "td3":
                noise = NormalActionNoise(mean=np.zeros(len(TICKERS)), sigma=0.10 * np.ones(len(TICKERS)))
                model = algo_cls("MlpPolicy", train_env, action_noise=noise, seed=args.seed, verbose=1)
            else:
                model = algo_cls("MlpPolicy", train_env, seed=args.seed, verbose=1)
            model.learn(total_timesteps=args.timesteps, progress_bar=False)
            model_path = model_dir / (
                f"portfolio_0050_0056_00713_00878_{algo_name}_continuous_"
                f"{_slug(args.train_start)}_{_slug(args.train_end)}_dji57_dividend_"
                f"turnover{args.turnover_penalty:g}_minreb{args.min_rebalance_days}_minw{args.min_weight:g}"
            )
            model.save(str(model_path))
            test_env = ContinuousPortfolioEnv(
                test_panel,
                turnover_penalty=args.turnover_penalty,
                min_rebalance_days=args.min_rebalance_days,
                min_weight=args.min_weight,
            )
            result = run_policy(model, test_env)
            result["model_path"] = str(model_path)
            outputs[algo_name] = result

    curves = {
        "MVO total return": mvo_curve,
        "Equal B&H total return": equal_curve,
        "0050 B&H total return": bh_0050_curve,
    }
    if "sac" in outputs:
        curves["SAC continuous"] = outputs["sac"]["equity_curve"]
    if "td3" in outputs:
        curves["TD3 continuous"] = outputs["td3"]["equity_curve"]

    chart_payload = {
        "title": "MVO / SAC / TD3 Continuous Portfolio Backtest",
        "dates": [str(pd.Timestamp(d).date()) for d in test_panel["date"]],
        "curves": curves,
    }
    prefix = result_dir / (
        f"portfolio_mvo_sac_td3_{_slug(args.train_start)}_{_slug(args.train_end)}_"
        f"backtest_{_slug(args.backtest_start)}_{_slug(args.backtest_end)}_{stamp}"
    )
    value_chart, drawdown_chart = make_chart(chart_payload, prefix)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tickers": TICKERS,
        "mode": args.mode,
        "requested_train_start": args.train_start,
        "requested_train_end": args.train_end,
        "requested_backtest_start": args.backtest_start,
        "requested_backtest_end": args.backtest_end,
        "actual_train_start": str(pd.Timestamp(train_panel["date"].min()).date()),
        "actual_train_end": str(pd.Timestamp(train_panel["date"].max()).date()),
        "actual_backtest_start": str(pd.Timestamp(test_panel["date"].min()).date()),
        "actual_backtest_end": str(pd.Timestamp(test_panel["date"].max()).date()),
        "train_rows": int(len(train_panel)),
        "backtest_rows": int(len(test_panel)),
        "timesteps": int(args.timesteps),
        "seed": int(args.seed),
        "turnover_penalty": float(args.turnover_penalty),
        "min_rebalance_days": int(args.min_rebalance_days),
        "min_weight": float(args.min_weight),
        "benchmarks": {
            "equal_bh_total": {
                "final_value": float(equal_curve[-1]),
                "metrics": calculate_backtest_metrics(equal_curve, initial_value=INITIAL_CASH),
            },
            "0050_bh_total": {
                "final_value": float(bh_0050_curve[-1]),
                "metrics": calculate_backtest_metrics(bh_0050_curve, initial_value=INITIAL_CASH),
            },
        },
        "results": outputs,
        "value_chart": value_chart,
        "drawdown_chart": drawdown_chart,
    }

    output_file = prefix.with_suffix(".json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    print("=" * 72)
    print("Portfolio MVO/SAC/TD3 complete")
    print(f"Actual train: {payload['actual_train_start']} ~ {payload['actual_train_end']} ({len(train_panel)} rows)")
    print(f"Actual test:  {payload['actual_backtest_start']} ~ {payload['actual_backtest_end']} ({len(test_panel)} rows)")
    for name, result in outputs.items():
        metrics = result["metrics"]
        print(
            f"{name.upper()}: final={result['final_value']:,.0f}, "
            f"return={metrics['total_return']:.2%}, sharpe={metrics['sharpe']:.3f}, mdd={metrics['max_drawdown']:.2%}"
        )
    print(f"Result: {output_file}")
    print(f"Chart:  {value_chart}")
    print(f"DD:     {drawdown_chart}")
    print("=" * 72)


if __name__ == "__main__":
    main()
