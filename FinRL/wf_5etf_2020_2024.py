#!/usr/bin/env python3
"""
Walk-Forward Backtest — 5 ETF 投資組合
訓練: 2020-07-10 ~ 2024-12-31
回測: 2025-01-02 ~ 2026-05-15

使用 5ETF 專用離散配置環境 + PPO，輸出 FinRL-X 格式權重與績效。
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import gymnasium as gym

warnings.filterwarnings('ignore')

# ── 路徑 ─────────────────────────────────────────────────────────────────
STOCK2       = Path(__file__).resolve().parent
RESULT_DIR   = STOCK2 / "results" / "wf_5etf_2020_2024"
RESULT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(STOCK2))

# ── 參數 ─────────────────────────────────────────────────────────────────
TICKERS       = ["0050.TW", "0056.TW", "00631L.TW", "00713.TW", "00878.TW"]
TRAIN_START   = "2020-07-10"
TRAIN_END     = "2024-12-31"
TEST_START    = "2025-01-02"
TEST_END      = "2026-05-15"
INITIAL_CASH  = 1_000_000
TIMESTEPS     = 50_000
SEED          = 42

# ── 共享常數（從 train_portfolio 移植）──────────────────────────────────
COMMISSION_RATE = 0.001425
ETF_TAX_RATE    = 0.001
TURNOVER_PENALTY = 0.01
MIN_REBALANCE_DAYS = 20

ACTION_LABELS = {
    0: "hold current weights",
    1: "20/20/20/20/20 equal weight",
    2: "100% 0050",
    3: "70/10/10/5/5 0050 core",
    4: "60/10/20/5/5 with 00631L tilt",
    5: "80/0/10/0/10 0050+00631L+00878",
    6: "15/25/0/25/35 dividend tilt",
    7: "100% best 6M momentum ETF",
    8: "50/50 top-2 6M momentum ETFs",
    9: "50% cash defensive basket",
}

FEATURE_COLUMNS = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126", "momentum_252",
    "rolling_mdd_63",
]
PER_TICKER_CONTEXT_COLUMNS = ["sector_correlation"]
SHARED_MARKET_FEATURE_COLUMNS = [
    "twse_index_return", "twse_index_volume_change", "sector_correlation",
    "market_volatility", "dji_return_1d_lag1", "dji_return_5d_lag1",
    "dji_volatility_20d_lag1", "dji_ma60_ratio_lag1", "dji_drawdown_60d_lag1",
]

# ─────────────────────────────────────────────────────────────────────────
# Step 1: 下載數據
# ─────────────────────────────────────────────────────────────────────────
print("═" * 60)
print("Step 1: 下載數據")
print("═" * 60)

cache_dir = STOCK2 / "data" / "cache"
cache_dir.mkdir(parents=True, exist_ok=True)

def download_with_cache(ticker, start, end):
    cache_path = cache_dir / f"{ticker}_{start}_{end}_1d.parquet"
    if cache_path.exists():
        try:
            df = pd.read_parquet(str(cache_path))
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date').sort_index()
            elif df.index.name == 'date':
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
            if len(df) > 100:
                print(f"  [{ticker}] 快取: {df.index.min().date()} ~ {df.index.max().date()}, {len(df)} 筆")
                return df
        except Exception:
            pass
    print(f"  [{ticker}] 下載中...", end=" ", flush=True)
    raw = yf.download(ticker, start=start, end=end, progress=False)
    if raw.empty:
        raise ValueError(f"{ticker} 無數據")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    df = raw.reset_index()
    date_col = [c for c in df.columns if c.lower() == 'date'][0]
    df = df.rename(columns={date_col: 'date'})
    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    df = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
    df.set_index('date', inplace=True)
    df.sort_index(inplace=True)
    try:
        df.to_parquet(str(cache_path))
    except Exception:
        pass
    print(f"完成 {len(df)} 筆, {df.index.min().date()} ~ {df.index.max().date()}")
    return df

stock_data = {}
for t in TICKERS:
    stock_data[t] = download_with_cache(t, TRAIN_START, TEST_END)

# ─────────────────────────────────────────────────────────────────────────
# Step 2: 計算技術指標（與 train_portfolio 一致）
# ─────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("Step 2: 技術指標")
print("═" * 60)

def add_portfolio_features(df):
    """與 train_portfolio_0050_0056_00713_00878... 的 _add_portfolio_features 一致"""
    df = df.copy()
    close = df['close']
    vol   = df['volume']

    df['returns'] = close.pct_change().fillna(0)

    # MA 類
    df['close_ma20']  = close.rolling(20, min_periods=1).mean()
    df['close_ma60']  = close.rolling(60, min_periods=1).mean()
    df['close_ma120'] = close.rolling(120, min_periods=1).mean()
    df['close_ma240'] = close.rolling(240, min_periods=1).mean()

    df['close_ma120_ratio'] = (close / df['close_ma120']).fillna(1.0)
    df['close_ma240_ratio'] = (close / df['close_ma240']).fillna(1.0)
    df['ma60_ma240_ratio']   = (df['close_ma60'] / df['close_ma240']).fillna(1.0)

    # 動能
    for w in [21, 63, 126, 252]:
        df[f'momentum_{w}'] = (close / close.shift(w) - 1).fillna(0)

    # 波動率
    df['volatility_20'] = close.pct_change().rolling(20, min_periods=1).std(ddof=1).fillna(0)

    # 成交量
    df['volume_ma20']  = vol.rolling(20, min_periods=1).mean()
    df['volume_ratio'] = (vol / df['volume_ma20']).fillna(1.0)

    # MDD
    rolling_max = close.rolling(63, min_periods=1).max()
    rolling_dd  = close / rolling_max - 1
    df['rolling_mdd_63'] = rolling_dd.fillna(0)

    return df

for t in TICKERS:
    stock_data[t] = add_portfolio_features(stock_data[t])

print(f"  技術指標完成")

# ─────────────────────────────────────────────────────────────────────────
# Step 3: 組裝 panel（與 train_portfolio._align_panel 完全一致）
# ─────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("Step 3: 組裝 Panel")
print("═" * 60)

def _slice_by_date(df, start, end):
    out = df.copy()
    if out.index.name == 'date':
        out = out.reset_index()
    out['date'] = pd.to_datetime(out['date'])
    out = out.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
    return out[(out['date'] >= pd.Timestamp(start)) & (out['date'] <= pd.Timestamp(end))].copy()

def _align_panel(stock_data, tickers, start, end):
    frames = []
    for ticker in tickers:
        df = _slice_by_date(stock_data[ticker], start, end)
        cols = ['date', 'close'] + [c for c in FEATURE_COLUMNS if c in df.columns]
        cols = list(dict.fromkeys(cols))  # preserve order, unique
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != 'date'})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on='date', how='inner')

    # market features from first ticker
    ref_df = _slice_by_date(stock_data[tickers[0]], start, end)
    shared_market_cols = ['date'] + [c for c in SHARED_MARKET_FEATURE_COLUMNS if c in ref_df.columns]
    if len(shared_market_cols) > 1:
        panel = panel.merge(ref_df[shared_market_cols].copy(), on='date', how='left')

    panel = panel.sort_values('date').reset_index(drop=True)
    panel = panel.ffill().bfill().fillna(0.0)
    return panel


class FiveETFPortfolioEnv(gym.Env):
    """Small 5-ETF discrete allocator used only by this walk-forward script."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        panel,
        initial_cash=INITIAL_CASH,
        commission_rate=COMMISSION_RATE,
        tax_rate=ETF_TAX_RATE,
        turnover_penalty=TURNOVER_PENALTY,
        min_rebalance_days=MIN_REBALANCE_DAYS,
        min_weight=0.0,
        max_weight=1.0,
    ):
        self.panel = panel.reset_index(drop=True).copy()
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.tax_rate = float(tax_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.min_rebalance_days = int(min_rebalance_days)
        self.min_weight = float(min_weight)
        self.max_weight = float(max_weight)
        self.tickers = list(TICKERS)
        self.price_cols = [f"{ticker}_close" for ticker in self.tickers]
        self.feature_cols = []
        for ticker in self.tickers:
            self.feature_cols.extend(
                [f"{ticker}_{col}" for col in FEATURE_COLUMNS if f"{ticker}_{col}" in self.panel.columns]
            )

        self.portfolio_state_dim = len(self.tickers) + 3
        obs_dim = len(self.feature_cols) + self.portfolio_state_dim
        self.observation_space = gym.spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = gym.spaces.Discrete(len(ACTION_LABELS))
        self.reset()

    def _prices(self, idx):
        return self.panel.loc[idx, self.price_cols].to_numpy(dtype=float)

    def _target_weights(self, action):
        action = int(action)
        if action == 0:
            return self.weights.copy()
        if action == 1:
            weights = np.ones(len(self.tickers), dtype=float) / len(self.tickers)
        elif action == 2:
            weights = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        elif action == 3:
            weights = np.array([0.70, 0.10, 0.10, 0.05, 0.05])
        elif action == 4:
            weights = np.array([0.60, 0.10, 0.20, 0.05, 0.05])
        elif action == 5:
            weights = np.array([0.80, 0.00, 0.10, 0.00, 0.10])
        elif action == 6:
            weights = np.array([0.15, 0.25, 0.00, 0.25, 0.35])
        elif action in (7, 8):
            momentum = np.array(
                [float(self.panel.iloc[self.step_idx].get(f"{ticker}_momentum_126", 0.0)) for ticker in self.tickers]
            )
            order = np.argsort(momentum)[::-1]
            weights = np.zeros(len(self.tickers), dtype=float)
            if action == 7:
                weights[order[0]] = 1.0
            else:
                weights[order[:2]] = 0.5
        elif action == 9:
            weights = np.array([0.20, 0.10, 0.00, 0.10, 0.10])
        else:
            weights = self.weights.copy()

        weights = np.clip(weights, self.min_weight, self.max_weight)
        total = weights.sum()
        if total <= 0:
            return np.ones(len(self.tickers), dtype=float) / len(self.tickers)
        if total > 1.0:
            return weights / total
        return weights

    def _portfolio_value(self, prices):
        return float(self.cash + np.dot(self.shares, prices))

    def _get_obs(self):
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        state = np.concatenate(
            [
                self.weights,
                np.array(
                    [
                        self.cash / max(self.portfolio_value, 1.0),
                        self.portfolio_value / self.initial_cash - 1.0,
                        self.portfolio_value / max(self.peak_value, 1.0) - 1.0,
                    ],
                    dtype=float,
                ),
            ]
        )
        obs = np.concatenate([features, state])
        return np.nan_to_num(obs, nan=0.0, posinf=10.0, neginf=-10.0).clip(-10.0, 10.0).astype(np.float32)

    def reset(self, seed=None, options=None):
        if seed is not None:
            np.random.seed(seed)
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = np.zeros(len(self.tickers), dtype=float)
        self.weights = np.zeros(len(self.tickers), dtype=float)
        self.portfolio_value = self.initial_cash
        self.peak_value = self.initial_cash
        self.last_rebalance_idx = -10**9
        return self._get_obs(), {}

    def step(self, action):
        current_idx = self.step_idx
        current_prices = self._prices(current_idx)
        value_before = self._portfolio_value(current_prices)
        old_weights = self.weights.copy()

        target_weights = self._target_weights(action)
        turnover = float(np.abs(target_weights - old_weights).sum())
        can_trade = current_idx - self.last_rebalance_idx >= self.min_rebalance_days
        if int(action) != 0 and can_trade:
            trade_cost = value_before * turnover * (self.commission_rate + self.tax_rate)
            investable_value = max(value_before - trade_cost, 0.0)
            self.shares = investable_value * target_weights / current_prices
            self.cash = investable_value * max(1.0 - target_weights.sum(), 0.0)
            self.weights = target_weights.copy()
            self.last_rebalance_idx = current_idx
        else:
            turnover = 0.0

        next_idx = min(current_idx + 1, len(self.panel) - 1)
        next_prices = self._prices(next_idx)
        next_value = self._portfolio_value(next_prices)
        daily_return = next_value / max(value_before, 1.0) - 1.0
        reward = float(daily_return - self.turnover_penalty * turnover)
        self.portfolio_value = next_value
        self.peak_value = max(self.peak_value, next_value)
        if next_value > 0:
            asset_values = self.shares * next_prices
            self.weights = asset_values / next_value

        self.step_idx = next_idx
        terminated = self.step_idx >= len(self.panel) - 1
        info = {
            "date": self.panel.iloc[self.step_idx]["date"],
            "portfolio_value": self.portfolio_value,
            "weights": {ticker: float(weight) for ticker, weight in zip(self.tickers, self.weights)},
            "action_label": ACTION_LABELS.get(int(action), f"action_{int(action)}"),
            "turnover": turnover,
        }
        return self._get_obs(), reward, terminated, False, info

train_panel = _align_panel(stock_data, TICKERS, TRAIN_START, TRAIN_END)
test_panel  = _align_panel(stock_data, TICKERS, TEST_START,  TEST_END)

train_dates = pd.to_datetime(train_panel['date'])
test_dates  = pd.to_datetime(test_panel['date'])
print(f"  訓練期: {train_panel['date'].min().date()} ~ {train_panel['date'].max().date()}, {len(train_panel)} 筆")
print(f"  回測期: {test_panel['date'].min().date()} ~ {test_panel['date'].max().date()}, {len(test_panel)} 筆")

# ─────────────────────────────────────────────────────────────────────────
# Step 4: 環境 + PPO 訓練
# ─────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("Step 4: PPO 訓練")
print("═" * 60)

model_path = RESULT_DIR / "ppo_5etf_native_2020_2024.zip"

train_env = FiveETFPortfolioEnv(
    train_panel,
    initial_cash=INITIAL_CASH,
    commission_rate=COMMISSION_RATE,
    tax_rate=ETF_TAX_RATE,
    turnover_penalty=TURNOVER_PENALTY,
    min_rebalance_days=MIN_REBALANCE_DAYS,
    min_weight=0.0,
    max_weight=1.0,
)

if model_path.exists():
    print("  載入既有模型:", model_path)
    from stable_baselines3 import PPO
    model = PPO.load(str(model_path))
else:
    print(f"  訓練新模型 (timesteps={TIMESTEPS:,})...")
    from stable_baselines3 import PPO
    model = PPO(
        "MlpPolicy",
        train_env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        ent_coef=0.01,
        verbose=1,
        seed=SEED,
    )
    model.learn(total_timesteps=TIMESTEPS)
    model.save(str(model_path))
    print("  模型已存檔:", model_path)

# ─────────────────────────────────────────────────────────────────────────
# Step 5: 回測
# ─────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("Step 5: 回測（2025-01-02 ~ 2026-05-15）")
print("═" * 60)

test_env  = FiveETFPortfolioEnv(
    test_panel,
    initial_cash=INITIAL_CASH,
    commission_rate=COMMISSION_RATE,
    tax_rate=ETF_TAX_RATE,
    turnover_penalty=TURNOVER_PENALTY,
    min_rebalance_days=MIN_REBALANCE_DAYS,
    min_weight=0.0,
    max_weight=1.0,
)

# 跑 inference
obs, _    = test_env.reset()
done      = False
equity_rl = [{'date': test_panel.iloc[0]['date'], 'equity': INITIAL_CASH}]
weights_rl = [{'date': test_panel.iloc[0]['date'], **{ticker: 0.0 for ticker in TICKERS}}]

for i in range(len(test_panel) - 1):
    if done:
        break
    action, _ = model.predict(obs, deterministic=True)
    new_obs, reward, terminated, truncated, info = test_env.step(int(action))

    current_date = info.get("date", test_panel.iloc[test_env.step_idx]["date"])
    equity_rl.append({
        'date': current_date,
        'equity': info['portfolio_value'],
    })
    w = info.get('weights', {})
    if isinstance(w, dict):
        weights_rl.append({'date': current_date, **w})
    done = terminated or truncated
    obs  = new_obs

rl_equity_df  = pd.DataFrame(equity_rl).set_index('date')
if weights_rl:
    rl_weights_df = pd.DataFrame(weights_rl).set_index('date')
else:
    rl_weights_df = pd.DataFrame(columns=TICKERS)

# B&H（均勻分配）
bh_init_per_asset = INITIAL_CASH / len(TICKERS)
first_test_row = test_panel.iloc[0]
bh_shares = {}
bh_cash = INITIAL_CASH
for t in TICKERS:
    first_price = first_test_row.get(f'{t}_close', np.nan)
    if np.isnan(first_price):
        bh_shares[t] = 0
        continue
    shares = int(bh_init_per_asset / first_price) // 1000 * 1000
    bh_shares[t] = shares
    bh_cash -= shares * first_price

bh_equity = []
for i, row in test_panel.iterrows():
    date   = row['date']
    total  = bh_cash
    for t in TICKERS:
        price = row.get(f'{t}_close', np.nan)
        if np.isnan(price):
            continue
        total += bh_shares.get(t, 0) * price
    bh_equity.append({'date': date, 'equity': total})

bh_equity_df = pd.DataFrame(bh_equity).set_index('date')

# ─────────────────────────────────────────────────────────────────────────
# Step 6: 績效指標
# ─────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("Step 6: 績效指標")
print("═" * 60)

def metrics(series):
    rets      = series.pct_change().dropna()
    total_ret = float(series.iloc[-1] / series.iloc[0] - 1)
    ann_ret   = float((1 + total_ret) ** (252 / max(len(rets), 1)) - 1)
    ann_vol   = float(rets.std(ddof=1) * np.sqrt(252))
    sharpe    = float((ann_ret - 0.02) / ann_vol) if ann_vol > 1e-10 else 0.0
    cum       = (1 + rets).cumprod()
    peak      = cum.cummax()
    dd        = cum / peak - 1
    mdd       = float(dd.min())
    calmar    = float(ann_ret / abs(mdd)) if mdd != 0 else 0.0
    downside = rets[rets < 0]
    sortino_vol = float(downside.std(ddof=1) * np.sqrt(252)) if len(downside) > 1 else 0.0
    # 正確 Sortino: (年化報酬 - 無風險利率) / 年化下行標準差
    sortino   = float((ann_ret - 0.02) / sortino_vol) if sortino_vol > 1e-10 else 0.0
    win_rate  = float((rets > 0).sum() / max(len(rets), 1))
    return {
        'total_return':   f"{total_ret:.2%}",
        'annual_return':  f"{ann_ret:.2%}",
        'sharpe':         f"{sharpe:.3f}",
        'sortino':        f"{sortino:.3f}",
        'max_drawdown':   f"{mdd:.2%}",
        'calmar':         f"{calmar:.3f}",
        'win_rate':       f"{win_rate:.1%}",
        'final_value':    f"{series.iloc[-1]:,.0f}",
    }

rl_m = metrics(rl_equity_df['equity'])
bh_m = metrics(bh_equity_df['equity'])

print(f"  {'指標':<14} {'RL策略':>12} {'B&H':>12} {'差異':>8}")
print("  " + "-" * 50)
for key in ['total_return', 'annual_return', 'sharpe', 'sortino', 'max_drawdown', 'calmar', 'win_rate']:
    rl_v = rl_m[key]; bh_v = bh_m[key]
    try:
        diff = float(rl_v.rstrip('%')) - float(bh_v.rstrip('%'))
        diff_s = f"{diff:+.2f}pp" if '%' in rl_v else f"{diff:+.3f}"
    except:
        diff_s = "—"
    print(f"  {key:<14} {rl_v:>12} {bh_v:>12} {diff_s:>8}")

# ─────────────────────────────────────────────────────────────────────────
# Step 7: 存檔
# ─────────────────────────────────────────────────────────────────────────
rl_equity_df.to_csv(RESULT_DIR / "rl_equity.csv")
bh_equity_df.to_csv(RESULT_DIR / "bh_equity.csv")
if not rl_weights_df.empty:
    rl_weights_df.to_csv(RESULT_DIR / "rl_weights.csv")

rl_ret = float(rl_m['total_return'].rstrip('%')) / 100
bh_ret = float(bh_m['total_return'].rstrip('%')) / 100
excess = rl_ret - bh_ret

summary = {
    "config": {
        "tickers":     TICKERS,
        "train_start": str(train_panel['date'].min().date()),
        "train_end":   str(train_panel['date'].max().date()),
        "test_start":  str(test_panel['date'].min().date()),
        "test_end":    str(test_panel['date'].max().date()),
        "n_test_days": len(test_panel),
        "initial_cash": INITIAL_CASH,
        "timesteps":   TIMESTEPS,
    },
    "rl":  rl_m,
    "bh":  bh_m,
    "excess_return": f"{excess:.2%}",
}
with open(RESULT_DIR / "summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(f"\n  結果存檔: {RESULT_DIR}")
print(f"  RL 超額報酬: {excess:+.2%}")
