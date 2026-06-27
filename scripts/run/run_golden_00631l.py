#!/usr/bin/env python3
"""golden_00631L 策略：專門處理 00631L（元大台灣50正二）
訓練 2020-2024，回測 2025-2026-06-20
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb
import gymnasium
from stable_baselines3 import PPO
from stable_baselines3.common.utils import FloatSchedule

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH, query_ohlcv
from FinRL.portfolio_data_loader import (
    add_market_features,
    download_market_features,
    MARKET_FEATURE_COLUMNS,
)

# ─── 預設值 ───
TICKER = "00631L.TW"
TRAIN_START = "2020-01-01"
TRAIN_END = "2025-12-31"
BACKTEST_START = "2026-01-02"
BACKTEST_END = "2026-06-18"
INITIAL_CASH = 1_000_000.0
TIMESTEPS = 100_000
SEED = 42
MODEL_NAME = "golden_00631l_pred_v10_2020_2025"

FEATURE_COLUMNS = [
    "close_ma120_ratio",
    "close_ma200_ratio",
    "close_ma240_ratio",
    "ma60_ma240_ratio",
    "momentum_21",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "rolling_mdd_63",
    "below_ma200",
    # ── Regime Detection ──
    "adx_14",          # Trend strength: >25 = trending, >40 = strong
    "price_ma200_dist", # Price above MA200 distance (%)
    "vol_ratio_20",     # Volume surge ratio
    "rsi_14",           # Overbought/oversold
    "macd_signal",      # MACD vs signal line
    "bb_position",      # Bollinger position
]


# ─── 資料載入 ───
def load_data(tickers, start, end):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT dt, ticker, close, open, high, low, volume
            FROM ohlcv
            WHERE ticker IN ({})
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
        """.format(", ".join(["?"] * len(tickers))),
            [*tickers, start, end]).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows


def build_features(rows: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """對每支 ticker 建立技術指標特徵。"""
    data = {}
    for ticker in tickers:
        df = rows[rows["ticker"] == ticker].copy()
        df = df.set_index("dt").sort_index()
        df = df[["close", "open", "high", "low", "volume"]]

        close = df["close"]
        # MA
        df["ma50"] = close.rolling(50).mean()
        df["ma60"] = close.rolling(60).mean()
        df["ma120"] = close.rolling(120).mean()
        df["ma240"] = close.rolling(240).mean()
        df["ma200"] = close.rolling(200).mean()
        # ratios
        df["close_ma120_ratio"] = close / df["ma120"]
        df["close_ma200_ratio"] = close / df["ma200"]
        df["close_ma240_ratio"] = close / df["ma240"]
        df["ma60_ma240_ratio"] = df["ma60"] / df["ma240"]
        # Trend guard: 價格低於 MA200 → 強制降倉
        df["below_ma200"] = (close < df["ma200"]).astype(float)
        df["below_ma50"] = (close < df["ma50"]).astype(float)
        df["close_ma50_ratio"] = close / df["ma50"]
        # momentum
        df["momentum_21"] = close.pct_change(21)
        df["momentum_63"] = close.pct_change(63)
        df["momentum_126"] = close.pct_change(126)
        df["momentum_252"] = close.pct_change(252)
        # rolling max drawdown
        rolling_max = close.rolling(63, min_periods=1).max()
        drawdown = (close - rolling_max) / rolling_max
        df["rolling_mdd_63"] = drawdown.rolling(63, min_periods=1).min()

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi_14"] = (100 - 100 / (1 + rs)).clip(0, 100)

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        df["macd_signal"] = macd - signal
        df["macd_hist"] = macd - 2 * signal

        # Bollinger
        bb_mean = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df["bb_position"] = (close - bb_mean) / (2 * bb_std + 1e-8)

        # Volume ratio
        df["vol_ratio_20"] = df["volume"] / df["volume"].rolling(20).mean()

        # ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - close.shift()).abs()
        low_close = (df["low"] - close.shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()

        # ── Regime Detection ──
        # Price vs MA200 distance (%)
        df["price_ma200_dist"] = (close - df["ma200"]) / df["ma200"]

        # ADX (Average Directional Index) - 手動計算
        high_diff = df["high"].diff()
        low_diff = -df["low"].diff()
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
        tr14 = df["atr_14"]
        plus_di = 100 * plus_dm.rolling(14).sum() / tr14
        minus_di = 100 * minus_dm.rolling(14).sum() / tr14
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)
        df["adx_14"] = dx.rolling(14).mean()

        df = df.dropna(subset=[
            "close_ma120_ratio", "close_ma200_ratio", "close_ma240_ratio",
            "ma60_ma240_ratio", "below_ma200", "below_ma50",
            "adx_14", "price_ma200_dist", "vol_ratio_20", "rsi_14", "macd_signal", "bb_position"
        ])
        data[ticker] = df
    return data


def _align(data: dict[str, pd.DataFrame], tickers: list[str]) -> pd.DataFrame:
    """把所有 ticker 合併成一個 panel，取共同日期。"""
    dfs = []
    for t in tickers:
        # open + close 是預測任務的必要欄位
        feat_cols = FEATURE_COLUMNS + ["close", "open"]
        d = data[t][feat_cols].rename(columns={c: f"{t}_{c}" for c in feat_cols})
        dfs.append(d)
    panel = dfs[0].join(dfs[1:], how="inner")
    panel = panel.dropna()
    return panel


class MultiTickerEnv(gymnasium.Env):
    """
    預測任務：action = 預測 next_open / close 比率。
    reward = -(預測誤差)² × 1000，誤差越小 reward 越高。
    """
    metadata = {"render_modes": []}

    def __init__(self, panel: pd.DataFrame, tickers: list[str], initial_cash: float = 1_000_000.0):
        super().__init__()
        self._panel = panel.reset_index(drop=True)
        self._tickers = tickers
        self._n_steps = len(panel) - 1  # 最後一天沒有 next_open
        self._initial_cash = initial_cash

        flat_cols = []
        for t in tickers:
            for f in FEATURE_COLUMNS + ["close", "open"]:
                col = f"{t}_{f}"
                if col in panel.columns:
                    flat_cols.append(col)

        self._flat_cols = flat_cols
        self._ticker = tickers[0]
        self._close_col = f"{self._ticker}_close"
        self._open_col = f"{self._ticker}_open"

        n_feat = len(flat_cols)
        self.observation_space = gymnasium.spaces.Box(low=-10, high=10, shape=(n_feat,), dtype=np.float32)
        self.action_space = gymnasium.spaces.Box(low=0.5, high=1.5, shape=(1,), dtype=np.float32)

        self._step_idx = 0

    def _obs(self) -> np.ndarray:
        feat = self._panel.iloc[self._step_idx][self._flat_cols].values.astype(np.float32)
        return feat

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._step_idx = 0
        return self._obs(), {}

    def step(self, action):
        cur_close = self._panel.iloc[self._step_idx][self._close_col]
        pred_ratio = float(np.clip(action[0], 0.5, 1.5))

        # 取得隔天開盤價（計算真實比率）
        if self._step_idx + 1 < len(self._panel):
            next_open = self._panel.iloc[self._step_idx + 1][self._open_col]
            actual_ratio = next_open / cur_close
        else:
            # 最後一天：沒有 next_open，用 1.0（中性猜測）
            actual_ratio = 1.0

        # Reward：預測誤差越小越好
        error = pred_ratio - actual_ratio
        reward = -error * error * 1000.0

        self._step_idx += 1
        done = self._step_idx >= self._n_steps
        truncated = False
        return self._obs(), reward, done, truncated, {}

    def render(self, mode="human"):
        pass

    def close(self):
        pass


def train_model(panel: pd.DataFrame, tickers: list[str], model_name: str, timesteps: int, seed: int):
    from gymnasium import spaces
    env = MultiTickerEnv(panel, tickers, INITIAL_CASH)
    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        n_steps=1024,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.08,
        seed=seed,
        verbose=1,
    )
    model.learn(total_timesteps=timesteps)
    path = PROJECT_ROOT / "models" / "portfolio" / model_name
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(path))
    print(f"模型儲存: {path}")
    return model, path

def backtest_model(model, panel: pd.DataFrame, tickers: list[str],
                    backtest_start: str, backtest_end: str):
    """評估 PPO 預測 next_open/close ratio 的準確度，並模擬日內交易"""
    bt_panel = panel.loc[backtest_start:backtest_end].reset_index(drop=True)
    n = len(bt_panel)

    env = MultiTickerEnv(bt_panel, tickers, INITIAL_CASH)
    obs, _ = env.reset()

    history = []
    total_value = INITIAL_CASH
    cash = INITIAL_CASH
    shares = 0.0
    ticker = tickers[0]
    close_col = f"{ticker}_close"
    open_col = f"{ticker}_open"

    for step_i in range(n - 1):
        action, _ = model.predict(obs, deterministic=True)
        pred_ratio = float(np.clip(action[0], 0.5, 1.5))
        obs, reward, done, _, _ = env.step(action)

        cur_close = bt_panel.iloc[step_i][close_col]
        next_open = bt_panel.iloc[step_i + 1][open_col]
        actual_ratio = next_open / cur_close
        error = pred_ratio - actual_ratio

        position_size = 1.0 if pred_ratio > 1.0 else 0.0

        if position_size > 0 and shares == 0:
            shares = cash / next_open
            cash = 0
        elif position_size == 0 and shares > 0:
            cash = shares * bt_panel.iloc[step_i + 1][close_col]
            shares = 0

        total_value = cash + shares * bt_panel.iloc[step_i + 1][close_col]

        dt = bt_panel.index[step_i]
        history.append({
            "date": str(dt.date()) if hasattr(dt, "date") else str(dt)[:10],
            "pred_ratio": pred_ratio,
            "actual_ratio": actual_ratio,
            "error": error,
            "abs_error": abs(error),
            "position": position_size,
            "total_value": total_value,
        })

    df = pd.DataFrame(history)
    mae = df["error"].abs().mean()
    rmse = np.sqrt((df["error"] ** 2).mean())
    corr = df["pred_ratio"].corr(df["actual_ratio"])

    strategy_return = df["total_value"].iloc[-1] / INITIAL_CASH - 1
    bh_start = bt_panel.iloc[0][open_col]
    bh_end = bt_panel.iloc[-1][close_col]
    bh_return = bh_end / bh_start - 1

    sharpe = df["total_value"].pct_change().mean() / df["total_value"].pct_change().std() * np.sqrt(252) if df["total_value"].pct_change().std() > 0 else 0
    running_max = df["total_value"].cummax()
    drawdown = (df["total_value"] - running_max) / running_max
    mdd = drawdown.min()

    metrics = {
        "final_value": float(df["total_value"].iloc[-1]),
        "cumulative_return": float(strategy_return),
        "annualized_return": float((1 + strategy_return) ** (252 / len(df)) - 1),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(mdd),
        "buy_hold_return": float(bh_return),
        "excess_return": float(strategy_return - bh_return),
        "prediction_mae": float(mae),
        "prediction_rmse": float(rmse),
        "prediction_corr": float(corr),
        "trading_days": int(len(df)),
    }
    return metrics, df


def generate_signal_json(model, panel: pd.DataFrame, tickers: list[str], output_path: Path):
    """產生 golden_00631L signal JSON（pred_ratio 格式）。"""
    env = MultiTickerEnv(panel, tickers, INITIAL_CASH)
    obs, _ = env.reset()
    done = False
    signals = []

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, done, _, _ = env.step(action)
        dt = panel.index[env._step_idx - 1]
        pred_ratio = float(np.clip(action[0], 0.5, 1.5))
        signals.append({
            "date": str(dt.date()) if hasattr(dt, "date") else str(dt)[:10],
            "pred_ratio": pred_ratio,
            "signal": "long" if pred_ratio > 1.0 else "cash",
        })

    last = signals[-1]
    pred_ratio = last["pred_ratio"]

    payload = {
        "group": "golden_00631l",
        "result_json": str(output_path),
        "model_path": str(PROJECT_ROOT / "models" / "portfolio" / MODEL_NAME),
        "signal_mode": "pred_ratio",
        "requested_as_of_date": BACKTEST_END,
        "signal_status": "rebalance",
        "signal_reason": f"pred_ratio={pred_ratio:.5f}",
        "guard_reasons": [],
        "latest_prices": {},
        "pred_ratio": pred_ratio,
        "signal": last["signal"],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Signal JSON: {output_path}")
    return payload


# ─── 主程式 ───
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-start", default=TRAIN_START)
    parser.add_argument("--train-end", default=TRAIN_END)
    parser.add_argument("--backtest-start", default=BACKTEST_START)
    parser.add_argument("--backtest-end", default=BACKTEST_END)
    parser.add_argument("--initial-cash", type=float, default=INITIAL_CASH)
    parser.add_argument("--timesteps", type=int, default=TIMESTEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--train-only", action="store_true")
    parser.add_argument("--backtest-only", action="store_true")
    args = parser.parse_args()

    tickers = [TICKER]
    print(f"{'='*60}")
    print(f"golden_00631L 策略")
    print(f"標的: {tickers} | 訓練: {args.train_start} ~ {args.train_end}")
    print(f"回測: {args.backtest_start} ~ {args.backtest_end}")
    print(f"{'='*60}")

    # 1. 載入資料
    print("\n[1] 載入資料...")
    rows = load_data(tickers, args.train_start, args.backtest_end)
    print(f"  總筆數: {len(rows)}")
    data = build_features(rows, tickers)
    panel = _align(data, tickers)
    print(f"  Panel 大小: {panel.shape}")

    model_path = PROJECT_ROOT / "models" / "portfolio" / args.model_name

    # 2. 訓練
    if not args.backtest_only:
        print(f"\n[2] 訓練模型 ({args.timesteps:,} steps)...")
        train_panel = panel.loc[args.train_start:args.train_end]
        if len(train_panel) < 100:
            raise RuntimeError(f"訓練資料不足：{len(train_panel)} 筆")
        model, _ = train_model(train_panel, tickers, args.model_name, args.timesteps, args.seed)
    else:
        if not model_path.exists():
            raise FileNotFoundError(f"模型不存在: {model_path}")
        model = PPO.load(str(model_path))
        print(f"  已載入模型: {model_path}")

    # 3. 回測
    if not args.train_only:
        print(f"\n[3] 回測 {args.backtest_start} ~ {args.backtest_end}...")
        metrics, df = backtest_model(model, panel, tickers, args.backtest_start, args.backtest_end)
        print(f"\n  === 回測結果（預測任務 v10）===")
        print(f"  最終淨值: {metrics['final_value']:,.0f} ({metrics['cumulative_return']:+.2%})")
        print(f"  年化報酬: {metrics['annualized_return']:+.2%}")
        print(f"  Sharpe:   {metrics['sharpe_ratio']:.3f}")
        print(f"  MDD:      {metrics['max_drawdown']:.2%}")
        print(f"  BH 報酬:  {metrics['buy_hold_return']:+.2%}")
        print(f"  超額報酬: {metrics['excess_return']:+.2%}")
        print(f"  預測 MAE: {metrics['prediction_mae']:.5f}")
        print(f"  預測 RMSE: {metrics['prediction_rmse']:.5f}")
        print(f"  預測相關性: {metrics['prediction_corr']:.4f}")

        # 存回測結果
        result = {
            "strategy": "golden_00631L_Pred_v10",
            "ticker": TICKER,
            "train_period": f"{args.train_start}_{args.train_end}",
            "backtest_period": f"{args.backtest_start}_{args.backtest_end}",
            "timesteps": args.timesteps,
            "seed": args.seed,
            "metrics": metrics,
        }
        result_path = PROJECT_ROOT / "results" / f"golden_00631l_pred_v10_backtest_{args.backtest_start}_{args.backtest_end}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  回測 JSON: {result_path}")

        frame_path = PROJECT_ROOT / "results" / f"golden_00631l_pred_v10_backtest_{args.backtest_start}_{args.backtest_end}_frame.csv"
        df.to_csv(frame_path, encoding="utf-8-sig", index=False)
        print(f"  回測 frame: {frame_path}")

        # 4. 產生 Signal JSON
        signal_path = PROJECT_ROOT / "results" / f"signal_golden_00631l_pred_v10_{args.backtest_end}.json"
        generate_signal_json(model, panel, tickers, signal_path)

        # 5. 買入持有 benchmark
        bt_panel = panel.loc[args.backtest_start:args.backtest_end]
        price_col = f"{TICKER}_close"
        bh_prices = bt_panel[price_col]
        bh_return = bh_prices.iloc[-1] / bh_prices.iloc[0] - 1
        print(f"\n  === Buy & Hold Benchmark ({TICKER}) ===")
        print(f"  買入持有報酬: {bh_return:+.2%}")
        print(f"  vs 策略超額報酬: {metrics['cumulative_return'] - bh_return:+.2%}")
    else:
        print(f"\n[3] 跳過回測（--train-only）")


if __name__ == "__main__":
    main()