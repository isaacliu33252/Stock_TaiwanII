#!/usr/bin/env python3
"""
FinRL-X style demo backtest
===========================
用本地 cache + 已訓練模型，走：
RLCachedStrategy -> StrategyResult -> BacktestEngine
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from FinRL import BacktestConfig, BacktestEngine, RLPortfolioConfig, RLCachedStrategy

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
OUTPUT_DIR = PROJECT_ROOT / "results" / "finrlx_demo"


def load_cached_ohlcv(ticker: str) -> pd.DataFrame:
    patterns = [
        f"{ticker}_*_1d.parquet",
        f"{ticker.replace('.TW', '')}_TW_*_1d.parquet",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(sorted(CACHE_DIR.glob(pattern)))
    if not matches:
        raise FileNotFoundError(f"No cached parquet found for {ticker} in {CACHE_DIR}")

    df = pd.read_parquet(matches[-1]).copy()
    if "date" not in df.columns:
        df = df.reset_index()
        if "date" not in df.columns:
            df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df.sort_values("date").reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local FinRL-X style backtest.")
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--agent-type", default="sac", choices=["ppo", "a2c", "sac", "td3"])
    parser.add_argument("--action-mode", default="continuous", choices=["discrete", "continuous"])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--max-position", type=int, default=40_000)
    parser.add_argument("--trade-unit", type=int, default=1_000)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = {args.ticker: load_cached_ohlcv(args.ticker)}
    strategy = RLCachedStrategy(
        RLPortfolioConfig(
            name=f"{args.agent_type}_{args.ticker}",
            agent_type=args.agent_type,
            action_mode=args.action_mode,
            initial_balance=args.initial_capital,
            max_position=args.max_position,
            trade_unit=args.trade_unit,
        ),
        model_path=args.model_path,
    )

    strategy_result = strategy.generate_weights(data, target_date=args.end_date)
    engine = BacktestEngine(
        BacktestConfig(
            start_date=args.start_date,
            end_date=args.end_date,
            initial_capital=args.initial_capital,
            benchmark_tickers=[args.ticker],
        )
    )
    backtest_result = engine.run(strategy_result)

    print(backtest_result.summary())

    strategy_result.weights.to_csv(output_dir / "rl_weights.csv")
    backtest_result.portfolio_values.to_csv(output_dir / "rl_equity.csv", header=True)
    if backtest_result.benchmark_values is not None:
        backtest_result.benchmark_values.to_csv(output_dir / "benchmark_equity.csv", header=True)
    if not backtest_result.trades.empty:
        backtest_result.trades.to_csv(output_dir / "trades.csv")

    summary = {
        "strategy": strategy_result.strategy_name,
        "ticker": args.ticker,
        "model_path": args.model_path,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "metrics": backtest_result.metrics,
    }
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=float)


if __name__ == "__main__":
    main()
