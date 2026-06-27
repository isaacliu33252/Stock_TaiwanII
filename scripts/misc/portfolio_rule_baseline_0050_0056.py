#!/usr/bin/env python3
"""Rule-based 0050/0056 monthly allocation baseline."""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics


TICKERS = ["0050.TW", "0056.TW"]
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"


def clean_slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["date", "close"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def align_data(stock_data: dict[str, pd.DataFrame], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker, df in stock_data.items():
        s = clean_slice(df, start, end)
        cols = [
            "date",
            "close",
            "momentum_63",
            "momentum_126",
            "momentum_252",
            "close_ma240_ratio",
            "rolling_mdd_63",
        ]
        missing = [c for c in cols if c not in s.columns]
        if missing:
            raise RuntimeError(f"{ticker} missing columns: {missing}")
        s = s[cols].copy()
        s.columns = ["date"] + [f"{c}_{ticker[:4]}" for c in cols[1:]]
        frames.append(s)

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="date", how="inner")
    return merged.sort_values("date").reset_index(drop=True)


def decide_weights(row: pd.Series) -> dict[str, float]:
    mom_0050 = 0.35 * row["momentum_63_0050"] + 0.40 * row["momentum_126_0050"] + 0.25 * row["momentum_252_0050"]
    mom_0056 = 0.35 * row["momentum_63_0056"] + 0.40 * row["momentum_126_0056"] + 0.25 * row["momentum_252_0056"]
    risk_0050 = row["close_ma240_ratio_0050"] < -0.05 or row["rolling_mdd_63_0050"] < -0.15
    risk_0056 = row["close_ma240_ratio_0056"] < -0.05 or row["rolling_mdd_63_0056"] < -0.15

    if risk_0050 and risk_0056:
        return {"0050": 0.25, "0056": 0.25, "cash": 0.50}
    if mom_0050 > mom_0056 + 0.03 and not risk_0050:
        return {"0050": 0.70, "0056": 0.30, "cash": 0.00}
    if mom_0056 > mom_0050 + 0.03 and not risk_0056:
        return {"0050": 0.30, "0056": 0.70, "cash": 0.00}
    if risk_0050 and not risk_0056:
        return {"0050": 0.10, "0056": 0.60, "cash": 0.30}
    if risk_0056 and not risk_0050:
        return {"0050": 0.60, "0056": 0.10, "cash": 0.30}
    return {"0050": 0.50, "0056": 0.50, "cash": 0.00}


def run_strategy(
    df: pd.DataFrame,
    initial_cash: float = 1_000_000.0,
    trade_unit: int = 1000,
    commission_rate: float = 0.001425,
    tax_rate: float = 0.003,
    rebalance_days: int = 20,
) -> dict:
    cash = float(initial_cash)
    shares = {"0050": 0, "0056": 0}
    trades = []
    equity_curve = []
    last_rebalance = -10**9

    for idx, row in df.iterrows():
        prices = {
            "0050": float(row["close_0050"]),
            "0056": float(row["close_0056"]),
        }
        equity = cash + shares["0050"] * prices["0050"] + shares["0056"] * prices["0056"]

        if idx - last_rebalance >= rebalance_days:
            weights = decide_weights(row)
            for asset in ("0050", "0056"):
                target_value = equity * weights[asset]
                target_shares = int(target_value / prices[asset] // trade_unit) * trade_unit
                delta = target_shares - shares[asset]

                if delta < 0:
                    sell_shares = int((-delta) // trade_unit) * trade_unit
                    if sell_shares > 0:
                        trade_price = prices[asset] * 0.999
                        proceeds = sell_shares * trade_price
                        fee = proceeds * commission_rate
                        tax = proceeds * tax_rate
                        cash += proceeds - fee - tax
                        shares[asset] -= sell_shares
                        trades.append({
                            "date": str(pd.Timestamp(row["date"]).date()),
                            "asset": asset,
                            "type": "SELL",
                            "shares": sell_shares,
                            "price": trade_price,
                            "fee": fee,
                            "tax": tax,
                            "weights": weights,
                        })

            for asset in ("0050", "0056"):
                target_value = equity * weights[asset]
                target_shares = int(target_value / prices[asset] // trade_unit) * trade_unit
                delta = target_shares - shares[asset]
                if delta > 0:
                    buy_shares = int(delta // trade_unit) * trade_unit
                    trade_price = prices[asset] * 1.001
                    max_affordable = int(cash / (trade_price * (1 + commission_rate)) // trade_unit) * trade_unit
                    buy_shares = min(buy_shares, max_affordable)
                    if buy_shares > 0:
                        cost = buy_shares * trade_price
                        fee = cost * commission_rate
                        cash -= cost + fee
                        shares[asset] += buy_shares
                        trades.append({
                            "date": str(pd.Timestamp(row["date"]).date()),
                            "asset": asset,
                            "type": "BUY",
                            "shares": buy_shares,
                            "price": trade_price,
                            "fee": fee,
                            "tax": 0.0,
                            "weights": weights,
                        })

            last_rebalance = idx

        equity_curve.append(float(cash + shares["0050"] * prices["0050"] + shares["0056"] * prices["0056"]))

    metrics = calculate_backtest_metrics(equity_curve, initial_value=initial_cash)
    fees_paid = float(sum(t["fee"] + t["tax"] for t in trades))
    return {
        "final_value": equity_curve[-1],
        "strategy_metrics": metrics,
        "num_trades": len(trades),
        "fees_paid_estimate": fees_paid,
        "final_cash": cash,
        "final_shares": shares,
        "equity_curve": equity_curve,
        "trades": trades,
    }


def benchmark_curve(df: pd.DataFrame, weights: dict[str, float], initial_cash: float = 1_000_000.0) -> list[float]:
    first_0050 = float(df.iloc[0]["close_0050"])
    first_0056 = float(df.iloc[0]["close_0056"])
    shares_0050 = initial_cash * weights.get("0050", 0.0) / first_0050
    shares_0056 = initial_cash * weights.get("0056", 0.0) / first_0056
    cash = initial_cash * weights.get("cash", 0.0)
    return (
        cash
        + shares_0050 * df["close_0050"].to_numpy(dtype=float)
        + shares_0056 * df["close_0056"].to_numpy(dtype=float)
    ).tolist()


def main() -> None:
    stock_data = download_all_stocks(TICKERS, TRAIN_START, DOWNLOAD_END)
    train_df = align_data(stock_data, TRAIN_START, TRAIN_END)
    test_df = align_data(stock_data, BACKTEST_START, BACKTEST_END)

    result = run_strategy(test_df)
    benchmarks = {
        "bh_0050": calculate_backtest_metrics(benchmark_curve(test_df, {"0050": 1.0}), initial_value=1_000_000),
        "bh_0056": calculate_backtest_metrics(benchmark_curve(test_df, {"0056": 1.0}), initial_value=1_000_000),
        "bh_50_50": calculate_backtest_metrics(benchmark_curve(test_df, {"0050": 0.5, "0056": 0.5}), initial_value=1_000_000),
    }
    result["excess_return_vs_50_50"] = (
        result["strategy_metrics"]["total_return"] - benchmarks["bh_50_50"]["total_return"]
    )

    payload = {
        "strategy": "0050_0056_relative_momentum_monthly_allocation",
        "tickers": TICKERS,
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
        "rebalance_days": 20,
        **result,
        "benchmarks": benchmarks,
    }

    output_file = (
        PROJECT_ROOT
        / "results"
        / f"portfolio_rule_0050_0056_backtest_2024_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps({
        "result_file": str(output_file),
        "final_value": payload["final_value"],
        "total_return": payload["strategy_metrics"]["total_return"],
        "sharpe": payload["strategy_metrics"]["sharpe"],
        "max_drawdown": payload["strategy_metrics"]["max_drawdown"],
        "num_trades": payload["num_trades"],
        "fees_paid_estimate": payload["fees_paid_estimate"],
        "excess_return_vs_50_50": payload["excess_return_vs_50_50"],
        "benchmarks": payload["benchmarks"],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
