"""
驗證：_backtest_single 修復後 RL vs B&H 數字是否正確
"""
import pandas as pd, numpy as np, torch, random, importlib.util
from pathlib import Path
from stable_baselines3 import PPO
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from environments.reward_function_v3 import DynamicRewardShaper
import pyarrow.parquet as pq
import sys

FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
CACHE = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"

# 清除 pycache
for p in FINRL.rglob("__pycache__"):
    for f in p.glob("walk_forward_v2*") or []:
        f.unlink(missing_ok=True)
    for f in p.glob("safe_ppo*") or []:
        f.unlink(missing_ok=True)

# Load TA
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

# 設定
test_start = pd.Timestamp('2015-12-14')
test_end = pd.Timestamp('2016-01-25')

# common_dates
common_dates = pd.DatetimeIndex(sorted(pd.to_datetime(df_ta['date']).unique()))
dates_in_window = [d for d in common_dates if test_start <= d <= test_end]
print(f"dates_in_window: {len(dates_in_window)}, {dates_in_window[0].date()} ~ {dates_in_window[-1].date()}")

# 模擬 _test_window 的 df_test + df_aligned 邏輯
df_full = df_ta.set_index('date').sort_index()
df_test_raw = df_full.loc[test_start:test_end].copy()
print(f"df_test_raw: {len(df_test_raw)} rows")

df_aligned = df_test_raw  # 直接用 30 rows（不 reindex）
print(f"df_test: {len(df_aligned)} rows (NOW CORRECT = 30 rows)")

# 訓練 mini model
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
print("Model trained")

# ── 測試「舊邏輯」（用 iloc）vs 「新邏輯」（用 loc） ──
df_test = df_aligned.copy()

# 舊：用 iloc（錯誤）
env_old = TaiwanStockTradingEnv(df=df_test, initial_balance=1_000_000, max_position=4000,
                                 commission_rate=0.001425, tax_rate=0.003)
env_old._print_enabled = True
obs_old, _ = env_old.reset()
env_old.current_step = 0

# 新：用 loc（正確）
env_new = TaiwanStockTradingEnv(df=df_test, initial_balance=1_000_000, max_position=4000,
                                 commission_rate=0.001425, tax_rate=0.003)
env_new._print_enabled = False
obs_new, _ = env_new.reset()
env_new.current_step = 0

bh_portfolio_new = 1_000_000
prev_price_new = None
rl_vals_new = []
bh_vals_new = []

print("\n─── NEW logic (df_test.loc[date]) ───")
for i, date in enumerate(dates_in_window):
    action, _ = model.predict(obs_new, deterministic=True)
    obs_new, reward, terminated, truncated, info = env_new.step(action)
    done = terminated or truncated

    cur_price = df_test.loc[date, 'close'] if date in df_test.index else np.nan

    rl_val_raw = info.get('portfolio_value', np.nan)
    if np.isnan(rl_val_raw):
        rl_val_raw = env_new.balance + env_new.position * cur_price

    if cur_price > 0 and prev_price_new is not None and prev_price_new > 0:
        bh_portfolio_new = bh_portfolio_new * (1 + cur_price/prev_price_new - 1)
    if cur_price > 0:
        prev_price_new = cur_price

    if i < 5 or done:
        print(f"  i={i} date={date.date()} | price={cur_price:.2f} | "
              f"rl={rl_val_raw:.0f} bh={bh_portfolio_new:.0f} | "
              f"action={action} bal={env_new.balance:.0f} pos={env_new.position}")

    rl_vals_new.append(float(rl_val_raw))
    bh_vals_new.append(float(bh_portfolio_new))

    if done:
        print(f"  [terminated at i={i}, filling remaining]")
        for rem in range(i + 1, len(dates_in_window)):
            rl_vals_new.append(np.nan)
            bh_vals_new.append(np.nan)
        break
else:
    while len(rl_vals_new) < len(dates_in_window):
        rl_vals_new.append(np.nan)
        bh_vals_new.append(np.nan)

# 計算 RL return
rl_vals_clean = [v for v in rl_vals_new if not np.isnan(v)]
bh_vals_clean = [v for v in bh_vals_new if not np.isnan(v)]
if rl_vals_clean and bh_vals_clean:
    rl_ret = rl_vals_clean[-1] / rl_vals_clean[0] - 1
    bh_ret = bh_vals_clean[-1] / bh_vals_clean[0] - 1
    rl_sharpe = np.nan if len(rl_vals_clean) < 2 else (rl_vals_clean[-1] - rl_vals_clean[0]) / (np.std(rl_vals_clean) + 1e-12) * np.sqrt(252)
    bh_sharpe = np.nan if len(bh_vals_clean) < 2 else (bh_vals_clean[-1] - bh_vals_clean[0]) / (np.std(bh_vals_clean) + 1e-12) * np.sqrt(252)
    print(f"\n  RL: ret={rl_ret*100:.2f}% sharpe={rl_sharpe:.1f}")
    print(f"  BH: ret={bh_ret*100:.2f}% sharpe={bh_sharpe:.1f}")
    print(f"  Δ: {(rl_ret - bh_ret)*100:.2f}%")
