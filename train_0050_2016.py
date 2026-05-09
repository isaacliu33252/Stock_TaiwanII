#!/usr/bin/env python3
"""用 2016-2023 訓練，2023-2026 測試 0050"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# 避免 package shadowing 問題，直接 import 模組
import pandas as pd
import numpy as np
from datetime import datetime
import pyarrow.parquet as pq
import importlib.util

# 直接載入 technical_analysis（避開 package init 的迴圈引用）
spec = importlib.util.spec_from_file_location(
    "technical_analysis",
    os.path.dirname(__file__) + "/data/technical_analysis.py"
)
ti_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ti_module)
TechnicalIndicators = ti_module.TechnicalIndicators

# 直接載入 environment（避開 package init）
env_spec = importlib.util.spec_from_file_location(
    "taiwan_stock_env",
    os.path.dirname(__file__) + "/environments/taiwan_stock_env.py"
)
env_module = importlib.util.module_from_spec(env_spec)

# reward_function_v3
reward_spec = importlib.util.spec_from_file_location(
    "reward_function_v3",
    os.path.dirname(__file__) + "/environments/reward_function_v3.py"
)
reward_module = importlib.util.module_from_spec(reward_spec)
reward_spec.loader.exec_module(reward_module)
DynamicRewardShaper = reward_module.DynamicRewardShaper

env_spec.loader.exec_module(env_module)
TaiwanStockTradingEnv = env_module.TaiwanStockTradingEnv

# 1. 讀取完整資料
cache = '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/data/cache/0050_2016-01-01_2026-05-05_1d.parquet'
df_full = pq.read_table(cache).to_pandas(timestamp_as_object=True)
print(f"Loaded: {len(df_full)} rows, {df_full.iloc[0]['date']} ~ {df_full.iloc[-1]['date']}")

# 2. 手動計算技術指標
ti = TechnicalIndicators()
df_ta = ti.calculate_all(df_full)
df_ta = df_ta.dropna()
print(f"After TA: {len(df_ta)} rows")

# 3. 切割訓練/測試
df_ta['date_str'] = df_ta['date'].astype(str)
train_end = '2023-06-30'
test_start = '2023-07-01'
df_train = df_ta[df_ta['date_str'] <= train_end].copy()
df_test = df_ta[df_ta['date_str'] >= test_start].copy()
print(f"Train: {len(df_train)} rows ({df_train.iloc[0]['date']} ~ {df_train.iloc[-1]['date']})")
print(f"Test:  {len(df_test)} rows ({df_test.iloc[0]['date']} ~ {df_test.iloc[-1]['date']})")

# 4. 訓練
env = TaiwanStockTradingEnv(
    df=df_train,
    initial_balance=1_000_000,
    max_position=4000,
    reward_func=DynamicRewardShaper(
        sortino_weight=0.25, calmar_weight=0.20,
        volatility_penalty=0.1, drawdown_penalty=0.5,
        holding_bonus=0.02, trade_reward=0.001,
        init_reward_scale=1.5, final_reward_scale=0.6,
    )
)

from stable_baselines3 import PPO
model = PPO("MlpPolicy", env, learning_rate=3e-4, n_steps=2048,
            batch_size=64, n_epochs=10, gamma=0.99, verbose=1)
print("\n開始訓練 (100k steps)...")
model.learn(total_timesteps=100_000)

# 5. 儲存
save_path = os.path.dirname(__file__) + "/FinRL/models/portfolio/0050.TW_2016train"
os.makedirs(os.path.dirname(save_path), exist_ok=True)
model.save(save_path)
print(f"\n模型已儲存: {save_path}")

# 6. 回測 2023-2026
print("\n" + "="*60)
print("Out-of-Sample 回測: 2023-07-01 ~ 2026-05-05")
print("="*60)
test_env = TaiwanStockTradingEnv(
    df=df_test,
    initial_balance=1_000_000,
    max_position=4000,
)
obs, _ = test_env.reset()
done = False
trades = []
portfolio_value = [test_env._initial_balance]
actions_history = []
while not done:
    action, _ = model.predict(obs, deterministic=True)
    obs, reward, terminated, truncated, info = test_env.step(action)
    done = terminated or truncated
    if info.get('trade_executed'):
        trades.append({'date': info['date'], 'action': info.get('action', action), 'price': info.get('price', 0)})
    actions_history.append(action)
    portfolio_value.append(info['portfolio_value'])

final_value = portfolio_value[-1]
initial = 1_000_000
total_return = (final_value - initial) / initial
days = len(df_test)
annual_return = (final_value / initial) ** (252 / days) - 1
returns = np.diff(portfolio_value) / portfolio_value[:-1]
sharpe = np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252) if np.std(returns, ddof=1) > 0 else 0
cummax = np.maximum.accumulate(portfolio_value)
drawdowns = (np.array(portfolio_value) - cummax) / cummax
max_dd = np.min(drawdowns)
print(f"總報酬: {total_return*100:.2f}%")
print(f"年化報酬: {annual_return*100:.2f}%")
print(f"Sharpe: {sharpe:.3f}")
print(f"最大回撤: {max_dd*100:.2f}%")
print(f"交易次數: {len(trades)}")
print(f"最終價值: {final_value:,.0f}")
