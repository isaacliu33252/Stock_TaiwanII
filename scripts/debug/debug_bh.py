#!/usr/bin/env python3
"""直接測試 _backtest_single 的 B&H + RL 數字"""
import pandas as pd
import pyarrow.parquet as pq
import importlib.util
import numpy as np
from pathlib import Path

FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
CACHE = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"

# Load TA
df_raw = pq.read_table(CACHE).to_pandas(timestamp_as_object=True)
df_raw["date"] = df_raw["date"].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, "tzinfo") and x.tzinfo else x)
df_raw["date"] = pd.to_datetime(df_raw["date"])
df_raw = df_raw.sort_values("date").reset_index(drop=True)
for col in ["close","high","low","open"]:
    df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")
df_raw["volume"] = pd.to_numeric(df_raw["volume"], errors="coerce")
df_raw["price"] = df_raw["close"]
df_raw = df_raw.dropna(subset=["price"])

spec_ta = importlib.util.spec_from_file_location("ta", str(FINRL / "data/technical_analysis.py"))
tm = importlib.util.module_from_spec(spec_ta); spec_ta.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df_raw).dropna().reset_index(drop=True)
df_ta["date"] = pd.to_datetime(df_ta["date"])

# Window 1 test period: 2015-12-14 ~ 2016-01-25
test_start = pd.Timestamp("2015-12-14")
test_end = pd.Timestamp("2016-01-25")
df = df_ta.copy().set_index("date").sort_index()
df_test = df.loc[test_start:test_end].copy()
print(f"df_test rows: {len(df_test)}")
print(f"df_test close prices:\n{df_test['close'].to_dict()}")

# Load env
from environments.taiwan_stock_env import TaiwanStockTradingEnv
env = TaiwanStockTradingEnv(df=df_test.reset_index(), initial_balance=1_000_000, max_position=2000, commission_rate=0.001425, tax_rate=0.003)
env._print_enabled = False

# B&H sim
bh_portfolio = 1_000_000.0
prev_price = None
bh_values = []
rl_values = []
dates = df_test.index.tolist()

obs, _ = env.reset()
env.current_step = 0

for i, date in enumerate(dates):
    # cur_price from df_test (correct)
    cur_price = df_test.iloc[env.current_step - 1]['close'] if env.current_step > 0 else df_test.iloc[0]['close']
    
    # RL: step with action=2 (BUY_1000)
    obs, reward, term, trunc, info = env.step(2)
    rl_val = info.get('portfolio_value', np.nan)
    if np.isnan(rl_val):
        rl_val = env.balance + env.position * cur_price

    # B&H
    if cur_price > 0:
        if prev_price is not None and prev_price > 0:
            bh_portfolio = bh_portfolio * (1 + (cur_price / prev_price - 1))
        prev_price = cur_price

    rl_values.append(float(rl_val))
    bh_values.append(float(bh_portfolio))
    print(f"  day {i}: price={cur_price:.4f} rl_pv={rl_val:.0f} bh={bh_portfolio:.0f} bal={env.balance} pos={env.position}")

rl_series = pd.Series(rl_values, index=dates)
bh_series = pd.Series(bh_values, index=dates)
rl_combined = rl_series.dropna()
bh_combined = bh_series.dropna()

print(f"\n=== Aggregated ===")
print(f"RL initial: {rl_combined.iloc[0]:.0f}, final: {rl_combined.iloc[-1]:.0f}")
print(f"BH initial: {bh_combined.iloc[0]:.0f}, final: {bh_combined.iloc[-1]:.0f}")
print(f"RL return: {rl_combined.iloc[-1]/rl_combined.iloc[0]-1:.2%}")
print(f"BH return: {bh_combined.iloc[-1]/bh_combined.iloc[0]-1:.2%}")

rl_daily = rl_combined.pct_change().dropna()
bh_daily = bh_combined.pct_change().dropna()
print(f"\nRL daily returns: {rl_daily.values[:5]}")
print(f"BH daily returns: {bh_daily.values[:5]}")

# Sharpe
std_rl = np.std(rl_daily.values, ddof=1)
std_bh = np.std(bh_daily.values, ddof=1)
print(f"\nstd RL={std_rl:.6f}, std BH={std_bh:.6f}")
if std_rl > 0:
    print(f"RL Sharpe = {np.mean(rl_daily.values)*252/std_rl:.2f}")
if std_bh > 0:
    print(f"BH Sharpe = {np.mean(bh_daily.values)*252/std_bh:.2f}")
