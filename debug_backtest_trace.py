#!/usr/bin/env python3
"""直接 call _backtest_single 追蹤每一步的值"""
import sys, importlib.util
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import torch

FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
for f in (FINRL/"__pycache__").glob("walk_forward_v2*.pyc"): f.unlink()
_spec = importlib.util.spec_from_file_location("wf", FINRL/"walk_forward_v2.py")
_wf = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_wf)

# Load data
CACHE = FINRL/"data/cache/0050_2014-05-11_2026-05-05_1d.parquet"
df_raw = pq.read_table(CACHE).to_pandas(timestamp_as_object=True)
df_raw['date'] = df_raw['date'].apply(lambda x: x.replace(tzinfo=None) if hasattr(x,'tzinfo') and x.tzinfo else x)
df_raw['date'] = pd.to_datetime(df_raw['date'])
df_raw = df_raw.sort_values('date').reset_index(drop=True)
for col in ['close','high','low','open','volume']:
    df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')
df_raw['price'] = df_raw['close']
df_raw = df_raw.dropna(subset=['price'])

spec_ta = importlib.util.spec_from_file_location("ta", str(FINRL/"data/technical_analysis.py"))
tm = importlib.util.module_from_spec(spec_ta); spec_ta.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df_raw).dropna().reset_index(drop=True)
df_ta['date'] = df_ta['date'].astype(str)

# Get window 1 config
test_start = pd.Timestamp('2015-12-14')
test_end = pd.Timestamp('2016-01-25')

df = df_ta.copy()
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date').sort_index()
df_test = df.loc[test_start:test_end].copy()
print(f"df_test len={len(df_test)}, first={df_test.iloc[0]['close']:.2f}, last={df_test.iloc[-1]['close']:.2f}")

# dates
all_dates = sorted(df_ta['date'].apply(lambda x: pd.Timestamp(x)).unique())
common_dates = pd.DatetimeIndex(all_dates)
dates_in_window = [d for d in common_dates if test_start <= d <= test_end]
print(f"dates_in_window len={len(dates_in_window)}")

# Simulate _backtest_single manually
from environments.taiwan_stock_env import TaiwanStockTradingEnv

env = TaiwanStockTradingEnv(
    df=df_test,
    initial_balance=1_000_000,
    max_position=2000,
    commission_rate=0.001425,
    tax_rate=0.003,
)
env._print_enabled = False

# Manual backtest
bh_portfolio = 1_000_000
prev_price = None
rl_values = []
bh_values = []

obs, _ = env.reset()
env.current_price = df_test.iloc[0]['close']
env.current_step = 0

for i, date in enumerate(dates_in_window):
    action = np.random.randint(0, 5)  # no model, random action
    obs, reward, terminated, truncated, info = env.step(action)
    done = terminated or truncated

    # cur_price from df_test.iloc
    cur_price = df_test.iloc[env.current_step - 1]['close'] if env.current_step > 0 else df_test.iloc[0]['close']
    rl_val_raw = info.get('portfolio_value', np.nan)
    if np.isnan(rl_val_raw):
        rl_val_raw = env.balance + env.position * cur_price

    # B&H
    if cur_price > 0:
        if prev_price is not None and prev_price > 0:
            daily_return = cur_price / prev_price - 1
            bh_portfolio = bh_portfolio * (1 + daily_return)
        prev_price = cur_price

    rl_values.append(float(rl_val_raw))
    bh_values.append(float(bh_portfolio))

    if i < 5 or i >= len(dates_in_window) - 3:
        print(f"  step {i}: date={date.date()}, action={action}, cur_price={cur_price:.2f}, "
              f"rl={rl_val_raw:.0f}, bh={bh_portfolio:.0f}, done={done}, "
              f"balance={env.balance:.0f}, position={env.position}")

    if done:
        print(f"  --> DONE at step {i}")
        for rem in range(i+1, len(dates_in_window)):
            rl_values.append(np.nan)
            bh_values.append(np.nan)
        break

rl_series = pd.Series(rl_values[:len(dates_in_window)], index=dates_in_window[:len(rl_values)])
bh_series = pd.Series(bh_values[:len(dates_in_window)], index=dates_in_window[:len(bh_values)])
print(f"\nRL: initial={rl_series.iloc[0]:.0f}, final={rl_series.iloc[-1]:.0f}, return={rl_series.iloc[-1]/rl_series.iloc[0]-1:.4f}")
print(f"BH: initial={bh_series.iloc[0]:.0f}, final={bh_series.iloc[-1]:.0f}, return={bh_series.iloc[-1]/bh_series.iloc[0]-1:.4f}")
