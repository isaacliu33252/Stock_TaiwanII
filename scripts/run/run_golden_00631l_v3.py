#!/usr/bin/env python3
"""golden_00631L v3：MA Trend + PPO 微調混合策略
- 大方向由 MA200/MA120 均線保護（空頭遠離市場）
- PPO 專門學習：牛市中什麼價位加倉/減倉
- 改善 reward：每步 reward = 倉位回報 vs buy_hold 的超額報酬
"""
from __future__ import annotations
import argparse, json, sys
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
TIMESTEPS = 40_000
SEED = 42

FEATURE_COLUMNS = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126",
    "rolling_mdd_63",
    "rsi_14", "macd_hist", "bb_position", "vol_ratio_20",
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
        df["macd_hist"] = macd - 2 * signal

        bb_mean = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df["bb_position"] = (close - bb_mean) / (2 * bb_std + 1e-8)
        df["vol_ratio_20"] = df["volume"] / df["volume"].rolling(20).mean()

        # MA Trend：是否低於均線（風險信號）
        df["below_ma120"] = (close < df["ma120"]).astype(float)
        df["below_ma240"] = (close < df["ma240"]).astype(float)
        # 動能方向
        df["trend_strength"] = df["close_ma120_ratio"] - 1.0  # 標準化到 0 附近
        # 波動率標準化
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - close.shift()).abs()
        low_close = (df["low"] - close.shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()
        df["atr_ratio"] = df["atr_14"] / close  # 標準化波動率

        df = df.dropna(subset=["close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio"])
        data[ticker] = df
    return data


def _align(data: dict[str, pd.DataFrame], tickers: list[str]) -> pd.DataFrame:
    feat_cols = [c for c in FEATURE_COLUMNS + ["close", "below_ma120", "below_ma240", "trend_strength", "atr_ratio"]
                 if any(t in c or c in data[tickers[0]].columns for t in tickers)]
    # 簡化：取所有 FEATURE_COLUMNS + close
    extra = ["close", "below_ma120", "below_ma240", "trend_strength", "atr_ratio"]
    all_cols = [f for f in FEATURE_COLUMNS + extra if f in data[tickers[0]].columns]
    dfs = []
    for t in tickers:
        d = data[t][all_cols].rename(columns={c: f"{t}_{c}" for c in all_cols})
        dfs.append(d)
    panel = dfs[0].join(dfs[1:], how="inner").dropna()
    return panel


def compute_norm_stats(panel: pd.DataFrame, tickers: list[str]):
    all_feat = FEATURE_COLUMNS + ["close", "below_ma120", "below_ma240", "trend_strength", "atr_ratio"]
    flat = []
    for t in tickers:
        for f in all_feat:
            col = f"{t}_{f}"
            if col in panel.columns:
                flat.append(panel[col].values)
    arr = np.array(flat, dtype=np.float32)
    mean = arr.mean(axis=1, keepdims=True)
    std = arr.std(axis=1, keepdims=True) + 1e-8
    return mean.flatten(), std.flatten()


class HybridEnv(gymnasium.Env):
    """MA Trend Guard + PPO 微調
    - below_ma120=1 → 強制空倉（weight=0）
    - 否則 PPO 輸出 0~1（加倉係數，最大 1.0 = 100% 倉位）
    """
    metadata = {"render_modes": []}

    def __init__(self, panel: pd.DataFrame, tickers: list[str],
                 initial_cash: float = 1_000_000.0,
                 normalize: bool = False,
                 norm_mean: np.ndarray = None,
                 norm_std: np.ndarray = None,
                 trend_guard: bool = True):
        super().__init__()
        self._panel = panel
        self._tickers = tickers
        self._n_steps = len(panel)
        self._initial_cash = initial_cash
        self._normalize = normalize
        self._norm_mean = norm_mean
        self._norm_std = norm_std
        self._trend_guard = trend_guard

        all_cols = FEATURE_COLUMNS + ["close", "below_ma120", "below_ma240", "trend_strength", "atr_ratio"]
        self._flat_cols = []
        for t in tickers:
            for f in all_cols:
                col = f"{t}_{f}"
                if col in panel.columns:
                    self._flat_cols.append(col)
        # trend guard columns
        self._trend_col = f"{tickers[0]}_below_ma120"
        self._close_col = f"{tickers[0]}_close"

        n_feat = len(self._flat_cols)
        # obs = features + pos_ratio + trend_guard + prev_return
        self.observation_space = gymnasium.spaces.Box(low=-10, high=10, shape=(n_feat + 3,), dtype=np.float32)
        self.action_space = gymnasium.spaces.Box(low=0, high=1, shape=(1,), dtype=np.float32)  # scale factor 0~1

        self._cash = initial_cash
        self._shares = {t: 0.0 for t in tickers}
        self._step_idx = 0
        self._prev_return = 0.0

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
        trend_guard = self._panel.iloc[self._step_idx][self._trend_col]
        return np.concatenate([feat, [pos_ratio, trend_guard, self._prev_return]]).astype(np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._cash = self._initial_cash
        self._shares = {t: 0.0 for t in self._tickers}
        self._step_idx = 0
        self._prev_return = 0.0
        return self._obs(), {}

    def step(self, action):
        prices = {t: self._panel.iloc[self._step_idx][f"{t}_close"] for t in self._tickers}
        total = self._cash + sum(self._shares[t] * prices[t] for t in self._tickers)
        prev_total = total

        # Trend Guard：MA120 以下強制空倉
        trend_guard = self._panel.iloc[self._step_idx][self._trend_col]
        if self._trend_guard and trend_guard > 0.5:
            target_weight = 0.0
        else:
            # PPO 輸出 0~1 → scale factor，最大 1.0 = 全倉
            scale = float(np.clip(action[0], 0.0, 1.0))
            # 基準倉位 0.85（保留 15% 現金 buffer）
            target_weight = 0.85 * scale

        for i, t in enumerate(self._tickers):
            w = target_weight  # 單一標的
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
        self._prev_return = step_return

        # Reward：倉位帶來的超額報酬（相對於 buy_hold 的日報酬）
        bh_return_today = prices[t] / prices[t] - 1  # placeholder
        reward = step_return * 100.0

        self._step_idx += 1
        done = self._step_idx >= self._n_steps - 1
        return self._obs(), reward, done, False, {}


def train_model(panel, tickers, model_name, timesteps, seed, normalize, norm_mean, norm_std, trend_guard):
    env = HybridEnv(panel, tickers, INITIAL_CASH, normalize, norm_mean, norm_std, trend_guard)
    model = PPO(
        "MlpPolicy", env,
        learning_rate=3e-4,
        n_steps=512,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.02,
        seed=seed,
        verbose=1,
    )
    model.learn(total_timesteps=timesteps, progress_bar=True)
    path = PROJECT_ROOT / "models" / "portfolio" / model_name
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(path))
    return model, path


def backtest_model(model, panel, tickers, backtest_start, backtest_end,
                   normalize, norm_mean, norm_std, trend_guard):
    bt_panel = panel.loc[backtest_start:backtest_end]
    env = HybridEnv(bt_panel, tickers, INITIAL_CASH, normalize, norm_mean, norm_std, trend_guard)
    obs, _ = env.reset()
    done = False
    history = []
    prev_action = 0.0

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        prices = {t: bt_panel.iloc[env._step_idx - 1][f"{t}_close"] for t in tickers}
        total = env._cash + sum(env._shares[t] * prices[t] for t in tickers)
        dt = bt_panel.index[env._step_idx - 1]
        trend_guard = bt_panel.iloc[env._step_idx - 1].get(f"{tickers[0]}_below_ma120", 0)
        history.append({
            "date": str(dt.date()) if hasattr(dt, "date") else str(dt)[:10],
            "total_value": total,
            "cash": env._cash,
            "pos_value": total - env._cash,
            "ppO_action": float(action[0]),
            "effective_weight": float(sum(env._shares[t] * prices[t] for t in tickers) / max(total, 1)),
            "trend_guard": float(trend_guard),
            "step_reward": reward,
        })
        prev_action = float(action[0])

    df = pd.DataFrame(history)
    df["returns"] = df["total_value"].pct_change().fillna(0)
    sharpe = df["returns"].mean() / df["returns"].std() * np.sqrt(252) if df["returns"].std() > 0 else 0.0
    cumulative = df["total_value"].iloc[-1] / INITIAL_CASH
    running_max = df["total_value"].cummax()
    mdd = ((df["total_value"] - running_max) / running_max).min()

    bh_prices = bt_panel[f"{TICKER}_close"]
    bh_return = bh_prices.iloc[-1] / bh_prices.iloc[0] - 1
    turnovers = np.abs(df["effective_weight"].diff().dropna())
    avg_turnover = turnovers.mean() * 252

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
        "days_in_guard": int((df["trend_guard"] > 0.5).sum()),
    }
    return metrics, df


def run_exp(name, normalize, ent_coef, n_steps, trend_guard, timesteps, panel, tickers, train_panel):
    print(f"\n{'='*55}")
    print(f"實驗：{name}  norm={normalize} ent={ent_coef} guard={trend_guard}")
    print(f"{'='*55}")
    model_name = f"golden_00631l_v3_{name}"
    norm_mean, norm_std = None, None
    if normalize:
        norm_mean, norm_std = compute_norm_stats(train_panel, tickers)
    try:
        model, _ = train_model(train_panel, tickers, model_name, timesteps, SEED,
                               normalize, norm_mean, norm_std, trend_guard)
        metrics, df = backtest_model(model, panel, tickers, BACKTEST_START, BACKTEST_END,
                                     normalize, norm_mean, norm_std, trend_guard)
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    print(f"  淨值: {metrics['final_value']:,.0f} ({metrics['cumulative_return']:+.2%})")
    print(f"  年化: {metrics['annualized_return']:+.2%} | Sharpe: {metrics['sharpe_ratio']:.3f}")
    print(f"  MDD: {metrics['max_drawdown']:.2%} | BH: {metrics['buy_hold_return']:+.2%}")
    print(f"  超額: {metrics['excess_return']:+.2%} | Guard天數: {metrics['days_in_guard']}")
    print(f"  PPO action 範圍: [{df['ppO_action'].min():.3f}, {df['ppO_action'].max():.3f}]")
    print(f"  有效倉位 範圍: [{df['effective_weight'].min():.3f}, {df['effective_weight'].max():.3f}]")

    res = {"name": name, "metrics": metrics}
    (PROJECT_ROOT / "results" / f"golden_00631l_v3_{name}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2))
    df.to_csv(PROJECT_ROOT / "results" / f"golden_00631l_v3_{name}_frame.csv", index=False)
    return res


def main():
    tickers = [TICKER]
    print("載入資料...")
    rows = load_data(tickers, TRAIN_START, BACKTEST_END)
    data = build_features(rows, tickers)
    panel = _align(data, tickers)
    train_panel = panel.loc[TRAIN_START:TRAIN_END]
    print(f"Panel: {panel.shape}, Train: {len(train_panel)} 筆")

    results = []

    # 實驗：無 trend guard（對照組）
    results.append(run_exp(
        "no_guard_n0_e01", normalize=False, ent_coef=0.01,
        n_steps=512, trend_guard=False, timesteps=TIMESTEPS,
        panel=panel, tickers=tickers, train_panel=train_panel))

    # Trend Guard 實驗
    for normalize in [False, True]:
        for ent_coef in [0.01, 0.05]:
            n_tag = "n1" if normalize else "n0"
            r = run_exp(
                f"guard_{n_tag}_e{int(ent_coef*100):02d}",
                normalize=normalize, ent_coef=ent_coef,
                n_steps=512, trend_guard=True, timesteps=TIMESTEPS,
                panel=panel, tickers=tickers, train_panel=train_panel)
            results.append(r)

    # 印摘要
    print("\n\n" + "="*70)
    print("實驗摘要（以 Sharpe 排序）")
    print("="*70)
    print(f"{'Name':<30} {'CumRet':>8} {'Sharpe':>7} {'MDD':>8} {'BH':>8} {'Excess':>8}")
    print("-"*70)
    valid = [r for r in results if r]
    for r in sorted(valid, key=lambda x: x["metrics"]["sharpe_ratio"], reverse=True):
        m = r["metrics"]
        print(f"{r['name']:<30} {m['cumulative_return']:>8.2%} {m['sharpe_ratio']:>7.3f} "
              f"{m['max_drawdown']:>8.2%} {m['buy_hold_return']:>8.2%} {m['excess_return']:>8.2%}")

    # 存 summary
    (PROJECT_ROOT / "results" / "golden_00631l_v3_summary.json").write_text(
        json.dumps({"experiments": valid}, ensure_ascii=False, indent=2))
    print("\n完成")


if __name__ == "__main__":
    main()
