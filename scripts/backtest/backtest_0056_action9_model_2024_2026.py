#!/usr/bin/env python3
"""Backtest the existing 0056.TW action-9 model on 2024-2026 data."""

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
from train_0056_40000_200k_backtest_2024_2026 import (
    BACKTEST_END,
    BACKTEST_START,
    MAX_POSITION,
    TIMESTEPS,
    TRAIN_END,
    TRAIN_START,
    buy_and_hold_metrics,
    clean_slice,
    run_backtest,
)


TICKER = "0056.TW"
DOWNLOAD_END = "2026-05-09"
MODEL_PATH = PROJECT_ROOT / "models" / "portfolio" / "0056_TW_2016_2023_40000_200k_action9"


def main() -> None:
    if not MODEL_PATH.with_suffix(".zip").exists():
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}.zip")

    stock_data = download_all_stocks([TICKER], TRAIN_START, DOWNLOAD_END)
    if TICKER not in stock_data:
        raise RuntimeError(f"Unable to load data for {TICKER}")

    full_df = stock_data[TICKER]
    train_df = clean_slice(full_df, TRAIN_START, TRAIN_END)
    test_df = clean_slice(full_df, BACKTEST_START, BACKTEST_END)
    if test_df.empty:
        raise RuntimeError("Backtest date range has no data")

    info = PORTFOLIO_HOLDINGS.get(TICKER, {})
    initial_shares = info.get("shares", 0)
    model = PPO.load(str(MODEL_PATH))

    result = run_backtest(model, test_df, initial_shares)
    bh = buy_and_hold_metrics(test_df)
    payload = {
        "ticker": TICKER,
        "train_start": TRAIN_START,
        "train_end": TRAIN_END,
        "backtest_start": BACKTEST_START,
        "backtest_end": BACKTEST_END,
        "actual_train_start": str(train_df["date"].min().date()) if not train_df.empty else None,
        "actual_train_end": str(train_df["date"].max().date()) if not train_df.empty else None,
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
        / f"backtest_0056_action9_model_2024_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps(payload, indent=2, default=str))
    print(f"RESULT_FILE={output_file}")


if __name__ == "__main__":
    main()
