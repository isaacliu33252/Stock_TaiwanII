#!/usr/bin/env python3
"""Fine-tune the 0050 model with lower turnover reward shaping."""

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
from portfolio_config import PORTFOLIO_HOLDINGS
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import EnhancedStockTrainer
from safe_ppo import GradientClipCallback


TICKER = "0050.TW"
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
BASE_MODEL = PROJECT_ROOT / "models" / "portfolio" / "0050_TW_2016_2023_enhanced"
TUNED_MODEL = PROJECT_ROOT / "models" / "portfolio" / "0050_TW_2016_2023_finetuned_low_turnover"
FINE_TUNE_STEPS = 50_000


def clean_slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def make_reward(total_steps: int) -> DynamicRewardShaper:
    reward = DynamicRewardShaper(
        trade_penalty=0.004,
        trade_reward=0.0,
        sortino_weight=0.25,
        calmar_weight=0.20,
        volatility_penalty=0.08,
        drawdown_penalty=0.12,
        holding_bonus=0.45,
        trend_bull_bonus=0.18,
        trend_bear_penalty=0.03,
        init_reward_scale=1.0,
        final_reward_scale=0.55,
        momentum_window=20,
    )
    reward.set_total_steps(total_steps)
    return reward


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
    print("0050.TW low-turnover fine tune")
    print(f"Base model: {BASE_MODEL}")
    print(f"Fine-tune steps: {FINE_TUNE_STEPS:,}")
    print("=" * 72)

    stock_data = download_all_stocks([TICKER], TRAIN_START, DOWNLOAD_END)
    full_df = stock_data[TICKER]
    train_df = clean_slice(full_df, TRAIN_START, TRAIN_END)
    test_df = clean_slice(full_df, BACKTEST_START, BACKTEST_END)

    info = PORTFOLIO_HOLDINGS.get(TICKER, {})
    initial_shares = info.get("shares", 0)
    reward = make_reward(FINE_TUNE_STEPS)
    env = TaiwanStockTradingEnv(
        df=train_df,
        initial_balance=1_000_000,
        max_position=40000,
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

    model = PPO.load(str(BASE_MODEL), env=env)
    model.learn(
        total_timesteps=FINE_TUNE_STEPS,
        progress_bar=False,
        reset_num_timesteps=False,
        callback=GradientClipCallback(max_norm=1.0),
    )
    TUNED_MODEL.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(TUNED_MODEL))

    trainer = EnhancedStockTrainer(
        TICKER,
        train_df,
        "ppo",
        initial_shares=initial_shares,
        enable_risk_manager=False,
        enable_enhanced_reward=True,
    )
    trainer.reward_func = make_reward(FINE_TUNE_STEPS)
    trainer.model = model
    trainer.timesteps = 100_000 + FINE_TUNE_STEPS
    result = trainer.backtest(df_test=test_df)
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
        "base_model": str(BASE_MODEL.resolve()),
        "tuned_model": str(TUNED_MODEL.resolve()),
        "base_steps": 100_000,
        "fine_tune_steps": FINE_TUNE_STEPS,
        **result,
        **bh,
    }
    payload["rl_total_return"] = payload["final_value"] / 1_000_000.0 - 1
    payload["rl_minus_bh"] = payload["rl_total_return"] - payload["bh_total_return"]

    output_file = (
        PROJECT_ROOT
        / "results"
        / f"finetune_0050_low_turnover_2016_2023_backtest_2024_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps(payload, indent=2, default=str))
    print(f"RESULT_FILE={output_file}")


if __name__ == "__main__":
    main()
