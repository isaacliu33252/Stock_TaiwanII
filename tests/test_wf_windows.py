#!/usr/bin/env python3
import sys, os
sys.path.insert(0, "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main")
os.chdir("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
import pyarrow.parquet as pq, importlib.util
df = pq.read_table("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/data/cache/0050_2016-01-01_2026-05-05_1d.parquet").to_pandas(timestamp_as_object=True)
spec = importlib.util.spec_from_file_location("ta", "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/data/technical_analysis.py")
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)
df_ta["ds"] = df_ta["date"].astype(str)
dates = sorted(df_ta["ds"].tolist())
print(f"Total dates: {len(dates)}")
wl = []
for i in range(5):
    ts_idx = 378 + i*63
    te_idx = ts_idx
    tst_idx = ts_idx
    tste_idx = min(ts_idx+63, len(dates)-1)
    wl.append((dates[max(0,te_idx-378)], dates[te_idx], dates[tst_idx], dates[tste_idx]))
for i,w in enumerate(wl):
    print(f"W{i+1}: Train {w[0][:10]}~{w[1][:10]}  Test {w[2][:10]}~{w[3][:10]}")
