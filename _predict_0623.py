#!/usr/bin/env python3
import sys, json, numpy as np
from pathlib import Path
import duckdb
import pandas as pd
from stable_baselines3 import PPO
from FinRL.data.stock_db import DB_PATH

TICKER = "00631L.TW"
MODEL_PATH = Path("models/portfolio/golden_00631l_pred_v10_2020_2025.zip")
BACKTEST_END = "2026-06-23"

FEATURE_COLUMNS = [
    "close_ma120_ratio","close_ma200_ratio","close_ma240_ratio",
    "ma60_ma240_ratio","momentum_21","momentum_63","momentum_126","momentum_252",
    "rolling_mdd_63","below_ma200",
    "adx_14","price_ma200_dist","vol_ratio_20","rsi_14","macd_signal","bb_position",
]

# Load data from DB
con = duckdb.connect(str(DB_PATH), read_only=True)
rows = con.execute("""
    SELECT dt, ticker, close, open, high, low, volume
    FROM ohlcv WHERE ticker = ? AND dt <= ?
    ORDER BY dt
""", [TICKER, BACKTEST_END]).fetchdf()
con.close()

rows["date"] = pd.to_datetime(rows["dt"])
rows = rows.set_index("date").sort_index()

# Build features
df = rows.copy()
df["close_ma120"] = df["close"].rolling(120).mean()
df["close_ma200"] = df["close"].rolling(200).mean()
df["close_ma240"] = df["close"].rolling(240).mean()
df["close_ma50"] = df["close"].rolling(50).mean()
df["close_ma60"] = df["close"].rolling(60).mean()
df["close_ma120_ratio"] = df["close"] / df["close_ma120"]
df["close_ma200_ratio"] = df["close"] / df["close_ma200"]
df["close_ma240_ratio"] = df["close"] / df["close_ma240"]
df["ma60_ma240_ratio"] = df["close_ma60"] / df["close_ma240"]
df["momentum_21"] = df["close"] / df["close"].shift(21) - 1
df["momentum_63"] = df["close"] / df["close"].shift(63) - 1
df["momentum_126"] = df["close"] / df["close"].shift(126) - 1
df["momentum_252"] = df["close"] / df["close"].shift(252) - 1

def rolling_mdd(x):
    cummax = x.cummax()
    return float(((x - cummax) / cummax).min())

df["rolling_mdd_63"] = df["close"].rolling(63).apply(rolling_mdd, raw=False)
df["below_ma200"] = (df["close"] < df["close_ma200"]).astype(float)

# ADX
high, low, close = df["high"], df["low"], df["close"]
tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
plus_dm = high.diff()
minus_dm = -low.diff()
plus_di = 100 * plus_dm.rolling(14).mean() / tr.rolling(14).mean()
minus_di = 100 * minus_dm.rolling(14).mean() / tr.rolling(14).mean()
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
df["adx_14"] = dx.rolling(14).mean()
df["price_ma200_dist"] = (df["close"] - df["close_ma200"]) / df["close_ma200"]
df["vol_ratio_20"] = df["volume"] / df["volume"].rolling(20).mean()

# RSI
delta = df["close"].diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)
avg_gain = gain.rolling(14).mean()
avg_loss = loss.rolling(14).mean()
rs = avg_gain / avg_loss.clip(lower=1e-10)
df["rsi_14"] = 100 - (100 / (1 + rs))

# MACD
emac = df["close"].ewm(span=12).mean()
emas = df["close"].ewm(span=26).mean()
macd_val = emac - emas
df["macd_signal"] = macd_val.ewm(span=9).mean()

# BB position
ma20 = df["close"].rolling(20).mean()
std20 = df["close"].rolling(20).std()
df["bb_position"] = (df["close"] - ma20) / (2 * std20)

df = df.dropna()
print(f"Feature rows: {len(df)}, last date: {df.index[-1].date()}")

# Load model
model = PPO.load(str(MODEL_PATH))
print("Model loaded")

# Get last row
last = df.iloc[-1]
close_price = float(last["close"])
close_ma200_val = float(last["close_ma200"])
close_ma50_val = float(last["close_ma50"])
below_ma200 = float(last["below_ma200"])
below_ma50 = 1.0 if close_price < close_ma50_val else 0.0
price_ma200_dist = float(last["price_ma200_dist"])

print(f"\n=== 00631L 當前狀態 (last date: {df.index[-1].date()}) ===")
print(f"Close: {close_price:.2f}")
print(f"MA200: {close_ma200_val:.2f}, MA50: {close_ma50_val:.2f}")
print(f"close/MA200 ratio: {close_price/close_ma200_val:.4f}")
print(f"close/MA50 ratio: {close_price/close_ma50_val:.4f}")
print(f"below_ma200={below_ma200:.2f}, below_ma50={below_ma50:.2f}")
print(f"price_ma200_dist={price_ma200_dist:.4f}")
print(f"ADX={last['adx_14']:.2f}, RSI={last['rsi_14']:.2f}")
print(f"vol_ratio_20={last['vol_ratio_20']:.3f}")

# V9 MA50 hybrid rule
if below_ma200 > 0.5:
    target_weight = 0.30
elif below_ma50 > 0.5:
    target_weight = 0.80
else:
    raw = 0.90 + (price_ma200_dist / 0.10) * 0.10
    target_weight = float(np.clip(raw, 0.90, 1.00))

print(f"\n=== Golden1 V9 (MA50 hybrid) ===")
print(f"target_weight: {target_weight:.0%}")

# PPO action
# Build full 18-feature observation (FEATURE_COLUMNS 16 + close + open)
t = TICKER
flat_cols = [f"{t}_{f}" for f in FEATURE_COLUMNS + ["close", "open"] if f"{t}_{f}" in df.columns]
obs = {col: float(last[col]) for col in flat_cols}
arr = np.array([[obs.get(f"{t}_{col}", 0.0) for col in FEATURE_COLUMNS + ["close", "open"]]])
action, _ = model.predict(arr, deterministic=True)
ppo_weight = float(action[0][0])
print(f"\n=== PPO Model (v10) ===")
print(f"action: {ppo_weight:.4f} (raw PPO output)")

print(f"\n==> 00631L V9 target_weight: {target_weight:.0%}")
print(f"==> 00631L PPO raw action: {ppo_weight:.4f}")
