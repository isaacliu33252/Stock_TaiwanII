#!/usr/bin/env python3
"""Backtest an existing 0050.TW model on an arbitrary historical window."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import PORTFOLIO_HOLDINGS
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import EnhancedStockTrainer


TICKER = "0050.TW"
DEFAULT_START = "2003-01-01"
DEFAULT_END = "2010-12-31"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "portfolio" / "0050_TW_2016_2023_ppo_enhanced"
INITIAL_VALUE = 1_000_000


def _download_end(end: str) -> str:
    return (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def _clean_slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    out = out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()
    return out.reset_index(drop=True)


def _buy_and_hold_curve(df: pd.DataFrame) -> list[float]:
    first = float(df.iloc[0]["close"])
    shares = INITIAL_VALUE / first
    return [float(shares * px) for px in df["close"]]


def _drawdown(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    peak = np.maximum.accumulate(arr)
    return arr / peak - 1.0


def _save_plots(df: pd.DataFrame, result: dict, prefix: Path) -> tuple[Path, Path]:
    dates = pd.to_datetime(df["date"])
    rl_curve = list(result["equity_curve"])
    if len(rl_curve) == len(dates) + 1:
        rl_dates = pd.concat([dates.iloc[[0]], dates], ignore_index=True)
    else:
        rl_dates = dates.iloc[: len(rl_curve)]

    bh_curve = _buy_and_hold_curve(df)

    value_path = prefix.with_suffix(".png")
    drawdown_path = prefix.parent / f"{prefix.name}_drawdown.png"

    plt.figure(figsize=(12, 6))
    plt.plot(rl_dates, rl_curve, label="RL 0050 PPO", linewidth=2)
    plt.plot(dates, bh_curve, label="0050 Buy & Hold", linewidth=2)
    plt.title("0050 Backtest Value Curve")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(value_path, dpi=150)
    plt.close()

    plt.figure(figsize=(12, 5))
    plt.plot(rl_dates, _drawdown(rl_curve), label="RL 0050 PPO", linewidth=2)
    plt.plot(dates, _drawdown(bh_curve), label="0050 Buy & Hold", linewidth=2)
    plt.title("0050 Backtest Drawdown")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(drawdown_path, dpi=150)
    plt.close()

    return value_path, drawdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest existing 0050.TW PPO model.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    args = parser.parse_args()

    stock_data = download_all_stocks([TICKER], args.start, _download_end(args.end))
    if TICKER not in stock_data:
        raise RuntimeError(f"Unable to load data for {TICKER}")

    df = _clean_slice(stock_data[TICKER], args.start, args.end)
    if len(df) < 80:
        raise RuntimeError(f"Not enough rows for 0050 backtest: {len(df)}")

    info = PORTFOLIO_HOLDINGS.get(TICKER, {})
    trainer = EnhancedStockTrainer(
        ticker=TICKER,
        df=df,
        agent_type="ppo",
        initial_shares=info.get("shares", 0),
        enable_risk_manager=False,
        enable_enhanced_reward=True,
        seed=42,
    )
    trainer.model = PPO.load(args.model)
    result = trainer.backtest(df_test=df)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_slug = args.start.replace("-", "")
    end_slug = args.end.replace("-", "")
    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_prefix = output_dir / f"backtest_0050_{start_slug}_{end_slug}_{stamp}"
    value_chart, drawdown_chart = _save_plots(df, result, plot_prefix)

    payload = {
        "ticker": TICKER,
        "model_path": str(Path(args.model).resolve()),
        "requested_start": args.start,
        "requested_end": args.end,
        "actual_start": str(df["date"].min().date()),
        "actual_end": str(df["date"].max().date()),
        "rows": int(len(df)),
        "value_chart": str(value_chart),
        "drawdown_chart": str(drawdown_chart),
        **result,
    }

    output_file = output_dir / f"backtest_0050_{start_slug}_{end_slug}_{stamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    rl = result.get("rl_metrics", {})
    bh = result.get("buy_and_hold_metrics", {})
    print("=" * 72)
    print("0050 backtest complete")
    print(f"Actual range: {payload['actual_start']} ~ {payload['actual_end']} ({payload['rows']} rows)")
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
    print(f"Chart:  {value_chart}")
    print(f"DD:     {drawdown_chart}")
    print("=" * 72)


if __name__ == "__main__":
    main()
