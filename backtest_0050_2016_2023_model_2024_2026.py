#!/usr/bin/env python3
"""Backtest the existing 0050 2016-2023 model on clean 2024-2026 data."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import PORTFOLIO_HOLDINGS
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import EnhancedStockTrainer, build_experiment_metadata


TICKER = "0050.TW"
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
MODEL_PATH = PROJECT_ROOT / "models" / "portfolio" / "0050_TW_2016_2023_enhanced"
SEED = 42


def clean_slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def main() -> None:
    stock_data = download_all_stocks([TICKER], TRAIN_START, DOWNLOAD_END)
    full_df = stock_data[TICKER]
    train_df = clean_slice(full_df, TRAIN_START, TRAIN_END)
    test_df = clean_slice(full_df, BACKTEST_START, BACKTEST_END)

    info = PORTFOLIO_HOLDINGS.get(TICKER, {})
    trainer = EnhancedStockTrainer(
        TICKER,
        train_df,
        "ppo",
        initial_shares=info.get("shares", 0),
        enable_risk_manager=False,
        enable_enhanced_reward=True,
        seed=SEED,
    )
    trainer.model = PPO.load(str(MODEL_PATH))
    trainer.timesteps = 100_000
    result = trainer.backtest(df_test=test_df)

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
        "total_steps": 100_000,
        "metadata": build_experiment_metadata(
            ticker=TICKER,
            agent_type="ppo",
            timesteps=100_000,
            seed=SEED,
            train_rows=len(train_df),
            test_rows=len(test_df),
            model_path=str(MODEL_PATH.resolve()),
            reward_config={"enhanced_reward": True},
            env_config={"risk_manager": False, "action_space": 9},
        ),
        **result,
    }

    output_file = (
        PROJECT_ROOT
        / "results"
        / f"training_0050_2016_2023_backtest_2024_2026_fixed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps(payload, indent=2, default=str))
    print(f"RESULT_FILE={output_file}")


if __name__ == "__main__":
    main()
