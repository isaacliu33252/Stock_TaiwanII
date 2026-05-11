#!/usr/bin/env python3
"""
Walk-Forward 訓練（簡化版）
5 個視窗：訓練 1.5 年，測試 3 個月
報酬調整：drawdown_penalty 0.5→0.15, holding_bonus 0.02→0.05
"""
import sys, os, json, subprocess, time
import pandas as pd
import numpy as np
import pyarrow.parquet as pq

WORK_DIR  = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main"
FINRL    = WORK_DIR + "/FinRL"
CACHE    = WORK_DIR + "/data/cache/0050_2016-01-01_2026-05-05_1d.parquet"
PY       = sys.executable

# ── 讀資料 & TA ───────────────────────────────────────────────────────────
df_raw = pq.read_table(CACHE).to_pandas(timestamp_as_object=True)
sys.path.insert(0, FINRL)
import importlib.util
spec = importlib.util.spec_from_file_location("ta", FINRL + "/data/technical_analysis.py")
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df_raw).dropna().reset_index(drop=True)
df_ta['ds'] = df_ta['date'].astype(str).sort_values()
print(f"TA: {len(df_ta)} rows")

dates = sorted(df_ta['ds'].tolist())

# ── 5 個 Walk-Forward 視窗 ─────────────────────────────────────────────────
# Train 1.5 年，Test 3 個月（~63 天），每 3 個月滑動
windows = []
train_len = int(1.5 * 252)   # ~378 days
test_len  = 63                 # ~3 months
stride   = 63                 # 滑動 3 個月

start_idx = train_len
while start_idx < len(dates) - test_len:
    end_idx = start_idx
    t_start = dates[max(0, end_idx - train_len)]
    t_end   = dates[end_idx]
    ts_idx  = start_idx
    te_idx  = min(start_idx + test_len, len(dates) - 1)
    test_start = dates[ts_idx]
    test_end   = dates[te_idx]
    windows.append((t_start, t_end, test_start, test_end))
    start_idx += stride

print(f"\n共 {len(windows)} 個視窗:")
for i, w in enumerate(windows):
    print(f"  [{i+1}] Train {w[0][:10]}~{w[1][:10]}  |  Test {w[2][:10]}~{w[3][:10]}")

# ── Patch 報酬函數 ──────────────────────────────────────────────────────────
trainer_path = FINRL + "/portfolio_train_v2.py"
with open(trainer_path) as f:
    src = f.read()
with open(trainer_path + ".bak", 'w') as f:
    f.write(src)

src = src.replace(
    "drawdown_penalty=0.5,\n        holding_bonus=0.02, trade_reward=0.001,",
    "drawdown_penalty=0.15,\n        holding_bonus=0.05, trade_reward=0.005,"
)
with open(trainer_path, 'w') as f:
    f.write(src)
print("\n報酬函數已調整: drawdown=0.15, holding=0.05, trade=0.005")

# ── 執行 ─────────────────────────────────────────────────────────────────
results = []
OUT_DIR = FINRL + "/FinRL/models/portfolio/wf0050"
os.makedirs(OUT_DIR, exist_ok=True)

for widx, (ts, te, tst, tste) in enumerate(windows):
    print(f"\n[{widx+1}/{len(windows)}] Train {ts[:10]}~{te[:10]} | Test {tst[:10]}~{tste[:10]}")
    t0 = time.time()

    # 訓練
    train_script = f"""
import sys, os
sys.path.insert(0, '{FINRL}')
sys.path.insert(0, '{WORK_DIR}')
os.chdir('{FINRL}')

import pandas as pd, pyarrow.parquet as pq, importlib.util
cache = '{CACHE}'
df = pq.read_table(cache).to_pandas(timestamp_as_object=True)
spec = importlib.util.spec_from_file_location('ta', '{FINRL}/data/technical_analysis.py')
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)
df_ta['ds'] = df_ta['date'].astype(str)
df_w = df_ta[(df_ta['ds'] >= '{ts}') & (df_ta['ds'] <= '{te}')].copy()
df_w.to_parquet('{FINRL}/data/cache/wf_train.parquet', index=False)

from portfolio_train_v2 import EnhancedStockTrainer
trainer = EnhancedStockTrainer(
    ticker='0050', df=df_w, agent_type='ppo',
    enable_risk_manager=True, enable_enhanced_reward=True,
)
save = '{OUT_DIR}/window_{widx+1:02d}'
os.makedirs(save, exist_ok=True)
stats = trainer.train(timesteps=30_000, save_path=save, verbose=0)
print('DONE', stats.get('best_sharpe', 0), stats.get('total_trades', 0))
"""

    r = subprocess.run([PY, "-c", train_script], capture_output=True, text=True, timeout=600, cwd=FINRL)
    elapsed = time.time() - t0
    if r.returncode != 0:
        print(f"  訓練失敗: {r.stderr[-400:]}")
        continue
    print(f"  訓練完成 ({elapsed:.0f}s)")

    # 找模型
    model_base = f"{OUT_DIR}/window_{widx+1:02d}"
    zips = [f for f in os.listdir(model_base) if f.endswith('.zip')] if os.path.exists(model_base) else []
    if not zips:
        # 嘗試上層
        zips = [f for f in os.listdir(OUT_DIR) if f.endswith('.zip')]
    model_path = f"{model_base}/{zips[0]}" if zips else model_base

    # 回測
    bt_r = subprocess.run([
        PY, "run_backtest.py",
        "--agent", "ppo", "--stock", "0050",
        "--start", tst, "--end", tste,
        "--model", model_path,
        "--initial_balance", "1000000",
    ], capture_output=True, text=True, timeout=120, cwd=FINRL)

    result_files = sorted([f for f in os.listdir(FINRL + "/results/") if f.startswith("backtest_0050_ppo_")],
                         key=lambda x: os.path.getmtime(FINRL + "/results/" + x))
    if result_files:
        with open(FINRL + "/results/" + result_files[-1]) as f:
            bt = json.load(f)
        m = bt['metrics']
        results.append({
            'window':       widx + 1,
            'train_start':  ts[:10],
            'train_end':    te[:10],
            'test_start':   tst[:10],
            'test_end':     tste[:10],
            'return':       m['total_return'],
            'ann_return':   m['annual_return'],
            'sharpe':       m['sharpe_ratio'],
            'max_dd':       m['max_drawdown'],
            'trades':       m['total_trades'],
            'final_value':  m['final_value'],
        })
        print(f"  → 報酬 {m['total_return']*100:.2f}%  Sharpe {m['sharpe_ratio']:.3f}  MDD {m['max_drawdown']*100:.2f}%  交易 {m['total_trades']}")

# ── 摘要 ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
df_res = pd.DataFrame(results)
print(df_res.to_string(index=False))

if len(df_res) > 0:
    print(f"\n平均 Sharpe: {df_res['sharpe'].mean():.3f}")
    print(f"平均報酬:   {df_res['return'].mean()*100:.2f}%")
    print(f"平均 MDD:   {df_res['max_dd'].mean()*100:.2f}%")
    print(f"勝率:       {(df_res['return']>0).mean()*100:.1f}%")

    # 用最後模型跑完整 OOS
    latest_window = f"{OUT_DIR}/window_{len(windows):02d}"
    zips = [f for f in os.listdir(latest_window) if f.endswith('.zip')] if os.path.exists(latest_window) else []
    if zips:
        final_model = f"{latest_window}/{zips[0]}"
        print(f"\n{'='*60}")
        print("最終模型 OOS: 2023-07-01 ~ 2026-05-05")
        print(f"{'='*60}")
        r = subprocess.run([
            PY, "run_backtest.py",
            "--agent", "ppo", "--stock", "0050",
            "--start", "2023-07-01", "--end", "2026-05-05",
            "--model", final_model,
            "--initial_balance", "1000000",
        ], capture_output=True, text=True, timeout=120, cwd=FINRL)
        result_files = sorted([f for f in os.listdir(FINRL + "/results/") if f.startswith("backtest_0050_ppo_")],
                             key=lambda x: os.path.getmtime(FINRL + "/results/" + x))
        if result_files:
            with open(FINRL + "/results/" + result_files[-1]) as f:
                bt = json.load(f)
            m = bt['metrics']
            bh_s = df_ta[df_ta['ds'] >= '2023-07-01'].iloc[0]['close']
            bh_e = df_ta[df_ta['ds'] <= '2026-05-05'].iloc[-1]['close']
            bh_r = (bh_e - bh_s) / bh_s
            print(f"模型: 報酬 {m['total_return']*100:.2f}%  Sharpe {m['sharpe_ratio']:.3f}  MDD {m['max_drawdown']*100:.2f}%  交易 {m['total_trades']}")
            print(f"B&H:  {bh_r*100:.2f}%")
            print(f"模型最終: {m['final_value']:,.0f}  vs B&H {1_000_000*(1+bh_r):,.0f}")

# 還原
with open(FINRL + "/portfolio_train_v2.py.bak") as f:
    orig = f.read()
with open(FINRL + "/portfolio_train_v2.py", 'w') as f:
    f.write(orig)
os.remove(FINRL + "/portfolio_train_v2.py.bak")
print("\n已還原 portfolio_train_v2.py")
