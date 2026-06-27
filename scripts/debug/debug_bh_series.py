#!/usr/bin/env python3
"""直接測試 _backtest_single 的 B&H 計算"""
import sys, importlib.util
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq

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

# Simulate window 1 dates
test_start = pd.Timestamp('2015-12-14')
test_end = pd.Timestamp('2016-01-25')
df = df_ta.copy()
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date').sort_index()
df_test = df.loc[test_start:test_end]
print(f"df_test len={len(df_test)}, first_close={df_test.iloc[0]['close']:.2f}, last_close={df_test.iloc[-1]['close']:.2f}")

# Simulate common_dates
all_dates = sorted(df_ta['date'].apply(lambda x: pd.Timestamp(x)).unique())
common_dates = pd.DatetimeIndex(all_dates)
dates_in_window = [d for d in common_dates if test_start <= d <= test_end]
print(f"dates_in_window len={len(dates_in_window)}, first={dates_in_window[0].date()}, last={dates_in_window[-1].date()}")

# Direct B&H simulation
initial_value = 1_000_000
bh_portfolio = initial_value
prev_price = None
bh_values = []
for i, date in enumerate(dates_in_window):
    if date in df_test.index:
        cur_price = df_test.loc[date, 'close']
    else:
        cur_price = np.nan
    if not np.isnan(cur_price) and prev_price is not None:
        daily_return = cur_price / prev_price - 1
        bh_portfolio = bh_portfolio * (1 + daily_return)
    prev_price = cur_price if not np.isnan(cur_price) else prev_price
    bh_values.append(float(bh_portfolio))
    print(f"  day {i}: date={date.date()}, price={cur_price:.2f}, bh={bh_portfolio:.0f}")

bh_series = pd.Series(bh_values, index=dates_in_window)
print(f"\nB&H series:\n{bh_series}")
print(f"\nB&H initial={bh_series.iloc[0]}, final={bh_series.iloc[-1]}, return={bh_series.iloc[-1]/bh_series.iloc[0]-1:.4f}")
