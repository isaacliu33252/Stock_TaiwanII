#!/usr/bin/env python3
"""Seed Collapse 安全閥測試 — 乾淨載入 FinRL/walk_forward_v2.py"""
import sys
from pathlib import Path
import importlib.util

FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")

# ── Step 1: 清除舊 pycache，確保乾淨載入 ───────────────────────────────────
for f in (FINRL / "__pycache__").glob("walk_forward_v2*.pyc"):
    f.unlink()

# ── Step 2: 用 importlib 直接從 FinRL/ 載入新版 walk_forward_v2 ─────────────
_spec = importlib.util.spec_from_file_location(
    "walk_forward_v2_fresh",
    FINRL / "walk_forward_v2.py"
)
_wf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wf)

# 從新版模組取值
WalkForwardConfig = _wf.WalkForwardConfig
EnhancedWalkForward = _wf.EnhancedWalkForward

# 驗證：確認 cur_price 使用 df_test.iloc
import inspect
src = inspect.getsource(_wf.EnhancedWalkForward._backtest_single)
assert "df_test.iloc" in src, "ERROR: df_test.iloc NOT found in _backtest_single!"
print("✓ _backtest_single 使用 df_test.iloc（價格邏輯正確）")

# ── Step 3: 資料 ───────────────────────────────────────────────────────────
import pandas as pd
import pyarrow.parquet as pq

CACHE = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"
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

# ── Step 4: Config ───────────────────────────────────────────────────────────
config = WalkForwardConfig(
    train_window_years=1.5,
    test_window_days=30,
    step_days=30,
    timesteps=10_000,
    loss_threshold=1.0,
    loss_check_interval=200,
    max_retrains=2,
)

print(f"設定: loss_threshold={config.loss_threshold}, max_retrains={config.max_retrains}")
print()

# ── Step 5: 跑 ─────────────────────────────────────────────────────────────
wf = EnhancedWalkForward(stock_data=stock_data, holdings=holdings, config=config)
results = wf.run()
wf.print_summary()
