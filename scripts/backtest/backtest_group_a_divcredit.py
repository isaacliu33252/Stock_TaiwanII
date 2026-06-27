#!/usr/bin/env python3
"""Standalone Group A backtest with legacy cash-only dividend crediting."""

import sys, json, importlib, zipfile, io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (
    _load_portfolio_cache_ohlcv,
    _align_panel,
    PortfolioEnv,
    _weights_for,
    calculate_backtest_metrics,
    LLM_SENTIMENT_COLUMNS,
)

# ── Config ──────────────────────────────────────────────────────────
BACKTEST_START = "2024-01-02"
BACKTEST_END   = "2026-05-22"
INITIAL_CASH   = 1_000_000.0
GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]

# Find latest model
models_dir = PROJECT_ROOT / "models" / "portfolio"
candidates = sorted(models_dir.glob("group_a_microopt*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
# Pick the one that matches the earlier best (group_a_microopt_b060_p030)
preferred = [p for p in candidates if "b060_p030" in p.name]
MODEL_PATH = preferred[0] if preferred else candidates[0]
print(f"Model: {MODEL_PATH.name}")

# ── Load model ──────────────────────────────────────────────────────
def _load_model(model_path):
    with zipfile.ZipFile(str(model_path), "r") as z:
        policy_bytes = z.read("policy.pth")
        policy_state = torch.load(io.BytesIO(policy_bytes), map_location="cpu", weights_only=False)
        data_json = json.loads(z.read("data"))

    trained_obs_dim = data_json["observation_space"]["_shape"][0]
    # Derive action count from policy action_net shape
    n_actions = policy_state["action_net.weight"].shape[0]

    class _DummyEnv(gym.Env):
        def __init__(self, obs_dim, n_acts):
            super().__init__()
            self.observation_space = spaces.Box(low=-10, high=10, shape=(obs_dim,), dtype=np.float32)
            self.action_space = spaces.Discrete(n_acts)
        def reset(self, seed=None, options=None):
            return np.zeros(self.observation_space.shape, dtype=np.float32), {}
        def step(self, action):
            return np.zeros(self.observation_space.shape, dtype=np.float32), 0.0, False, False, {}

    dummy = _DummyEnv(trained_obs_dim, n_actions)
    model = PPO("MlpPolicy", dummy, verbose=0)
    model.policy.load_state_dict(policy_state, strict=False)
    return model, trained_obs_dim

# ── Feature columns from obs_dim ──────────────────────────────────
FEATURE_COLUMNS = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126", "momentum_252", "rolling_mdd_63",
]
STATE_DIM = 5
def _feature_cols_from_obs_dim(obs_dim, n_tickers):
    base = len(FEATURE_COLUMNS) * n_tickers + STATE_DIM
    shared = obs_dim - base
    return FEATURE_COLUMNS, list(range(shared)) if shared > 0 else None

def _infer_env_kwargs_from_model(model_path):
    """Infer env kwargs from model zip: obs_dim, action count, tickers count."""
    with zipfile.ZipFile(str(model_path), "r") as z:
        policy_bytes = z.read("policy.pth")
        policy_state = torch.load(io.BytesIO(policy_bytes), map_location="cpu", weights_only=False)
        data_json = json.loads(z.read("data"))
    obs_dim = data_json["observation_space"]["_shape"][0]
    n_actions = policy_state["action_net.weight"].shape[0]
    return obs_dim, n_actions

# ── Load data & run ───────────────────────────────────────────────
print(f"\nLoading data: {BACKTEST_START} ~ {BACKTEST_END}")
stock_data = {}
for t in GROUP_A_TICKERS:
    df = _load_portfolio_cache_ohlcv(t, BACKTEST_START, BACKTEST_END)
    if df.empty:
        raise RuntimeError(f"No data for {t}")
    stock_data[t] = df
    print(f"  {t}: {len(df)} rows, dividends={df['dividends'].sum():.3f}")

feature_cols, shared_cols = _feature_cols_from_obs_dim(37, len(GROUP_A_TICKERS))  # 37 from earlier
# shared_feature_cols = LLM_SENTIMENT_COLUMNS (4 cols) + DJI_FEATURE_COLUMNS (5 cols, but use_dji=False)
# Since group_a_use_dji_features=False, shared = 4 LLM sentiment cols
SHARED_FEATURES = LLM_SENTIMENT_COLUMNS  # ['llm_sentiment_score', 'llm_sentiment_confidence', 'llm_risk_off_score', 'llm_news_intensity']
panel = _align_panel(stock_data, GROUP_A_TICKERS, BACKTEST_START, BACKTEST_END,
                     shared_feature_cols=SHARED_FEATURES)
print(f"Panel: {len(panel)} rows, columns={len(panel.columns)}")
div_cols = [c for c in panel.columns if "dividend" in c.lower()]
print(f"Dividend cols: {div_cols}")

# Build env
env_kwargs = {
    "initial_cash": INITIAL_CASH,
    "enable_pva_features": True,
    "enable_pva_sigmoid": True,
    "pva_weight": 0.3,
    "pva_j_state_weight": 0.17,
    "pva_m_state_weight": 1.0,
    "pva_drift_threshold": 0.05,
    "pva_target_vol": 0.012,
    "pva_min_leverage_scale": 0.4,
    "pva_inverse_hedge_budget": 0.3,
    "pva_s_state_drift_boost": 0.0,
    "pva_s_state_max_weight": 0.3,
    "pva_buy_dip_strength": 0.7,
    "dca_monthly_amounts": {"0050.TW": 5000.0},
    "dca_day": 20,
    "inverse_m_state_only": True,
    "inverse_max_holding_days": 5,
    "sentiment_gate_enabled": False,
    "start_allocation": "blend50",
    "group_a_action_schema": "triplet_v3_cash50",
    "profile_name": "default",
    "dividend_mode": "cash",
}

model, obs_dim = _load_model(MODEL_PATH)
_, n_actions = _infer_env_kwargs_from_model(MODEL_PATH)
actual_feature_cols, actual_shared = _feature_cols_from_obs_dim(obs_dim, len(GROUP_A_TICKERS))
print(f"Model obs_dim={obs_dim}, n_actions={n_actions}, features={len(actual_feature_cols) if actual_feature_cols else 0}")
print(f"  shared_feature_cols={actual_shared}")

panel2 = _align_panel(stock_data, GROUP_A_TICKERS, BACKTEST_START, BACKTEST_END,
                      shared_feature_cols=SHARED_FEATURES)
env = PortfolioEnv(panel2, GROUP_A_TICKERS, shared_feature_cols=actual_shared, **env_kwargs)

obs, _ = env.reset()
done = False
while not done:
    action, _ = model.predict(obs, deterministic=True)
    obs, _, terminated, truncated, _ = env.step(action)
    done = terminated or truncated

equity = [float(v) for v in env.equity_curve]
total_contributions = float(env.total_contributions)
total_invested = float(INITIAL_CASH + total_contributions)
net_profit = float(equity[-1] - total_invested)

print(f"\n{'='*60}")
print(f"  Group A 回測（含股息入帳）")
print(f"  期間: {BACKTEST_START} ~ {BACKTEST_END}")
print(f"{'='*60}")
print(f"  最終價值:     {equity[-1]:>14,.0f}")
print(f"  總投入:       {total_invested:>14,.0f}")
print(f"  淨利:         {net_profit:>14,.0f}")
print(f"  投報率:       {net_profit/total_invested*100:.2f}%")
print(f"  DCA 次數:    {env.dca_purchase_count}")
print(f"  DCA 總投入:  {total_contributions:>14,.0f}")
print(f"  總股息入帳:  {env.total_dividend_credited:>14,.0f}")
print(f"  交易次數:    {env.trade_count}")

print(f"\n  股息入帳事件 ({len(env.dividend_credited_history)} 次):")
for h in env.dividend_credited_history:
    print(f"    {h['date']}: {json.dumps(h['credits'], ensure_ascii=False)} total={h['total']:,.0f}")

metrics = calculate_backtest_metrics(equity)
print(f"\n  年化報酬: {metrics['annual_return']*100:.2f}%")
print(f"  Sharpe:  {metrics['sharpe']:.3f}")
print(f"  Max DD:  {metrics['max_drawdown']*100:.2f}%")

# Save
result = {
    "experiment": "group_a_backtest_with_dividend_credit",
    "model": MODEL_PATH.name,
    "backtest_start": BACKTEST_START,
    "backtest_end": BACKTEST_END,
    "initial_cash": INITIAL_CASH,
    "final_value": float(equity[-1]),
    "rl_metrics": metrics,
    "total_invested_capital": total_invested,
    "net_profit": net_profit,
    "dca_config": {"dca_day": 20, "monthly_amounts": {"0050.TW": 5000.0}},
    "dca_purchase_count": int(env.dca_purchase_count),
    "dca_total_contributions": total_contributions,
    "dividend_credited_history": env.dividend_credited_history,
    "total_dividend_credited": float(env.total_dividend_credited),
    "equity_curve": equity,
}

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path = PROJECT_ROOT / "results" / f"group_a_divcredit_{ts}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print(f"\n結果已儲存: {out_path}")
