#!/usr/bin/env python3
"""分段訓練：Group A / Group B 各 10K timesteps 一段，共 10 段，支援 --resume 接著跑"""

import argparse
import json
import sys
import zipfile
import io
import torch
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE, TRANSACTION_TAX_RATE
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics
from train_dual_group_2024_2026 import load_stock_data_db_first

# ==============================================================================
# 雙組設定
# ==============================================================================

INITIAL_CASH = 1_000_000.0
DOWNLOAD_END = "2026-05-09"

# Group A: 0050 + 00631L + 00632R（預設訓練期：2020-2025）
GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
GROUP_A_TRAIN_START = "2020-01-01"
GROUP_A_TRAIN_END = "2025-05-31"
GROUP_A_BASE_NAME = "group_a_seg"

# Group B: 高股息/S&P500/美債（2020-2024 訓練）
GROUP_B_TICKERS = [
    "0056.TW",  # 元大高股息
    "00713.TW",  # 元大台灣高息低波
    "00878.TW",  # 國泰永續高股息
    "00646.TW",  # 元大S&P500
    "00679B.TWO", # 元大美債20年
    "00751B.TWO", # 元大AAA至A公司債
]
GROUP_B_TRAIN_START = "2020-01-01"
GROUP_B_TRAIN_END = "2024-12-31"
GROUP_B_BASE_NAME = "group_b_seg"

DOWNLOAD_END = "2026-05-20"
BACKTEST_START = "2025-01-01"
BACKTEST_END = "2026-05-20"

# 訓練超參
SEG_TIMESTEPS = 10_000   # 每段 10K
TOTAL_SEGS = 10          # 共 10 段 = 100K
SEED = 42

BASE_FEATURE_COLUMNS = [
    "close_ma120_ratio",
    "close_ma240_ratio",
    "ma60_ma240_ratio",
    "momentum_21",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "rolling_mdd_63",
]

ENHANCED_FEATURE_COLUMNS = [
    "rsi_14",
    "macd_signal",
    "macd_hist",
    "vol_ratio_20",
    "bb_position",
    "atr_14",
]

FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + ENHANCED_FEATURE_COLUMNS
STATE_FEATURE_DIM = 5


def _weights_for(tickers, target: dict) -> np.ndarray:
    w = np.zeros(len(tickers), dtype=float)
    for ticker, weight in target.items():
        if ticker in tickers:
            w[tickers.index(ticker)] = weight
    return w / w.sum()


def load_stock_data(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """優先使用本地 DB / cache，缺資料時才退回網路下載。"""
    stock_data = load_stock_data_db_first(sorted(set(tickers)), start, end)
    missing = [ticker for ticker in tickers if ticker not in stock_data]
    # 檢查數據完整性（年份覆蓋是否足夠）
    request_start = pd.Timestamp(start)
    request_end = pd.Timestamp(end)
    for ticker in tickers:
        df = stock_data.get(ticker)
        if df is not None:
            df_dates = pd.to_datetime(df['date']).dt.tz_localize(None)
            actual_start = df_dates.min()
            actual_end = df_dates.max()
            # 如果數據少於預期的 80%，視為不完整，需要 fallback
            expected_days = (request_end - request_start).days
            actual_days = (actual_end - actual_start).days
            if actual_days < expected_days * 0.8:
                missing.append(ticker)
    missing = list(dict.fromkeys(missing))  # 去重
    if not missing:
        return stock_data

    print(f"[Fallback downloader] 補抓不完整/缺少標的: {missing}")
    downloaded = download_all_stocks(missing, start, end)
    for ticker, df in downloaded.items():
        if df is not None and not df.empty:
            stock_data[ticker] = df.copy()
    return stock_data


def _feature_columns_from_obs_dim(obs_dim: int, tickers: list[str]) -> list[str]:
    if len(tickers) == 0:
        raise RuntimeError("tickers cannot be empty")
    if obs_dim <= STATE_FEATURE_DIM:
        raise RuntimeError(f"Invalid obs_dim={obs_dim}")

    feature_dim = obs_dim - STATE_FEATURE_DIM
    if feature_dim % len(tickers) != 0:
        raise RuntimeError(
            f"Observation dim {obs_dim} cannot be evenly split across {len(tickers)} tickers"
        )

    features_per_ticker = feature_dim // len(tickers)
    if features_per_ticker == len(BASE_FEATURE_COLUMNS):
        return list(BASE_FEATURE_COLUMNS)
    if features_per_ticker == len(FEATURE_COLUMNS):
        return list(FEATURE_COLUMNS)

    raise RuntimeError(
        f"Unsupported features_per_ticker={features_per_ticker} for obs_dim={obs_dim}"
    )


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """計算技術指標（單 ticker dataframe，無 tic column）"""
    df = df.copy()
    close = df["close"]
    volume = df["volume"]

    # 原有指標
    df["close_ma120_ratio"] = close / (close.rolling(120).mean() + 1e-10)
    df["close_ma240_ratio"] = close / (close.rolling(240).mean() + 1e-10)
    df["ma60_ma240_ratio"] = close.rolling(60).mean() / (close.rolling(240).mean() + 1e-10)
    df["momentum_21"] = close / (close.shift(21) + 1e-10) - 1
    df["momentum_63"] = close / (close.shift(63) + 1e-10) - 1
    df["momentum_126"] = close / (close.shift(126) + 1e-10) - 1
    df["momentum_252"] = close / (close.shift(252) + 1e-10) - 1
    rolling_max = close.rolling(63).max()
    rolling_min = close.rolling(63).min()
    df["rolling_mdd_63"] = (close - rolling_max) / (rolling_max - rolling_min + 1e-10)

    # ── 新增指標 ──
    # RSI-14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi_14"] = 100 - (100 / (rs + 1))

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    df["macd_signal"] = signal_line / (close + 1e-10)
    df["macd_hist"] = (macd_line - signal_line) / (close + 1e-10)

    # 成交量比（今日量 / 20日均量）
    vol_ma20 = volume.rolling(20, min_periods=1).mean()
    df["vol_ratio_20"] = volume / (vol_ma20 + 1e-10)

    # Bollinger Bands 位置（(close - lower) / (upper - lower)）
    bb20 = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb20 + 2 * bb_std
    bb_lower = bb20 - 2 * bb_std
    df["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)

    # ATR-14（Average True Range）
    high = df.get("high", close)
    low = df.get("low", close)
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean() / (close + 1e-10)

    return df


def _align_panel(
    stock_data: dict,
    tickers: list,
    start: str,
    end: str,
    *,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    """對多檔取共同日期交集，計算技術指標，轉成 panel"""
    selected_features = list(feature_columns or FEATURE_COLUMNS)
    panels = []
    missing_tickers = []
    for tic in tickers:
        df = stock_data.get(tic)
        if df is None:
            missing_tickers.append(tic)
            continue
        df = df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df[(df["date"] >= start) & (df["date"] <= end)].copy()
        if df.empty:
            raise RuntimeError(f"{tic} 在 {start} ~ {end} 無有效資料")
        if any(col not in df.columns for col in selected_features):
            df = _compute_features(df)
        panels.append((tic, df))
    if missing_tickers:
        raise RuntimeError(f"缺少標的資料: {missing_tickers}")
    if not panels:
        raise RuntimeError(f"無可用數據 for {tickers}")
    dates = set(panels[0][1]["date"])
    for _, p in panels[1:]:
        dates.intersection_update(p["date"])
    if not dates:
        raise RuntimeError(f"共同日期交集為空: {tickers}")
    dates = sorted(dates)
    result = pd.DataFrame({"date": dates})
    for tic, p in panels:
        p = p.set_index("date")
        for col in ["close"] + selected_features:
            if col in p.columns:
                result = result.merge(p[[col]].rename(columns={col: f"{tic}_{col}"}),
                                      left_on="date", right_index=True, how="left")
    result = result.sort_values("date").reset_index(drop=True)
    expected_close_cols = [f"{ticker}_close" for ticker in tickers]
    missing_close_cols = [col for col in expected_close_cols if col not in result.columns]
    if missing_close_cols:
        raise RuntimeError(f"Panel 缺少 close 欄位: {missing_close_cols}")
    return result


def _prices(panel: pd.DataFrame, tickers: list) -> np.ndarray:
    close_cols = [f"{ticker}_close" for ticker in tickers]
    missing_close_cols = [col for col in close_cols if col not in panel.columns]
    if missing_close_cols:
        raise RuntimeError(f"Panel 缺少 close 欄位: {missing_close_cols}")
    return panel[close_cols].values.astype(float)


class PortfolioEnv(gym.Env):
    """通用多檔投資組合環境，5 個動作策略。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        tickers: list[str],
        feature_columns: list[str] | None = None,
        initial_cash: float = 1_000_000,
        commission_rate: float = COMMISSION_RATE,
        turnover_penalty: float = 0.0005,
        equal_benchmark_weight: float = 1.5,
        underperform_0050_weight: float = 0.5,
        drawdown_penalty_weight: float = 0.3,
        min_rebalance_days: int = 5,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.tickers = tickers
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.equal_benchmark_weight = float(equal_benchmark_weight)
        self.underperform_0050_weight = float(underperform_0050_weight)
        self.drawdown_penalty_weight = float(drawdown_penalty_weight)
        self.min_rebalance_days = int(min_rebalance_days)
        self.price_array = _prices(self.panel, self.tickers)
        self.tax_rates = np.array([ETF_TAX_RATE] * len(tickers), dtype=float)
        self.base_feature_columns = list(feature_columns or FEATURE_COLUMNS)

        # benchmark curves
        self.equal_bh_curve = self._benchmark_curve(np.ones(len(tickers)) / len(tickers))
        self.bh_0050_curve = self._benchmark_curve(_weights_for(self.tickers, {"0050.TW": 1.0})) \
            if "0050.TW" in self.tickers else None
        self.bh_00631l_curve = self._benchmark_curve(_weights_for(self.tickers, {"00631L.TW": 1.0})) \
            if "00631L.TW" in self.tickers else None
        blend_weights = {}
        if "0050.TW" in self.tickers and "00631L.TW" in self.tickers:
            blend_weights = {"0050.TW": 0.5, "00631L.TW": 0.5}
        self.blend50_bh_curve = self._benchmark_curve(_weights_for(self.tickers, blend_weights)) \
            if blend_weights else None

        # observation
        self.feature_cols = []
        for ticker in self.tickers:
            self.feature_cols.extend(
                [f"{ticker}_{c}" for c in self.base_feature_columns if f"{ticker}_{c}" in self.panel.columns]
            )
        expected_feature_dim = len(self.base_feature_columns) * len(self.tickers)
        if len(self.feature_cols) != expected_feature_dim:
            raise RuntimeError(
                f"Feature columns mismatch: expected {expected_feature_dim}, got {len(self.feature_cols)}"
            )
        obs_dim = len(self.feature_cols) + STATE_FEATURE_DIM
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(5)
        self.reset()

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = self.initial_cash * weights / self.price_array[0]
        return self.price_array @ shares

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _target_weights(self, action: int) -> np.ndarray:
        t = self.tickers
        w = lambda d: _weights_for(t, d)
        n = len(t)

        if action == 0:  # 持有不動
            return self.weights.copy()

        if action == 1:
            # 50% 0050 / 50% 00631L（平衡槓桿）
            if "0050.TW" in t and "00631L.TW" in t:
                return w({"0050.TW": 0.50, "00631L.TW": 0.50})
            return np.ones(n, dtype=float) / n

        if action == 2:
            # 40% 0050 / 60% 00631L（適度槓桿）
            if "0050.TW" in t and "00631L.TW" in t:
                return w({"0050.TW": 0.40, "00631L.TW": 0.60})
            return np.ones(n, dtype=float) / n

        if action == 3:
            # 高股息：40% 0050 / 35% 00713 / 25% 00878
            if "0050.TW" in t and "00713.TW" in t and "00878.TW" in t:
                return w({"0050.TW": 0.40, "00713.TW": 0.35, "00878.TW": 0.25})
            return np.ones(n, dtype=float) / n

        if action == 4:  # 等權
            return np.ones(n, dtype=float) / n

        return w({"0050.TW": 1.0}) if "0050.TW" in t else np.ones(n, dtype=float) / n

    def _get_obs(self) -> np.ndarray:
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        prices = self.price_array[self.step_idx]
        value = max(self._portfolio_value(prices), 1.0)
        weights = self.shares * prices / value
        peak = max(self.peak_value, value, 1.0)
        days_since_rebalance = min(max(self.step_idx - self.last_rebalance_idx, 0), 252) / 252.0

        extra = [self.cash / value, value / peak - 1.0, days_since_rebalance]
        if self.equal_bh_curve is not None:
            extra.append(value / max(float(self.equal_bh_curve[self.step_idx]), 1.0) - 1.0)
        else:
            extra.append(0.0)
        if self.bh_0050_curve is not None:
            extra.append(value / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0)
        else:
            extra.append(0.0)

        state = np.array(extra, dtype=float)
        obs = np.concatenate([features, state])
        obs = np.nan_to_num(obs, nan=0.0, posinf=10.0, neginf=-10.0)
        return np.clip(obs, -10.0, 10.0).astype(np.float32)

    def _rebalance(self, target_weights: np.ndarray, prices: np.ndarray) -> float:
        value_before = self._portfolio_value(prices)
        current_values = self.shares * prices
        target_values = value_before * target_weights
        deltas = target_values - current_values
        fees = 0.0

        for i, delta in enumerate(deltas):
            if delta >= 0:
                continue
            sell_value = min(-delta, self.shares[i] * prices[i])
            if sell_value <= 0:
                continue
            fee_rate = self.commission_rate + self.tax_rates[i]
            fees += sell_value * fee_rate
            self.cash += sell_value * (1 - fee_rate)
            self.shares[i] -= sell_value / prices[i]

        for i, delta in enumerate(deltas):
            if delta <= 0:
                continue
            buy_value = min(delta, self.cash / (1 + self.commission_rate))
            if buy_value <= 0:
                continue
            fees += buy_value * self.commission_rate
            self.cash -= buy_value * (1 + self.commission_rate)
            self.shares[i] += buy_value / prices[i]

        value_after = max(self._portfolio_value(prices), 1.0)
        self.weights = self.shares * prices / value_after
        # 單一持股上限 50%
        self.weights = np.clip(self.weights, 0, 0.5)
        self.weights /= self.weights.sum()
        return float(fees)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = np.zeros(len(self.tickers), dtype=float)

        # 初始配置：50/50 blend 或等權
        if "0050.TW" in self.tickers and "00631L.TW" in self.tickers:
            self.weights = _weights_for(self.tickers, {"0050.TW": 0.50, "00631L.TW": 0.50})
        else:
            self.weights = np.ones(len(self.tickers), dtype=float) / len(self.tickers)

        self.last_rebalance_idx = -10**9
        self.trade_count = 0
        self.fees_paid = 0.0
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        return self._get_obs(), {}

    def step(self, action):
        prices = self.price_array[self.step_idx]
        value_before = self._portfolio_value(prices)
        target_weights = self._target_weights(int(action))
        fees = 0.0
        turnover = float(np.abs(target_weights - self.weights).sum())

        if int(action) != 0 and self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days:
            fees = self._rebalance(target_weights, prices)
            if fees > 0:
                self.trade_count += 1
                self.last_rebalance_idx = self.step_idx
                self.fees_paid += fees

        self.step_idx += 1
        next_prices = self.price_array[self.step_idx]
        value_after = self._portfolio_value(next_prices)
        self.peak_value = max(self.peak_value, value_after)
        self.equity_curve.append(value_after)

        daily_return = value_after / max(value_before, 1.0) - 1

        # benchmarks
        equal_return = 0.0
        if self.equal_bh_curve is not None and self.step_idx > 0:
            equal_return = float(self.equal_bh_curve[self.step_idx] / max(self.equal_bh_curve[self.step_idx - 1], 1.0) - 1)

        excess_equal = daily_return - equal_return

        excess_vs_blend50 = 0.0
        if self.blend50_bh_curve is not None and self.step_idx > 0:
            excess_vs_blend50 = value_after / max(float(self.blend50_bh_curve[self.step_idx]), 1.0) - 1.0

        reward = daily_return
        reward += self.equal_benchmark_weight * excess_equal
        reward -= self.turnover_penalty * turnover
        reward -= self.drawdown_penalty_weight * max(value_after / max(self.peak_value, 1.0) - 1, 0.0)
        if "0050.TW" in self.tickers and self.bh_0050_curve is not None:
            reward += self.underperform_0050_weight * (value_after / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0)

        done = self.step_idx >= len(self.panel) - 1
        return self._get_obs(), reward, done, False, {}


def _run_model_single(model, panel, tickers, *, feature_columns: list[str] | None = None):
    """單一模型回測"""
    env = PortfolioEnv(panel, tickers, feature_columns=feature_columns)
    obs, _ = env.reset()
    equity = [env.initial_cash]
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        equity.append(env.equity_curve[-1])
    m = calculate_backtest_metrics(equity)
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": m,
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "final_weights": {t: float(w) for t, w in zip(tickers, env.weights)},
        "equity_curve": [float(v) for v in equity],
    }


def _buy_and_hold(panel, tickers, weights):
    prices = _prices(panel, tickers)
    shares = INITIAL_CASH * weights / prices[0]
    equity = (prices @ shares).astype(float).tolist()
    return {"final_value": float(equity[-1]), "metrics": calculate_backtest_metrics(equity)}


# ==============================================================================
# 訓練函式（支援分段）
# ==============================================================================

def train_group(tickers, train_start, train_end, base_name, seg_num, resume_path=None, seg_timesteps=10_000):
    """訓練一段。seg_num: 1~10"""
    seg_label = f"{base_name}_s{seg_num:02d}"
    print(f"\n{'='*72}")
    print(f"訓練 {seg_label} ({'resume' if resume_path else 'fresh'})")
    print(f"  標的: {tickers}")
    print(f"  訓練: {train_start} ~ {train_end}")
    print(f"  段: {seg_num}/10 (每段 {seg_timesteps:,} timesteps)")
    print(f"{'='*72}")

    all_tickers = list(set(tickers))
    stock_data = load_stock_data(all_tickers, train_start, DOWNLOAD_END)

    for t in tickers:
        if t not in stock_data:
            raise RuntimeError(f"無法載入 {t} 數據")

    panel = _align_panel(
        stock_data,
        tickers,
        train_start,
        train_end,
        feature_columns=FEATURE_COLUMNS,
    )
    if len(panel) < 100:
        raise RuntimeError(f"訓練數據不足：{len(panel)} 筆")

    print(f"  訓練期: {panel['date'].min().date()} ~ {panel['date'].max().date()} ({len(panel)} 筆)")

    train_env = PortfolioEnv(panel, tickers, feature_columns=FEATURE_COLUMNS)

    if resume_path:
        print(f"  載入模型: {resume_path}")
        loaded = PPO.load(resume_path)
        # 建立新 env 但借用載入模型的 policy 引數
        model = PPO(
            "MlpPolicy",
            train_env,
            learning_rate=3e-4,
            n_steps=1024,
            gamma=0.99,
            gae_lambda=0.95,
            ent_coef=0.08,
            seed=SEED,
            verbose=1,
        )
        model.policy = loaded.policy
        model.num_timesteps = loaded.num_timesteps
        model._last_obs = None
    else:
        model = PPO(
            "MlpPolicy",
            train_env,
            learning_rate=3e-4,
            n_steps=1024,
            gamma=0.99,
            gae_lambda=0.95,
            ent_coef=0.08,
            seed=SEED,
            verbose=1,
        )

    model.learn(total_timesteps=seg_timesteps, reset_num_timesteps=False)

    model_path = PROJECT_ROOT / "models" / "portfolio" / seg_label
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    print(f"  模型儲存: {model_path}")
    return model, panel


# ==============================================================================
# Backtest（載入最終模型）
# ==============================================================================

def _load_model_without_cloudpickle(model_path: Path):
    """直接從 zip 讀取 policy weights，跳過 cloudpickle/numpy2 不相容問題"""
    if not str(model_path).endswith(".zip"):
        model_path = Path(str(model_path) + ".zip")

    with zipfile.ZipFile(str(model_path), "r") as z:
        policy_bytes = z.read("policy.pth")
        policy_state = torch.load(io.BytesIO(policy_bytes), map_location="cpu", weights_only=False)
        data_json = json.loads(z.read("data"))

    # 從模型中讀取當初訓練時的 obs_dim
    trained_obs_dim = data_json["observation_space"]["_shape"][0]

    # 用對應維度的 dummy env 初始化模型
    class _DummyEnv(gym.Env):
        def __init__(self, obs_dim):
            super().__init__()
            self.observation_space = spaces.Box(low=-10, high=10, shape=(obs_dim,), dtype=np.float32)
            self.action_space = spaces.Discrete(5)
            self._current_step = 0

        def reset(self, seed=None, options=None):
            self._current_step = 0
            return np.zeros(self.observation_space.shape, dtype=np.float32), {}

        def step(self, action):
            self._current_step += 1
            obs = np.zeros(self.observation_space.shape, dtype=np.float32)
            return obs, 0.0, False, False, {}

        def close(self):
            pass

        def render(self, mode="human"):
            pass

    dummy = _DummyEnv(trained_obs_dim)
    model = PPO(
        "MlpPolicy",
        dummy,
        learning_rate=3e-4,
        n_steps=1024,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.08,
        verbose=0,
    )
    model.policy.load_state_dict(policy_state, strict=False)
    return model, trained_obs_dim


def _run_model_from_checkpoint(model_name: str, tickers: list[str], stock_data: dict[str, pd.DataFrame]):
    model_path = PROJECT_ROOT / "models" / "portfolio" / model_name
    model, obs_dim = _load_model_without_cloudpickle(model_path)
    feature_columns = _feature_columns_from_obs_dim(obs_dim, tickers)
    panel = _align_panel(
        stock_data,
        tickers,
        BACKTEST_START,
        BACKTEST_END,
        feature_columns=feature_columns,
    )
    result = _run_model_single(model, panel, tickers, feature_columns=feature_columns)
    return result, panel, feature_columns, obs_dim


def backtest_all(group_a_final_model, group_b_final_model):
    print(f"\n{'='*72}")
    print(f"統一回測: {BACKTEST_START} ~ {BACKTEST_END}")
    print(f"{'='*72}")

    all_tickers = list(set(GROUP_A_TICKERS + GROUP_B_TICKERS))
    backtest_data = load_stock_data(all_tickers, BACKTEST_START, DOWNLOAD_END)

    result_a, panel_a, feature_columns_a, obs_dim_a = _run_model_from_checkpoint(
        group_a_final_model,
        GROUP_A_TICKERS,
        backtest_data,
    )
    result_b, panel_b, feature_columns_b, obs_dim_b = _run_model_from_checkpoint(
        group_b_final_model,
        GROUP_B_TICKERS,
        backtest_data,
    )

    # B&H 參考
    bh_a = _buy_and_hold(panel_a, GROUP_A_TICKERS, _weights_for(GROUP_A_TICKERS, {t: 1.0/len(GROUP_A_TICKERS) for t in GROUP_A_TICKERS}))
    bh_b = _buy_and_hold(panel_b, GROUP_B_TICKERS, _weights_for(GROUP_B_TICKERS, {t: 1.0/len(GROUP_B_TICKERS) for t in GROUP_B_TICKERS}))

    return {
        "group_a_model": group_a_final_model,
        "group_b_model": group_b_final_model,
        "backtest_start": BACKTEST_START,
        "backtest_end": BACKTEST_END,
        "group_a_obs_dim": obs_dim_a,
        "group_b_obs_dim": obs_dim_b,
        "group_a_feature_columns": feature_columns_a,
        "group_b_feature_columns": feature_columns_b,
        "result_a": result_a,
        "result_b": result_b,
        "bh_a": bh_a,
        "bh_b": bh_b,
    }


# ==============================================================================
# main
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="分段訓練 + 回測")
    parser.add_argument("--group", choices=["a", "b"], default=None,
                        help="訓練哪組（不指定則全部）")
    parser.add_argument("--seg", type=int, default=None,
                        help=f"訓練第幾段 1~{TOTAL_SEGS}（需配合 --resume 指定模型路徑）")
    parser.add_argument("--timesteps", type=int, default=SEG_TIMESTEPS,
                        help=f"每段 timesteps（預設 {SEG_TIMESTEPS:,}）")
    parser.add_argument("--resume", type=str, default=None,
                        help="模型路徑（接著訓練用）")
    parser.add_argument("--backtest", action="store_true",
                        help="執行統一回測（需指定最終模型）")
    parser.add_argument("--model-a", type=str, default=None,
                        help="Group A 最終模型（backtest 用）")
    parser.add_argument("--model-b", type=str, default=None,
                        help="Group B 最終模型（backtest 用）")
    parser.add_argument("--blend", type=float, default=None,
                        help="Blend 權重（0~100，代表 A 的比例。如 50 表示 50%% A + 50%% B）")
    args = parser.parse_args()

    seg_ts = SEG_TIMESTEPS
    if args.timesteps != SEG_TIMESTEPS:
        seg_ts = args.timesteps

    # ── 純回測 ──
    if args.backtest:
        if not args.model_a or not args.model_b:
            print("錯誤：--backtest 需搭配 --model-a 和 --model-b")
            sys.exit(1)
        result = backtest_all(args.model_a, args.model_b)
        out = PROJECT_ROOT / "results" / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n回測結果: {out}")
        for label, res in [("Group A", result["result_a"]), ("Group B", result["result_b"])]:
            if res is None:
                print(f"\n{label}: (skipped)")
                continue
            m = res["rl_metrics"]
            print(f"\n{label}:")
            print(f"  最終價值: {res['final_value']:,.0f}")
            print(f"  報酬率:   {m['total_return']*100:.2f}%")
            print(f"  Sharpe:   {m['sharpe']:.3f}")
            print(f"  Max DD:   {m['max_drawdown']*100:.2f}%")
        if result["result_b"] is not None and args.blend is not None:
            blend_a = args.blend / 100.0
            blend_b = 1.0 - blend_a
            # Blend 兩個 equity curve
            eq_a = result["result_a"]["equity_curve"]
            eq_b = result["result_b"]["equity_curve"]
            min_len = min(len(eq_a), len(eq_b))
            blended = [eq_a[i] * blend_a + eq_b[i] * blend_b for i in range(min_len)]
            m_blend = calculate_backtest_metrics(blended)
            total_value = blended[-1]
            print(f"\nBlend ({int(blend_a*100)}% A + {int(blend_b*100)}% B):")
            print(f"  最終價值: {total_value:,.0f}")
            print(f"  報酬率:   {m_blend['total_return']*100:.2f}%")
            print(f"  Sharpe:   {m_blend['sharpe']:.3f}")
            print(f"  Max DD:   {m_blend['max_drawdown']*100:.2f}%")
        return

    # ── 訓練 ──
    groups_to_run = []
    if args.group in (None, "a"):
        groups_to_run.append(("a", GROUP_A_TICKERS, GROUP_A_TRAIN_START, GROUP_A_TRAIN_END, GROUP_A_BASE_NAME))
    if args.group in (None, "b"):
        groups_to_run.append(("b", GROUP_B_TICKERS, GROUP_B_TRAIN_START, GROUP_B_TRAIN_END, GROUP_B_BASE_NAME))

    if args.seg is not None:
        # 只跑指定段
        for gid, tickers, ts, te, base in groups_to_run:
            if gid == args.group or args.group is None:
                resume = args.resume if args.resume else None
                train_group(tickers, ts, te, base, args.seg, resume_path=resume, seg_timesteps=seg_ts)
        return

    # 預設：跑所有段（分開執行，每段都是獨立的 learn() call）
    for gid, tickers, ts, te, base in groups_to_run:
        print(f"\n{'#'*72}")
        print(f"# Group {gid.upper()}: {tickers}")
        print(f"# 共 {TOTAL_SEGS} 段，每段 {SEG_TIMESTEPS:,} timesteps")
        print(f"{'#'*72}")
        prev_model = None
        for seg in range(1, TOTAL_SEGS + 1):
            model, panel = train_group(tickers, ts, te, base, seg, resume_path=prev_model, seg_timesteps=seg_ts)
            prev_model = PROJECT_ROOT / "models" / "portfolio" / f"{base}_s{seg:02d}"
        print(f"\nGroup {gid.upper()} 完成！最終模型: {base}_s{TOTAL_SEGS:02d}")

    print("\n全部訓練完成。要回測請執行：")
    print(f"  python train_segments.py --backtest --model-a {GROUP_A_BASE_NAME}_s{TOTAL_SEGS:02d} --model-b {GROUP_B_BASE_NAME}_s{TOTAL_SEGS:02d}")


if __name__ == "__main__":
    main()
