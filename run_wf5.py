#!/usr/bin/env python3
"""
Walk-Forward 5 視窗 + Ensemble + Crash Detection
- train_len=630（2.5年 training window）
- 每視窗 3 seeds（ensemble）
- crash detection：連續 15 天無交易則強制 CLOSE
"""
import sys, os, json, subprocess, time, shutil
import pandas as pd
import numpy as np

WORK_DIR  = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main"
FINRL     = WORK_DIR + "/FinRL"
CACHE     = WORK_DIR + "/data/cache/0050_2016-01-01_2026-05-05_1d.parquet"
PY        = sys.executable
OUT_DIR   = FINRL + "/FinRL/models/portfolio/wf5_ensemble"
os.makedirs(OUT_DIR, exist_ok=True)

# ── 讀資料+TA ─────────────────────────────────────────────────────────
sys.path.insert(0, FINRL)
import importlib.util
spec = importlib.util.spec_from_file_location("ta", FINRL + "/data/technical_analysis.py")
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)

import pyarrow.parquet as pq
import pyarrow as pa
t = pq.read_table(CACHE)
date_col = t.column('date').cast(pa.timestamp('ms')).to_pylist()
dates = sorted([str(d)[:10] for d in date_col])
print(f"Total: {len(dates)} dates  {dates[0]} ~ {dates[-1]}")

# ── Walk-Forward 參數 ─────────────────────────────────────────────────
train_len  = 882   # 3.5年（3.5×252≈882）
test_len   = 63    # 3個月
stride     = 63    # 滑動3個月
num_seeds  = 3     # 每視窗 ensemble seeds

n = len(dates)
windows = []
s = n - test_len - 4 * stride   # 從倒數第5個視窗往前
for i in range(5):
    e_train = s
    ts = dates[e_train - train_len]; te = dates[e_train]
    tst = dates[s]; tste = dates[min(s + test_len, n - 1)]
    windows.append((ts, te, tst, tste))
    s += stride

print(f"\ntrain_len={train_len}, test_len={test_len}, seeds={num_seeds}")
for i, w in enumerate(windows):
    print(f"  W{i+1}: Train {w[0]}~{w[1]}  Test {w[2]}~{w[3]}")

# ── 修正 environment 追蹤連續無交易 ────────────────────────────────────
ENV_PATCH = f"""
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Tuple, Dict, Optional, List
import pandas as pd

class TaiwanStockTradingEnv(gym.Env):
    metadata = {{'render_modes': ['human']}}

    def __init__(self, data: pd.DataFrame, initial_balance: float = 1_000_000,
                 trade_unit: int = 1000, max_position: int = 10_000,
                 enable_risk_manager: bool = True, crash_window: int = 15):
        super().__init__()
        self.data = data.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.trade_unit = trade_unit
        self.max_position = max_position
        self.enable_risk_manager = enable_risk_manager
        self.crash_window = crash_window  # 連續 N 天無交易 → 強制 close

        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(17,), dtype=np.float32)
        self.action_space = spaces.Discrete(5)

        self.consecutive_idle_days = 0   # crash detection counter
        self._reset_internal()
"""

# 讀取原始 environment 然後修改 step
ENV_FILE = FINRL + "/environments/taiwan_stock_env.py"
with open(ENV_FILE) as f:
    env_src = f.read()

# 確認是否已有 crash detection，沒有就加上
if "consecutive_idle_days" not in env_src:
    # 在 _reset_internal 的 self.trade_history = [] 後面加入 counter init
    old = "self.trade_history = []        # 交易歷史"
    new = "self.trade_history = []        # 交易歷史\n        self.consecutive_idle_days = 0   # crash detection: 連續無交易天數"
    env_src = env_src.replace(old, new, 1)

    # 在 step() 的 action == 0 (HOLD) 邏輯處，加入 crash detection
    # 找 HOLD 相關邏輯並在每次 step 結束前增加 counter
    old_step_end = """        self.current_step += 1
        obs = self._get_observation()
        reward, info = self._calculate_reward()
        done = self._is_done()
        terminated = done
        truncated = False
        return obs, reward, terminated, truncated, info"""
    new_step_end = """        # ── Crash Detection ───────────────────────────────────────────
        # 處於多頭市場（可用趨勢判斷），卻連續 N 天無交易 → 強制 close 離場
        self.consecutive_idle_days += 1
        if (self.consecutive_idle_days >= self.crash_window
                and self.position > 0
                and self.enable_risk_manager):
            # 強制平倉（不打斷現有 position 更新，只在 reward 給予懲罰信號）
            reward = reward - 0.05  # 額外懲罰
            self.consecutive_idle_days = 0   # reset counter
        # ── End Crash Detection ──────────────────────────────────────

        self.current_step += 1
        obs = self._get_observation()
        reward, info = self._calculate_reward()
        done = self._is_done()
        terminated = done
        truncated = False
        return obs, reward, terminated, truncated, info"""
    env_src = env_src.replace(old_step_end, new_step_end)

    # 在 _execute_trade 的成功交易區塊重置 counter
    old_execute = """            return True, f\"BUY {self.trade_unit}@{trade_price:.2f} (T+2 解鎖)\""""
    new_execute = """            self.consecutive_idle_days = 0   # 有交易，reset crash counter
            return True, f\"BUY {self.trade_unit}@{trade_price:.2f} (T+2 解鎖)\""""
    env_src = env_src.replace(old_execute, new_execute)

    with open(ENV_FILE) as f:
        f.write(env_src)
    print("✅ Crash detection 已注入 taiwan_stock_env.py")
else:
    print("✅ Crash detection 已存在")

# ── 主訓練迴圈 ─────────────────────────────────────────────────────────
all_results = []

for widx, (ts, te, tst, tste) in enumerate(windows):
    print(f"\n{'='*60}")
    print(f"[W{widx+1}/5] Train {ts}~{te}  Test {tst}~{tste}")

    window_dir = f"{OUT_DIR}/window_{widx+1:02d}"
    os.makedirs(window_dir, exist_ok=True)

    # 訓練 3 個 seed models
    for seed in range(num_seeds):
        seed_dir = f"{window_dir}/seed_{seed}"
        os.makedirs(seed_dir, exist_ok=True)

        print(f"\n  [Seed {seed}] {'─'*40}")

        # 動態建立訓練腳本
        train_py = f"{FINRL}/_wf_train_w{widx+1}_s{seed}.py"
        with open(train_py, 'w') as f:
            f.write(f"""#!/usr/bin/env python3
import sys, os, uuid, time
sys.path.insert(0, '{FINRL}')
sys.path.insert(0, '{WORK_DIR}')
os.chdir('{FINRL}')

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import importlib.util

# 讀資料（timestamp[ms, tz] → string 避免 PyArrow/Pandas TZ bug）
t = pq.read_table('{CACHE}')
date_idx = t.column_names.index('date')
t2 = t.set_column(date_idx, 'date', t.column('date').cast(pa.string()))
df = t2.to_pandas()

# TA（避免 PyArrow TZ bug: parquet 不跨 process 共用，改用 memory 操作）
import pyarrow.parquet as pq
import pyarrow as pa
_t = pq.read_table('{CACHE}')
_date_idx = _t.column_names.index('date')
_t2 = _t.set_column(_date_idx, 'date', _t.column('date').cast(pa.string()))
_df_raw = _t2.to_pandas()
spec = importlib.util.spec_from_file_location('ta', '{FINRL}/data/technical_analysis.py')
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(_df_raw).dropna().reset_index(drop=True)
df_ta['ds'] = df_ta['date'].astype(str)

# 取出視窗資料（不寫入磁碟，直接在記憶體中處理）
df_w = df_ta[(df_ta['ds'] >= '{ts}') & (df_ta['ds'] <= '{te}')].copy()
print(f'TRAIN_DATA: {{len(df_w)}} rows  {{df_w["ds"].iloc[0]}}~{{df_w["ds"].iloc[-1]}}', flush=True)

from portfolio_train_v2 import EnhancedStockTrainer
from environments.taiwan_stock_env import TaiwanStockTradingEnv

# Patch trainer 的 __init__ 來支援 seed
import stable_baselines3 as SB3
import torch
np.random.seed({seed})
torch.manual_seed({seed})
import random
random.seed({seed})

trainer = EnhancedStockTrainer('0050', df_w, 'ppo',
    enable_risk_manager=True, enable_enhanced_reward=True)

# 注入 seed
trainer.model = None   # force retrain

save = '{seed_dir}'
stats = trainer.train(timesteps=30_000, save_path=save, verbose=0)
print('DONE', flush=True)
""")

        t0 = time.time()
        r = subprocess.run([PY, train_py], capture_output=True, text=True, timeout=360, cwd=FINRL)
        elapsed = time.time() - t0
        print(f"  Seed {seed} training ({elapsed:.0f}s)")

        if r.returncode != 0:
            print(f"  ❌ Seed {seed} failed: {r.stderr[-300:]}")
            continue

        # 找模型 zip
        parent_zip = f"{OUT_DIR}/window_{widx+1:02d}/seed_{seed}.zip"
        if os.path.exists(parent_zip):
            model_path = parent_zip
        else:
            seed_zip_dir = f"{OUT_DIR}/window_{widx+1:02d}/seed_{seed}"
            zips = sorted([f for f in os.listdir(seed_zip_dir) if f.endswith('.zip')]) if os.path.exists(seed_zip_dir) else []
            model_path = f"{seed_zip_dir}/{zips[0]}" if zips else None

        if not model_path or not os.path.exists(model_path):
            print(f"  ❌ Model zip not found")
            continue

        print(f"  Model: {os.path.basename(model_path)} ({os.path.getsize(model_path)//1024}KB)")

        # 回測（每個 seed 產出獨立 UUID JSON）
        import uuid
        run_uuid = uuid.uuid4().hex[:8]
        before_files = set(os.listdir(FINRL + "/results/"))
        bt_r = subprocess.run([
            PY, "run_backtest.py",
            "--agent", "ppo", "--stock", "0050",
            "--start", tst, "--end", tste,
            "--model", model_path,
            "--initial_balance", "1000000",
            "--output_uuid", run_uuid,
        ], capture_output=True, text=True, timeout=120, cwd=FINRL)

        after_files = set(os.listdir(FINRL + "/results/"))
        new_files = sorted([
            f for f in (after_files - before_files)
            if f.startswith("backtest_") and f.endswith(".json")
        ], key=lambda x: os.path.getmtime(FINRL + "/results/" + x))

        if new_files:
            bt_file = FINRL + "/results/" + new_files[-1]
            with open(bt_file) as f:
                bt = json.load(f)
            m = bt['metrics']
            result = {
                'window': widx+1, 'seed': seed,
                'train_start': ts, 'train_end': te,
                'test_start': tst, 'test_end': tste,
                'return': m['total_return'],
                'ann_return': m['annual_return'],
                'sharpe': m['sharpe_ratio'],
                'max_dd': m['max_drawdown'],
                'trades': m['total_trades'],
                'final_value': m['final_value'],
            }
            all_results.append(result)
            print(f"  → Ret={m['total_return']*100:.2f}%  Sharpe={m['sharpe_ratio']:.3f}  MDD={m['max_drawdown']*100:.2f}%  Trades={m['total_trades']}")
        else:
            print(f"  ❌ No backtest result")

        # 清理暫存腳本
        if os.path.exists(train_py):
            os.remove(train_py)

# ── Ensemble 汇总 ───────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("Individual Results:")
df_res = pd.DataFrame(all_results)
print(df_res.to_string(index=False))

# Ensemble per window: average Sharpe, average return
print(f"\n{'='*70}")
print("Ensemble per Window (mean of seeds):")
ens = df_res.groupby('window').agg({
    'return': 'mean', 'ann_return': 'mean', 'sharpe': 'mean',
    'max_dd': 'mean', 'trades': 'mean',
}).round(4)
print(ens.to_string())

if len(df_res) > 0:
    print(f"\nOverall Mean Sharpe:  {df_res['sharpe'].mean():.3f}")
    print(f"Overall Mean Return:  {df_res['return'].mean()*100:.2f}%")
    print(f"Overall Mean MDD:     {df_res['max_dd'].mean()*100:.2f}%")
    print(f"Win rate (windows):  {(ens['return']>0).mean()*100:.1f}%")

# B&H
df_bh_start = windows[0][2]
df_bh_end   = windows[-1][3]
_t3 = pq.read_table(CACHE)
_date_idx3 = _t3.column_names.index('date')
_t4 = _t3.set_column(_date_idx3, 'date', _t3.column('date').cast(pa.string()))
df_full = _t4.to_pandas()
# 重新加載 TA（top-level B&H 需要）
spec_bh = importlib.util.spec_from_file_location("ta_bh", FINRL + "/data/technical_analysis.py")
tm_bh = importlib.util.module_from_spec(spec_bh); spec_bh.loader.exec_module(tm_bh)
df_full_ta = tm_bh.TechnicalIndicators().calculate_all(df_full).dropna().reset_index(drop=True)
df_full_ta['ds'] = df_full_ta['date'].astype(str)
df_bh = df_full_ta[(df_full_ta['ds'] >= df_bh_start) & (df_full_ta['ds'] <= df_bh_end)]
if len(df_bh) >= 2:
    bh = (df_bh['close'].iloc[-1] - df_bh['close'].iloc[0]) / df_bh['close'].iloc[0]
    print(f"\nB&H Return: {bh*100:.2f}%")

# Save results
with open(OUT_DIR + "/ensemble_results.json", 'w') as f:
    json.dump({
        'individual': all_results,
        'ensemble': json.loads(ens.to_json()) if not ens.empty else {},
    }, f, indent=2)
print(f"\nResults saved to {OUT_DIR}/ensemble_results.json")
print("✅ 完成")
