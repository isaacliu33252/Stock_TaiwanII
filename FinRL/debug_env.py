#!/usr/bin/env python3
import pandas as pd
import pyarrow.parquet as pq
import importlib.util
from environments.taiwan_stock_env import TaiwanStockTradingEnv

CACHE = "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"
df_raw = pq.read_table(CACHE).to_pandas(timestamp_as_object=True)
df_raw["date"] = df_raw["date"].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, "tzinfo") and x.tzinfo else x)
df_raw["date"] = pd.to_datetime(df_raw["date"])
df_raw = df_raw.sort_values("date").reset_index(drop=True)
for col in ["close","high","low","open"]:
    df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")
df_raw["volume"] = pd.to_numeric(df_raw["volume"], errors="coerce")
df_raw["price"] = df_raw["close"]
df_raw = df_raw.dropna(subset=["price"])

spec = importlib.util.spec_from_file_location("ta", "data/technical_analysis.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df_raw).dropna().reset_index(drop=True)
df_ta["date"] = df_ta["date"].astype(str)

# Window 1 test period: 2015-12-14 to 2016-01-25
test = df_ta[(df_ta["date"] >= "2015-12-14") & (df_ta["date"] < "2016-01-25")].copy()
print("Test rows:", len(test))
print("Prices:", test["price"].tolist())
print("Dates:", test["date"].tolist())

env = TaiwanStockTradingEnv(df=test, initial_balance=1_000_000, max_position=2000, commission_rate=0.001425, tax_rate=0.003)
env._print_enabled = False
obs, info = env.reset()
print("\n=== After reset ===")
print("portfolio_value:", info.get("portfolio_value"))
print("balance:", env.balance)
print("position:", env.position)
print("price:", info.get("price"))

print("\n=== First 5 steps ===")
for i in range(5):
    obs, r, term, trunc, info = env.step(2)
    print(f"step {i}: pv={info.get('portfolio_value')} price={info.get('price')} bal={env.balance} pos={env.position} action={info.get('action')}")
    if term or trunc:
        print("ENV DONE")
        break
