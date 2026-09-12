#!/usr/bin/env python3
"""Cheap empirical test of Fable direction #7: does 0050.TW show a detectable
structural price effect around its quarterly index-reconstitution effective
dates (FTSE TWSE Taiwan 50 Index quarterly review, effective the next trading
day after the third Friday of March/June/September/December)?

No project-specific reconstitution-date dataset exists (searched codebase,
none found) -- dates below are derived from the standard, publicly documented
FTSE Russell quarterly review convention, stated explicitly as an assumption.

Research-only. Does not touch any live signal, target weight, or production file.
"""
import calendar
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, ".")
from backtest_group_a_plus_switch_policy import DB_PATH


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    fridays = [
        date(year, month, day)
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
        if date(year, month, day).weekday() == 4
    ]
    return fridays[2]


con = duckdb.connect(str(DB_PATH), read_only=True)
prices = con.execute(
    "SELECT dt, close FROM ohlcv WHERE ticker='0050.TW' ORDER BY dt"
).fetchdf()
prices["dt"] = pd.to_datetime(prices["dt"])
prices = prices.set_index("dt")["close"]
trading_days = prices.index

data_start = trading_days.min()
data_end = trading_days.max()
print(f"0050.TW data range: {data_start.date()} .. {data_end.date()}, {len(trading_days)} rows")

# Build quarterly effective dates over the full data range.
effective_dates = []
for year in range(data_start.year, data_end.year + 1):
    for month in (3, 6, 9, 12):
        tf = third_friday(year, month)
        # effective = next trading day after third Friday
        candidate = pd.Timestamp(tf) + pd.Timedelta(days=1)
        idx = trading_days.searchsorted(candidate)
        if idx < len(trading_days):
            eff = trading_days[idx]
            if data_start <= eff <= data_end:
                effective_dates.append(eff)

effective_dates = sorted(set(effective_dates))
print(f"Constructed {len(effective_dates)} quarterly effective dates")

PRE_WIN = 5   # -5..-1 trading days before effective date
POST_WIN = 5  # 0..+5 trading days after effective date


def window_return(center_idx: int, start_off: int, end_off: int) -> float | None:
    i0 = center_idx + start_off
    i1 = center_idx + end_off
    if i0 < 0 or i1 >= len(trading_days):
        return None
    p0 = prices.iloc[i0]
    p1 = prices.iloc[i1]
    return float(p1 / p0 - 1.0)


pre_returns = []
post_returns = []
event_rows = []
for eff in effective_dates:
    pos = trading_days.get_indexer([eff])[0]
    if pos == -1:
        continue
    pre_r = window_return(pos, -PRE_WIN, -1)
    post_r = window_return(pos, 0, POST_WIN)
    if pre_r is not None and post_r is not None:
        pre_returns.append(pre_r)
        post_returns.append(post_r)
        event_rows.append({"effective_date": str(eff.date()), "pre_return": pre_r, "post_return": post_r})

pre_returns = np.array(pre_returns)
post_returns = np.array(post_returns)
n_events = len(pre_returns)
print(f"\nUsable events (full pre/post window available): {n_events}")

# Unconditional baseline: rolling windows of the same length, sampled at
# EVERY trading day in the sample (overlapping), to get the unconditional
# mean/std of a 5-day return, for a fair comparison against the event-window
# means (controls for 0050's general uptrend over the sample).
all_5d_rets = prices.pct_change(PRE_WIN).dropna().to_numpy()
all_5d_rets_post = prices.pct_change(POST_WIN).dropna().to_numpy()

from scipy import stats

pre_mean, pre_std = pre_returns.mean(), pre_returns.std(ddof=1)
post_mean, post_std = post_returns.mean(), post_returns.std(ddof=1)
base_pre_mean = all_5d_rets.mean()
base_post_mean = all_5d_rets_post.mean()

t_pre, p_pre = stats.ttest_1samp(pre_returns - base_pre_mean, 0.0)
t_post, p_post = stats.ttest_1samp(post_returns - base_post_mean, 0.0)

frac_pre_positive = float((pre_returns > 0).mean())
frac_post_positive = float((post_returns > 0).mean())
base_frac_pre_positive = float((all_5d_rets > 0).mean())
base_frac_post_positive = float((all_5d_rets_post > 0).mean())

print(f"\n=== PRE-window (-{PRE_WIN}..-1 trading days before effective date) ===")
print(f"  event mean return: {pre_mean:.4%}  (unconditional baseline mean: {base_pre_mean:.4%})")
print(f"  excess vs baseline: {pre_mean - base_pre_mean:+.4%}, t={t_pre:.3f}, p={p_pre:.4f}")
print(f"  fraction positive: {frac_pre_positive:.1%}  (baseline: {base_frac_pre_positive:.1%})")

print(f"\n=== POST-window (0..+{POST_WIN} trading days after effective date) ===")
print(f"  event mean return: {post_mean:.4%}  (unconditional baseline mean: {base_post_mean:.4%})")
print(f"  excess vs baseline: {post_mean - base_post_mean:+.4%}, t={t_post:.3f}, p={p_post:.4f}")
print(f"  fraction positive: {frac_post_positive:.1%}  (baseline: {base_frac_post_positive:.1%})")

print("\n=== per-event detail ===")
for row in event_rows:
    print(f"  {row['effective_date']}: pre={row['pre_return']:+.4%}  post={row['post_return']:+.4%}")

import json
out = {
    "n_events": n_events,
    "pre_window_days": PRE_WIN,
    "post_window_days": POST_WIN,
    "pre_mean": pre_mean, "pre_baseline_mean": base_pre_mean, "pre_excess": pre_mean - base_pre_mean,
    "pre_t": float(t_pre), "pre_p": float(p_pre), "pre_frac_positive": frac_pre_positive, "pre_baseline_frac_positive": base_frac_pre_positive,
    "post_mean": post_mean, "post_baseline_mean": base_post_mean, "post_excess": post_mean - base_post_mean,
    "post_t": float(t_post), "post_p": float(p_post), "post_frac_positive": frac_post_positive, "post_baseline_frac_positive": base_frac_post_positive,
    "events": event_rows,
}
with open("results/test_0050_reconstitution_effect_20260908.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("\nSaved: results/test_0050_reconstitution_effect_20260908.json")
