"""
快速重現 NaN logits：訓練到 loss 超標，看 policy 輸出
"""
import numpy as np, pandas as pd, torch, random, sys
from pathlib import Path
from stable_baselines3 import PPO
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from environments.reward_function_v3 import DynamicRewardShaper
import pyarrow.parquet as pq

FINRL = Path("/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL")
CACHE = FINRL / "data/cache/0050_2014-05-11_2026-05-05_1d.parquet"

# Load
table = pq.read_table(CACHE)
df = table.to_pandas(timestamp_as_object=True)
df['date'] = df['date'].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'tzinfo') and x.tzinfo else x)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)
for col in ["close","high","low","open","volume"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df = df.dropna(subset=["close"])

# TA
import importlib.util
spec_ta = importlib.util.spec_from_file_location("ta", str(FINRL/"data/technical_analysis.py"))
tm = importlib.util.module_from_spec(spec_ta); spec_ta.loader.exec_module(tm)
df_ta = tm.TechnicalIndicators().calculate_all(df).dropna().reset_index(drop=True)

train_start = pd.Timestamp('2015-01-02')
train_end = pd.Timestamp('2015-12-13')
df_train = df_ta[df_ta['date'].between(train_start, train_end)].copy()

reward_func = DynamicRewardShaper(
    sortino_weight=0.25, calmar_weight=0.20, volatility_penalty=0.1,
    drawdown_penalty=0.15, holding_bonus=0.30, trade_reward=0.005,
    trend_bull_bonus=0.10, trend_bear_penalty=0.08,
    init_reward_scale=1.5, final_reward_scale=0.6,
)
reward_func.set_total_steps(10000)

env = TaiwanStockTradingEnv(
    df=df_train, initial_balance=1_000_000,
    max_position=4000, trade_unit=1000, price_limit=0.10,
    commission_rate=0.001425, tax_rate=0.003,
    lookback_window=60, initial_shares=0, initial_avg_cost=0.0,
    reward_func=reward_func, enable_risk_manager=False, crash_window=15,
)
env._print_enabled = False

# Seed collapse callback
class SeedCollapseCallback:
    def __init__(self, threshold=1.0, check_interval=500, verbose=0):
        self.threshold = threshold
        self.check_interval = check_interval
        self.verbose = verbose
        self.collapsed = False
        self.best_loss = float('inf')

    def __call__(self, _locals, _globals):
        if self.collapsed:
            return False
        step = _locals.get('n_steps', 0)
        if step % self.check_interval == 0 and step > 0:
            loss_vals = _locals.get('lossvals', [])
            if loss_vals:
                cur_loss = np.mean(loss_vals[-10:])
                if cur_loss > self.threshold:
                    print(f"  [CollapseCB] loss={cur_loss:.4f} > {self.threshold}, abort!")
                    self.collapsed = True
                    return False
                self.best_loss = min(self.best_loss, cur_loss)
        return True

np.random.seed(42); random.seed(42); torch.manual_seed(42)

model = PPO(
    "MlpPolicy", env,
    learning_rate=3e-4, n_steps=2048, batch_size=64, n_epochs=10,
    gamma=0.99, verbose=0,
)

cb = SeedCollapseCallback(threshold=1.0, check_interval=500, verbose=1)
print("Training 10k timesteps with loss threshold=1.0...")
try:
    model.learn(total_timesteps=10000, progress_bar=False, callback=cb)
except ValueError as e:
    print(f"  ValueError caught: {e}")
print(f"  collapsed={cb.collapsed}, best_loss={cb.best_loss:.4f}")

# Check policy output
if cb.collapsed:
    print("\n模型已崩潰，檢查 policy weights:")
    for name, param in model.policy.named_parameters():
        if torch.isnan(param).any():
            print(f"  NaN in {name}: shape={param.shape}")
        if torch.isinf(param).any():
            print(f"  Inf in {name}: shape={param.shape}")
    print("  (如果上面沒輸出，代表 weights 沒 NaN，是 forward pass 時才產生)")
    
    # Try predict
    obs, _ = env.reset()
    try:
        action, _state = model.predict(obs, deterministic=True)
        print(f"\n  predict action={action}, nan={np.isnan(action).any()}")
    except Exception as e:
        print(f"\n  predict ERROR: {e}")

print("\nDONE")
