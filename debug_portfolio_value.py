"""
Debug: 看 env.step() 後 portfolio_value / balance / position 的實際值
"""
import pandas as pd, numpy as np, torch, random, importlib.util
from pathlib import Path
from stable_baselines3 import PPO
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from environments.reward_function_v3 import DynamicRewardShaper
import pyarrow.parquet as pq

FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
CACHE = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"

table = pq.read_table(CACHE)
df = table.to_pandas(timestamp_as_object=True)
df['date'] = df['date'].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'tzinfo') and x.tzinfo else x)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)
for col in ["close","high","low","open","volume"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df = df.dropna(subset=["close"])

spec_ta = importlib.util.spec_from_file_location("ta", str(FINRL/"data/technical_analysis.py"))
tm = importlib.util.module_from_spec(spec_ta); spec_ta.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)

test_start = pd.Timestamp('2015-12-14')
test_end = pd.Timestamp('2016-01-25')
df_test = df_ta[df_ta['date'].between(test_start, test_end)].copy()

env = TaiwanStockTradingEnv(
    df=df_test,
    initial_balance=1_000_000,
    max_position=4000,
    commission_rate=0.001425,
    tax_rate=0.003,
)
env._print_enabled = False

# 訓練一個 mini model（5k timesteps）
from safe_ppo import SafeActorCriticPolicy
train_start = pd.Timestamp('2015-01-02')
train_end = pd.Timestamp('2015-12-13')
df_train = df_ta[df_ta['date'].between(train_start, train_end)].copy()

reward_func = DynamicRewardShaper(
    sortino_weight=0.25, calmar_weight=0.20, volatility_penalty=0.1,
    drawdown_penalty=0.15, holding_bonus=0.30, trade_reward=0.005,
    trend_bull_bonus=0.10, trend_bear_penalty=0.08,
    init_reward_scale=1.5, final_reward_scale=0.6,
)
reward_func.set_total_steps(5000)

env_train = TaiwanStockTradingEnv(
    df=df_train, initial_balance=1_000_000,
    max_position=4000, trade_unit=1000, price_limit=0.10,
    commission_rate=0.001425, tax_rate=0.003,
    lookback_window=60, initial_shares=0, initial_avg_cost=0.0,
    reward_func=reward_func, enable_risk_manager=False, crash_window=15,
)
env_train._print_enabled = False

np.random.seed(42); random.seed(42); torch.manual_seed(42)
model = PPO(
    SafeActorCriticPolicy, env_train,
    policy_kwargs={'log_clip_min': -20.0, 'log_clip_max': 20.0},
    learning_rate=3e-4, n_steps=2048, batch_size=64, n_epochs=10,
    gamma=0.99, verbose=0,
)
model.learn(5000, progress_bar=False)

# 回測：用 _backtest_single 的邏輯
print("\n=== 回測測試（視窗1：2015-12-14 ~ 2016-01-25）===")
from stable_baselines3 import PPO
agent_model = model  # 直接用 model 物件

env_test = TaiwanStockTradingEnv(
    df=df_test.copy(),
    initial_balance=1_000_000,
    max_position=4000,
    commission_rate=0.001425,
    tax_rate=0.003,
)
env_test._print_enabled = False

obs, _ = env_test.reset()
env_test.current_step = 0

rl_values = []
actions_log = []
for i in range(min(10, len(df_test))):
    action, _ = agent_model.predict(obs, deterministic=True)
    actions_log.append(action)
    obs, reward, terminated, truncated, info = env_test.step(action)

    pv = info.get('portfolio_value', np.nan)
    bal = env_test.balance
    pos = env_test.position
    cur_price = df_test.iloc[env_test.current_step-1]['close'] if env_test.current_step > 0 else df_test.iloc[0]['close']
    calc_pv = bal + pos * cur_price

    print(f"  step {i}: action={action} | price={cur_price:.2f} | bal={bal:.0f} | pos={pos} | "
          f"pv(info)={pv} | calc={calc_pv:.0f} | reward={reward:.4f}")

    rl_values.append(pv if pv is not None else calc_pv)

    if terminated or truncated:
        print(f"  [terminated at step {i}]")
        break

print(f"\nrl_values: {rl_values[:5]}")
print(f"actions: {actions_log[:5]}")
print(f"全部 action 都是 0? {all(a == 0 for a in actions_log)}")
print(f"全部 pv=1M? {all(abs(v - 1_000_000) < 1 for v in rl_values[:5]) if rl_values else 'N/A'}")
