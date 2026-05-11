#!/usr/bin/env python3
"""快速測試：訓練一個視窗並回測，確認 reward function 是否正確"""
import sys, os, json, subprocess, time, glob
sys.path.insert(0, "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main")
os.chdir("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
import pyarrow.parquet as pq, importlib.util

CACHE = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/data/cache/0050_2016-01-01_2026-05-05_1d.parquet"
FINRL = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL"
OUT   = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/FinRL/models/portfolio/test_reward"

df = pq.read_table(CACHE).to_pandas(timestamp_as_object=True)
spec = importlib.util.spec_from_file_location("ta", FINRL + "/data/technical_analysis.py")
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)
df_ta['ds'] = df_ta['date'].astype(str)

# Train: 2023-03-20~2024-10-08, Test: 2024-10-08~2025-01-08
df_train = df_ta[(df_ta['ds'] >= '2023-03-20') & (df_ta['ds'] <= '2024-10-08')].copy()
df_test  = df_ta[(df_ta['ds'] >= '2024-10-08') & (df_ta['ds'] <= '2025-01-08')].copy()
print(f"Train: {len(df_train)} rows  {df_train['ds'].iloc[0]}~{df_train['ds'].iloc[-1]}")
print(f"Test:  {len(df_test)} rows   {df_test['ds'].iloc[0]}~{df_test['ds'].iloc[-1]}")

# Save train
df_train.to_parquet(FINRL + "/data/cache/wf_train.parquet", index=False)

# 訓練
from portfolio_train_v2 import EnhancedStockTrainer
print("\n開始訓練...")
t0 = time.time()
trainer = EnhancedStockTrainer('0050', df_train, 'ppo',
    enable_risk_manager=True, enable_enhanced_reward=True)
print(f"Reward params: dd={trainer.reward_func.drawdown_penalty}, "
      f"hold={trainer.reward_func.holding_bonus}, trade={trainer.reward_func.trade_reward}")
os.makedirs(OUT, exist_ok=True)
stats = trainer.train(timesteps=30_000, save_path=OUT, verbose=0)
print(f"訓練完成 ({time.time()-t0:.0f}s)")

# Find zip (SB3 saves as .zip in the parent directory when save_path is a directory)
parent = os.path.dirname(OUT.rstrip('/'))
zips = sorted([f for f in os.listdir(parent) if f.endswith('.zip') and 'test_reward' in f])
if not zips:
    # fallback: look in OUT itself
    zips = sorted([f for f in os.listdir(OUT) if f.endswith('.zip')])
if not zips:
    print("沒有 zip"); sys.exit(1)
model_path = parent + "/" + zips[-1]
print(f"Model: {zips[-1]} ({os.path.getsize(model_path)//1024}KB)")

# Backtest
# 清除舊 results
old_results = sorted(glob.glob(FINRL + "/results/backtest_0050_ppo_*.json"), key=os.path.getmtime)
for f in old_results[-5:]:
    os.remove(f)

print("\n開始回測...")
r = subprocess.run([
    'python3', 'run_backtest.py',
    '--agent', 'ppo', '--stock', '0050',
    '--start', '2024-10-08', '--end', '2025-01-08',
    '--model', model_path, '--initial_balance', '1000000',
], capture_output=True, text=True, timeout=120, cwd=FINRL)
print("stdout:", r.stdout[-300:] if r.stdout else "")
print("stderr:", r.stderr[-300:] if r.stderr else "")

# 讀結果
results = sorted(glob.glob(FINRL + "/results/backtest_0050_ppo_*.json"), key=os.path.getmtime)
if results:
    with open(results[-1]) as f:
        bt = json.load(f)
    m = bt['metrics']
    print(f"\n=== 結果 ===")
    print(f"報酬: {m['total_return']*100:.2f}%")
    print(f"Sharpe: {m['sharpe_ratio']:.3f}")
    print(f"MDD: {m['max_drawdown']*100:.2f}%")
    print(f"交易: {m['total_trades']}")
