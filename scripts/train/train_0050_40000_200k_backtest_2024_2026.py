#!/usr/bin/env python3
"""Train 0050.TW from scratch with max_position=40000 and 200k steps."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from environments.reward_function_v3 import DynamicRewardShaper
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from portfolio_config import PORTFOLIO_HOLDINGS, LEARNING_RATE
from portfolio_data_loader import download_all_stocks
from safe_ppo import SafeActorCriticPolicy, GradientClipCallback


TICKER = "0050.TW"
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
TIMESTEPS = 200_000
MAX_POSITION = 40_000
MODEL_PATH = PROJECT_ROOT / "models" / "portfolio" / "0050_TW_2016_2023_40000_200k_action9"


def clean_slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def make_reward(total_steps: int) -> DynamicRewardShaper:
    reward = DynamicRewardShaper(
        trade_penalty=0.003,
        trade_reward=0.0,
        sortino_weight=0.25,
        calmar_weight=0.20,
        volatility_penalty=0.08,
        drawdown_penalty=0.12,
        holding_bonus=0.45,
        trend_bull_bonus=0.18,
        trend_bear_penalty=0.03,
        init_reward_scale=1.15,
        final_reward_scale=0.55,
        momentum_window=20,
    )
    reward.set_total_steps(total_steps)
    return reward


def make_env(df: pd.DataFrame, reward: DynamicRewardShaper, initial_shares: int) -> TaiwanStockTradingEnv:
    return TaiwanStockTradingEnv(
        df=df,
        initial_balance=1_000_000,
        max_position=MAX_POSITION,
        trade_unit=1000,
        price_limit=0.10,
        commission_rate=0.001425,
        tax_rate=0.003,
        lookback_window=60,
        initial_shares=initial_shares,
        initial_avg_cost=0.0,
        reward_func=reward,
        enable_risk_manager=False,
        crash_window=15,
    )


def run_backtest(model: PPO, test_df: pd.DataFrame, initial_shares: int) -> dict:
    reward = make_reward(TIMESTEPS)
    env = make_env(test_df, reward, initial_shares)
    obs, _ = env.reset()

    done = False
    total_reward = 0.0
    trades = 0
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward_value, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        total_reward += float(reward_value)
        if info.get("trade_executed"):
            trades += 1

    final_price = float(test_df.iloc[-1]["close"])
    final_value = env.balance + env.position * final_price
    return {
        "final_value": final_value,
        "total_reward": total_reward,
        "num_trades": trades,
        "final_position": int(env.position),
        "final_balance": float(env.balance),
    }


def buy_and_hold_metrics(df: pd.DataFrame, initial_cash: float = 1_000_000.0) -> dict:
    first = float(df.iloc[0]["close"])
    last = float(df.iloc[-1]["close"])
    shares = int(initial_cash // first)
    cash = initial_cash - shares * first
    final_value = cash + shares * last
    return {
        "bh_shares": shares,
        "bh_final_value": final_value,
        "bh_total_return": final_value / initial_cash - 1,
    }


def main() -> None:
    print("=" * 72)
    print("0050.TW retrain from scratch")
    print(f"Train: {TRAIN_START} ~ {TRAIN_END}")
    print(f"Backtest: {BACKTEST_START} ~ {BACKTEST_END}")
    print(f"Steps: {TIMESTEPS:,}, max_position={MAX_POSITION:,}, actions=9")
    print("=" * 72)

    stock_data = download_all_stocks([TICKER], TRAIN_START, DOWNLOAD_END)
    full_df = stock_data[TICKER]
    train_df = clean_slice(full_df, TRAIN_START, TRAIN_END)
    test_df = clean_slice(full_df, BACKTEST_START, BACKTEST_END)
    info = PORTFOLIO_HOLDINGS.get(TICKER, {})
    initial_shares = info.get("shares", 0)

    train_reward = make_reward(TIMESTEPS)
    env = make_env(train_df, train_reward, initial_shares)
    model = PPO(
        SafeActorCriticPolicy,
        env,
        policy_kwargs={
            "log_clip_min": -20.0,
            "log_clip_max": 20.0,
            "net_arch": [256, 256],
        },
        learning_rate=LEARNING_RATE,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        verbose=1,
    )
    model.learn(
        total_timesteps=TIMESTEPS,
        progress_bar=False,
        callback=GradientClipCallback(max_norm=1.0),
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(MODEL_PATH))

    result = run_backtest(model, test_df, initial_shares)
    bh = buy_and_hold_metrics(test_df)
    payload = {
        "ticker": TICKER,
        "train_start": TRAIN_START,
        "train_end": TRAIN_END,
        "backtest_start": BACKTEST_START,
        "backtest_end": BACKTEST_END,
        "actual_train_start": str(train_df["date"].min().date()),
        "actual_train_end": str(train_df["date"].max().date()),
        "actual_backtest_start": str(test_df["date"].min().date()),
        "actual_backtest_end": str(test_df["date"].max().date()),
        "train_rows": int(len(train_df)),
        "backtest_rows": int(len(test_df)),
        "model_path": str(MODEL_PATH.resolve()),
        "timesteps": TIMESTEPS,
        "max_position": MAX_POSITION,
        "action_space": 9,
        **result,
        **bh,
    }
    payload["rl_total_return"] = payload["final_value"] / 1_000_000.0 - 1
    payload["rl_minus_bh"] = payload["rl_total_return"] - payload["bh_total_return"]

    output_file = (
        PROJECT_ROOT
        / "results"
        / f"retrain_0050_40000_200k_backtest_2024_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps(payload, indent=2, default=str))
    print(f"RESULT_FILE={output_file}")


if __name__ == "__main__":
    main()
