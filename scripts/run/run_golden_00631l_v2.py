#!/usr/bin/env python3
"""golden_00631L v2：改善版
- 修正 reward 為單步報酬
- 加入波動率懲罰
- Observation 標準化
- 可配置多種實驗
"""
from __future__ import annotations
import argparse, json, sys, itertools
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb
import gymnasium
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
from FinRL.data.stock_db import DB_PATH

# ─── 預設值 ───
TICKER = "00631L.TW"
TRAIN_START = "2020-01-01"
TRAIN_END = "2024-12-31"
BACKTEST_START = "2025-01-02"
BACKTEST_END = "2026-06-18"
INITIAL_CASH = 1_000_000.0
TIMESTEPS = 30_000
SEED = 42
N_STEPS = 512

FEATURE_COLUMNS = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126", "momentum_252",
    "rolling_mdd_63",
    "rsi_14", "macd_signal", "macd_hist", "bb_position", "vol_ratio_20",
]


# ─── 資料 ───
def load_data(tickers, start, end):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT dt, ticker, close, open, high, low, volume
            FROM ohlcv WHERE ticker IN ({})
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
        """.format(",".join(["?"] * len(tickers))),
            [*tickers, start, end]).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows


def build_features(rows: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    data = {}
    for ticker in tickers:
        df = rows[rows["ticker"] == ticker].copy()
        df = df.set_index("dt").sort_index()
        df = df[["close", "open", "high", "low", "volume"]]
        close = df["close"]

        df["ma60"] = close.rolling(60).mean()
        df["ma120"] = close.rolling(120).mean()
        df["ma240"] = close.rolling(240).mean()
        df["close_ma120_ratio"] = close / df["ma120"]
        df["close_ma240_ratio"] = close / df["ma240"]
        df["ma60_ma240_ratio"] = df["ma60"] / df["ma240"]
        df["momentum_21"] = close.pct_change(21)
        df["momentum_63"] = close.pct_change(63)
        df["momentum_126"] = close.pct_change(126)
        df["momentum_252"] = close.pct_change(252)
        rolling_max = close.rolling(63, min_periods=1).max()
        drawdown = (close - rolling_max) / rolling_max
        df["rolling_mdd_63"] = drawdown.rolling(63, min_periods=1).min()

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi_14"] = (100 - 100 / (1 + rs)).clip(0, 100)

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        df["macd_signal"] = macd - signal
        df["macd_hist"] = macd - 2 * signal

        bb_mean = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df["bb_position"] = (close - bb_mean) / (2 * bb_std + 1e-8)
        df["vol_ratio_20"] = df["volume"] / df["volume"].rolling(20).mean()

        high_low = df["high"] - df["low"]
        high_close = (df["high"] - close.shift()).abs()
        low_close = (df["low"] - close.shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()

        df = df.dropna(subset=["close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio"])
        data[ticker] = df
    return data


def _align(data: dict[str, pd.DataFrame], tickers: list[str]) -> pd.DataFrame:
    dfs = []
    for t in tickers:
        feat_cols = FEATURE_COLUMNS + ["close"]
        d = data[t][feat_cols].rename(columns={c: f"{t}_{c}" for c in feat_cols})
        dfs.append(d)
    panel = dfs[0].join(dfs[1:], how="inner").dropna()
    return panel


# ─── 觀測值標準化（訓練期統計） ───
def compute_norm_stats(panel: pd.DataFrame, tickers: list[str], feat_cols: list[str]):
    """計算標準化用 mean/std"""
    flat = []
    for t in tickers:
        for f in feat_cols:
            col = f"{t}_{f}"
            if col in panel.columns:
                flat.append(panel[col].values)
    arr = np.array(flat, dtype=np.float32)  # (n_feat, n_steps)
    mean = arr.mean(axis=1, keepdims=True)
    std = arr.std(axis=1, keepdims=True) + 1e-8
    return mean.flatten(), std.flatten()  # (n_feat,)


class MultiTickerEnv(gymnasium.Env):
    metadata = {"render_modes": []}

    def __init__(self, panel: pd.DataFrame, tickers: list[str],
                 initial_cash: float = 1_000_000.0,
                 normalize: bool = False,
                 norm_mean: np.ndarray = None,
                 norm_std: np.ndarray = None,
                 vol_penalty: float = 0.0,
                 prev_return: float = 0.0):
        super().__init__()
        self._panel = panel
        self._tickers = tickers
        self._n_steps = len(panel)
        self._initial_cash = initial_cash
        self._normalize = normalize
        self._norm_mean = norm_mean
        self._norm_std = norm_std
        self._vol_penalty = vol_penalty
        self._prev_return = prev_return

        flat_cols = []
        for t in tickers:
            for f in FEATURE_COLUMNS + ["close"]:
                col = f"{t}_{f}"
                if col in panel.columns:
                    flat_cols.append(col)
        self._flat_cols = flat_cols
        self._feat_close_idx = [i for i, c in enumerate(flat_cols) if c.endswith("_close")]

        n_feat = len(flat_cols)
        self.observation_space = gymnasium.spaces.Box(low=-10, high=10, shape=(n_feat + 2,), dtype=np.float32)
        self.action_space = gymnasium.spaces.Box(low=0, high=1, shape=(len(tickers),), dtype=np.float32)

        self._cash = initial_cash
        self._shares = {t: 0.0 for t in tickers}
        self._step_idx = 0

    def _obs(self) -> np.ndarray:
        feat = self._panel.iloc[self._step_idx][self._flat_cols].values.astype(np.float32)
        if self._normalize and self._norm_mean is not None:
            feat = (feat - self._norm_mean) / self._norm_std
        total = self._cash + sum(
            self._shares[t] * self._panel.iloc[self._step_idx][f"{t}_close"]
            for t in self._tickers
        )
        pos_ratio = sum(
            self._shares[t] * self._panel.iloc[self._step_idx][f"{t}_close"]
            for t in self._tickers
        ) / max(total, 1)
        return np.concatenate([feat, [pos_ratio, self._prev_return]]).astype(np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._cash = self._initial_cash
        self._shares = {t: 0.0 for t in self._tickers}
        self._step_idx = 0
        self._prev_return = 0.0
        return self._obs(), {}

    def step(self, action):
        prev_total = self._cash + sum(
            self._shares[t] * self._panel.iloc[self._step_idx][f"{t}_close"]
            for t in self._tickers
        )
        prices = {t: self._panel.iloc[self._step_idx][f"{t}_close"] for t in self._tickers}
        total = self._cash + sum(self._shares[t] * prices[t] for t in self._tickers)

        for i, t in enumerate(self._tickers):
            w = np.clip(float(action[i]), 0.0, 1.0)
            target_val = total * w
            diff = target_val - self._shares[t] * prices[t]
            if diff > 0:
                self._cash -= diff * (1.0 + 0.001425)
                self._shares[t] += diff / prices[t]
            elif diff < 0:
                proceeds = -diff * (1.0 - 0.001425 - 0.001)
                self._cash += proceeds
                self._shares[t] += diff / prices[t]

        new_total = self._cash + sum(self._shares[t] * prices[t] for t in self._tickers)
        step_return = (new_total / prev_total - 1.0) if prev_total > 0 else 0.0

        # Reward：單步報酬 × 100 - 波動率懲罰
        reward = step_return * 100.0 - self._vol_penalty * abs(step_return) * 100.0

        self._prev_return = step_return
        self._step_idx += 1
        done = self._step_idx >= self._n_steps - 1
        return self._obs(), reward, done, False, {}


def train_model(panel, tickers, model_name, timesteps, seed, normalize, norm_mean, norm_std,
                vol_penalty, ent_coef, n_steps):
    env = MultiTickerEnv(panel, tickers, INITIAL_CASH, normalize, norm_mean, norm_std, vol_penalty)
    model = PPO(
        "MlpPolicy", env,
        learning_rate=3e-4,
        n_steps=n_steps,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=ent_coef,
        seed=seed,
        verbose=0,
    )
    model.learn(total_timesteps=timesteps, progress_bar=True)
    path = PROJECT_ROOT / "models" / "portfolio" / model_name
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(path))
    return model, path


def backtest_model(model, panel, tickers, backtest_start, backtest_end,
                   normalize, norm_mean, norm_std, vol_penalty):
    bt_panel = panel.loc[backtest_start:backtest_end]
    env = MultiTickerEnv(bt_panel, tickers, INITIAL_CASH, normalize, norm_mean, norm_std, vol_penalty)
    obs, _ = env.reset()
    done = False
    history = []

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        prices = {t: bt_panel.iloc[env._step_idx - 1][f"{t}_close"] for t in tickers}
        total = env._cash + sum(env._shares[t] * prices[t] for t in tickers)
        dt = bt_panel.index[env._step_idx - 1]
        history.append({
            "date": str(dt.date()) if hasattr(dt, "date") else str(dt)[:10],
            "total_value": total,
            "cash": env._cash,
            "pos_value": total - env._cash,
            "weight": float(action[0]),
            "step_reward": reward,
        })

    df = pd.DataFrame(history)
    df["returns"] = df["total_value"].pct_change().fillna(0)
    sharpe = df["returns"].mean() / df["returns"].std() * np.sqrt(252) if df["returns"].std() > 0 else 0.0
    cumulative = df["total_value"].iloc[-1] / INITIAL_CASH
    running_max = df["total_value"].cummax()
    mdd = ((df["total_value"] - running_max) / running_max).min()

    bh_prices = bt_panel[f"{TICKER}_close"]
    bh_return = bh_prices.iloc[-1] / bh_prices.iloc[0] - 1

    # 計算 turnover
    weights = df["weight"].values
    turnovers = np.abs(np.diff(weights))
    avg_turnover = turnovers.mean() * 252 if len(turnovers) > 0 else 0.0

    metrics = {
        "final_value": float(df["total_value"].iloc[-1]),
        "cumulative_return": float(cumulative - 1),
        "annualized_return": float(cumulative ** (252 / len(df)) - 1),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(mdd),
        "buy_hold_return": float(bh_return),
        "excess_return": float(cumulative - 1 - bh_return),
        "avg_turnover": float(avg_turnover),
        "trading_days": int(len(df)),
    }
    return metrics, df


def run_experiment(exp_config, panel, tickers, train_panel):
    name = exp_config["name"]
    normalize = exp_config.get("normalize", False)
    vol_penalty = exp_config.get("vol_penalty", 0.0)
    ent_coef = exp_config.get("ent_coef", 0.05)
    n_steps = exp_config.get("n_steps", 1024)
    model_name = f"golden_00631l_v2_{name}"
    print(f"\n{'='*60}")
    print(f"實驗：{name}")
    print(f"  normalize={normalize}, vol_penalty={vol_penalty}, ent_coef={ent_coef}, n_steps={n_steps}")
    print(f"{'='*60}")

    norm_mean, norm_std = None, None
    if normalize:
        flat_cols = []
        for t in tickers:
            for f in FEATURE_COLUMNS + ["close"]:
                col = f"{t}_{f}"
                if col in panel.columns:
                    flat_cols.append(col)
        norm_mean, norm_std = compute_norm_stats(train_panel, tickers, FEATURE_COLUMNS + ["close"])

    try:
        model, _ = train_model(
            train_panel, tickers, model_name, TIMESTEPS, SEED,
            normalize, norm_mean, norm_std, vol_penalty, ent_coef, n_steps
        )
        metrics, df = backtest_model(
            model, panel, tickers, BACKTEST_START, BACKTEST_END,
            normalize, norm_mean, norm_std, vol_penalty
        )
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    print(f"  最終淨值: {metrics['final_value']:,.0f} ({metrics['cumulative_return']:+.2%})")
    print(f"  年化: {metrics['annualized_return']:+.2%} | Sharpe: {metrics['sharpe_ratio']:.3f}")
    print(f"  MDD: {metrics['max_drawdown']:.2%} | BH: {metrics['buy_hold_return']:+.2%}")
    print(f"  超額: {metrics['excess_return']:+.2%} | Avg Turnover: {metrics['avg_turnover']:.3f}")
    print(f"  weight 範圍: [{df['weight'].min():.3f}, {df['weight'].max():.3f}]")
    print(f"  weight std: {df['weight'].std():.4f}")

    # 存 result
    result = {"name": name, "config": exp_config, "metrics": metrics}
    res_path = PROJECT_ROOT / "results" / f"golden_00631l_v2_{name}.json"
    res_path.parent.mkdir(parents=True, exist_ok=True)
    res_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    df_path = PROJECT_ROOT / "results" / f"golden_00631l_v2_{name}_frame.csv"
    df.to_csv(df_path, index=False)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", default="all")
    args = parser.parse_args()

    tickers = [TICKER]
    print("載入資料...")
    rows = load_data(tickers, TRAIN_START, BACKTEST_END)
    data = build_features(rows, tickers)
    panel = _align(data, tickers)
    train_panel = panel.loc[TRAIN_START:TRAIN_END]
    print(f"Panel: {panel.shape}, Train: {len(train_panel)} 筆")

    # 實驗配置
    experiments = [
        # 修正 reward：單步報酬（無標準化）
        {"name": "step_n0_e01_vp0", "reward_type": "step", "normalize": False,
         "ent_coef": 0.01, "n_steps": N_STEPS, "vol_penalty": 0.0},
        {"name": "step_n0_e01_vp5", "reward_type": "step", "normalize": False,
         "ent_coef": 0.01, "n_steps": N_STEPS, "vol_penalty": 0.05},
        {"name": "step_n0_e05_vp0", "reward_type": "step", "normalize": False,
         "ent_coef": 0.05, "n_steps": N_STEPS, "vol_penalty": 0.0},
        {"name": "step_n0_e05_vp5", "reward_type": "step", "normalize": False,
         "ent_coef": 0.05, "n_steps": N_STEPS, "vol_penalty": 0.05},
        # 標準化
        {"name": "step_n1_e01_vp0", "reward_type": "step", "normalize": True,
         "ent_coef": 0.01, "n_steps": N_STEPS, "vol_penalty": 0.0},
        {"name": "step_n1_e01_vp5", "reward_type": "step", "normalize": True,
         "ent_coef": 0.01, "n_steps": N_STEPS, "vol_penalty": 0.05},
        {"name": "step_n1_e05_vp0", "reward_type": "step", "normalize": True,
         "ent_coef": 0.05, "n_steps": N_STEPS, "vol_penalty": 0.0},
        {"name": "step_n1_e05_vp5", "reward_type": "step", "normalize": True,
         "ent_coef": 0.05, "n_steps": N_STEPS, "vol_penalty": 0.05},
        # 更大 batch
        {"name": "step_n1_e05_vp5_ns1024", "reward_type": "step", "normalize": True,
         "ent_coef": 0.05, "n_steps": 1024, "vol_penalty": 0.05},
    ]

    results = []
    for exp in experiments:
        r = run_experiment(exp, panel, tickers, train_panel)
        if r:
            results.append(r)

    # 摘要
    print("\n\n" + "="*70)
    print("實驗摘要")
    print("="*70)
    print(f"{'Name':<35} {'CumRet':>8} {'Sharpe':>7} {'MDD':>8} {'BH':>8} {'Excess':>8}")
    print("-"*70)
    for r in sorted(results, key=lambda x: x["metrics"]["sharpe_ratio"], reverse=True):
        m = r["metrics"]
        print(f"{r['name']:<35} {m['cumulative_return']:>8.2%} {m['sharpe_ratio']:>7.3f} "
              f"{m['max_drawdown']:>8.2%} {m['buy_hold_return']:>8.2%} {m['excess_return']:>8.2%}")

    # 存 summary
    summary_path = PROJECT_ROOT / "results" / "golden_00631l_v2_summary.json"
    summary_path.write_text(json.dumps({"experiments": results}, ensure_ascii=False, indent=2))
    print(f"\n摘要已存：{summary_path}")


if __name__ == "__main__":
    main()
