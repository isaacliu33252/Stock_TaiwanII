#!/usr/bin/env python3
import sys, os, uuid, time
sys.path.insert(0, '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL')
sys.path.insert(0, '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')
os.chdir('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL')

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import importlib.util

# 讀資料（timestamp[ms, tz] → string 避免 PyArrow/Pandas TZ bug）
t = pq.read_table('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/data/cache/0050_2016-01-01_2026-05-05_1d.parquet')
date_idx = t.column_names.index('date')
t2 = t.set_column(date_idx, 'date', t.column('date').cast(pa.string()))
df = t2.to_pandas()

# TA（避免 PyArrow TZ bug: parquet 不跨 process 共用，改用 memory 操作）
import pyarrow.parquet as pq
import pyarrow as pa
_t = pq.read_table('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/data/cache/0050_2016-01-01_2026-05-05_1d.parquet')
_date_idx = _t.column_names.index('date')
_t2 = _t.set_column(_date_idx, 'date', _t.column('date').cast(pa.string()))
_df_raw = _t2.to_pandas()
spec = importlib.util.spec_from_file_location('ta', '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/data/technical_analysis.py')
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(_df_raw).dropna().reset_index(drop=True)
df_ta['ds'] = df_ta['date'].astype(str)

# 取出視窗資料（不寫入磁碟，直接在記憶體中處理）
df_w = df_ta[(df_ta['ds'] >= '2022-03-07') & (df_ta['ds'] <= '2025-10-20')].copy()
print(f'TRAIN_DATA: {len(df_w)} rows  {df_w["ds"].iloc[0]}~{df_w["ds"].iloc[-1]}', flush=True)

from portfolio_train_v2 import EnhancedStockTrainer
from environments.taiwan_stock_env import TaiwanStockTradingEnv

# Patch trainer 的 __init__ 來支援 seed
import stable_baselines3 as SB3
import torch
np.random.seed(1)
torch.manual_seed(1)
import random
random.seed(1)

trainer = EnhancedStockTrainer('0050', df_w, 'ppo',
    enable_risk_manager=True, enable_enhanced_reward=True)

# 注入 seed
trainer.model = None   # force retrain

save = '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/FinRL/models/portfolio/wf5_ensemble/window_04/seed_1'
stats = trainer.train(timesteps=30_000, save_path=save, verbose=0)
print('DONE', flush=True)
