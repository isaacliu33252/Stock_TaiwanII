#!/usr/bin/env python3
"""Evaluate current 0050.TW action and price bands for the action-9 model."""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from environments.reward_function_v3 import DynamicRewardShaper
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from portfolio_data_loader import download_all_stocks


TICKER = "0050.TW"
START = "2016-01-01"
END = "2026-05-10"
MODEL_PATH = PROJECT_ROOT / "models" / "portfolio" / "0050_TW_2016_2023_40000_200k_action9"
MAX_POSITION = 40_000
INITIAL_BALANCE = 1_000_000
LAST_BACKTEST_POSITION = 11_089
LAST_BACKTEST_BALANCE = 682_545.0872325415

ACTION_NAMES = [
    "HOLD",
    "BUY_1000",
    "BUY_5000",
    "BUY_10000",
    "SELL_1000",
    "SELL_5000",
    "SELL_10000",
    "TARGET_50_PERCENT",
    "TARGET_100_PERCENT",
]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    return out.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)


def reward() -> DynamicRewardShaper:
    r = DynamicRewardShaper(
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
    r.set_total_steps(200_000)
    return r


def make_env(df: pd.DataFrame, position: int = 0, balance: float = INITIAL_BALANCE) -> TaiwanStockTradingEnv:
    env = TaiwanStockTradingEnv(
        df=df,
        initial_balance=balance,
        max_position=MAX_POSITION,
        trade_unit=1000,
        price_limit=0.10,
        commission_rate=0.001425,
        tax_rate=0.003,
        lookback_window=60,
        initial_shares=position,
        initial_avg_cost=float(df.iloc[-1]["close"]) if position > 0 else 0.0,
        reward_func=reward(),
        enable_risk_manager=False,
        crash_window=15,
    )
    env._print_enabled = False
    return env


def predict_for_df(model: PPO, df: pd.DataFrame, position: int = 0, balance: float = INITIAL_BALANCE) -> int:
    env = make_env(df, position=position, balance=balance)
    obs, _ = env.reset()
    env.current_step = len(df) - 1
    obs = env._create_state()
    action, _ = model.predict(obs, deterministic=True)
    return int(np.asarray(action).item())


def classify(action: int) -> str:
    if action in (1, 2, 3, 7, 8):
        return "buy/add"
    if action in (4, 5, 6):
        return "sell/reduce"
    return "hold"


def evaluate_scenario(
    model: PPO,
    df: pd.DataFrame,
    latest_close: float,
    name: str,
    position: int,
    balance: float,
) -> dict:
    base_action = predict_for_df(model, df, position=position, balance=balance)
    grid = np.arange(max(1.0, latest_close * 0.70), latest_close * 1.31, 0.25)
    rows = []
    for px in grid:
        df2 = df.copy()
        ratio = px / latest_close
        for col in ("open", "high", "low", "close"):
            df2.loc[df2.index[-1], col] = float(df2.iloc[-1][col]) * ratio
        action = predict_for_df(model, df2, position=position, balance=balance)
        rows.append({"price": float(px), "action": action, "name": ACTION_NAMES[action], "class": classify(action)})

    bands = {}
    for cls in ("buy/add", "hold", "sell/reduce"):
        prices = [r["price"] for r in rows if r["class"] == cls]
        bands[cls] = None if not prices else {"low": round(min(prices), 2), "high": round(max(prices), 2)}

    return {
        "scenario": name,
        "position": position,
        "balance": round(balance, 2),
        "current_action": base_action,
        "current_action_name": ACTION_NAMES[base_action],
        "current_class": classify(base_action),
        "bands": bands,
    }


def main() -> None:
    stock_data = download_all_stocks([TICKER], START, END)
    df = clean(stock_data[TICKER])
    model = PPO.load(str(MODEL_PATH))
    latest = df.iloc[-1].copy()
    latest_close = float(latest["close"])

    payload = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "ticker": TICKER,
        "model_path": str(MODEL_PATH.resolve()),
        "latest_date": str(pd.Timestamp(latest["date"]).date()),
        "latest_close": latest_close,
        "latest_open": float(latest["open"]),
        "latest_high": float(latest["high"]),
        "latest_low": float(latest["low"]),
        "latest_volume": int(latest["volume"]),
        "scenarios": [
            evaluate_scenario(model, df, latest_close, "cash_only", 0, INITIAL_BALANCE),
            evaluate_scenario(
                model,
                df,
                latest_close,
                "last_backtest_state",
                LAST_BACKTEST_POSITION,
                LAST_BACKTEST_BALANCE,
            ),
        ],
        "scan_step": 0.25,
        "scan_range": "latest close +/- 30%",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
