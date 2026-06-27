#!/usr/bin/env python3
"""只跑視窗1測試，確認 B&H 和 RL 數字"""
import pandas as pd
import pyarrow.parquet as pq
import importlib.util
import numpy as np
import sys
from pathlib import Path

WORK_DIR = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main")
FINRL   = WORK_DIR / "FinRL"
CACHE   = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"

# Load walk_forward_v2
_spec = importlib.util.spec_from_file_location("wf2", FINRL / "walk_forward_v2.py")
_wf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wf)
WalkForwardConfig = _wf.WalkForwardConfig
EnhancedWalkForward = _wf.EnhancedWalkForward

# Read & prepare data
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
df_ta["date"] = df_ta["date"].astype(str)

stock_data = {"0050": df_ta}
holdings   = {"0050": {"shares": 2000, "avg_cost": 95.0}}

config = WalkForwardConfig(
    train_window_years=1.5,
    test_window_days=30,
    step_days=240,
    timesteps=10_000,
    loss_threshold=1.0,
    loss_check_interval=200,
    max_retrains=2,
)

print("Running 1 window only...")
wf = EnhancedWalkForward(stock_data=stock_data, holdings=holdings, config=config)
results = wf.run()
print("\n=== RESULT ===")
for r in results:
    print(f"Window {r.window_id}: RL return={r.total_return:.2%}, Sharpe={r.sharpe:.2f}, BH not in result")
    break
print("Done")
