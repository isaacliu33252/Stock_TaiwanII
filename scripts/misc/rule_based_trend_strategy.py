#!/usr/bin/env python3
"""Three-position long-horizon trend baseline for Taiwan ETFs."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics, calculate_buy_and_hold_metrics


TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"


def slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].reset_index(drop=True)


def target_position(row: pd.Series, defensive_position: float) -> float:
    close_ma120 = float(row.get("close_ma120_ratio", 0.0))
    close_ma240 = float(row.get("close_ma240_ratio", 0.0))
    ma60_ma240 = float(row.get("ma60_ma240_ratio", 0.0))
    momentum_126 = float(row.get("momentum_126", 0.0))
    momentum_252 = float(row.get("momentum_252", 0.0))
    rolling_mdd_63 = float(row.get("rolling_mdd_63", 0.0))

    strong_uptrend = (
        close_ma120 > 0.0
        and close_ma240 > 0.0
        and ma60_ma240 > 0.0
        and momentum_126 > 0.0
        and momentum_252 > 0.0
    )
    risk_off = close_ma240 < -0.05 or rolling_mdd_63 < -0.15
    neutral = close_ma240 > 0.0 or close_ma120 > 0.0

    if strong_uptrend:
        return 1.0
    if risk_off:
        return 0.0
    if neutral:
        return defensive_position
    return defensive_position


def run_strategy(
    df: pd.DataFrame,
    initial_cash: float = 1_000_000.0,
    trade_unit: int = 1000,
    commission_rate: float = 0.001425,
    tax_rate: float = 0.003,
    min_rebalance_days: int = 60,
    defensive_position: float = 0.5,
) -> dict:
    cash = float(initial_cash)
    position = 0
    last_rebalance_idx = -10**9
    equity_curve = []
    trades = []

    for idx, row in df.iterrows():
        close = float(row["close"])
        date = row["date"]
        equity_before = cash + position * close

        desired_ratio = target_position(row, defensive_position)
        can_rebalance = idx - last_rebalance_idx >= min_rebalance_days
        if can_rebalance:
            target_value = equity_before * desired_ratio
            target_shares = int(target_value / close // trade_unit) * trade_unit
            delta = target_shares - position

            if abs(delta) >= trade_unit:
                if delta > 0:
                    trade_price = close * 1.001
                    max_affordable = int(cash / (trade_price * (1 + commission_rate)) // trade_unit) * trade_unit
                    shares = min(delta, max_affordable)
                    if shares >= trade_unit:
                        cost = shares * trade_price
                        fee = cost * commission_rate
                        cash -= cost + fee
                        position += shares
                        trades.append({
                            "date": str(pd.Timestamp(date).date()),
                            "type": "BUY",
                            "shares": int(shares),
                            "price": trade_price,
                            "fee": fee,
                            "tax": 0.0,
                            "target_ratio": desired_ratio,
                        })
                        last_rebalance_idx = idx
                else:
                    shares = min(-delta, position)
                    shares = int(shares // trade_unit) * trade_unit
                    if shares >= trade_unit:
                        trade_price = close * 0.999
                        proceeds = shares * trade_price
                        fee = proceeds * commission_rate
                        tax = proceeds * tax_rate
                        cash += proceeds - fee - tax
                        position -= shares
                        trades.append({
                            "date": str(pd.Timestamp(date).date()),
                            "type": "SELL",
                            "shares": int(shares),
                            "price": trade_price,
                            "fee": fee,
                            "tax": tax,
                            "target_ratio": desired_ratio,
                        })
                        last_rebalance_idx = idx

        equity_curve.append(float(cash + position * close))

    final_value = equity_curve[-1] if equity_curve else initial_cash
    metrics = calculate_backtest_metrics(equity_curve, initial_value=initial_cash)
    bh = calculate_buy_and_hold_metrics(df, initial_value=initial_cash)
    fees_paid = float(sum(t["fee"] + t["tax"] for t in trades))

    return {
        "final_value": final_value,
        "position": int(position),
        "cash": cash,
        "num_trades": len(trades),
        "fees_paid_estimate": fees_paid,
        "strategy_metrics": metrics,
        "buy_and_hold_metrics": {k: v for k, v in bh.items() if k != "equity_curve"},
        "excess_return_vs_bh": metrics.get("total_return", 0.0) - bh.get("total_return", 0.0),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a 0/50/100 long-horizon trend baseline.")
    parser.add_argument("--ticker", default="0056.TW")
    parser.add_argument("--min-rebalance-days", type=int, default=60)
    parser.add_argument("--defensive-position", type=float, default=0.5)
    args = parser.parse_args()

    ticker = args.ticker
    ticker_slug = ticker.replace(".", "_")
    stock_data = download_all_stocks([ticker], TRAIN_START, DOWNLOAD_END)
    if ticker not in stock_data:
        raise RuntimeError(f"Unable to load data for {ticker}")

    full_df = stock_data[ticker].copy()
    train_df = slice_by_date(full_df, TRAIN_START, TRAIN_END)
    test_df = slice_by_date(full_df, BACKTEST_START, BACKTEST_END)
    if train_df.empty or test_df.empty:
        raise RuntimeError("Date range has no data")

    result = run_strategy(
        test_df,
        min_rebalance_days=args.min_rebalance_days,
        defensive_position=args.defensive_position,
    )
    payload = {
        "ticker": ticker,
        "strategy": "three_position_long_horizon_trend",
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
        "min_rebalance_days": args.min_rebalance_days,
        "defensive_position": args.defensive_position,
        **result,
    }

    output_file = (
        PROJECT_ROOT
        / "results"
        / f"rule_three_position_{ticker_slug}_backtest_2024_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps({
        "ticker": payload["ticker"],
        "result_file": str(output_file),
        "final_value": payload["final_value"],
        "num_trades": payload["num_trades"],
        "total_return": payload["strategy_metrics"]["total_return"],
        "sharpe": payload["strategy_metrics"]["sharpe"],
        "max_drawdown": payload["strategy_metrics"]["max_drawdown"],
        "excess_return_vs_bh": payload["excess_return_vs_bh"],
        "fees_paid_estimate": payload["fees_paid_estimate"],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
