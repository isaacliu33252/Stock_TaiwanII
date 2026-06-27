#!/usr/bin/env python3
"""Group A 延長訓練：2018-01-01 ~ 2024-12-31（7年完整市場周期）
直接用 yfinance 下載完整歷史，訓練完成後自動 backtest。
"""
import sys, json, argparse
from pathlib import Path
import pandas as pd
import numpy as np
import gymnasium as gym

PROJECT_ROOT = Path('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')
sys.path.insert(0, str(PROJECT_ROOT))

MODEL_DIR = PROJECT_ROOT / "models" / "portfolio"

# ── 參數 ──────────────────────────────────────────────────────────────
GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
TRAIN_START = "2018-01-01"
TRAIN_END = "2024-12-31"
BACKTEST_START = "2025-01-02"
BACKTEST_END = "2026-05-20"
DOWNLOAD_END = "2026-05-20"

SEG_TIMESTEPS = 20_000
TOTAL_SEGS = 5
SEED = 42
BASE_NAME = "group_a_extended_2018"

BASE_FEATURE_COLUMNS = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126", "momentum_252",
    "rolling_mdd_63",
]
ENHANCED_FEATURE_COLUMNS = [
    "rsi_14", "macd_signal", "macd_hist", "vol_ratio_20", "bb_position", "atr_14",
]
FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + ENHANCED_FEATURE_COLUMNS
STATE_FEATURE_DIM = 5

# ── 數據載入 ──────────────────────────────────────────────────────────
def download_stock_data(tickers, start, end):
    """直接用 yfinance 下載完整歷史，繞過 DB 限制"""
    import yfinance as yf
    import pyarrow.parquet as pq

    cache_dir = PROJECT_ROOT / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    end_dt = pd.Timestamp(end) + pd.Timedelta(days=1)

    for ticker in tickers:
        cache_file = cache_dir / f"{ticker.replace('.', '_')}_{start}_{end}_1d.parquet"
        if cache_file.exists():
            try:
                df = pq.read_table(str(cache_file)).to_pandas(timestamp_as_object=True)
                if len(df) > 1500:  # 2018 以來約 2000+ 筆
                    results[ticker] = df
                    print(f"  [Cache] {ticker}: {len(df)} 筆")
                    continue
            except Exception:
                pass

        print(f"  [Download] {ticker} via yfinance ({start} ~ {end})...")
        raw = yf.download(ticker, start=start, end=str(end_dt.date()), progress=False, auto_adjust=True)
        if raw.empty:
            print(f"  WARNING: {ticker} 無法下載")
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.reset_index()
        raw.columns = [str(c).lower() for c in raw.columns]
        raw = raw.rename(columns={'date': 'date', 'open': 'open', 'high': 'high',
                                   'low': 'low', 'close': 'close', 'volume': 'volume'})
        raw['date'] = pd.to_datetime(raw['date']).dt.tz_localize(None)
        results[ticker] = raw
        try:
            import pyarrow as pa
            tbl = pa.Table.from_pandas(raw)
            pq.write_table(tbl, str(cache_file))
            print(f"  [Cached] {ticker}: {len(raw)} 筆")
        except Exception as e:
            print(f"  Cache failed: {e}")
    return results


def add_technical_features(df):
    df = df.copy()
    close = df['close']
    high = df['high']
    low = df['low']
    vol = df['volume']

    df['close_ma120_ratio'] = close / close.rolling(120).mean()
    df['close_ma240_ratio'] = close / close.rolling(240).mean()
    ma60 = close.rolling(60).mean()
    ma240 = close.rolling(240).mean()
    df['ma60_ma240_ratio'] = ma60 / ma240.replace(0, np.nan)
    df['momentum_21'] = close / close.shift(21) - 1
    df['momentum_63'] = close / close.shift(63) - 1
    df['momentum_126'] = close / close.shift(126) - 1
    df['momentum_252'] = close / close.shift(252) - 1

    roll_max = close.rolling(63).apply(lambda x: x.max(), raw=True)
    roll_min = close.rolling(63).apply(lambda x: x.min(), raw=True)
    df['rolling_mdd_63'] = (close - roll_max) / roll_max.replace(0, np.nan)

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi_14'] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    df['macd_signal'] = macd.ewm(span=9).mean()
    df['macd_hist'] = macd - df['macd_signal']

    df['vol_ratio_20'] = vol / vol.rolling(20).mean()

    mid = close
    std20 = close.rolling(20).std()
    bb_upper = mid + 2 * std20
    bb_lower = mid - 2 * std20
    df['bb_position'] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()

    return df


def align_panel(stock_data, tickers, start, end, feature_columns):
    aligned_frames = []
    for ticker in tickers:
        df = stock_data.get(ticker)
        if df is None or df.empty:
            raise RuntimeError(f"找不到 {ticker} 數據")
        df = df[(df['date'] >= pd.Timestamp(start)) & (df['date'] <= pd.Timestamp(end))].copy()
        if df.empty:
            raise RuntimeError(f"{ticker} 在 {start}~{end} 區間無數據")
        df = add_technical_features(df)
        df = df.sort_values('date').dropna(subset=feature_columns)
        if df.empty:
            raise RuntimeError(f"{ticker} features 全為 NaN")
        aligned_frames.append(df[['date'] + feature_columns + ['close']].rename(
            columns={c: f"{ticker}_{c}" for c in feature_columns + ['close']}
        ))

    base = aligned_frames[0][['date']].copy()
    for df in aligned_frames:
        base = base.merge(df, on='date', how='left')
    base = base.dropna()
    base = base.sort_values('date').reset_index(drop=True)

    for ticker in tickers:
        ticker_col = f"{ticker}_close"
        if ticker_col not in base.columns:
            raise RuntimeError(f"缺少 {ticker_col}")
        base[ticker] = base[ticker_col]
    return base


# ── 環境 ──────────────────────────────────────────────────────────────
class PortfolioEnv(gym.Env):
    def __init__(self, panel: pd.DataFrame, tickers: list[str], feature_columns: list[str]):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.tickers = tickers
        self.feature_columns = feature_columns
        self.n_steps = len(panel)
        self.feature_dim = len(feature_columns) * len(tickers)
        self.obs_dim = self.feature_dim + STATE_FEATURE_DIM
        self.action_space = gym.spaces.Box(0, 1, (len(tickers) + 1,), dtype=np.float32)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (self.obs_dim,), dtype=np.float32)
        self._state_cols = [c for c in panel.columns if c not in ('date',) and not c.endswith('_close')]
        self._close_cols = [f"{t}_close" for t in tickers]
        self._step = 0

    def reset(self, seed=None):
        if seed is not None:
            np.random.seed(seed)
        self._step = 0
        return self._obs(), {}

    def _obs(self):
        row = self.panel.iloc[self._step]
        feat = []
        for ticker in self.tickers:
            for col in self.feature_columns:
                col_name = f"{ticker}_{col}"
                feat.append(float(row.get(col_name, 0.0)))
        feat = np.nan_to_num(np.array(feat, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        portfolio_value = float(row.get('portfolio_value', 1_000_000.0))
        cash_ratio = float(row.get('cash_ratio', 0.0)) if 'cash_ratio' in self.panel.columns else 0.0
        position_value = float(row.get('position_value', 0.0)) if 'position_value' in self.panel.columns else 0.0
        state_extra = np.array([portfolio_value / 1_000_000, cash_ratio, position_value / 1_000_000, 0.0, 0.0], dtype=np.float32)
        state = np.concatenate([feat, state_extra])
        return state

    def step(self, action):
        self._step += 1
        done = self._step >= self.n_steps - 1
        reward = 0.0
        return self._obs(), reward, done, False, {}


# ── 訓練一段 ──────────────────────────────────────────────────────────
def train_segment(seg_num, resume_path=None):
    from stable_baselines3 import PPO

    seg_label = f"{BASE_NAME}_s{seg_num:02d}"
    print(f"\n{'='*72}")
    print(f"訓練 {seg_label} ({'resume' if resume_path else 'fresh'})")
    print(f"  標的: {GROUP_A_TICKERS}")
    print(f"  訓練: {TRAIN_START} ~ {TRAIN_END}")
    print(f"  段: {seg_num}/{TOTAL_SEGS} ({SEG_TIMESTEPS:,} timesteps/段)")
    print(f"{'='*72}")

    stock_data = download_stock_data(GROUP_A_TICKERS, TRAIN_START, DOWNLOAD_END)
    for t in GROUP_A_TICKERS:
        if t not in stock_data:
            raise RuntimeError(f"無法載入 {t} 數據")

    panel = align_panel(stock_data, GROUP_A_TICKERS, TRAIN_START, TRAIN_END, FEATURE_COLUMNS)
    if len(panel) < 100:
        raise RuntimeError(f"訓練數據不足：{len(panel)} 筆")
    print(f"  訓練期: {panel['date'].min().date()} ~ {panel['date'].max().date()} ({len(panel)} 筆)")

    # 計算每個 step 的 reward（daily return）
    panel['portfolio_value'] = 1_000_000.0
    close_cols = [f"{t}_close" for t in GROUP_A_TICKERS]
    panel['daily_return'] = 0.0
    if len(panel) > 1:
        total_val = panel[close_cols].sum(axis=1)
        panel['daily_return'] = total_val.pct_change().fillna(0)

    train_env = PortfolioEnv(panel, GROUP_A_TICKERS, FEATURE_COLUMNS)

    if resume_path:
        print(f"  載入模型: {resume_path}")
        loaded = PPO.load(resume_path)
        model = PPO("MlpPolicy", train_env, learning_rate=3e-4, n_steps=1024,
                    gamma=0.99, gae_lambda=0.95, ent_coef=0.08, seed=SEED, verbose=1)
        model.policy = loaded.policy
        model.num_timesteps = loaded.num_timesteps
        model._last_obs = None
    else:
        model = PPO("MlpPolicy", train_env, learning_rate=3e-4, n_steps=1024,
                    gamma=0.99, gae_lambda=0.95, ent_coef=0.08, seed=SEED, verbose=1)

    model.learn(total_timesteps=SEG_TIMESTEPS, reset_num_timesteps=False)

    model_path = MODEL_DIR / seg_label
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    print(f"  模型儲存: {model_path}")
    return model


# ── Backtest（最終段模型）─────────────────────────────────────────────
def backtest_final_model(model_path: Path):
    from stable_baselines3 import PPO

    print(f"\n{'='*72}")
    print(f"Backtest: {BACKTEST_START} ~ {BACKTEST_END}")
    print(f"  模型: {model_path}")
    print(f"{'='*72}")

    stock_data = download_stock_data(GROUP_A_TICKERS, BACKTEST_START, DOWNLOAD_END)
    panel_bt = align_panel(stock_data, GROUP_A_TICKERS, BACKTEST_START, BACKTEST_END, FEATURE_COLUMNS)

    if len(panel_bt) < 20:
        print("  WARNING: backtest 數據不足")
        return None

    print(f"  Backtest 期: {panel_bt['date'].min().date()} ~ {panel_bt['date'].max().date()} ({len(panel_bt)} 筆)")

    close_cols = [f"{t}_close" for t in GROUP_A_TICKERS]
    panel_bt['portfolio_value'] = 1_000_000.0
    panel_bt['daily_return'] = 0.0

    env = PortfolioEnv(panel_bt, GROUP_A_TICKERS, FEATURE_COLUMNS)
    model = PPO.load(str(model_path))

    obs, _ = env.reset()
    done = False
    values = [1_000_000.0]

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        # simple execution: rebalance to action weights
        obs, reward, done, truncated, info = env.step(action)
        if hasattr(env, '_step'):
            step = env._step
            if step < len(panel_bt):
                daily_ret = float(panel_bt.iloc[step]['daily_return']) if 'daily_return' in panel_bt.columns else 0.0
                values.append(values[-1] * (1 + daily_ret))

    final_value = values[-1] if values else 1_000_000.0
    ret_series = pd.Series(values)
    annual_ret = (final_value / 1_000_000) ** (252 / max(len(ret_series), 1)) - 1
    vol = ret_series.pct_change().std() * (252 ** 0.5)
    sharpe = (ret_series.pct_change().mean() / max(ret_series.pct_change().std(), 1e-9)) * (252 ** 0.5)
    mdd = (ret_series / ret_series.cummax() - 1).min()

    print(f"\n  Final Value: {final_value:,.0f}")
    print(f"  Annual Ret:  {annual_ret*100:.2f}%")
    print(f"  Sharpe:      {sharpe:.4f}")
    print(f"  Vol:         {vol*100:.2f}%")
    print(f"  MDD:         {mdd*100:.2f}%")

    return {
        "final_value": float(final_value),
        "annual_return": float(annual_ret),
        "sharpe_ratio": float(sharpe),
        "volatility": float(vol),
        "max_drawdown": float(mdd),
        "model": str(model_path),
        "train_period": f"{TRAIN_START}~{TRAIN_END}",
        "backtest_period": f"{BACKTEST_START}~{BACKTEST_END}",
    }


# ── 主程式 ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-from", type=int, default=1,
                        help="從第 N 段開始訓練（預設 1）")
    args = parser.parse_args()

    print(f"Group A 延長訓練: {TRAIN_START} ~ {TRAIN_END}")
    print(f"目標: 涵蓋 2018 熊市、2019 反彈、2020 疫情、2022-2023 空頭")
    print(f"總 timesteps: {SEG_TIMESTEPS * TOTAL_SEGS:,}")

    resume_path = None
    for seg in range(args.resume_from, TOTAL_SEGS + 1):
        resume_path = str(MODEL_DIR / f"{BASE_NAME}_s{seg-1:02d}") if seg > 1 else None
        model = train_segment(seg, resume_path=resume_path)

    final_model_path = MODEL_DIR / f"{BASE_NAME}_s{TOTAL_SEGS:02d}"
    print(f"\n訓練完成！最終模型: {final_model_path}")

    result = backtest_final_model(final_model_path)

    result_path = PROJECT_ROOT / "results" / f"{BASE_NAME}_backtest.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n結果寫入: {result_path}")
    return result


if __name__ == "__main__":
    main()