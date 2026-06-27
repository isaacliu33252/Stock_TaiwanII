#!/usr/bin/env python3
"""Backtest a 0050 model on a TWII-based proxy path covering the 2008 crisis."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
from gymnasium import spaces
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_train_v2 import calculate_backtest_metrics, calculate_buy_and_hold_metrics
from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv as Action9TaiwanStockEnv
from twii_proxy_utils import DEFAULT_TWII_MARKET_CACHE, build_0050_twii_proxy_df


TICKER = "0050.TW"
DEFAULT_START = "2007-07-01"
DEFAULT_END = "2010-12-31"
DEFAULT_MODEL = (
    PROJECT_ROOT / "FinRL" / "models" / "portfolio" / "0050_TW_20030101_20231231_ppo_enhanced.zip"
)


class LegacyAction952Env(Action9TaiwanStockEnv):
    """Compatibility wrapper for the older 52-dim 0050 action-9 models."""

    LEGACY_SENTIMENT_FEATURES = [
        "twse_index_return",
        "twse_index_volume_change",
        "sector_correlation",
        "market_volatility",
    ]

    def __init__(self, df: pd.DataFrame):
        super().__init__(
            df=df,
            initial_balance=1_000_000,
            max_position=40_000,
            trade_unit=1000,
            price_limit=0.10,
            commission_rate=0.001425,
            tax_rate=0.003,
            lookback_window=60,
            enable_risk_manager=False,
            crash_window=15,
            turnover_penalty=0.01,
            min_hold_days=20,
            short_hold_penalty=0.02,
        )
        self.sentiment_features = self.LEGACY_SENTIMENT_FEATURES.copy()
        self.sentiment_features_available = [c for c in self.sentiment_features if c in self.df.columns]
        self.state_dim = 52
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(52,), dtype=np.float32)

    def step(self, action):
        state, reward, terminated, truncated, info = super().step(action)
        if terminated and self.current_step < self.max_steps:
            terminated = False
            state = self._create_state()
        return state, reward, terminated, truncated, info


def _resolve_model_path(raw: str | Path) -> Path:
    candidate = Path(raw)
    if candidate.exists():
        return candidate
    if candidate.suffix != ".zip":
        zipped = candidate.with_suffix(".zip")
        if zipped.exists():
            return zipped
    raise FileNotFoundError(f"Unable to locate model: {raw}")


def _run_backtest(model: PPO, df: pd.DataFrame) -> dict:
    env = LegacyAction952Env(df)
    obs, _ = env.reset()
    done = False
    total_reward = 0.0
    equity_curve = [float(env.balance + env.position * df.iloc[0]["close"])]
    trade_count = 0

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        total_reward += float(reward)
        equity_curve.append(float(info.get("portfolio_value", equity_curve[-1])))
        if info.get("trade_executed"):
            trade_count += 1

    final_price = float(df.iloc[-1]["close"])
    final_value = float(env.balance + env.position * final_price)
    rl_metrics = calculate_backtest_metrics(equity_curve, initial_value=1_000_000)
    bh_metrics = calculate_buy_and_hold_metrics(df, initial_value=1_000_000)

    fees_paid = 0.0
    for trade in env.trade_history:
        trade_value = float(trade.get("price", 0.0)) * float(trade.get("shares", 0.0))
        fees_paid += trade_value * env.commission_rate
        trade_type = str(trade.get("type", "")).upper()
        if trade_type.startswith("SELL") or (
            trade_type.startswith("TARGET_") and float(trade.get("pnl", 0.0)) != 0.0
        ):
            fees_paid += trade_value * env.tax_rate

    return {
        "final_value": final_value,
        "total_reward": total_reward,
        "num_trades": trade_count,
        "final_position": int(env.position),
        "rl_metrics": rl_metrics,
        "buy_and_hold_metrics": {k: v for k, v in bh_metrics.items() if k != "equity_curve"},
        "excess_return_vs_bh": rl_metrics.get("total_return", 0.0) - bh_metrics.get("total_return", 0.0),
        "fees_paid_estimate": fees_paid,
        "turnover_trades": len(env.trade_history),
        "equity_curve": equity_curve,
        "trade_history": env.trade_history,
        "dividend_cash_received": float(env.dividend_cash_received),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest 0050 model on a TWII proxy path.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    args = parser.parse_args()

    model_path = _resolve_model_path(args.model)
    proxy_df, market = build_0050_twii_proxy_df(args.start, args.end)
    model = PPO.load(str(model_path))
    result = _run_backtest(model, proxy_df)

    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"backtest_0050_twii_proxy_{args.start.replace('-', '')}_{args.end.replace('-', '')}_{stamp}.json"

    payload = {
        "experiment": "0050_twii_proxy_2008_backtest",
        "ticker": TICKER,
        "proxy_asset": "^TWII",
        "proxy_method": "0050 close path approximated from TWII daily returns",
        "model_path": str(model_path.resolve()),
        "twii_market_cache": str(DEFAULT_TWII_MARKET_CACHE.resolve()),
        "requested_start": args.start,
        "requested_end": args.end,
        "actual_start": str(proxy_df["date"].min().date()),
        "actual_end": str(proxy_df["date"].max().date()),
        "rows": int(len(proxy_df)),
        "market_rows": int(len(market)),
        "limitations": [
            "Proxy uses TWII daily returns rather than real 0050 ETF history.",
            "Proxy volume and intraday range are synthesized from TWII market features.",
            "This is a stress test, not a tradable historical replay of the actual ETF.",
        ],
        **result,
    }

    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)

    rl = result.get("rl_metrics", {})
    bh = result.get("buy_and_hold_metrics", {})
    print("=" * 72)
    print("0050 TWII proxy backtest complete")
    print(f"Range: {payload['actual_start']} ~ {payload['actual_end']} ({payload['rows']} rows)")
    print(f"RL final: {result.get('final_value', 0):,.0f}")
    print(
        "RL metrics: "
        f"return={rl.get('total_return', 0):.2%}, "
        f"annual={rl.get('annual_return', 0):.2%}, "
        f"sharpe={rl.get('sharpe', 0):.3f}, "
        f"mdd={rl.get('max_drawdown', 0):.2%}"
    )
    print(
        "B&H metrics: "
        f"return={bh.get('total_return', 0):.2%}, "
        f"annual={bh.get('annual_return', 0):.2%}, "
        f"sharpe={bh.get('sharpe', 0):.3f}, "
        f"mdd={bh.get('max_drawdown', 0):.2%}"
    )
    print(f"Trades: {result.get('num_trades', 0)}, fees: {result.get('fees_paid_estimate', 0):,.0f}")
    print(f"Result: {output_file}")
    print("=" * 72)


if __name__ == "__main__":
    main()
