#!/usr/bin/env python3
"""Train one Taiwan ticker on a configurable period and backtest it."""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import PORTFOLIO_HOLDINGS
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import EnhancedStockTrainer


DEFAULT_TICKER = "0050.TW"
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"

TIMESTEPS = 100_000
SEED = 42


def _download_end(end: str) -> str:
    # yfinance treats end as exclusive; use the next day to include the
    # requested backtest end when data exists for that date.
    return (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def _date_slug(date: str) -> str:
    return date.replace("-", "")


def _slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Train one Taiwan ticker and backtest it.")
    parser.add_argument("--ticker", default=DEFAULT_TICKER)
    parser.add_argument("--agent", choices=["ppo", "a2c", "dqn"], default="ppo")
    parser.add_argument("--timesteps", type=int, default=TIMESTEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--train-start", default=TRAIN_START)
    parser.add_argument("--train-end", default=TRAIN_END)
    parser.add_argument("--backtest-start", default=BACKTEST_START)
    parser.add_argument("--backtest-end", default=BACKTEST_END)
    args = parser.parse_args()

    ticker = args.ticker
    ticker_slug = ticker.replace(".", "_")
    train_start = args.train_start
    train_end = args.train_end
    backtest_start = args.backtest_start
    backtest_end = args.backtest_end

    print("=" * 72)
    print(f"{ticker} FinRL training/backtest")
    print(f"Train:    {train_start} ~ {train_end}")
    print(f"Backtest: {backtest_start} ~ {backtest_end}")
    print(f"Agent:    {args.agent.upper()}")
    print(f"Steps:    {args.timesteps:,}")
    print(f"Seed:     {args.seed}")
    print("=" * 72)

    stock_data = download_all_stocks([ticker], train_start, _download_end(backtest_end))
    if ticker not in stock_data:
        raise RuntimeError(f"Unable to load data for {ticker}")

    full_df = stock_data[ticker].copy()
    train_df = _slice_by_date(full_df, train_start, train_end)
    test_df = _slice_by_date(full_df, backtest_start, backtest_end)

    if train_df.empty:
        raise RuntimeError("Training date range has no data")
    if test_df.empty:
        raise RuntimeError("Backtest date range has no data")

    print(f"Loaded rows: train={len(train_df)}, backtest={len(test_df)}")
    print(
        "Actual ranges: "
        f"train={train_df['date'].min().date()}~{train_df['date'].max().date()}, "
        f"backtest={test_df['date'].min().date()}~{test_df['date'].max().date()}"
    )

    info = PORTFOLIO_HOLDINGS.get(ticker, {})
    trainer = EnhancedStockTrainer(
        ticker=ticker,
        df=train_df,
        agent_type=args.agent,
        initial_shares=info.get("shares", 0),
        enable_risk_manager=False,
        enable_enhanced_reward=True,
        seed=args.seed,
    )

    model_path = (
        PROJECT_ROOT
        / "models"
        / "portfolio"
        / f"{ticker_slug}_{_date_slug(train_start)}_{_date_slug(train_end)}_{args.agent}_enhanced"
    )
    model_path.parent.mkdir(parents=True, exist_ok=True)

    stats = trainer.train(timesteps=args.timesteps, save_path=str(model_path), verbose=1)
    result = trainer.backtest(df_test=test_df)

    payload = {
        "ticker": ticker,
        "train_start": train_start,
        "train_end": train_end,
        "backtest_start": backtest_start,
        "backtest_end": backtest_end,
        "actual_train_start": str(train_df["date"].min().date()),
        "actual_train_end": str(train_df["date"].max().date()),
        "actual_backtest_start": str(test_df["date"].min().date()),
        "actual_backtest_end": str(test_df["date"].max().date()),
        "train_rows": int(len(train_df)),
        "backtest_rows": int(len(test_df)),
        "model_path": str(model_path),
        "seed": args.seed,
        "requested_timesteps": args.timesteps,
        **stats,
        **result,
    }

    output_file = (
        PROJECT_ROOT
        / "results"
        / (
            f"training_{ticker_slug}_{_date_slug(train_start)}_{_date_slug(train_end)}_"
            f"{args.agent}_backtest_{_date_slug(backtest_start)}_{_date_slug(backtest_end)}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print("=" * 72)
    print("Done")
    print(f"Model:  {model_path}")
    print(f"Result: {output_file}")
    print(f"Final value: {result.get('final_value', 0):,.0f}")
    print(f"Trades: {result.get('num_trades', 0)}")
    print("=" * 72)


if __name__ == "__main__":
    main()
