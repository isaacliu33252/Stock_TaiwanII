#!/usr/bin/env python3
"""Train one PPO portfolio allocator for 0050/0056/00713/00878."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE
from portfolio_data_loader import download_all_stocks
from portfolio_train_v2 import calculate_backtest_metrics


TICKERS = ["0050.TW", "0056.TW", "00713.TW", "00878.TW"]
TRAIN_START = "2009-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-08"
DOWNLOAD_END = "2026-05-09"
TIMESTEPS = 20_000
SEED = 42
DCA_DEFAULT_AMOUNTS = {
    "0050.TW": 5_000.0,
    "0056.TW": 5_000.0,
    "00713.TW": 5_000.0,
    "00878.TW": 10_000.0,
}


FEATURE_COLUMNS = [
    "close_ma120_ratio",
    "close_ma240_ratio",
    "ma60_ma240_ratio",
    "momentum_21",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "rolling_mdd_63",
]

DERIVED_FEATURE_COLUMNS = [
    "0050_trend_score",
    "0050_above_ma120",
    "0050_above_ma240",
    "0050_ma60_above_ma240",
    "0050_drawdown_risk",
    "0050_volatility_63",
    "0050_volatility_rank_252",
    "high_dividend_momentum_avg_63",
    "high_dividend_momentum_avg_126",
    "high_dividend_vs_0050_momentum_63",
    "high_dividend_vs_0050_momentum_126",
    "00878_vs_0050_momentum_63",
    "00713_vs_0050_momentum_63",
    "0056_vs_0050_momentum_63",
    "00878_vs_0056_momentum_126",
    "0050_momentum_rank_63",
    "0050_momentum_rank_126",
    "0050_momentum_rank_252",
    "00878_momentum_rank_126",
    "best_momentum_spread_126",
    "top2_momentum_avg_126",
    "momentum_dispersion_126",
    "0050_rsi_14",
    "0050_rsi_14_rank_252",
    "high_dividend_rsi_14_avg",
    "0050_rsi_minus_hd_rsi",
    "0050_pva_p",
    "0050_pva_v",
    "0050_pva_a",
    "0050_pva_p_z",
    "0050_pva_v_z",
    "0050_pva_a_z",
    "0050_sjm_state_code",
]

ACTIVE_DERIVED_FEATURE_COLUMNS = [
    "0050_trend_score",
    "0050_volatility_rank_252",
    "high_dividend_vs_0050_momentum_126",
    "00878_vs_0050_momentum_63",
    "0050_momentum_rank_126",
]

RSI_DERIVED_FEATURE_COLUMNS = [
    "0050_rsi_14",
    "0050_rsi_14_rank_252",
    "high_dividend_rsi_14_avg",
    "0050_rsi_minus_hd_rsi",
]


def _slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def _align_panel(stock_data: dict[str, pd.DataFrame], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in TICKERS:
        df = _slice_by_date(stock_data[ticker], start, end)
        cols = ["date", "close"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        if "dividends" in df.columns:
            cols.append("dividends")
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")

    panel = panel.sort_values("date").reset_index(drop=True)
    panel = panel.ffill().bfill().fillna(0.0)
    panel = _add_portfolio_features(panel)
    return panel


def _safe_col(panel: pd.DataFrame, ticker: str, feature: str, default: float = 0.0) -> pd.Series:
    col = f"{ticker}_{feature}"
    if col in panel.columns:
        return panel[col].astype(float)
    return pd.Series(default, index=panel.index, dtype=float)


def _rank_desc(values: pd.DataFrame) -> pd.DataFrame:
    return values.rank(axis=1, ascending=False, method="min")


def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0).clip(0.0, 100.0) / 100.0


def _rolling_zscore(series: pd.Series, window: int = 252, min_periods: int = 63) -> pd.Series:
    values = series.astype(float)
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std(ddof=1)
    return ((values - mean) / std.replace(0.0, np.nan)).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def _add_portfolio_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Features that describe cross-ETF relative strength and market regime."""
    panel = panel.copy()

    ma120 = _safe_col(panel, "0050.TW", "close_ma120_ratio", 0.0)
    ma240 = _safe_col(panel, "0050.TW", "close_ma240_ratio", 0.0)
    ma60_240 = _safe_col(panel, "0050.TW", "ma60_ma240_ratio", 0.0)
    mdd63 = _safe_col(panel, "0050.TW", "rolling_mdd_63", 0.0)
    panel["0050_above_ma120"] = (ma120 > 0.0).astype(float)
    panel["0050_above_ma240"] = (ma240 > 0.0).astype(float)
    panel["0050_ma60_above_ma240"] = (ma60_240 > 0.0).astype(float)
    panel["0050_drawdown_risk"] = mdd63.clip(upper=0.0).abs()
    panel["0050_trend_score"] = (
        panel["0050_above_ma120"] + panel["0050_above_ma240"] + panel["0050_ma60_above_ma240"]
    ) / 3.0

    close_0050 = _safe_col(panel, "0050.TW", "close", np.nan)
    ret_0050 = close_0050.pct_change()
    vol63 = ret_0050.rolling(63, min_periods=20).std(ddof=1).fillna(0.0) * np.sqrt(252)
    panel["0050_volatility_63"] = vol63
    panel["0050_volatility_rank_252"] = vol63.rolling(252, min_periods=63).rank(pct=True).fillna(0.5)

    high_dividend = ["0056.TW", "00713.TW", "00878.TW"]
    for lookback in (63, 126):
        hd_momentum = pd.concat(
            [_safe_col(panel, ticker, f"momentum_{lookback}", 0.0) for ticker in high_dividend],
            axis=1,
        )
        panel[f"high_dividend_momentum_avg_{lookback}"] = hd_momentum.mean(axis=1)
        panel[f"high_dividend_vs_0050_momentum_{lookback}"] = (
            panel[f"high_dividend_momentum_avg_{lookback}"] - _safe_col(panel, "0050.TW", f"momentum_{lookback}", 0.0)
        )

    panel["00878_vs_0050_momentum_63"] = _safe_col(panel, "00878.TW", "momentum_63") - _safe_col(panel, "0050.TW", "momentum_63")
    panel["00713_vs_0050_momentum_63"] = _safe_col(panel, "00713.TW", "momentum_63") - _safe_col(panel, "0050.TW", "momentum_63")
    panel["0056_vs_0050_momentum_63"] = _safe_col(panel, "0056.TW", "momentum_63") - _safe_col(panel, "0050.TW", "momentum_63")
    panel["00878_vs_0056_momentum_126"] = _safe_col(panel, "00878.TW", "momentum_126") - _safe_col(panel, "0056.TW", "momentum_126")

    rsi_0050 = _calculate_rsi(_safe_col(panel, "0050.TW", "close", np.nan), 14)
    high_dividend_rsi = pd.concat(
        [_calculate_rsi(_safe_col(panel, ticker, "close", np.nan), 14) for ticker in high_dividend],
        axis=1,
    )
    panel["0050_rsi_14"] = rsi_0050
    panel["0050_rsi_14_rank_252"] = rsi_0050.rolling(252, min_periods=63).rank(pct=True).fillna(0.5)
    panel["high_dividend_rsi_14_avg"] = high_dividend_rsi.mean(axis=1)
    panel["0050_rsi_minus_hd_rsi"] = rsi_0050 - panel["high_dividend_rsi_14_avg"]

    # PVA/SJM 狀態特徵：
    # - close_ma120_ratio 已經是圍繞 0.0 的均線偏離，不是 close/MA 比值。
    #   這裡必須用 0.0 當中性點；若誤用 1.0，恐慌/貪婪判斷會失真，
    #   也是先前 PVA 幾乎不觸發的主因。
    # - P 使用 0050 的中期價格位置，V 使用 63 日動能，A 使用 V 的
    #   20 個交易日變化。SJM 故意只看 0050，因為它是整個 ETF 投組的
    #   市場 beta 錨點。
    # - z-score 使用 rolling 統計，因此門檻代表「相對近期市場狀態的極端」，
    #   不是固定的絕對報酬水準。
    pva_p = _safe_col(panel, "0050.TW", "close_ma120_ratio", 0.0)
    pva_v = _safe_col(panel, "0050.TW", "momentum_63", 0.0)
    pva_a = pva_v - pva_v.shift(20).fillna(pva_v)
    panel["0050_pva_p"] = pva_p
    panel["0050_pva_v"] = pva_v
    panel["0050_pva_a"] = pva_a
    panel["0050_pva_p_z"] = _rolling_zscore(pva_p)
    panel["0050_pva_v_z"] = _rolling_zscore(pva_v)
    panel["0050_pva_a_z"] = _rolling_zscore(pva_a)
    # SJM state code 會進入 PPO observation；下方 _sjm_state() 也用同一組
    # 門檻控制 overlay 是否執行。若未來調整門檻，兩邊必須同步修改。
    panic = (panel["0050_pva_a_z"] < -2.0) | (panel["0050_pva_v_z"] < -2.0)
    greed = (panel["0050_pva_v_z"] > 1.0) & (panel["0050_pva_a_z"] > 0.0)
    panel["0050_sjm_state_code"] = 0.0
    panel.loc[greed, "0050_sjm_state_code"] = 1.0
    panel.loc[panic, "0050_sjm_state_code"] = -1.0

    for lookback in (63, 126, 252):
        momentum = pd.concat(
            [_safe_col(panel, ticker, f"momentum_{lookback}", 0.0).rename(ticker) for ticker in TICKERS],
            axis=1,
        )
        ranks = _rank_desc(momentum)
        panel[f"0050_momentum_rank_{lookback}"] = (ranks["0050.TW"] - 1.0) / (len(TICKERS) - 1)
        if lookback == 126:
            panel["00878_momentum_rank_126"] = (ranks["00878.TW"] - 1.0) / (len(TICKERS) - 1)
            sorted_momentum = np.sort(momentum.to_numpy(dtype=float), axis=1)[:, ::-1]
            panel["best_momentum_spread_126"] = sorted_momentum[:, 0] - sorted_momentum[:, -1]
            panel["top2_momentum_avg_126"] = sorted_momentum[:, :2].mean(axis=1)
            panel["momentum_dispersion_126"] = momentum.std(axis=1)

    panel[DERIVED_FEATURE_COLUMNS] = panel[DERIVED_FEATURE_COLUMNS].replace([np.inf, -np.inf], 0.0)
    panel[DERIVED_FEATURE_COLUMNS] = panel[DERIVED_FEATURE_COLUMNS].fillna(0.0)
    return panel


def _prices(panel: pd.DataFrame) -> np.ndarray:
    return panel[[f"{ticker}_close" for ticker in TICKERS]].to_numpy(dtype=float)


def _holding_segments(mask: np.ndarray) -> list[int]:
    segments = []
    current = 0
    for held in mask.astype(bool):
        if held:
            current += 1
        elif current > 0:
            segments.append(current)
            current = 0
    if current > 0:
        segments.append(current)
    return segments


def calculate_holding_time_stats(
    panel: pd.DataFrame,
    weight_history: list[list[float]],
    rebalance_indices: list[int],
    threshold: float = 0.01,
) -> dict:
    dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
    weights = np.asarray(weight_history, dtype=float)
    if len(weights) == 0:
        weights = np.zeros((len(panel), len(TICKERS)), dtype=float)
    weights = weights[: len(panel)]

    clean_rebalances = sorted({int(i) for i in rebalance_indices if 0 <= int(i) < len(panel)})
    intervals = np.diff(clean_rebalances).astype(int).tolist() if len(clean_rebalances) >= 2 else []

    asset_stats = {}
    for idx, ticker in enumerate(TICKERS):
        mask = weights[:, idx] > threshold
        segments = _holding_segments(mask)
        asset_stats[ticker] = {
            "holding_days": int(mask.sum()),
            "holding_ratio": float(mask.mean()) if len(mask) else 0.0,
            "avg_continuous_holding_days": float(np.mean(segments)) if segments else 0.0,
            "max_continuous_holding_days": int(max(segments)) if segments else 0,
            "holding_period_count": int(len(segments)),
        }

    return {
        "threshold": float(threshold),
        "calendar_start": str(dates.iloc[0].date()) if len(dates) else None,
        "calendar_end": str(dates.iloc[-1].date()) if len(dates) else None,
        "total_trading_days": int(len(weights)),
        "rebalance_indices": clean_rebalances,
        "rebalance_dates": [str(dates.iloc[i].date()) for i in clean_rebalances],
        "rebalance_interval_days": {
            "intervals": intervals,
            "avg": float(np.mean(intervals)) if intervals else 0.0,
            "min": int(min(intervals)) if intervals else 0,
            "max": int(max(intervals)) if intervals else 0,
        },
        "asset_holding_days": asset_stats,
    }


def _dividends(panel: pd.DataFrame) -> np.ndarray:
    cols = []
    for ticker in TICKERS:
        col = f"{ticker}_dividends"
        if col not in panel.columns:
            panel[col] = 0.0
        cols.append(col)
    return panel[cols].fillna(0.0).to_numpy(dtype=float)


class ETFPortfolioEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        initial_cash: float = 1_000_000,
        commission_rate: float = COMMISSION_RATE,
        tax_rate: float = ETF_TAX_RATE,
        turnover_penalty: float = 0.001,
        benchmark_weight: float = 2.0,
        min_rebalance_days: int = 20,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        active_derived_features: list[str] | None = None,
        dca_monthly_amounts: dict[str, float] | None = None,
        dca_day: int = 26,
        enable_range_harvest: bool = False,
        range_drift_threshold: float = 0.05,
        enable_pva_sigmoid: bool = False,
        pva_weight: float = 0.30,
        pva_drift_threshold: float = 0.05,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.tax_rate = float(tax_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.benchmark_weight = float(benchmark_weight)
        self.min_rebalance_days = int(min_rebalance_days)
        self.min_weight = float(min_weight)
        self.max_weight = float(max_weight)
        self.active_derived_features = active_derived_features or ACTIVE_DERIVED_FEATURE_COLUMNS
        self.dca_monthly_amounts = dca_monthly_amounts or {}
        self.dca_amount_array = np.array([float(self.dca_monthly_amounts.get(ticker, 0.0)) for ticker in TICKERS])
        self.dca_day = int(dca_day)
        self.dca_schedule = self._build_dca_schedule()
        self.enable_range_harvest = bool(enable_range_harvest)
        self.range_drift_threshold = float(range_drift_threshold)
        self.range_target_weights = self._constrain_weights(np.array([0.40, 0.20, 0.20, 0.20], dtype=float))
        self.enable_pva_sigmoid = bool(enable_pva_sigmoid)
        self.pva_weight = float(pva_weight)
        self.pva_drift_threshold = float(pva_drift_threshold)
        self.price_array = _prices(self.panel)
        self.dividend_array = _dividends(self.panel)
        self.equal_bh_curve = self._benchmark_curve(np.array([0.25, 0.25, 0.25, 0.25], dtype=float))
        self.bh_0050_curve = self._benchmark_curve(np.array([1.0, 0.0, 0.0, 0.0], dtype=float))
        self.feature_cols = []
        for ticker in TICKERS:
            self.feature_cols.extend([f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns])
        self.feature_cols.extend([c for c in self.active_derived_features if c in self.panel.columns])

        self.portfolio_state_dim = len(TICKERS) + 6
        obs_dim = len(self.feature_cols) + self.portfolio_state_dim
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(10)
        self.reset()

    def _constrain_weights(self, weights: np.ndarray) -> np.ndarray:
        weights = np.asarray(weights, dtype=float)
        weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)
        weights = np.clip(weights, 0.0, None)
        if weights.sum() <= 0:
            weights = np.ones(len(TICKERS), dtype=float) / len(TICKERS)
        else:
            weights = weights / weights.sum()

        if self.min_weight <= 0 and self.max_weight >= 1:
            return weights
        if self.min_weight * len(TICKERS) > 1.0:
            raise ValueError("min_weight is too high for the number of assets")
        if self.max_weight * len(TICKERS) < 1.0:
            raise ValueError("max_weight is too low for the number of assets")

        weights = np.maximum(weights, self.min_weight)
        weights = weights / weights.sum()
        for _ in range(20):
            over = weights > self.max_weight
            if not over.any():
                break
            excess = float((weights[over] - self.max_weight).sum())
            weights[over] = self.max_weight
            under = ~over
            room = np.maximum(self.max_weight - weights[under], 0.0)
            if room.sum() <= 0:
                break
            weights[under] += excess * room / room.sum()

        weights = np.maximum(weights, self.min_weight)
        weights = np.minimum(weights, self.max_weight)
        return weights / weights.sum()

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _is_range_bound(self, idx: int) -> bool:
        row = self.panel.iloc[idx]
        near_ma120 = abs(float(row.get("0050.TW_close_ma120_ratio", 0.0))) <= 0.08
        near_ma240 = abs(float(row.get("0050.TW_close_ma240_ratio", 0.0))) <= 0.10
        muted_momentum = abs(float(row.get("0050.TW_momentum_126", 0.0))) <= 0.12
        volatility_ok = float(row.get("0050_volatility_rank_252", 0.5)) <= 0.65
        drawdown_ok = float(row.get("0050_drawdown_risk", 0.0)) <= 0.15
        dispersion_ok = abs(float(row.get("momentum_dispersion_126", 0.0))) <= 0.12
        return bool((near_ma120 or near_ma240) and muted_momentum and volatility_ok and drawdown_ok and dispersion_ok)

    def _sjm_state(self, idx: int) -> tuple[str, dict]:
        # SJM 是刻意保持很小的狀態機：
        # - M（恐慌）：動能或加速度落在近期統計極端。
        # - J（貪婪）：動能偏強，而且仍在向上加速。
        # - S（平靜）：其他全部情況。S 本來就會佔大多數，2026-05-10
        #   修正後不再讓 S 觸發 PVA overlay，因為先前測試證明 S 狀態
        #   再平衡容易製造錯誤買點。
        row = self.panel.iloc[idx]
        p_z = float(row.get("0050_pva_p_z", 0.0))
        v_z = float(row.get("0050_pva_v_z", 0.0))
        a_z = float(row.get("0050_pva_a_z", 0.0))
        if a_z < -2.0 or v_z < -2.0:
            state = "M"
        elif v_z > 1.0 and a_z > 0.0:
            state = "J"
        else:
            state = "S"
        return state, {
            "p": float(row.get("0050_pva_p", 0.0)),
            "v": float(row.get("0050_pva_v", 0.0)),
            "a": float(row.get("0050_pva_a", 0.0)),
            "p_z": p_z,
            "v_z": v_z,
            "a_z": a_z,
            "state": state,
        }

    def _pva_sigmoid_weights(self, idx: int) -> tuple[np.ndarray, dict]:
        sjm_state, sjm_details = self._sjm_state(idx)
        scores = []
        details = {}
        for ticker in TICKERS:
            p = float(self.panel.iloc[idx].get(f"{ticker}_close_ma120_ratio", 0.0))
            v = float(self.panel.iloc[idx].get(f"{ticker}_momentum_63", 0.0))
            v_prev = float(self.panel.iloc[max(idx - 20, 0)].get(f"{ticker}_momentum_63", 0.0))
            a = v - v_prev
            long_trend = float(self.panel.iloc[idx].get(f"{ticker}_close_ma240_ratio", 0.0))

            # PVA 分數偏向均值回歸：
            # 價格位置 P 越低、動能 V 越弱、加速度 A 越往下，sigmoid
            # 分數越高。這一步先產生「弱勢時提高吸引力」的原始權重，
            # 再交給 SJM policy layer 依 M/J/S 狀態調整最終配置。
            mean_reversion_score = -3.0 * p - 1.5 * v - 1.0 * a
            trend_bonus = 0.75 if long_trend > 0 else -0.25
            state_bias = {"M": 0.80, "S": 0.00, "J": -0.50}[sjm_state]
            z = mean_reversion_score + trend_bonus + state_bias
            score = 1.0 / (1.0 + np.exp(-z))
            scores.append(score)
            details[ticker] = {
                "p": float(p),
                "v": float(v),
                "a": float(a),
                "long_trend": float(long_trend),
                "z": float(z),
                "sigmoid": float(score),
            }

        raw_weights = self._constrain_weights(np.asarray(scores, dtype=float))
        policy = "sigmoid"
        if sjm_state == "M":
            # 恐慌政策：舊版 30%/45% overlay 仍讓 PPO 主導，導致
            # 2025-04-08 這種明確恐慌點過度降低 0050。
            # M 狀態下改成偏市場 beta 反彈：70% 固定 beta target +
            # 30% raw PVA。step() 會用 100% overlay weight 套用此 target，
            # 避免 PPO 在少數恐慌事件中覆蓋掉 PVA 的處理。
            panic_beta_target = np.array([self.max_weight, 0.1333, 0.1333, 0.1334], dtype=float)
            weights = self._constrain_weights(0.70 * panic_beta_target + 0.30 * raw_weights)
            policy = "panic_beta_rebound"
        elif sjm_state == "J":
            # 貪婪政策：強勢且加速上行時不要繼續追 beta。
            # 權重偏向高股息 ETF，並讓 0050 接近最低權重；同時保留
            # 35% raw PVA，避免配置變成完全寫死的規則。
            defensive_target = np.array([self.min_weight, 0.35, 0.30, 0.30], dtype=float)
            weights = self._constrain_weights(0.65 * defensive_target + 0.35 * raw_weights)
            policy = "greed_defensive"
        else:
            weights = raw_weights

        return weights, {"sjm": sjm_details, "assets": details, "policy": policy, "raw_pva_weights": {ticker: float(w) for ticker, w in zip(TICKERS, raw_weights)}}

    def _pva_overlay_allowed(self, idx: int) -> tuple[bool, str, dict]:
        sjm_state, sjm_details = self._sjm_state(idx)
        # 目前只允許 M 恐慌觸發 overlay。三 seed 測試顯示 J 狀態的
        # greed_defensive 會在強趨勢段過早降 beta，尤其 seed 7 被
        # 多次 J 觸發拖累；因此 J 先保留為 observation 特徵，不直接
        # 覆蓋 PPO 交易。S 狀態也刻意關閉，避免舊版 2024-12-30
        # 那類平靜狀態錯誤再平衡。
        if sjm_state == "M":
            return True, sjm_state, sjm_details
        return False, sjm_state, sjm_details

    def _range_harvest_due(self, idx: int) -> tuple[bool, float]:
        if not self.enable_range_harvest or not self._is_range_bound(idx):
            return False, 0.0
        current_weights = self.weights.copy()
        drift = float(np.abs(current_weights - self.range_target_weights).sum())
        return drift >= self.range_drift_threshold, drift

    def _build_dca_schedule(self) -> list[dict]:
        if self.dca_amount_array.sum() <= 0 or len(self.panel) == 0:
            return []
        dates = pd.to_datetime(self.panel["date"])
        start = dates.min().to_period("M")
        end = dates.max().to_period("M")
        schedule = []
        for period in pd.period_range(start, end, freq="M"):
            day = min(self.dca_day, period.days_in_month)
            schedule.append(
                {
                    "month": str(period),
                    "scheduled_date": pd.Timestamp(year=period.year, month=period.month, day=day),
                }
            )
        return schedule

    def _apply_dca_if_due(self, idx: int, prices: np.ndarray) -> float:
        if self.dca_amount_array.sum() <= 0:
            return 0.0
        current_date = pd.Timestamp(self.panel.iloc[idx]["date"])
        due_items = [
            item for item in self.dca_schedule
            if item["month"] not in self.dca_executed_months and current_date >= item["scheduled_date"]
        ]
        if not due_items:
            return 0.0

        fees = 0.0
        history_items = []
        for item in due_items:
            purchases = {}
            self.dca_executed_months.add(item["month"])
            for i, amount in enumerate(self.dca_amount_array):
                if amount <= 0:
                    continue
                self.cash += amount
                self.total_contributions += amount
                buy_value = amount / (1.0 + self.commission_rate)
                fee = buy_value * self.commission_rate
                self.cash -= buy_value + fee
                self.shares[i] += buy_value / prices[i]
                fees += fee
                purchases[TICKERS[i]] = {
                    "cash_contribution": float(amount),
                    "buy_value": float(buy_value),
                    "fee": float(fee),
                    "price": float(prices[i]),
                    "shares_bought": float(buy_value / prices[i]),
                }
            history_items.append(
                {
                    "date": str(current_date.date()),
                    "month": item["month"],
                    "scheduled_date": str(item["scheduled_date"].date()),
                    "total_contribution": float(self.dca_amount_array.sum()),
                    "fees": float(sum(p["fee"] for p in purchases.values())),
                    "purchases": purchases,
                }
            )

        value_after = max(self._portfolio_value(prices), 1.0)
        self.weights = self.shares * prices / value_after
        self.dca_purchase_count += len(history_items)
        self.dca_purchase_history.extend(history_items)
        return float(fees)

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = self.initial_cash * weights / self.price_array[0]
        cash = 0.0
        curve = []
        for idx, prices in enumerate(self.price_array):
            if idx > 0:
                cash += float(np.dot(shares, self.dividend_array[idx]))
            curve.append(float(cash + np.dot(shares, prices)))
        return np.array(curve, dtype=float)

    def _target_weights(self, action: int) -> np.ndarray:
        if action == 0:
            return self.weights.copy()
        if action == 1:
            return self._constrain_weights(np.array([0.25, 0.25, 0.25, 0.25], dtype=float))
        if action == 2:
            return self._constrain_weights(np.array([1.0, 0.0, 0.0, 0.0], dtype=float))
        if action == 3:
            return self._constrain_weights(np.array([0.50, 0.30, 0.10, 0.10], dtype=float))
        if action == 4:
            return self._constrain_weights(np.array([0.70, 0.10, 0.10, 0.10], dtype=float))
        if action == 5:
            return self._constrain_weights(np.array([0.80, 0.00, 0.00, 0.20], dtype=float))
        if action == 6:
            return self._constrain_weights(np.array([0.15, 0.25, 0.25, 0.35], dtype=float))
        if action == 7:
            return self._constrain_weights(np.array([0.0, 0.40, 0.30, 0.30], dtype=float))

        momentum = []
        for ticker in TICKERS:
            col = f"{ticker}_momentum_126"
            momentum.append(float(self.panel.iloc[self.step_idx].get(col, 0.0)))
        order = np.argsort(momentum)[::-1]
        weights = np.zeros(len(TICKERS), dtype=float)
        if action == 8:
            weights[order[0]] = 1.0
        else:
            weights[order[:2]] = 0.5
        return self._constrain_weights(weights)

    def _get_obs(self) -> np.ndarray:
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        prices = self.price_array[self.step_idx]
        value = max(self._portfolio_value(prices), 1.0)
        weights = self.shares * prices / value
        cash_weight = self.cash / value
        peak = max(self.peak_value, value, 1.0)
        current_drawdown = value / peak - 1.0
        days_since_rebalance = min(max(self.step_idx - self.last_rebalance_idx, 0), 252) / 252.0
        equal_relative = value / max(float(self.equal_bh_curve[self.step_idx]), 1.0) - 1.0
        bh_0050_relative = value / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0
        high_dividend_weight = float(weights[1:].sum())
        state = np.array(
            [
                *weights,
                cash_weight,
                current_drawdown,
                days_since_rebalance,
                equal_relative,
                bh_0050_relative,
                high_dividend_weight,
            ],
            dtype=float,
        )
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
            if delta < 0:
                sell_value = min(-delta, self.shares[i] * prices[i])
                if sell_value <= 0:
                    continue
                fees += sell_value * (self.commission_rate + self.tax_rate)
                self.cash += sell_value - sell_value * (self.commission_rate + self.tax_rate)
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
        return float(fees)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = np.zeros(len(TICKERS), dtype=float)
        self.weights = np.zeros(len(TICKERS), dtype=float)
        self.last_rebalance_idx = -10**9
        self.trade_count = 0
        self.fees_paid = 0.0
        self.dividend_cash_received = 0.0
        self.total_contributions = 0.0
        self.dca_purchase_count = 0
        self.dca_purchase_history = []
        self.dca_executed_months = set()
        self.range_harvest_count = 0
        self.range_harvest_history = []
        self.pva_sigmoid_count = 0
        self.pva_sigmoid_history = []
        self.sjm_state_history = []
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        self.weight_history = [self.weights.copy().tolist()]
        self.rebalance_indices = []
        return self._get_obs(), {}

    def step(self, action):
        prices = self.price_array[self.step_idx]
        value_before = self._portfolio_value(prices)
        target_weights = self._target_weights(int(action))
        fees = 0.0
        turnover = float(np.abs(target_weights - self.weights).sum())
        range_harvest_executed = False
        range_harvest_drift = 0.0
        sjm_state, sjm_details = self._sjm_state(self.step_idx)
        self.sjm_state_history.append(
            {
                "date": str(pd.Timestamp(self.panel.iloc[self.step_idx]["date"]).date()),
                **sjm_details,
            }
        )

        harvest_due, range_harvest_drift = self._range_harvest_due(self.step_idx)
        if harvest_due and self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days:
            target_weights = self.range_target_weights
            turnover = float(np.abs(target_weights - self.weights).sum())
            fees = self._rebalance(target_weights, prices)
            if fees > 0:
                self.trade_count += 1
                self.range_harvest_count += 1
                self.last_rebalance_idx = self.step_idx
                self.fees_paid += fees
                self.rebalance_indices.append(int(self.step_idx))
                self.range_harvest_history.append(
                    {
                        "date": str(pd.Timestamp(self.panel.iloc[self.step_idx]["date"]).date()),
                        "step_idx": int(self.step_idx),
                        "drift": float(range_harvest_drift),
                        "target_weights": {ticker: float(w) for ticker, w in zip(TICKERS, target_weights)},
                    }
                )
                range_harvest_executed = True

        pva_sigmoid_executed = False
        pva_allowed, sjm_state, sjm_details = self._pva_overlay_allowed(self.step_idx)
        if (
            not range_harvest_executed
            and self.enable_pva_sigmoid
            and pva_allowed
            and self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days
        ):
            pva_weights, pva_details = self._pva_sigmoid_weights(self.step_idx)
            state_weight = self.pva_weight
            if sjm_state == "M":
                # 恐慌事件很少，且在 2024-2026 檢查中是唯一有效的
                # PVA/SJM 觸發。這裡讓 PVA 恐慌政策完整覆蓋 PPO；
                # 否則 PPO 可能把正確的恐慌訊號變成最差時點的防禦再平衡。
                state_weight = 1.0
            elif sjm_state == "J":
                # 貪婪比恐慌不急迫，所以限制 overlay 比重。除非未來測試
                # 證明需要更強的出場規則，否則仍讓 PPO 保留多數控制權。
                state_weight = min(0.40, self.pva_weight)
            blended_weights = self._constrain_weights((1.0 - state_weight) * target_weights + state_weight * pva_weights)
            pva_drift = float(np.abs(blended_weights - self.weights).sum())
            if pva_drift >= self.pva_drift_threshold:
                target_weights = blended_weights
                turnover = float(np.abs(target_weights - self.weights).sum())
                fees = self._rebalance(target_weights, prices)
                if fees > 0:
                    self.trade_count += 1
                    self.pva_sigmoid_count += 1
                    self.last_rebalance_idx = self.step_idx
                    self.fees_paid += fees
                    self.rebalance_indices.append(int(self.step_idx))
                    self.pva_sigmoid_history.append(
                        {
                            "date": str(pd.Timestamp(self.panel.iloc[self.step_idx]["date"]).date()),
                            "step_idx": int(self.step_idx),
                            "sjm_state": sjm_state,
                            "drift": float(pva_drift),
                            "pva_weight": float(state_weight),
                            "pva_weights": {ticker: float(w) for ticker, w in zip(TICKERS, pva_weights)},
                            "target_weights": {ticker: float(w) for ticker, w in zip(TICKERS, target_weights)},
                            "details": pva_details,
                        }
                    )
                    pva_sigmoid_executed = True

        if (
            not range_harvest_executed
            and not pva_sigmoid_executed
            and int(action) != 0
            and self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days
        ):
            fees = self._rebalance(target_weights, prices)
            if fees > 0:
                self.trade_count += 1
                self.last_rebalance_idx = self.step_idx
                self.fees_paid += fees
                self.rebalance_indices.append(int(self.step_idx))

        self.step_idx += 1
        next_prices = self.price_array[self.step_idx]
        dividend_cash = float(np.dot(self.shares, self.dividend_array[self.step_idx]))
        if dividend_cash > 0:
            self.cash += dividend_cash
            self.dividend_cash_received += dividend_cash
        dca_fees = self._apply_dca_if_due(self.step_idx, next_prices)
        if dca_fees > 0:
            self.fees_paid += dca_fees
        value_after = self._portfolio_value(next_prices)
        self.peak_value = max(self.peak_value, value_after)
        self.equity_curve.append(value_after)
        self.weight_history.append(self.weights.copy().tolist())

        daily_return = value_after / max(value_before, 1.0) - 1
        equal_return = self.equal_bh_curve[self.step_idx] / self.equal_bh_curve[self.step_idx - 1] - 1
        bh_0050_return = self.bh_0050_curve[self.step_idx] / self.bh_0050_curve[self.step_idx - 1] - 1
        benchmark_return = max(float(equal_return), float(bh_0050_return))
        excess_return = daily_return - benchmark_return
        reward = float(
            (daily_return + self.benchmark_weight * excess_return) * 100.0
            - self.turnover_penalty * turnover
            - fees / max(value_before, 1.0)
        )
        terminated = self.step_idx >= len(self.panel) - 1
        info = {
            "portfolio_value": value_after,
            "fees_paid": self.fees_paid,
            "dividend_cash_received": self.dividend_cash_received,
            "total_contributions": self.total_contributions,
            "trade_count": self.trade_count,
            "range_harvest_count": self.range_harvest_count,
            "pva_sigmoid_count": self.pva_sigmoid_count,
            "weights": self.weights.copy(),
        }
        return self._get_obs(), reward, terminated, False, info


def _run_model(model: PPO, panel: pd.DataFrame, env_kwargs: dict | None = None) -> dict:
    env = ETFPortfolioEnv(panel, **(env_kwargs or {}))
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    metrics = calculate_backtest_metrics(equity)
    total_invested = env.initial_cash + env.total_contributions
    net_profit = float(equity[-1] - total_invested)
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": metrics,
        "num_trades": int(env.trade_count),
        "dca_purchase_count": int(env.dca_purchase_count),
        "range_harvest_count": int(env.range_harvest_count),
        "pva_sigmoid_count": int(env.pva_sigmoid_count),
        "fees_paid_estimate": float(env.fees_paid),
        "dividend_cash_received": float(env.dividend_cash_received),
        "total_contributions": float(env.total_contributions),
        "investment_summary": {
            "initial_cash": float(env.initial_cash),
            "total_contributions": float(env.total_contributions),
            "total_invested": float(total_invested),
            "final_value": float(equity[-1]),
            "net_profit": net_profit,
            "simple_return_on_total_invested": float(net_profit / total_invested) if total_invested > 0 else 0.0,
        },
        "dca_config": {
            "dca_day": int(env.dca_day),
            "monthly_amounts": {ticker: float(amount) for ticker, amount in zip(TICKERS, env.dca_amount_array)},
        },
        "dca_purchase_history": env.dca_purchase_history,
        "range_harvest_config": {
            "enabled": bool(env.enable_range_harvest),
            "range_drift_threshold": float(env.range_drift_threshold),
            "range_target_weights": {ticker: float(weight) for ticker, weight in zip(TICKERS, env.range_target_weights)},
        },
        "range_harvest_history": env.range_harvest_history,
        "pva_sigmoid_config": {
            "enabled": bool(env.enable_pva_sigmoid),
            "pva_weight": float(env.pva_weight),
            "pva_drift_threshold": float(env.pva_drift_threshold),
        },
        "pva_sigmoid_history": env.pva_sigmoid_history,
        "sjm_state_history": env.sjm_state_history,
        "sjm_state_counts": {
            state: int(sum(1 for item in env.sjm_state_history if item.get("state") == state))
            for state in ("S", "J", "M")
        },
        "holding_time_stats": calculate_holding_time_stats(panel, env.weight_history, env.rebalance_indices),
        "weight_history": env.weight_history,
        "final_weights": {ticker: float(w) for ticker, w in zip(TICKERS, info["weights"])},
        "equity_curve": equity,
    }


def _buy_and_hold(panel: pd.DataFrame, weights: np.ndarray) -> dict:
    prices = _prices(panel)
    dividends = _dividends(panel)
    initial = 1_000_000.0
    shares = initial * weights / prices[0]
    cash = 0.0
    equity = []
    for idx, row_prices in enumerate(prices):
        if idx > 0:
            cash += float(np.dot(shares, dividends[idx]))
        equity.append(float(cash + np.dot(row_prices, shares)))
    return {
        "final_value": float(equity[-1]),
        "metrics": calculate_backtest_metrics(equity),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a 4-ETF PPO portfolio allocator.")
    parser.add_argument("--train-start", default=TRAIN_START)
    parser.add_argument("--train-end", default=TRAIN_END)
    parser.add_argument("--backtest-start", default=BACKTEST_START)
    parser.add_argument("--backtest-end", default=BACKTEST_END)
    parser.add_argument("--download-end", default=DOWNLOAD_END)
    parser.add_argument("--timesteps", type=int, default=TIMESTEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--turnover-penalty", type=float, default=0.001)
    parser.add_argument("--min-rebalance-days", type=int, default=20)
    parser.add_argument("--min-weight", type=float, default=0.0)
    parser.add_argument("--max-weight", type=float, default=1.0)
    parser.add_argument("--use-rsi-features", action="store_true")
    parser.add_argument("--enable-dca", action="store_true")
    parser.add_argument("--dca-day", type=int, default=26)
    parser.add_argument("--dca-0050", type=float, default=DCA_DEFAULT_AMOUNTS["0050.TW"])
    parser.add_argument("--dca-0056", type=float, default=DCA_DEFAULT_AMOUNTS["0056.TW"])
    parser.add_argument("--dca-00713", type=float, default=DCA_DEFAULT_AMOUNTS["00713.TW"])
    parser.add_argument("--dca-00878", type=float, default=DCA_DEFAULT_AMOUNTS["00878.TW"])
    parser.add_argument("--enable-range-harvest", action="store_true")
    parser.add_argument("--range-drift-threshold", type=float, default=0.05)
    parser.add_argument("--enable-pva-sigmoid", action="store_true")
    parser.add_argument("--pva-weight", type=float, default=0.30)
    parser.add_argument("--pva-drift-threshold", type=float, default=0.05)
    parser.add_argument("--ppo-verbose", type=int, default=1)
    args = parser.parse_args()

    print("=" * 72)
    print("0050+0056+00713+00878 portfolio PPO training/backtest")
    print(f"Train:    {args.train_start} ~ {args.train_end}")
    print(f"Backtest: {args.backtest_start} ~ {args.backtest_end}")
    print(f"Steps:    {args.timesteps:,}")
    print(f"Seed:     {args.seed}")
    print(
        "Constraints: "
        f"turnover_penalty={args.turnover_penalty}, "
        f"min_rebalance_days={args.min_rebalance_days}, "
        f"min_weight={args.min_weight}, max_weight={args.max_weight}, "
        f"use_rsi_features={args.use_rsi_features}, enable_dca={args.enable_dca}, "
        f"enable_range_harvest={args.enable_range_harvest}, "
        f"enable_pva_sigmoid={args.enable_pva_sigmoid}"
    )
    print("=" * 72)

    stock_data = download_all_stocks(TICKERS, args.train_start, args.download_end)
    missing = [ticker for ticker in TICKERS if ticker not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    train_panel = _align_panel(stock_data, args.train_start, args.train_end)
    test_panel = _align_panel(stock_data, args.backtest_start, args.backtest_end)
    if len(train_panel) < 100 or len(test_panel) < 100:
        raise RuntimeError("Not enough aligned train/backtest rows")

    print(f"Loaded rows: train={len(train_panel)}, backtest={len(test_panel)}")
    print(
        "Actual ranges: "
        f"train={train_panel['date'].min().date()}~{train_panel['date'].max().date()}, "
        f"backtest={test_panel['date'].min().date()}~{test_panel['date'].max().date()}"
    )

    active_derived_features = list(ACTIVE_DERIVED_FEATURE_COLUMNS)
    if args.use_rsi_features:
        active_derived_features.extend(RSI_DERIVED_FEATURE_COLUMNS)

    env_kwargs = {
        "turnover_penalty": args.turnover_penalty,
        "min_rebalance_days": args.min_rebalance_days,
        "min_weight": args.min_weight,
        "max_weight": args.max_weight,
        "active_derived_features": active_derived_features,
        "enable_range_harvest": args.enable_range_harvest,
        "range_drift_threshold": args.range_drift_threshold,
        "enable_pva_sigmoid": args.enable_pva_sigmoid,
        "pva_weight": args.pva_weight,
        "pva_drift_threshold": args.pva_drift_threshold,
    }
    train_env = ETFPortfolioEnv(train_panel, **env_kwargs)
    model = PPO(
        "MlpPolicy",
        train_env,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=128,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        seed=args.seed,
        verbose=args.ppo_verbose,
    )
    model.learn(total_timesteps=args.timesteps)

    train_tag = args.train_start.replace("-", "") + "_" + args.train_end.replace("-", "")
    constraint_tag = (
        f"turnover{args.turnover_penalty:g}_minreb{args.min_rebalance_days}"
        f"_minw{args.min_weight:g}_maxw{args.max_weight:g}"
    )
    feature_tag = "features_v4_rsi" if args.use_rsi_features else "features_v4_reduced"
    model_path = PROJECT_ROOT / "models" / "portfolio" / (
        f"portfolio_0050_0056_00713_00878_{train_tag}_ppo_raw_dividend_"
        f"{feature_tag}_{constraint_tag}_steps{args.timesteps}"
    )
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))

    train_eval = _run_model(model, train_panel, env_kwargs)
    eval_env_kwargs = dict(env_kwargs)
    dca_monthly_amounts = {
        "0050.TW": args.dca_0050,
        "0056.TW": args.dca_0056,
        "00713.TW": args.dca_00713,
        "00878.TW": args.dca_00878,
    }
    if args.enable_dca:
        eval_env_kwargs.update(
            {
                "dca_monthly_amounts": dca_monthly_amounts,
                "dca_day": args.dca_day,
            }
        )
    result = _run_model(model, test_panel, eval_env_kwargs)
    equal_bh = _buy_and_hold(test_panel, np.array([0.25, 0.25, 0.25, 0.25], dtype=float))
    bh_0050 = _buy_and_hold(test_panel, np.array([1.0, 0.0, 0.0, 0.0], dtype=float))

    payload = {
        "tickers": TICKERS,
        "train_start": args.train_start,
        "train_end": args.train_end,
        "backtest_start": args.backtest_start,
        "backtest_end": args.backtest_end,
        "actual_train_start": str(train_panel["date"].min().date()),
        "actual_train_end": str(train_panel["date"].max().date()),
        "actual_backtest_start": str(test_panel["date"].min().date()),
        "actual_backtest_end": str(test_panel["date"].max().date()),
        "train_rows": int(len(train_panel)),
        "backtest_rows": int(len(test_panel)),
        "model_path": str(model_path),
        "seed": args.seed,
        "requested_timesteps": args.timesteps,
        "agent_type": "ppo",
        "constraints": {
            "turnover_penalty": args.turnover_penalty,
            "min_rebalance_days": args.min_rebalance_days,
            "min_weight": args.min_weight,
            "max_weight": args.max_weight,
        },
        "dca_enabled": bool(args.enable_dca),
        "dca_note": "DCA is applied only during evaluation/backtest, not during PPO training reward. DCA cash, DCA shares, PPO cash, and PPO rebalanced shares all use one shared portfolio account.",
        "dca_config": {
            "dca_day": args.dca_day,
            "monthly_amounts": dca_monthly_amounts if args.enable_dca else {},
        },
        "range_harvest_config": {
            "enabled": bool(args.enable_range_harvest),
            "range_drift_threshold": args.range_drift_threshold,
            "target_weights": {
                "0050.TW": 0.40,
                "0056.TW": 0.20,
                "00713.TW": 0.20,
                "00878.TW": 0.20,
            },
            "note": "When range-bound conditions are detected and drift exceeds the threshold, PPO target weights are overridden by range-harvest target weights for the shared portfolio.",
        },
        "pva_sigmoid_config": {
            "enabled": bool(args.enable_pva_sigmoid),
            "pva_weight": args.pva_weight,
            "pva_drift_threshold": args.pva_drift_threshold,
            "note": "When range-bound conditions are detected, PVA sigmoid target weights are blended with PPO target weights for the shared portfolio.",
        },
        "feature_config": {
            "base_features_per_ticker": FEATURE_COLUMNS,
            "available_derived_portfolio_features": DERIVED_FEATURE_COLUMNS,
            "active_derived_portfolio_features": active_derived_features,
            "rsi_features_enabled": bool(args.use_rsi_features),
            "portfolio_state_features": [
                "current_weights_4",
                "cash_weight",
                "current_drawdown",
                "days_since_rebalance_scaled",
                "relative_value_vs_equal_weight_bh",
                "relative_value_vs_0050_bh",
                "high_dividend_weight",
            ],
            "observation_dim": int(ETFPortfolioEnv(train_panel, **env_kwargs).observation_space.shape[0]),
        },
        "action_space": {
            "0": "hold current weights",
            "1": "25/25/25/25",
            "2": "100% 0050",
            "3": "50/30/10/10",
            "4": "70/10/10/10 0050 core",
            "5": "80/0/0/20 0050+00878 core",
            "6": "15/25/25/35 high-dividend tilt",
            "7": "0/40/30/30 defensive high-dividend tilt",
            "8": "100% best 6M momentum ETF",
            "9": "50/50 top-2 6M momentum ETFs",
        },
        "reward_note": "daily_return + 2.0 * excess daily return versus max(equal-weight B&H, 0050 B&H); observation includes relative momentum, market regime, and portfolio-vs-benchmark state features",
        "price_note": "raw OHLC from yfinance auto_adjust=False plus explicit dividends cashflow",
        "train_eval": train_eval,
        **result,
        "equal_weight_buy_and_hold": equal_bh,
        "buy_and_hold_0050": bh_0050,
        "excess_return_vs_equal_bh": result["rl_metrics"]["total_return"] - equal_bh["metrics"]["total_return"],
        "excess_return_vs_0050_bh": result["rl_metrics"]["total_return"] - bh_0050["metrics"]["total_return"],
    }

    output_file = PROJECT_ROOT / "results" / (
        f"training_portfolio_0050_0056_00713_00878_{train_tag}_ppo_raw_dividend_"
        f"backtest_{args.backtest_start.replace('-', '')}_{args.backtest_end.replace('-', '')}_"
        f"{constraint_tag}{'_dca' if args.enable_dca else ''}"
        f"{'_range' if args.enable_range_harvest else ''}"
        f"{'_pva' if args.enable_pva_sigmoid else ''}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print("=" * 72)
    print("Done")
    print(f"Model:  {model_path}")
    print(f"Result: {output_file}")
    print(f"Final value: {result['final_value']:,.0f}")
    if args.enable_dca:
        print(f"Total contributions: {result['total_contributions']:,.0f}")
        print(f"Net profit: {result['investment_summary']['net_profit']:,.0f}")
        print(f"Return on invested capital: {result['investment_summary']['simple_return_on_total_invested']:.2%}")
    print(f"Trades: {result['num_trades']}")
    print(f"DCA purchases: {result.get('dca_purchase_count', 0)}")
    print(f"Range harvests: {result.get('range_harvest_count', 0)}")
    print(f"PVA sigmoid rebalances: {result.get('pva_sigmoid_count', 0)}")
    print(f"Equal B&H final value: {equal_bh['final_value']:,.0f}")
    print(f"0050 B&H final value: {bh_0050['final_value']:,.0f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
