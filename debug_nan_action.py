"""
隔離測試：直接看 PPO model.predict 的 action 輸出
"""
import sys, os, importlib, hashlib

# 強迫只 load FinRL/ 下的版本
finrl_root = "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL"
sys.path.insert(0, finrl_root)

# 清除 walk_forward_v2 的舊 pycache
import pathlib
for p in pathlib.Path(finrl_root).rglob("__pycache__"):
    for f in p.glob("walk_forward_v2*"):
        f.unlink(missing_ok=True)

# 用 importlib 直接 load
spec = importlib.util.spec_from_file_location(
    "wf2",
    f"{finrl_root}/walk_forward_v2.py"
)
_wf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_wf)

print("WalkForwardConfig fields:", [f for f in dir(_wf.WalkForwardConfig) if not f.startswith('_')])

# 只取一小段數據測試
from stable_baselines3 import PPO
import pandas as pd
import numpy as np

# Load cache
cache_path = f"{finrl_root}/data/cache/0050_2014-05-11_2026-05-05_1d.parquet"
import pandas as pd
import pyarrow.parquet as pq
table = pq.read_table(cache_path)
df = table.to_pandas(timestamp_as_object=True)
df['date'] = df['date'].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'tzinfo') and x.tzinfo else x)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)
df_ta = df[df['date'] >= '2014-05-11'].copy()

# 簡單訓練：5k timesteps, 看 action 輸出
train_start = pd.Timestamp('2015-01-02')
train_end = pd.Timestamp('2015-12-13')
df_train = df_ta[df_ta['date'].between(train_start, train_end)].copy()

from environments.taiwan_stock_env import TaiwanStockTradingEnv
from environments.reward_function_v3 import DynamicRewardShaper

reward_func = DynamicRewardShaper(
    sortino_weight=0.25, calmar_weight=0.20, volatility_penalty=0.1,
    drawdown_penalty=0.15, holding_bonus=0.30, trade_reward=0.005,
    trend_bull_bonus=0.10, trend_bear_penalty=0.08,
    init_reward_scale=1.5, final_reward_scale=0.6,
)
reward_func.set_total_steps(5000)

env = TaiwanStockTradingEnv(
    df=df_train,
    initial_balance=1_000_000,
    max_position=4000,
    trade_unit=1000,
    price_limit=0.10,
    commission_rate=0.001425,
    tax_rate=0.003,
    lookback_window=60,
    initial_shares=0,
    initial_avg_cost=0.0,
    reward_func=reward_func,
    enable_risk_manager=False,
    crash_window=15,
)
env._print_enabled = False

np.random.seed(42)
import random; random.seed(42)
import torch; torch.manual_seed(42)

model = PPO(
    "MlpPolicy", env,
    learning_rate=3e-4,
    n_steps=2048,
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    verbose=0,
)

print("開始 training (5k timesteps)...")
model.learn(total_timesteps=5000, progress_bar=False)
print("訓練完成")

# 看 predict
obs, _ = env.reset()
for _ in range(3):
    action, _state = model.predict(obs, deterministic=True)
    print(f"  action={action}, nan={np.isnan(action).any()}")
    obs, _, terminated, truncated, _ = env.step(action)
    if terminated or truncated:
        obs, _ = env.reset()

print("DONE")
