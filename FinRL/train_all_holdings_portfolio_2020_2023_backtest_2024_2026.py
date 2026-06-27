#!/usr/bin/env python3
"""Train one PPO allocator using every ticker in PORTFOLIO_HOLDINGS."""

from __future__ import annotations

import argparse
import json
import re
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

try:
    from .portfolio_config import (  # noqa: E402
        ALL_TICKERS,
        COMMISSION_RATE,
        ETF_TAX_RATE,
        MIN_COMMISSION_FEE,
        MIN_TRADE_SHARES,
        PORTFOLIO_HOLDINGS,
        TRANSACTION_TAX_RATE,
    )
    from .portfolio_data_loader import MARKET_FEATURE_COLUMNS, download_all_stocks  # noqa: E402
    from .portfolio_train_v2 import calculate_backtest_metrics  # noqa: E402
except ImportError:
    from portfolio_config import (  # noqa: E402
        ALL_TICKERS,
        COMMISSION_RATE,
        ETF_TAX_RATE,
        MIN_COMMISSION_FEE,
        MIN_TRADE_SHARES,
        PORTFOLIO_HOLDINGS,
        TRANSACTION_TAX_RATE,
    )
    from portfolio_data_loader import MARKET_FEATURE_COLUMNS, download_all_stocks  # noqa: E402
    from portfolio_train_v2 import calculate_backtest_metrics  # noqa: E402


TRAIN_START = "2020-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-15"
DOWNLOAD_END = "2026-05-22"
TIMESTEPS = 100_000
SEED = 42
BENCHMARK_TICKER = "0050.TW"

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
PER_TICKER_CONTEXT_COLUMNS = ["sector_correlation"]
SHARED_MARKET_FEATURE_COLUMNS = [
    col for col in MARKET_FEATURE_COLUMNS if col not in PER_TICKER_CONTEXT_COLUMNS
]

ACTION_LABELS = {
    0: "hold current weights",
    1: "100% 0050",
    2: "90% 0050 / 10% 00878",
    3: "80% 0050 / 20% 00878",
    4: "80% 0050 / 10% 00713 / 10% 00878",
    5: "70% 0050 / 10% 0056 / 10% 00713 / 10% 00878",
    6: "70% 0050 / 15% 00646 / 7.5% 00679B / 7.5% 00751B",
    7: "80% 0050 / 10% 00679B / 10% 00751B",
    8: "80% 0050 / 10% 00631L / 10% 00878",
    9: "70% 0050 / 20% 00631L / 10% 00878",
    10: "60% 0050 / 30% 00631L / 10% 00878",
}

DEFAULT_DCA_TOTAL_MONTHLY = 25_000.0
DEFAULT_RANGE_TARGET = {
    "0050.TW": 0.55,
    "0056.TW": 0.10,
    "00646.TW": 0.05,
    "00679B.TWO": 0.08,
    "00713.TW": 0.08,
    "00751B.TWO": 0.08,
    "00878.TW": 0.06,
}
DEFAULT_RISK_OFF_TARGET = {
    "0050.TW": 0.35,
    "00679B.TWO": 0.20,
    "00751B.TWO": 0.10,
    "00878.TW": 0.10,
}
DEFAULT_DEEP_RISK_OFF_TARGET = {
    "0050.TW": 0.20,
    "00679B.TWO": 0.15,
    "00751B.TWO": 0.10,
    "00878.TW": 0.05,
}
DEFAULT_PANIC_BETA_TARGET = {
    "0050.TW": 0.70,
    "00646.TW": 0.10,
    "00878.TW": 0.10,
    "00679B.TWO": 0.05,
    "00751B.TWO": 0.05,
}
DEFAULT_GREED_DEFENSIVE_TARGET = {
    "0056.TW": 0.20,
    "00713.TW": 0.20,
    "00878.TW": 0.20,
    "00679B.TWO": 0.20,
    "00751B.TWO": 0.20,
}

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
    "0050_sector_correlation",
    "high_dividend_sector_correlation_avg",
    "0050_vs_high_dividend_corr_gap",
    "market_stress_score",
    "market_trend_score",
    "cross_market_momentum_gap",
]
ACTIVE_DERIVED_FEATURE_COLUMNS = [
    "0050_trend_score",
    "0050_volatility_rank_252",
    "high_dividend_vs_0050_momentum_126",
    "00878_vs_0050_momentum_63",
    "0050_momentum_rank_126",
]
ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS = [
    "0050_vs_high_dividend_corr_gap",
    "market_stress_score",
    "market_trend_score",
    "cross_market_momentum_gap",
]
RSI_DERIVED_FEATURE_COLUMNS = [
    "0050_rsi_14",
    "0050_rsi_14_rank_252",
    "high_dividend_rsi_14_avg",
    "0050_rsi_minus_hd_rsi",
]


def _safe_col(panel: pd.DataFrame, ticker: str, feature: str, default: float = 0.0) -> pd.Series:
    col = f"{ticker}_{feature}"
    if col in panel.columns:
        return panel[col].astype(float)
    return pd.Series(default, index=panel.index, dtype=float)


def _shared_market_col(panel: pd.DataFrame, feature: str, default: float = 0.0) -> pd.Series:
    if feature in panel.columns:
        return panel[feature].astype(float)
    return pd.Series(default, index=panel.index, dtype=float)


def _parse_ticker_code(ticker: str) -> str:
    return ticker.split(".")[0]


def _slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def _weights_for_existing(
    tickers: list[str],
    weights_by_ticker: dict[str, float],
    target_total: float = 1.0,
) -> np.ndarray:
    weights = np.array([weights_by_ticker.get(ticker, 0.0) for ticker in tickers], dtype=float)
    target_total = float(np.clip(target_total, 0.0, 1.0))
    total = float(weights.sum())
    if total <= 0.0:
        if len(tickers) == 0 or target_total <= 0.0:
            return np.zeros(len(tickers), dtype=float)
        return np.ones(len(tickers), dtype=float) / len(tickers) * target_total
    return weights / total * target_total


def _actual_holdings_weights(tickers: list[str], first_prices: np.ndarray) -> np.ndarray:
    values = []
    for ticker, price in zip(tickers, first_prices):
        shares = float(PORTFOLIO_HOLDINGS.get(ticker, {}).get("shares", 0))
        values.append(shares * float(price))
    values = np.array(values, dtype=float)
    total = float(values.sum())
    if total <= 0.0:
        return np.ones(len(tickers), dtype=float) / max(len(tickers), 1)
    return values / total


def _commission_fee(trade_value: float, commission_rate: float) -> float:
    trade_value = float(trade_value)
    if trade_value <= 0.0:
        return 0.0
    return max(trade_value * float(commission_rate), float(MIN_COMMISSION_FEE))


def _buy_total_cost(shares: float, price: float, commission_rate: float) -> tuple[float, float, float]:
    gross = float(shares) * float(price)
    fee = _commission_fee(gross, commission_rate)
    return gross, fee, gross + fee


def _sell_net_proceeds(shares: float, price: float, commission_rate: float, tax_rate: float) -> tuple[float, float, float, float]:
    gross = float(shares) * float(price)
    fee = _commission_fee(gross, commission_rate)
    tax = gross * float(tax_rate)
    return gross, fee, tax, gross - fee - tax


def _floor_to_trade_step(shares: float, min_trade_shares: float = MIN_TRADE_SHARES) -> float:
    shares = float(shares)
    step = float(min_trade_shares)
    if shares < step:
        return 0.0
    return float(np.floor(shares / step) * step)


def _quantize_buy_shares(desired_shares: float, min_trade_shares: float = MIN_TRADE_SHARES) -> float:
    return _floor_to_trade_step(desired_shares, min_trade_shares)


def _quantize_sell_shares(
    desired_shares: float,
    available_shares: float,
    min_trade_shares: float = MIN_TRADE_SHARES,
) -> float:
    desired = float(min(desired_shares, available_shares))
    available = float(available_shares)
    step = float(min_trade_shares)
    if desired <= 0.0 or available <= 0.0:
        return 0.0
    rounded = _floor_to_trade_step(desired, step)
    if rounded > 0.0:
        remaining = available - rounded
        # Allow one final odd-lot cleanup when the rebalance wants to exit the position.
        if desired >= available - 1e-9 and 0.0 < remaining < step:
            return available
        return min(rounded, available)
    if desired >= available - 1e-9 and available < step:
        return available
    return 0.0


def _max_affordable_buy_shares(cash: float, price: float, commission_rate: float) -> float:
    cash = float(cash)
    price = float(price)
    if cash <= float(MIN_COMMISSION_FEE) or price <= 0.0:
        return 0.0
    approx = _floor_to_trade_step(cash / (price * (1.0 + commission_rate)))
    if approx <= 0.0:
        approx = _floor_to_trade_step((cash - float(MIN_COMMISSION_FEE)) / price)
    qty = approx
    while qty >= float(MIN_TRADE_SHARES):
        _, _, total = _buy_total_cost(qty, price, commission_rate)
        if total <= cash + 1e-9:
            return qty
        qty -= float(MIN_TRADE_SHARES)
    return 0.0


def _allocate_cash_to_weights(
    cash: float,
    weights: np.ndarray,
    prices: np.ndarray,
    commission_rate: float,
) -> tuple[np.ndarray, float, float]:
    shares = np.zeros(len(prices), dtype=float)
    fees = 0.0
    cash_remaining = float(cash)
    if cash_remaining <= 0.0 or len(prices) == 0:
        return shares, cash_remaining, fees

    weights = np.clip(np.asarray(weights, dtype=float), 0.0, None)
    total_weight = float(weights.sum())
    if total_weight <= 0.0:
        return shares, cash_remaining, fees
    weights = weights / total_weight
    target_values = cash_remaining * weights

    for idx in np.argsort(-target_values):
        desired_shares = _quantize_buy_shares(target_values[idx] / prices[idx])
        buy_shares = min(desired_shares, _max_affordable_buy_shares(cash_remaining, prices[idx], commission_rate))
        if buy_shares <= 0.0:
            continue
        _, fee, total = _buy_total_cost(buy_shares, prices[idx], commission_rate)
        cash_remaining -= total
        fees += fee
        shares[idx] += buy_shares
    return shares, cash_remaining, fees


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


def _high_dividend_tickers(tickers: list[str]) -> list[str]:
    preferred = ["0056.TW", "00713.TW", "00878.TW"]
    return [ticker for ticker in preferred if ticker in tickers]


def _anchor_ticker(tickers: list[str]) -> str:
    return "0050.TW" if "0050.TW" in tickers else tickers[0]


def _add_portfolio_features(panel: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    panel = panel.copy()
    anchor = _anchor_ticker(tickers)
    high_dividend = _high_dividend_tickers(tickers)

    ma120 = _safe_col(panel, anchor, "close_ma120_ratio", 0.0)
    ma240 = _safe_col(panel, anchor, "close_ma240_ratio", 0.0)
    ma60_240 = _safe_col(panel, anchor, "ma60_ma240_ratio", 0.0)
    mdd63 = _safe_col(panel, anchor, "rolling_mdd_63", 0.0)
    panel["0050_above_ma120"] = (ma120 > 0.0).astype(float)
    panel["0050_above_ma240"] = (ma240 > 0.0).astype(float)
    panel["0050_ma60_above_ma240"] = (ma60_240 > 0.0).astype(float)
    panel["0050_drawdown_risk"] = mdd63.clip(upper=0.0).abs()
    panel["0050_trend_score"] = (
        panel["0050_above_ma120"] + panel["0050_above_ma240"] + panel["0050_ma60_above_ma240"]
    ) / 3.0

    close_anchor = _safe_col(panel, anchor, "close", np.nan)
    ret_anchor = close_anchor.pct_change()
    vol63 = ret_anchor.rolling(63, min_periods=20).std(ddof=1).fillna(0.0) * np.sqrt(252)
    panel["0050_volatility_63"] = vol63
    panel["0050_volatility_rank_252"] = vol63.rolling(252, min_periods=63).rank(pct=True).fillna(0.5)

    if high_dividend:
        for lookback in (63, 126):
            hd_momentum = pd.concat(
                [_safe_col(panel, ticker, f"momentum_{lookback}", 0.0) for ticker in high_dividend],
                axis=1,
            )
            panel[f"high_dividend_momentum_avg_{lookback}"] = hd_momentum.mean(axis=1)
            panel[f"high_dividend_vs_0050_momentum_{lookback}"] = (
                panel[f"high_dividend_momentum_avg_{lookback}"] - _safe_col(panel, anchor, f"momentum_{lookback}", 0.0)
            )
        hd_sector_corr = pd.concat(
            [_safe_col(panel, ticker, "sector_correlation", 0.0) for ticker in high_dividend],
            axis=1,
        )
        panel["high_dividend_sector_correlation_avg"] = hd_sector_corr.mean(axis=1)
        high_dividend_rsi = pd.concat(
            [_calculate_rsi(_safe_col(panel, ticker, "close", np.nan), 14) for ticker in high_dividend],
            axis=1,
        )
        panel["high_dividend_rsi_14_avg"] = high_dividend_rsi.mean(axis=1)
    else:
        panel["high_dividend_momentum_avg_63"] = 0.0
        panel["high_dividend_momentum_avg_126"] = 0.0
        panel["high_dividend_vs_0050_momentum_63"] = 0.0
        panel["high_dividend_vs_0050_momentum_126"] = 0.0
        panel["high_dividend_sector_correlation_avg"] = 0.0
        panel["high_dividend_rsi_14_avg"] = 0.5

    panel["00878_vs_0050_momentum_63"] = _safe_col(panel, "00878.TW", "momentum_63") - _safe_col(panel, anchor, "momentum_63")
    panel["00713_vs_0050_momentum_63"] = _safe_col(panel, "00713.TW", "momentum_63") - _safe_col(panel, anchor, "momentum_63")
    panel["0056_vs_0050_momentum_63"] = _safe_col(panel, "0056.TW", "momentum_63") - _safe_col(panel, anchor, "momentum_63")
    panel["00878_vs_0056_momentum_126"] = _safe_col(panel, "00878.TW", "momentum_126") - _safe_col(panel, "0056.TW", "momentum_126")
    panel["0050_sector_correlation"] = _safe_col(panel, anchor, "sector_correlation")
    panel["0050_vs_high_dividend_corr_gap"] = (
        panel["0050_sector_correlation"] - panel["high_dividend_sector_correlation_avg"]
    )

    rsi_anchor = _calculate_rsi(_safe_col(panel, anchor, "close", np.nan), 14)
    panel["0050_rsi_14"] = rsi_anchor
    panel["0050_rsi_14_rank_252"] = rsi_anchor.rolling(252, min_periods=63).rank(pct=True).fillna(0.5)
    panel["0050_rsi_minus_hd_rsi"] = rsi_anchor - panel["high_dividend_rsi_14_avg"]

    pva_p = _safe_col(panel, anchor, "close_ma120_ratio", 0.0)
    pva_v = _safe_col(panel, anchor, "momentum_63", 0.0)
    pva_a = pva_v - pva_v.shift(20).fillna(pva_v)
    panel["0050_pva_p"] = pva_p
    panel["0050_pva_v"] = pva_v
    panel["0050_pva_a"] = pva_a
    panel["0050_pva_p_z"] = _rolling_zscore(pva_p)
    panel["0050_pva_v_z"] = _rolling_zscore(pva_v)
    panel["0050_pva_a_z"] = _rolling_zscore(pva_a)
    panic = (panel["0050_pva_a_z"] < -2.0) | (panel["0050_pva_v_z"] < -2.0)
    greed = (panel["0050_pva_v_z"] > 1.0) & (panel["0050_pva_a_z"] > 0.0)
    panel["0050_sjm_state_code"] = 0.0
    panel.loc[greed, "0050_sjm_state_code"] = 1.0
    panel.loc[panic, "0050_sjm_state_code"] = -1.0

    twse_return = _shared_market_col(panel, "twse_index_return")
    twse_volume_change = _shared_market_col(panel, "twse_index_volume_change")
    market_volatility = _shared_market_col(panel, "market_volatility")
    dji_return_1d = _shared_market_col(panel, "dji_return_1d_lag1")
    dji_return_5d = _shared_market_col(panel, "dji_return_5d_lag1")
    dji_volatility = _shared_market_col(panel, "dji_volatility_20d_lag1")
    dji_ma60_ratio = _shared_market_col(panel, "dji_ma60_ratio_lag1")
    dji_drawdown = _shared_market_col(panel, "dji_drawdown_60d_lag1")
    twse_downside = (-twse_return).clip(lower=0.0)
    global_downside = (-dji_return_5d).clip(lower=0.0)
    twse_volume_shock = twse_volume_change.abs().clip(0.0, 2.0)
    global_drawdown_pressure = (-dji_drawdown).clip(lower=0.0) * 3.0
    panel["market_stress_score"] = (
        0.35 * twse_downside
        + 0.20 * market_volatility.clip(lower=0.0)
        + 0.20 * global_downside
        + 0.15 * global_drawdown_pressure
        + 0.10 * twse_volume_shock
    ).clip(0.0, 3.0)
    panel["market_trend_score"] = (
        0.45 * twse_return
        + 0.25 * dji_return_5d
        + 0.20 * (dji_ma60_ratio * 2.0)
        - 0.15 * market_volatility.clip(lower=0.0)
        - 0.10 * dji_volatility.clip(lower=0.0)
    ).clip(-3.0, 3.0)
    panel["cross_market_momentum_gap"] = (twse_return - dji_return_1d).clip(-3.0, 3.0)

    for lookback in (63, 126, 252):
        momentum = pd.concat(
            [_safe_col(panel, ticker, f"momentum_{lookback}", 0.0).rename(ticker) for ticker in tickers],
            axis=1,
        )
        ranks = _rank_desc(momentum)
        divisor = max(len(tickers) - 1, 1)
        panel[f"0050_momentum_rank_{lookback}"] = (ranks[anchor] - 1.0) / divisor
        if lookback == 126:
            focus_ticker = "00878.TW" if "00878.TW" in ranks.columns else anchor
            panel["00878_momentum_rank_126"] = (ranks[focus_ticker] - 1.0) / divisor
            sorted_momentum = np.sort(momentum.to_numpy(dtype=float), axis=1)[:, ::-1]
            panel["best_momentum_spread_126"] = sorted_momentum[:, 0] - sorted_momentum[:, -1]
            panel["top2_momentum_avg_126"] = sorted_momentum[:, : min(2, len(tickers))].mean(axis=1)
            panel["momentum_dispersion_126"] = momentum.std(axis=1)

    existing_cols = [col for col in DERIVED_FEATURE_COLUMNS if col in panel.columns]
    panel[existing_cols] = panel[existing_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    for col in DERIVED_FEATURE_COLUMNS:
        if col not in panel.columns:
            panel[col] = 0.0
    return panel


def _align_panel(stock_data: dict[str, pd.DataFrame], tickers: list[str], start: str, end: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        df = _slice_by_date(stock_data[ticker], start, end)
        cols = ["date", "open", "close"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        cols.extend([c for c in PER_TICKER_CONTEXT_COLUMNS if c in df.columns])
        if "dividends" in df.columns:
            cols.append("dividends")
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")

    reference_df = _slice_by_date(stock_data[tickers[0]], start, end)
    shared_market_cols = ["date"] + [c for c in SHARED_MARKET_FEATURE_COLUMNS if c in reference_df.columns]
    if len(shared_market_cols) > 1:
        panel = panel.merge(reference_df[shared_market_cols].copy(), on="date", how="left")

    panel = panel.sort_values("date").reset_index(drop=True)
    panel = panel.ffill().bfill().fillna(0.0)
    return _add_portfolio_features(panel, tickers)


def _prices(panel: pd.DataFrame, tickers: list[str]) -> np.ndarray:
    return panel[[f"{ticker}_close" for ticker in tickers]].to_numpy(dtype=float)


def _open_prices(panel: pd.DataFrame, tickers: list[str]) -> np.ndarray:
    return panel[[f"{ticker}_open" for ticker in tickers]].to_numpy(dtype=float)


def _dividends(panel: pd.DataFrame, tickers: list[str]) -> np.ndarray:
    cols = []
    for ticker in tickers:
        col = f"{ticker}_dividends"
        if col not in panel.columns:
            panel[col] = 0.0
        cols.append(col)
    return panel[cols].fillna(0.0).to_numpy(dtype=float)


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
    tickers: list[str],
    weight_history: list[list[float]],
    rebalance_indices: list[int],
    threshold: float = 0.01,
) -> dict:
    dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
    weights = np.asarray(weight_history, dtype=float)
    if len(weights) == 0:
        weights = np.zeros((len(panel), len(tickers)), dtype=float)
    weights = weights[: len(panel)]

    clean_rebalances = sorted({int(i) for i in rebalance_indices if 0 <= int(i) < len(panel)})
    intervals = np.diff(clean_rebalances).astype(int).tolist() if len(clean_rebalances) >= 2 else []

    asset_stats = {}
    for idx, ticker in enumerate(tickers):
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


def get_active_derived_features(
    use_rsi_features: bool = False,
    use_market_regime_features: bool = True,
) -> list[str]:
    features = list(ACTIVE_DERIVED_FEATURE_COLUMNS)
    if use_market_regime_features:
        features.extend(ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS)
    if use_rsi_features:
        features.extend(RSI_DERIVED_FEATURE_COLUMNS)
    return features


def build_env_kwargs(
    *,
    turnover_penalty: float = 0.001,
    equal_benchmark_weight: float = 1.5,
    actual_benchmark_weight: float = 1.0,
    underperform_0050_weight: float = 0.8,
    drawdown_penalty_weight: float = 0.5,
    benchmark_shortfall_penalty_weight: float = 0.0,
    benchmark_shortfall_penalty_cap: float = 0.15,
    benchmark_shortfall_stress_scale: float = 0.50,
    stress_budget_caution_invested_cap: float = 0.92,
    stress_budget_caution_0050_cap: float = 0.55,
    stress_budget_risk_off_invested_cap: float = 0.82,
    stress_budget_risk_off_0050_cap: float = 0.45,
    stress_budget_deep_risk_off_invested_cap: float = 0.65,
    stress_budget_deep_risk_off_0050_cap: float = 0.30,
    min_rebalance_days: int = 20,
    stress_rebalance_cooldown_days: int | None = 0,
    stress_confirm_days: int = 3,
    use_rsi_features: bool = False,
    use_market_regime_features: bool = True,
    enable_range_harvest: bool = False,
    range_drift_threshold: float = 0.05,
    enable_pva_sigmoid: bool = False,
    pva_weight: float = 0.30,
    pva_drift_threshold: float = 0.05,
    leverage_block_trend_threshold: float = -0.10,
    leverage_positive_trend_threshold: float = 0.05,
    leverage_strong_trend_threshold: float = 0.20,
    leverage_positive_stress_cap: float = 0.20,
    leverage_strong_stress_cap: float = 0.15,
    daily_open_only: bool = False,
    monday_open_only: bool = False,
    dca_monthly_amounts: dict[str, float] | None = None,
    dca_day: int = 26,
) -> dict:
    env_kwargs = {
        "turnover_penalty": float(turnover_penalty),
        "equal_benchmark_weight": float(equal_benchmark_weight),
        "actual_benchmark_weight": float(actual_benchmark_weight),
        "underperform_0050_weight": float(underperform_0050_weight),
        "drawdown_penalty_weight": float(drawdown_penalty_weight),
        "benchmark_shortfall_penalty_weight": float(benchmark_shortfall_penalty_weight),
        "benchmark_shortfall_penalty_cap": float(benchmark_shortfall_penalty_cap),
        "benchmark_shortfall_stress_scale": float(benchmark_shortfall_stress_scale),
        "stress_budget_caution_invested_cap": float(stress_budget_caution_invested_cap),
        "stress_budget_caution_0050_cap": float(stress_budget_caution_0050_cap),
        "stress_budget_risk_off_invested_cap": float(stress_budget_risk_off_invested_cap),
        "stress_budget_risk_off_0050_cap": float(stress_budget_risk_off_0050_cap),
        "stress_budget_deep_risk_off_invested_cap": float(stress_budget_deep_risk_off_invested_cap),
        "stress_budget_deep_risk_off_0050_cap": float(stress_budget_deep_risk_off_0050_cap),
        "min_rebalance_days": int(min_rebalance_days),
        "stress_rebalance_cooldown_days": (
            None if stress_rebalance_cooldown_days is None else int(stress_rebalance_cooldown_days)
        ),
        "stress_confirm_days": int(stress_confirm_days),
        "active_derived_features": get_active_derived_features(
            use_rsi_features,
            use_market_regime_features,
        ),
        "enable_range_harvest": bool(enable_range_harvest),
        "range_drift_threshold": float(range_drift_threshold),
        "enable_pva_sigmoid": bool(enable_pva_sigmoid),
        "pva_weight": float(pva_weight),
        "pva_drift_threshold": float(pva_drift_threshold),
        "leverage_block_trend_threshold": float(leverage_block_trend_threshold),
        "leverage_positive_trend_threshold": float(leverage_positive_trend_threshold),
        "leverage_strong_trend_threshold": float(leverage_strong_trend_threshold),
        "leverage_positive_stress_cap": float(leverage_positive_stress_cap),
        "leverage_strong_stress_cap": float(leverage_strong_stress_cap),
        "daily_open_only": bool(daily_open_only),
        "monday_open_only": bool(monday_open_only),
    }
    if dca_monthly_amounts:
        env_kwargs.update(
            {
                "dca_monthly_amounts": {ticker: float(amount) for ticker, amount in dca_monthly_amounts.items()},
                "dca_day": int(dca_day),
            }
        )
    return env_kwargs


class AllHoldingsPortfolioEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        tickers: list[str],
        initial_cash: float = 1_000_000,
        commission_rate: float = COMMISSION_RATE,
        turnover_penalty: float = 0.001,
        equal_benchmark_weight: float = 1.5,
        actual_benchmark_weight: float = 1.0,
        underperform_0050_weight: float = 0.8,
        drawdown_penalty_weight: float = 0.5,
        benchmark_shortfall_penalty_weight: float = 0.0,
        benchmark_shortfall_penalty_cap: float = 0.15,
        benchmark_shortfall_stress_scale: float = 0.50,
        stress_budget_caution_invested_cap: float = 0.92,
        stress_budget_caution_0050_cap: float = 0.55,
        stress_budget_risk_off_invested_cap: float = 0.82,
        stress_budget_risk_off_0050_cap: float = 0.45,
        stress_budget_deep_risk_off_invested_cap: float = 0.65,
        stress_budget_deep_risk_off_0050_cap: float = 0.30,
        min_rebalance_days: int = 20,
        stress_rebalance_cooldown_days: int | None = 0,
        stress_confirm_days: int = 3,
        active_derived_features: list[str] | None = None,
        dca_monthly_amounts: dict[str, float] | None = None,
        dca_day: int = 26,
        enable_range_harvest: bool = False,
        range_drift_threshold: float = 0.05,
        enable_pva_sigmoid: bool = False,
        pva_weight: float = 0.30,
        pva_drift_threshold: float = 0.05,
        leverage_block_trend_threshold: float = -0.10,
        leverage_positive_trend_threshold: float = 0.05,
        leverage_strong_trend_threshold: float = 0.20,
        leverage_positive_stress_cap: float = 0.20,
        leverage_strong_stress_cap: float = 0.15,
        daily_open_only: bool = False,
        monday_open_only: bool = False,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.tickers = list(tickers)
        self.anchor = _anchor_ticker(self.tickers)
        self.high_dividend_tickers = _high_dividend_tickers(self.tickers)
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.equal_benchmark_weight = float(equal_benchmark_weight)
        self.actual_benchmark_weight = float(actual_benchmark_weight)
        self.underperform_0050_weight = float(underperform_0050_weight)
        self.drawdown_penalty_weight = float(drawdown_penalty_weight)
        self.benchmark_shortfall_penalty_weight = max(float(benchmark_shortfall_penalty_weight), 0.0)
        self.benchmark_shortfall_penalty_cap = max(float(benchmark_shortfall_penalty_cap), 0.0)
        self.benchmark_shortfall_stress_scale = max(float(benchmark_shortfall_stress_scale), 0.0)
        self.stress_budget_caution_invested_cap = float(np.clip(stress_budget_caution_invested_cap, 0.0, 1.0))
        self.stress_budget_caution_0050_cap = float(np.clip(stress_budget_caution_0050_cap, 0.0, 1.0))
        self.stress_budget_risk_off_invested_cap = float(np.clip(stress_budget_risk_off_invested_cap, 0.0, 1.0))
        self.stress_budget_risk_off_0050_cap = float(np.clip(stress_budget_risk_off_0050_cap, 0.0, 1.0))
        self.stress_budget_deep_risk_off_invested_cap = float(
            np.clip(stress_budget_deep_risk_off_invested_cap, 0.0, 1.0)
        )
        self.stress_budget_deep_risk_off_0050_cap = float(np.clip(stress_budget_deep_risk_off_0050_cap, 0.0, 1.0))
        self.min_rebalance_days = int(min_rebalance_days)
        self.stress_rebalance_cooldown_days = (
            self.min_rebalance_days
            if stress_rebalance_cooldown_days is None
            else max(int(stress_rebalance_cooldown_days), 0)
        )
        self.stress_confirm_days = max(int(stress_confirm_days), 1)
        self.active_derived_features = active_derived_features or ACTIVE_DERIVED_FEATURE_COLUMNS
        self.dca_monthly_amounts = dca_monthly_amounts or {}
        self.dca_amount_array = np.array(
            [float(self.dca_monthly_amounts.get(ticker, 0.0)) for ticker in self.tickers],
            dtype=float,
        )
        self.dca_day = int(dca_day)
        self.enable_range_harvest = bool(enable_range_harvest)
        self.range_drift_threshold = float(range_drift_threshold)
        self.enable_pva_sigmoid = bool(enable_pva_sigmoid)
        self.pva_weight = float(pva_weight)
        self.pva_drift_threshold = float(pva_drift_threshold)
        self.leverage_block_trend_threshold = float(leverage_block_trend_threshold)
        self.leverage_positive_trend_threshold = float(leverage_positive_trend_threshold)
        self.leverage_strong_trend_threshold = float(leverage_strong_trend_threshold)
        self.leverage_positive_stress_cap = float(leverage_positive_stress_cap)
        self.leverage_strong_stress_cap = float(leverage_strong_stress_cap)
        self.daily_open_only = bool(daily_open_only)
        self.monday_open_only = bool(monday_open_only)
        if self.daily_open_only and self.monday_open_only:
            raise ValueError("daily_open_only and monday_open_only cannot both be enabled")
        self.open_execution = self.daily_open_only or self.monday_open_only

        self.price_array = _prices(self.panel, self.tickers)
        self.open_price_array = _open_prices(self.panel, self.tickers)
        self.dividend_array = _dividends(self.panel, self.tickers)
        self.tax_rates = np.array(
            [TRANSACTION_TAX_RATE if ticker == "2884.TW" else ETF_TAX_RATE for ticker in self.tickers],
            dtype=float,
        )
        self.actual_weights = _actual_holdings_weights(self.tickers, self.price_array[0])
        self.equal_bh_curve = self._benchmark_curve(np.ones(len(self.tickers)) / len(self.tickers))
        self.actual_bh_curve = self._benchmark_curve(self.actual_weights)
        self.bh_0050_curve = self._benchmark_curve(_weights_for_existing(self.tickers, {BENCHMARK_TICKER: 1.0}))
        self.range_target_weights = self._named_target(DEFAULT_RANGE_TARGET)
        self.risk_off_target_weights = self._named_target(DEFAULT_RISK_OFF_TARGET, target_total=0.75)
        self.deep_risk_off_target_weights = self._named_target(DEFAULT_DEEP_RISK_OFF_TARGET, target_total=0.50)
        self.dca_schedule = self._build_dca_schedule()
        self.start_step_idx = 1 if self.open_execution and len(self.panel) > 1 else 0

        self.feature_cols = []
        for ticker in self.tickers:
            self.feature_cols.extend([f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns])
        self.feature_cols.extend([c for c in self.active_derived_features if c in self.panel.columns])

        obs_dim = len(self.feature_cols) + len(self.tickers) + 6
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(len(ACTION_LABELS))
        self.reset()

    def _named_target(self, mapping: dict[str, float], target_total: float = 1.0) -> np.ndarray:
        return _weights_for_existing(self.tickers, mapping, target_total=target_total)

    @staticmethod
    def _cash_weight_from_asset_weights(weights: np.ndarray) -> float:
        return float(max(0.0, 1.0 - float(np.asarray(weights, dtype=float).sum())))

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _is_trade_day(self, idx: int) -> bool:
        if not self.monday_open_only:
            return True
        return pd.Timestamp(self.panel.iloc[idx]["date"]).weekday() == 0

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = np.zeros(len(self.tickers), dtype=float)
        cash = float(self.initial_cash)
        invested = not self.open_execution
        if invested:
            shares, cash, _ = _allocate_cash_to_weights(
                self.initial_cash,
                weights,
                self.price_array[0],
                self.commission_rate,
            )
        curve = []
        for idx, prices in enumerate(self.price_array):
            if self.open_execution and not invested and self._is_trade_day(idx):
                shares, cash, _ = _allocate_cash_to_weights(
                    cash,
                    weights,
                    self.open_price_array[idx],
                    self.commission_rate,
                )
                invested = True
            if idx > 0 and invested:
                cash += float(np.dot(shares, self.dividend_array[idx]))
            curve.append(float(cash + np.dot(shares, prices)))
        return np.array(curve, dtype=float)

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
        if self.monday_open_only and current_date.weekday() != 0:
            return 0.0
        due_items = [
            item
            for item in self.dca_schedule
            if item["month"] not in self.dca_executed_months and current_date >= item["scheduled_date"]
        ]
        if not due_items:
            return 0.0

        fees = 0.0
        for item in due_items:
            purchases = {}
            self.dca_executed_months.add(item["month"])
            for i, amount in enumerate(self.dca_amount_array):
                if amount <= 0:
                    continue
                self.cash += amount
                self.total_contributions += amount
                desired_buy_shares = _quantize_buy_shares(max(amount - float(MIN_COMMISSION_FEE), 0.0) / prices[i])
                max_buy_shares = _max_affordable_buy_shares(self.cash, prices[i], self.commission_rate)
                buy_shares = min(desired_buy_shares, max_buy_shares)
                buy_value = 0.0
                fee = 0.0
                if buy_shares > 0.0:
                    buy_value, fee, total_cost = _buy_total_cost(buy_shares, prices[i], self.commission_rate)
                    self.cash -= total_cost
                    self.shares[i] += buy_shares
                    fees += fee
                purchases[self.tickers[i]] = {
                    "cash_contribution": float(amount),
                    "buy_value": float(buy_value),
                    "fee": float(fee),
                    "price": float(prices[i]),
                    "shares_bought": float(buy_shares),
                }
            self.dca_purchase_history.append(
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
        self.dca_purchase_count += len(due_items)
        return float(fees)

    def _is_range_bound(self, idx: int) -> bool:
        row = self.panel.iloc[idx]
        near_ma120 = abs(float(row.get(f"{self.anchor}_close_ma120_ratio", 0.0))) <= 0.08
        near_ma240 = abs(float(row.get(f"{self.anchor}_close_ma240_ratio", 0.0))) <= 0.10
        muted_momentum = abs(float(row.get(f"{self.anchor}_momentum_126", 0.0))) <= 0.12
        volatility_ok = float(row.get("0050_volatility_rank_252", 0.5)) <= 0.65
        drawdown_ok = float(row.get("0050_drawdown_risk", 0.0)) <= 0.15
        dispersion_ok = abs(float(row.get("momentum_dispersion_126", 0.0))) <= 0.12
        return bool((near_ma120 or near_ma240) and muted_momentum and volatility_ok and drawdown_ok and dispersion_ok)

    def _sjm_state(self, idx: int) -> tuple[str, dict]:
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
        for ticker in self.tickers:
            p = float(self.panel.iloc[idx].get(f"{ticker}_close_ma120_ratio", 0.0))
            v = float(self.panel.iloc[idx].get(f"{ticker}_momentum_63", 0.0))
            v_prev = float(self.panel.iloc[max(idx - 20, 0)].get(f"{ticker}_momentum_63", 0.0))
            a = v - v_prev
            long_trend = float(self.panel.iloc[idx].get(f"{ticker}_close_ma240_ratio", 0.0))

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

        raw_weights = _weights_for_existing(self.tickers, dict(zip(self.tickers, scores)))
        policy = "sigmoid"
        if sjm_state == "M":
            weights = 0.70 * self._named_target(DEFAULT_PANIC_BETA_TARGET) + 0.30 * raw_weights
            policy = "panic_beta_rebound"
        elif sjm_state == "J":
            weights = 0.65 * self._named_target(DEFAULT_GREED_DEFENSIVE_TARGET) + 0.35 * raw_weights
            policy = "greed_defensive"
        else:
            weights = raw_weights
        weights = weights / max(float(weights.sum()), 1e-12)
        return weights, {
            "sjm": sjm_details,
            "assets": details,
            "policy": policy,
            "raw_pva_weights": {ticker: float(w) for ticker, w in zip(self.tickers, raw_weights)},
        }

    def _pva_overlay_allowed(self, idx: int) -> tuple[bool, str, dict]:
        sjm_state, sjm_details = self._sjm_state(idx)
        if sjm_state == "M":
            return True, sjm_state, sjm_details
        return False, sjm_state, sjm_details

    def _range_harvest_due(self, idx: int) -> tuple[bool, float]:
        if not self.enable_range_harvest or not self._is_range_bound(idx):
            return False, 0.0
        drift = float(np.abs(self.weights - self.range_target_weights).sum())
        return drift >= self.range_drift_threshold, drift

    def _market_stress_snapshot(self, idx: int) -> dict:
        row = self.panel.iloc[idx]
        stress_score = float(row.get("market_stress_score", 0.0))
        trend_score = float(row.get("market_trend_score", 0.0))
        cross_market_gap = float(row.get("cross_market_momentum_gap", 0.0))
        if stress_score >= 0.60 or (stress_score >= 0.45 and trend_score <= -0.25):
            level = "deep_risk_off"
        elif stress_score >= 0.35 or (stress_score >= 0.20 and trend_score < -0.10) or trend_score <= -0.35:
            level = "risk_off"
        else:
            level = "normal"
        return {
            "score": stress_score,
            "trend_score": trend_score,
            "cross_market_gap": cross_market_gap,
            "level": level,
        }

    def _stress_confirmation_streak(self, idx: int, level: str) -> int:
        streak = 0
        accepted = {"deep_risk_off"} if level == "deep_risk_off" else {"risk_off", "deep_risk_off"}
        for pos in range(idx, -1, -1):
            snapshot = self._market_stress_snapshot(pos)
            if snapshot["level"] not in accepted:
                break
            streak += 1
        return streak

    def _stress_guardrail_target(
        self,
        idx: int,
        current_weights: np.ndarray,
        stress_snapshot: dict,
    ) -> tuple[np.ndarray | None, dict]:
        level = str(stress_snapshot["level"])
        current_cash_weight = self._cash_weight_from_asset_weights(current_weights)
        if level == "normal":
            return None, {
                "applied": False,
                "reason": "normal_market",
                "current_cash_weight": current_cash_weight,
            }

        target_weights = self.risk_off_target_weights.copy() if level == "risk_off" else self.deep_risk_off_target_weights.copy()
        target_cash_weight = self._cash_weight_from_asset_weights(target_weights)
        confirm_streak = self._stress_confirmation_streak(idx, level)
        if confirm_streak < self.stress_confirm_days:
            return None, {
                "applied": False,
                "reason": f"stress_wait_confirm_{confirm_streak}d",
                "level": level,
                "confirm_streak": int(confirm_streak),
                "required_confirm_days": int(self.stress_confirm_days),
                "current_cash_weight": current_cash_weight,
                "target_cash_weight": target_cash_weight,
            }
        if current_cash_weight >= target_cash_weight - 1e-9:
            return None, {
                "applied": False,
                "reason": "stress_cash_already_sufficient",
                "level": level,
                "confirm_streak": int(confirm_streak),
                "required_confirm_days": int(self.stress_confirm_days),
                "current_cash_weight": current_cash_weight,
                "target_cash_weight": target_cash_weight,
            }
        return target_weights, {
            "applied": True,
            "reason": "market_stress_deep_risk_off" if level == "deep_risk_off" else "market_stress_cash_defense",
            "level": level,
            "confirm_streak": int(confirm_streak),
            "required_confirm_days": int(self.stress_confirm_days),
            "current_cash_weight": current_cash_weight,
            "target_cash_weight": target_cash_weight,
        }

    def _stress_risk_budget_profile(self, idx: int, stress_snapshot: dict) -> dict:
        score = float(stress_snapshot.get("score", 0.0))
        trend_score = float(stress_snapshot.get("trend_score", 0.0))
        level = str(stress_snapshot.get("level", "normal"))
        row = self.panel.iloc[idx]
        local_trend_score = float(row.get("0050_trend_score", 1.0))
        drawdown_risk = float(row.get("0050_drawdown_risk", 0.0))
        if level == "deep_risk_off":
            return {
                "budget_level": "deep_risk_off",
                "invested_cap": self.stress_budget_deep_risk_off_invested_cap,
                "core_0050_cap": self.stress_budget_deep_risk_off_0050_cap,
            }
        if level == "risk_off":
            return {
                "budget_level": "risk_off",
                "invested_cap": self.stress_budget_risk_off_invested_cap,
                "core_0050_cap": self.stress_budget_risk_off_0050_cap,
            }
        caution_shared_stress = score >= 0.18 and trend_score <= 0.0
        caution_local_weakness = local_trend_score <= (1.0 / 3.0)
        caution_drawdown = drawdown_risk >= 0.08 and trend_score <= 0.05
        if (caution_shared_stress and caution_local_weakness) or caution_drawdown:
            return {
                "budget_level": "caution",
                "invested_cap": self.stress_budget_caution_invested_cap,
                "core_0050_cap": self.stress_budget_caution_0050_cap,
            }
        return {
            "budget_level": "normal",
            "invested_cap": 1.0,
            "core_0050_cap": 1.0,
        }

    def _apply_stress_risk_budget(self, idx: int, weights: np.ndarray, stress_snapshot: dict) -> tuple[np.ndarray, dict]:
        profile = self._stress_risk_budget_profile(idx, stress_snapshot)
        budget_level = str(profile["budget_level"])
        original = np.clip(np.asarray(weights, dtype=float), 0.0, None)
        adjusted = original.copy()
        original_total = float(original.sum())
        original_0050 = float(original[self.tickers.index(BENCHMARK_TICKER)]) if BENCHMARK_TICKER in self.tickers else 0.0
        invested_cap = float(np.clip(profile["invested_cap"], 0.0, 1.0))
        core_0050_cap = float(np.clip(profile["core_0050_cap"], 0.0, 1.0))

        if budget_level == "normal" or len(adjusted) == 0:
            return adjusted, {
                "applied": False,
                "budget_level": budget_level,
                "invested_cap": invested_cap,
                "core_0050_cap": core_0050_cap,
                "reason": "normal_market_budget",
                "pre_invested_weight": original_total,
                "post_invested_weight": original_total,
                "pre_0050_weight": original_0050,
                "post_0050_weight": original_0050,
            }

        target_total = min(original_total, invested_cap)
        if original_total > 0.0:
            adjusted = adjusted / original_total * target_total
        else:
            adjusted = np.zeros(len(self.tickers), dtype=float)

        if BENCHMARK_TICKER in self.tickers:
            anchor_idx = self.tickers.index(BENCHMARK_TICKER)
            if adjusted[anchor_idx] > core_0050_cap:
                adjusted[anchor_idx] = core_0050_cap

        current_total = float(adjusted.sum())
        if current_total > 0.0 and current_total > target_total:
            adjusted *= target_total / current_total

        post_total = float(adjusted.sum())
        post_0050 = float(adjusted[self.tickers.index(BENCHMARK_TICKER)]) if BENCHMARK_TICKER in self.tickers else 0.0
        applied = bool(abs(post_total - original_total) > 1e-9 or abs(post_0050 - original_0050) > 1e-9)
        return adjusted, {
            "applied": applied,
            "budget_level": budget_level,
            "invested_cap": invested_cap,
            "core_0050_cap": core_0050_cap,
            "reason": f"stress_budget_{budget_level}",
            "pre_invested_weight": original_total,
            "post_invested_weight": post_total,
            "pre_0050_weight": original_0050,
            "post_0050_weight": post_0050,
        }

    def _apply_leverage_guardrail(self, idx: int, weights: np.ndarray, stress_snapshot: dict) -> tuple[np.ndarray, dict]:
        if "00631L.TW" not in self.tickers:
            return weights, {"applied": False, "reason": "00631l_unavailable"}

        row = self.panel.iloc[idx]
        trend_score = float(stress_snapshot.get("trend_score", 0.0))
        stress_score = float(stress_snapshot.get("score", 0.0))
        local_trend_score = float(row.get("0050_trend_score", 0.0))

        if stress_snapshot.get("level") in {"risk_off", "deep_risk_off"} or trend_score <= self.leverage_block_trend_threshold:
            max_00631l_weight = 0.0
            reason = "leverage_blocked_weak_market"
        elif (
            trend_score >= self.leverage_strong_trend_threshold
            and stress_score < self.leverage_strong_stress_cap
            and local_trend_score >= (2.0 / 3.0)
        ):
            max_00631l_weight = 0.30
            reason = "leverage_cap_30_strong_market"
        elif (
            trend_score >= self.leverage_positive_trend_threshold
            and stress_score < self.leverage_positive_stress_cap
            and local_trend_score >= (1.0 / 3.0)
        ):
            max_00631l_weight = 0.20
            reason = "leverage_cap_20_positive_market"
        else:
            max_00631l_weight = 0.10
            reason = "leverage_cap_10_neutral_market"

        adjusted = np.asarray(weights, dtype=float).copy()
        leverage_idx = self.tickers.index("00631L.TW")
        pre_weight = float(adjusted[leverage_idx])
        if pre_weight <= max_00631l_weight + 1e-12:
            return adjusted, {
                "applied": False,
                "reason": reason,
                "max_00631l_weight": float(max_00631l_weight),
                "pre_00631l_weight": pre_weight,
                "post_00631l_weight": pre_weight,
            }

        excess = pre_weight - max_00631l_weight
        adjusted[leverage_idx] = max_00631l_weight
        if BENCHMARK_TICKER in self.tickers:
            adjusted[self.tickers.index(BENCHMARK_TICKER)] += excess

        return adjusted, {
            "applied": True,
            "reason": reason,
            "max_00631l_weight": float(max_00631l_weight),
            "pre_00631l_weight": pre_weight,
            "post_00631l_weight": float(adjusted[leverage_idx]),
        }

    def _benchmark_shortfall_penalty(self, idx: int, portfolio_value: float, stress_snapshot: dict) -> dict:
        equal_relative = portfolio_value / max(float(self.equal_bh_curve[idx]), 1.0) - 1.0
        actual_relative = portfolio_value / max(float(self.actual_bh_curve[idx]), 1.0) - 1.0
        bh_0050_relative = portfolio_value / max(float(self.bh_0050_curve[idx]), 1.0) - 1.0
        raw_shortfall = max(
            max(-bh_0050_relative, 0.0),
            0.50 * max(-equal_relative, 0.0),
            0.25 * max(-actual_relative, 0.0),
        )
        capped_shortfall = min(float(raw_shortfall), self.benchmark_shortfall_penalty_cap)
        stress_score = float(np.clip(stress_snapshot.get("score", 0.0), 0.0, 1.0))
        stress_multiplier = 1.0 + self.benchmark_shortfall_stress_scale * stress_score
        penalty = self.benchmark_shortfall_penalty_weight * capped_shortfall * stress_multiplier
        return {
            "equal_relative": float(equal_relative),
            "actual_relative": float(actual_relative),
            "bh_0050_relative": float(bh_0050_relative),
            "raw_shortfall": float(raw_shortfall),
            "capped_shortfall": float(capped_shortfall),
            "stress_multiplier": float(stress_multiplier),
            "penalty": float(penalty),
        }

    def _target_weights(self, action: int) -> np.ndarray:
        if action == 0:
            return self.weights.copy()
        if action == 1:
            return self._named_target({"0050.TW": 1.0})
        if action == 2:
            return self._named_target({"0050.TW": 0.90, "00878.TW": 0.10})
        if action == 3:
            return self._named_target({"0050.TW": 0.80, "00878.TW": 0.20})
        if action == 4:
            return self._named_target({"0050.TW": 0.80, "00713.TW": 0.10, "00878.TW": 0.10})
        if action == 5:
            return self._named_target({"0050.TW": 0.70, "0056.TW": 0.10, "00713.TW": 0.10, "00878.TW": 0.10})
        if action == 6:
            return self._named_target({"0050.TW": 0.70, "00646.TW": 0.15, "00679B.TWO": 0.075, "00751B.TWO": 0.075})
        if action == 7:
            return self._named_target({"0050.TW": 0.80, "00679B.TWO": 0.10, "00751B.TWO": 0.10})
        if action == 8:
            return self._named_target({"0050.TW": 0.80, "00631L.TW": 0.10, "00878.TW": 0.10})
        if action == 9:
            return self._named_target({"0050.TW": 0.70, "00631L.TW": 0.20, "00878.TW": 0.10})
        if action == 10:
            return self._named_target({"0050.TW": 0.60, "00631L.TW": 0.30, "00878.TW": 0.10})
        return self._named_target({"0050.TW": 1.0})

    def _plan_trade(self, action: int) -> dict:
        action = int(action)
        signal_idx = max(self.step_idx - 1, 0) if self.open_execution else self.step_idx
        current_weights = self.weights.copy()
        base_target_weights = self._target_weights(action)
        raw_action_turnover = float(np.abs(base_target_weights - current_weights).sum())
        current_timestamp = pd.Timestamp(self.panel.iloc[self.step_idx]["date"])
        signal_timestamp = pd.Timestamp(self.panel.iloc[signal_idx]["date"])
        current_date = str(current_timestamp.date())
        signal_date = str(signal_timestamp.date())
        can_trade_by_weekday = self._is_trade_day(self.step_idx)
        if self.last_rebalance_idx <= -10**8:
            since_last_rebalance = self.min_rebalance_days
            cooldown_remaining = 0
            stress_cooldown_remaining = 0
            can_trade_by_schedule = True
            can_trade_by_stress_schedule = True
        else:
            since_last_rebalance = max(self.step_idx - self.last_rebalance_idx, 0)
            cooldown_remaining = max(self.min_rebalance_days - since_last_rebalance, 0)
            stress_cooldown_remaining = max(self.stress_rebalance_cooldown_days - since_last_rebalance, 0)
            can_trade_by_schedule = cooldown_remaining == 0
            can_trade_by_stress_schedule = stress_cooldown_remaining == 0

        harvest_due, range_harvest_drift = self._range_harvest_due(signal_idx)
        market_stress = self._market_stress_snapshot(signal_idx)
        pva_allowed, sjm_state, sjm_details = self._pva_overlay_allowed(signal_idx)
        pva_weights = None
        pva_details = None
        pva_state_weight = 0.0
        pva_drift = 0.0

        candidate_source = "hold"
        candidate_reason = "hold_action"
        candidate_target_weights = base_target_weights.copy()
        candidate_turnover = raw_action_turnover

        if harvest_due:
            candidate_source = "range_harvest"
            candidate_reason = "range_bound_rebalance"
            candidate_target_weights = self.range_target_weights.copy()
            candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
        elif self.enable_pva_sigmoid and pva_allowed:
            pva_weights, pva_details = self._pva_sigmoid_weights(signal_idx)
            pva_state_weight = 1.0 if sjm_state == "M" else self.pva_weight
            candidate_target_weights = (
                (1.0 - pva_state_weight) * base_target_weights + pva_state_weight * pva_weights
            )
            candidate_target_weights = candidate_target_weights / max(float(candidate_target_weights.sum()), 1e-12)
            pva_drift = float(np.abs(candidate_target_weights - current_weights).sum())
            candidate_turnover = pva_drift
            candidate_source = "pva_sigmoid"
            candidate_reason = f"pva_overlay_{sjm_state.lower()}"

        stress_guardrail = {"applied": False, "reason": "not_evaluated"}
        stress_blocks_ppo = False
        if candidate_source == "hold":
            stress_target_weights, stress_guardrail = self._stress_guardrail_target(
                signal_idx,
                current_weights,
                market_stress,
            )
            if stress_guardrail.get("applied"):
                candidate_target_weights = stress_target_weights.copy()
                candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
                candidate_source = "market_stress"
                candidate_reason = str(stress_guardrail["reason"])
            elif stress_guardrail.get("level") in {"risk_off", "deep_risk_off"} and action != 0:
                stress_blocks_ppo = True
                candidate_reason = str(stress_guardrail["reason"])
            elif action != 0:
                candidate_source = "ppo_action"
                candidate_reason = ACTION_LABELS.get(action, f"action_{action}")

        risk_budget_input = current_weights.copy() if stress_blocks_ppo else candidate_target_weights.copy()
        candidate_target_weights, stress_risk_budget = self._apply_stress_risk_budget(
            signal_idx,
            risk_budget_input,
            market_stress,
        )
        candidate_target_weights, leverage_guardrail = self._apply_leverage_guardrail(
            signal_idx,
            candidate_target_weights,
            market_stress,
        )
        candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
        if stress_risk_budget.get("applied") and candidate_source == "hold":
            candidate_source = "stress_budget"
            candidate_reason = str(stress_risk_budget["reason"])

        execute_trade = False
        execution_source = "hold"
        effective_target_weights = current_weights.copy()
        reward_turnover = 0.0
        final_reason = candidate_reason

        if not can_trade_by_weekday:
            if candidate_source == "hold" and not stress_blocks_ppo:
                final_reason = "hold_action"
                reward_turnover = 0.0
            else:
                final_reason = "not_monday_open"
                reward_turnover = candidate_turnover
        elif candidate_source == "range_harvest":
            if can_trade_by_schedule:
                execute_trade = True
                execution_source = "range_harvest"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"cooldown_{cooldown_remaining}d"
                reward_turnover = raw_action_turnover if action != 0 else 0.0
        elif candidate_source == "pva_sigmoid":
            if not can_trade_by_schedule:
                final_reason = f"cooldown_{cooldown_remaining}d"
                reward_turnover = raw_action_turnover if action != 0 else 0.0
            elif pva_drift >= self.pva_drift_threshold:
                execute_trade = True
                execution_source = "pva_sigmoid"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = "pva_drift_below_threshold"
                reward_turnover = raw_action_turnover if action != 0 else 0.0
        elif candidate_source in {"market_stress", "stress_budget"}:
            if can_trade_by_stress_schedule:
                execute_trade = True
                execution_source = candidate_source
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"stress_cooldown_{stress_cooldown_remaining}d"
                reward_turnover = candidate_turnover
        elif candidate_source == "ppo_action" and not stress_blocks_ppo:
            if can_trade_by_schedule:
                execute_trade = True
                execution_source = "ppo_action"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"cooldown_{cooldown_remaining}d"
                reward_turnover = candidate_turnover
        else:
            final_reason = candidate_reason if stress_blocks_ppo else "hold_action"

        return {
            "date": current_date,
            "signal_date": signal_date,
            "signal_idx": int(signal_idx),
            "execution_idx": int(self.step_idx),
            "action": action,
            "action_label": ACTION_LABELS.get(action, f"action_{action}"),
            "sjm_state": sjm_state,
            "sjm_details": sjm_details,
            "market_stress": market_stress,
            "stress_guardrail": stress_guardrail,
            "stress_risk_budget": stress_risk_budget,
            "leverage_guardrail": leverage_guardrail,
            "current_weights": current_weights,
            "candidate_target_weights": candidate_target_weights,
            "effective_target_weights": effective_target_weights,
            "raw_action_turnover": float(raw_action_turnover),
            "candidate_turnover": float(candidate_turnover),
            "reward_turnover": float(reward_turnover),
            "cooldown_remaining": int(cooldown_remaining),
            "stress_cooldown_remaining": int(stress_cooldown_remaining),
            "can_trade_by_weekday": bool(can_trade_by_weekday),
            "range_harvest_due": bool(harvest_due),
            "range_harvest_drift": float(range_harvest_drift),
            "pva_allowed": bool(pva_allowed),
            "pva_weights": pva_weights,
            "pva_details": pva_details,
            "pva_state_weight": float(pva_state_weight),
            "pva_drift": float(pva_drift),
            "candidate_source": candidate_source,
            "execute_trade": bool(execute_trade),
            "execution_source": execution_source,
            "reason": final_reason,
        }

    def _get_obs(self) -> np.ndarray:
        obs_idx = max(self.step_idx - 1, 0) if self.open_execution else self.step_idx
        row = self.panel.iloc[obs_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        prices = self.price_array[obs_idx]
        value = max(self._portfolio_value(prices), 1.0)
        weights = self.shares * prices / value
        peak = max(self.peak_value, value, 1.0)
        days_since_rebalance = min(max(obs_idx - self.last_rebalance_idx, 0), 252) / 252.0
        state = np.array(
            [
                *weights,
                self.cash / value,
                value / peak - 1.0,
                days_since_rebalance,
                value / max(float(self.equal_bh_curve[obs_idx]), 1.0) - 1.0,
                value / max(float(self.actual_bh_curve[obs_idx]), 1.0) - 1.0,
                value / max(float(self.bh_0050_curve[obs_idx]), 1.0) - 1.0,
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
            if delta >= 0:
                continue
            desired_sell_shares = min(-delta / prices[i], self.shares[i]) if prices[i] > 0 else 0.0
            sell_shares = _quantize_sell_shares(desired_sell_shares, self.shares[i])
            if sell_shares <= 0:
                continue
            _, fee, tax, net = _sell_net_proceeds(
                sell_shares,
                prices[i],
                self.commission_rate,
                self.tax_rates[i],
            )
            fees += fee + tax
            self.cash += net
            self.shares[i] -= sell_shares

        for i, delta in enumerate(deltas):
            if delta <= 0:
                continue
            desired_buy_shares = delta / prices[i] if prices[i] > 0 else 0.0
            buy_shares = _quantize_buy_shares(desired_buy_shares)
            if buy_shares <= 0:
                continue
            buy_shares = min(buy_shares, _max_affordable_buy_shares(self.cash, prices[i], self.commission_rate))
            if buy_shares <= 0:
                continue
            _, fee, total_cost = _buy_total_cost(buy_shares, prices[i], self.commission_rate)
            fees += fee
            self.cash -= total_cost
            self.shares[i] += buy_shares

        value_after = max(self._portfolio_value(prices), 1.0)
        self.weights = self.shares * prices / value_after
        return float(fees)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = self.start_step_idx
        self.cash = self.initial_cash
        self.shares = np.zeros(len(self.tickers), dtype=float)
        self.weights = np.zeros(len(self.tickers), dtype=float)
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
        self.market_stress_count = 0
        self.market_stress_history = []
        self.stress_budget_count = 0
        self.stress_budget_history = []
        self.sjm_state_history = []
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        self.weight_history = [self.weights.copy().tolist()]
        self.rebalance_indices = []
        return self._get_obs(), {}

    def step(self, action):
        if self.open_execution:
            current_idx = self.step_idx
            prev_idx = max(current_idx - 1, 0)
            value_before = self._portfolio_value(self.price_array[prev_idx])
            fees = 0.0
            decision = self._plan_trade(int(action))
            turnover = float(decision["reward_turnover"])
            self.sjm_state_history.append({"date": decision["date"], **decision["sjm_details"]})

            if decision["execute_trade"]:
                fees = self._rebalance(decision["effective_target_weights"], self.open_price_array[current_idx])
                if fees > 0:
                    self.trade_count += 1
                    self.last_rebalance_idx = current_idx
                    self.fees_paid += fees
                    self.rebalance_indices.append(int(current_idx))
                    if decision["execution_source"] == "range_harvest":
                        self.range_harvest_count += 1
                        self.range_harvest_history.append(
                            {
                                "date": decision["date"],
                                "drift": float(decision["range_harvest_drift"]),
                                "target_weights": {
                                    ticker: float(weight)
                                    for ticker, weight in zip(self.tickers, decision["effective_target_weights"])
                                },
                            }
                        )
                    elif decision["execution_source"] == "pva_sigmoid":
                        self.pva_sigmoid_count += 1
                        self.pva_sigmoid_history.append(
                            {
                                "date": decision["date"],
                                "sjm_state": decision["sjm_state"],
                                "drift": float(decision["pva_drift"]),
                                "pva_weight": float(decision["pva_state_weight"]),
                                "target_weights": {
                                    ticker: float(weight)
                                    for ticker, weight in zip(self.tickers, decision["effective_target_weights"])
                                },
                                "details": decision["pva_details"],
                            }
                        )
                    elif decision["execution_source"] == "market_stress":
                        self.market_stress_count += 1
                        self.market_stress_history.append(
                            {
                                "date": decision["date"],
                                "reason": decision["reason"],
                                "market_stress": decision["market_stress"],
                                "target_cash_weight": self._cash_weight_from_asset_weights(
                                    decision["effective_target_weights"]
                                ),
                            }
                        )
                    elif decision["execution_source"] == "stress_budget":
                        self.stress_budget_count += 1
                        self.stress_budget_history.append(
                            {
                                "date": decision["date"],
                                "market_stress": decision["market_stress"],
                                "risk_budget": decision["stress_risk_budget"],
                                "target_cash_weight": self._cash_weight_from_asset_weights(
                                    decision["effective_target_weights"]
                                ),
                            }
                        )

            dca_fees = self._apply_dca_if_due(current_idx, self.open_price_array[current_idx])
            if dca_fees > 0:
                self.fees_paid += dca_fees

            dividend_cash = float(np.dot(self.shares, self.dividend_array[current_idx]))
            if dividend_cash > 0:
                self.cash += dividend_cash
                self.dividend_cash_received += dividend_cash

            close_prices = self.price_array[current_idx]
            value_after = self._portfolio_value(close_prices)
            self.weights = self.shares * close_prices / max(value_after, 1.0)
            self.peak_value = max(self.peak_value, value_after)
            self.equity_curve.append(value_after)
            self.weight_history.append(self.weights.copy().tolist())

            daily_return = value_after / max(value_before, 1.0) - 1
            equal_return = float(self.equal_bh_curve[current_idx] / self.equal_bh_curve[prev_idx] - 1)
            actual_return = float(self.actual_bh_curve[current_idx] / self.actual_bh_curve[prev_idx] - 1)
            bh_0050_return = float(self.bh_0050_curve[current_idx] / self.bh_0050_curve[prev_idx] - 1)
            terminated = current_idx >= len(self.panel) - 1
            if not terminated:
                self.step_idx += 1
            next_obs = (
                self._get_obs()
                if not terminated
                else np.zeros(self.observation_space.shape, dtype=np.float32)
            )
        else:
            execution_prices = self.price_array[self.step_idx]
            value_before = self._portfolio_value(self.price_array[self.step_idx])
            fees = 0.0
            decision = self._plan_trade(int(action))
            turnover = float(decision["reward_turnover"])
            self.sjm_state_history.append({"date": decision["date"], **decision["sjm_details"]})

            if decision["execute_trade"]:
                fees = self._rebalance(decision["effective_target_weights"], execution_prices)
                if fees > 0:
                    self.trade_count += 1
                    self.last_rebalance_idx = self.step_idx
                    self.fees_paid += fees
                    self.rebalance_indices.append(int(self.step_idx))
                    if decision["execution_source"] == "range_harvest":
                        self.range_harvest_count += 1
                        self.range_harvest_history.append(
                            {
                                "date": decision["date"],
                                "drift": float(decision["range_harvest_drift"]),
                                "target_weights": {
                                    ticker: float(weight)
                                    for ticker, weight in zip(self.tickers, decision["effective_target_weights"])
                                },
                            }
                        )
                    elif decision["execution_source"] == "pva_sigmoid":
                        self.pva_sigmoid_count += 1
                        self.pva_sigmoid_history.append(
                            {
                                "date": decision["date"],
                                "sjm_state": decision["sjm_state"],
                                "drift": float(decision["pva_drift"]),
                                "pva_weight": float(decision["pva_state_weight"]),
                                "target_weights": {
                                    ticker: float(weight)
                                    for ticker, weight in zip(self.tickers, decision["effective_target_weights"])
                                },
                                "details": decision["pva_details"],
                            }
                        )
                    elif decision["execution_source"] == "market_stress":
                        self.market_stress_count += 1
                        self.market_stress_history.append(
                            {
                                "date": decision["date"],
                                "reason": decision["reason"],
                                "market_stress": decision["market_stress"],
                                "target_cash_weight": self._cash_weight_from_asset_weights(
                                    decision["effective_target_weights"]
                                ),
                            }
                        )
                    elif decision["execution_source"] == "stress_budget":
                        self.stress_budget_count += 1
                        self.stress_budget_history.append(
                            {
                                "date": decision["date"],
                                "market_stress": decision["market_stress"],
                                "risk_budget": decision["stress_risk_budget"],
                                "target_cash_weight": self._cash_weight_from_asset_weights(
                                    decision["effective_target_weights"]
                                ),
                            }
                        )

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
            self.weights = self.shares * next_prices / max(value_after, 1.0)
            self.peak_value = max(self.peak_value, value_after)
            self.equity_curve.append(value_after)
            self.weight_history.append(self.weights.copy().tolist())

            daily_return = value_after / max(value_before, 1.0) - 1
            equal_return = float(self.equal_bh_curve[self.step_idx] / self.equal_bh_curve[self.step_idx - 1] - 1)
            actual_return = float(self.actual_bh_curve[self.step_idx] / self.actual_bh_curve[self.step_idx - 1] - 1)
            bh_0050_return = float(self.bh_0050_curve[self.step_idx] / self.bh_0050_curve[self.step_idx - 1] - 1)
            terminated = self.step_idx >= len(self.panel) - 1
            next_obs = self._get_obs()

        excess_equal = daily_return - equal_return
        excess_actual = daily_return - actual_return
        underperform_0050 = max(0.0, bh_0050_return - daily_return)
        current_drawdown = min(0.0, value_after / max(self.peak_value, 1.0) - 1.0)
        benchmark_penalty = self._benchmark_shortfall_penalty(
            self.step_idx,
            value_after,
            decision["market_stress"],
        )
        reward = float(
            (
                daily_return
                + self.equal_benchmark_weight * excess_equal
                + self.actual_benchmark_weight * excess_actual
                - self.underperform_0050_weight * underperform_0050
                - self.drawdown_penalty_weight * abs(current_drawdown)
                - benchmark_penalty["penalty"]
            )
            * 100.0
            - self.turnover_penalty * turnover
                - fees / max(value_before, 1.0)
        )
        info = {
            "portfolio_value": value_after,
            "fees_paid": self.fees_paid,
            "dividend_cash_received": self.dividend_cash_received,
            "total_contributions": self.total_contributions,
            "trade_count": self.trade_count,
            "range_harvest_count": self.range_harvest_count,
            "pva_sigmoid_count": self.pva_sigmoid_count,
            "market_stress_count": self.market_stress_count,
            "stress_budget_count": self.stress_budget_count,
            "benchmark_penalty": benchmark_penalty,
            "weights": self.weights.copy(),
        }
        return next_obs, reward, terminated, False, info


def _simulate_model(
    model: PPO,
    panel: pd.DataFrame,
    tickers: list[str],
    env_kwargs: dict | None = None,
) -> tuple[AllHoldingsPortfolioEnv, dict]:
    env = AllHoldingsPortfolioEnv(panel, tickers, **(env_kwargs or {}))
    obs, _ = env.reset()
    done = False
    info = {"weights": np.zeros(len(tickers))}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    return env, info


def _run_model(
    model: PPO,
    panel: pd.DataFrame,
    tickers: list[str],
    env_kwargs: dict | None = None,
) -> dict:
    env, info = _simulate_model(model, panel, tickers, env_kwargs)
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
        "market_stress_count": int(env.market_stress_count),
        "stress_budget_count": int(env.stress_budget_count),
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
            "monthly_amounts": {ticker: float(amount) for ticker, amount in zip(tickers, env.dca_amount_array)},
        },
        "dca_purchase_history": env.dca_purchase_history,
        "range_harvest_config": {
            "enabled": bool(env.enable_range_harvest),
            "range_drift_threshold": float(env.range_drift_threshold),
            "range_target_weights": {ticker: float(weight) for ticker, weight in zip(tickers, env.range_target_weights)},
        },
        "range_harvest_history": env.range_harvest_history,
        "pva_sigmoid_config": {
            "enabled": bool(env.enable_pva_sigmoid),
            "pva_weight": float(env.pva_weight),
            "pva_drift_threshold": float(env.pva_drift_threshold),
        },
        "pva_sigmoid_history": env.pva_sigmoid_history,
        "market_stress_history": env.market_stress_history,
        "stress_budget_history": env.stress_budget_history,
        "sjm_state_history": env.sjm_state_history,
        "sjm_state_counts": {
            state: int(sum(1 for item in env.sjm_state_history if item.get("state") == state))
            for state in ("S", "J", "M")
        },
        "holding_time_stats": calculate_holding_time_stats(panel, tickers, env.weight_history, env.rebalance_indices),
        "weight_history": env.weight_history,
        "final_weights": {ticker: float(w) for ticker, w in zip(tickers, info["weights"])},
        "equity_curve": equity,
    }


def _buy_and_hold(
    panel: pd.DataFrame,
    tickers: list[str],
    weights: np.ndarray,
    *,
    dca_total_monthly: float = 0.0,
    dca_day: int = 26,
    daily_open_only: bool = False,
    monday_open_only: bool = False,
) -> dict:
    prices = _prices(panel, tickers)
    open_prices = _open_prices(panel, tickers)
    dividends = _dividends(panel.copy(), tickers)
    tax_rates = np.array(
        [TRANSACTION_TAX_RATE if ticker == "2884.TW" else ETF_TAX_RATE for ticker in tickers],
        dtype=float,
    )
    if daily_open_only and monday_open_only:
        raise ValueError("daily_open_only and monday_open_only cannot both be enabled")
    open_execution = daily_open_only or monday_open_only
    initial = 1_000_000.0
    shares = np.zeros(len(tickers), dtype=float)
    cash = float(initial)
    fees_paid = 0.0
    invested = not open_execution
    if invested:
        shares, cash, fees_paid = _allocate_cash_to_weights(initial, weights, prices[0], COMMISSION_RATE)
    equity = []
    total_contributions = 0.0
    executed_months: set[str] = set()
    dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
    for idx, row_prices in enumerate(prices):
        current_date = dates.iloc[idx]
        if open_execution and not invested and ((not monday_open_only) or current_date.weekday() == 0):
            new_shares, cash, buy_fees = _allocate_cash_to_weights(cash, weights, open_prices[idx], COMMISSION_RATE)
            shares += new_shares
            fees_paid += buy_fees
            invested = True
        if idx > 0:
            if invested:
                cash += float(np.dot(shares, dividends[idx]))
            if dca_total_monthly > 0:
                month = str(current_date.to_period("M"))
                scheduled_day = min(dca_day, current_date.days_in_month)
                scheduled_date = pd.Timestamp(year=current_date.year, month=current_date.month, day=scheduled_day)
                can_buy_today = (not monday_open_only) or current_date.weekday() == 0
                if month not in executed_months and current_date >= scheduled_date and can_buy_today:
                    executed_months.add(month)
                    total_contributions += dca_total_monthly
                    if invested:
                        contribution_cash = float(dca_total_monthly)
                        buy_prices = open_prices[idx] if open_execution else row_prices
                        new_shares, leftover_cash, buy_fees = _allocate_cash_to_weights(
                            contribution_cash,
                            weights,
                            buy_prices,
                            COMMISSION_RATE,
                        )
                        shares += new_shares
                        cash += leftover_cash
                        fees_paid += buy_fees
                    else:
                        cash += dca_total_monthly
        equity.append(float(cash + np.dot(row_prices, shares)))
    result = {"final_value": float(equity[-1]), "metrics": calculate_backtest_metrics(equity)}
    if dca_total_monthly > 0:
        total_invested = initial + total_contributions
        net_profit = float(equity[-1] - total_invested)
        result["investment_summary"] = {
            "initial_cash": float(initial),
            "total_contributions": float(total_contributions),
            "total_invested": float(total_invested),
            "final_value": float(equity[-1]),
            "net_profit": net_profit,
            "simple_return_on_total_invested": float(net_profit / total_invested) if total_invested > 0 else 0.0,
        }
    result["execution_assumptions"] = {
        "commission_rate": float(COMMISSION_RATE),
        "min_commission_fee": float(MIN_COMMISSION_FEE),
        "tax_rates": {ticker: float(rate) for ticker, rate in zip(tickers, tax_rates)},
        "min_trade_shares": int(MIN_TRADE_SHARES),
        "fees_paid_estimate": float(fees_paid),
    }
    return result


def _build_dca_monthly_amounts(
    tickers: list[str],
    total_monthly: float,
    mode: str,
    actual_weights: np.ndarray,
) -> dict[str, float]:
    total_monthly = float(max(total_monthly, 0.0))
    if total_monthly <= 0.0:
        return {}
    if mode == "equal":
        weights = np.ones(len(tickers), dtype=float) / max(len(tickers), 1)
    elif mode == "core_satellite":
        weights = _weights_for_existing(tickers, DEFAULT_RANGE_TARGET)
    else:
        weights = actual_weights
    return {ticker: float(total_monthly * weight) for ticker, weight in zip(tickers, weights)}


def _slugify_number(value: float) -> str:
    return re.sub(r"[^0-9a-z]+", "", f"{value:.4f}".rstrip("0").rstrip(".").replace(".", "p").lower())


def _build_model_stem(args: argparse.Namespace) -> str:
    date_tag = f"{args.train_start.replace('-', '')}_{args.train_end.replace('-', '')}"
    config_tag = (
        f"turn{_slugify_number(args.turnover_penalty)}"
        f"_reb{args.min_rebalance_days}"
        f"_eq{_slugify_number(args.equal_benchmark_weight)}"
        f"_act{_slugify_number(args.actual_benchmark_weight)}"
        f"_u0050{_slugify_number(args.underperform_0050_weight)}"
        f"_dd{_slugify_number(args.drawdown_penalty_weight)}"
        f"_short{_slugify_number(args.benchmark_shortfall_penalty_weight)}"
        f"_steps{args.timesteps}"
        f"_seed{args.seed}"
    )
    if args.enable_dca:
        config_tag += f"_dca{_slugify_number(args.dca_total_monthly)}{args.dca_mode}"
    if args.enable_range_harvest:
        config_tag += f"_range{_slugify_number(args.range_drift_threshold)}"
    if args.enable_pva_sigmoid:
        config_tag += (
            f"_pva{_slugify_number(args.pva_weight)}"
            f"_pvad{_slugify_number(args.pva_drift_threshold)}"
        )
    if args.daily_open_only:
        config_tag += "_dayopen"
    elif args.monday_open_only:
        config_tag += "_monopen"
    if args.model_tag:
        config_tag = f"{config_tag}_{args.model_tag}"
    return f"portfolio_all_holdings_{date_tag}_fullstack_{config_tag}"


def _execution_mode(args: argparse.Namespace) -> str:
    if args.monday_open_only:
        return "monday_open"
    if args.daily_open_only:
        return "daily_open"
    return "daily_close"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train all current holdings as one PPO portfolio allocator.")
    parser.add_argument("--timesteps", type=int, default=TIMESTEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--train-start", default=TRAIN_START)
    parser.add_argument("--train-end", default=TRAIN_END)
    parser.add_argument("--backtest-start", default=BACKTEST_START)
    parser.add_argument("--backtest-end", default=BACKTEST_END)
    parser.add_argument("--download-end", default=DOWNLOAD_END)
    parser.add_argument("--turnover-penalty", type=float, default=0.001)
    parser.add_argument("--equal-benchmark-weight", type=float, default=1.5)
    parser.add_argument("--actual-benchmark-weight", type=float, default=1.0)
    parser.add_argument("--underperform-0050-weight", type=float, default=0.8)
    parser.add_argument("--drawdown-penalty-weight", type=float, default=0.5)
    parser.add_argument("--benchmark-shortfall-penalty-weight", type=float, default=0.0)
    parser.add_argument("--benchmark-shortfall-penalty-cap", type=float, default=0.15)
    parser.add_argument("--benchmark-shortfall-stress-scale", type=float, default=0.50)
    parser.add_argument("--stress-budget-caution-invested-cap", type=float, default=0.92)
    parser.add_argument("--stress-budget-caution-0050-cap", type=float, default=0.55)
    parser.add_argument("--stress-budget-risk-off-invested-cap", type=float, default=0.82)
    parser.add_argument("--stress-budget-risk-off-0050-cap", type=float, default=0.45)
    parser.add_argument("--stress-budget-deep-risk-off-invested-cap", type=float, default=0.65)
    parser.add_argument("--stress-budget-deep-risk-off-0050-cap", type=float, default=0.30)
    parser.add_argument("--min-rebalance-days", type=int, default=20)
    parser.add_argument("--stress-rebalance-cooldown-days", type=int, default=0)
    parser.add_argument("--stress-confirm-days", type=int, default=3)
    parser.add_argument("--use-rsi-features", action="store_true")
    parser.add_argument("--disable-market-regime-features", action="store_true")
    parser.add_argument("--enable-dca", action="store_true")
    parser.add_argument("--dca-day", type=int, default=26)
    parser.add_argument("--dca-total-monthly", type=float, default=DEFAULT_DCA_TOTAL_MONTHLY)
    parser.add_argument("--dca-mode", choices=["actual_holdings", "equal", "core_satellite"], default="actual_holdings")
    parser.add_argument("--enable-range-harvest", action="store_true")
    parser.add_argument("--range-drift-threshold", type=float, default=0.05)
    parser.add_argument("--enable-pva-sigmoid", action="store_true")
    parser.add_argument("--pva-weight", type=float, default=0.30)
    parser.add_argument("--pva-drift-threshold", type=float, default=0.05)
    parser.add_argument("--leverage-block-trend-threshold", type=float, default=-0.10)
    parser.add_argument("--leverage-positive-trend-threshold", type=float, default=0.05)
    parser.add_argument("--leverage-strong-trend-threshold", type=float, default=0.20)
    parser.add_argument("--leverage-positive-stress-cap", type=float, default=0.20)
    parser.add_argument("--leverage-strong-stress-cap", type=float, default=0.15)
    parser.add_argument("--daily-open-only", action="store_true")
    parser.add_argument("--monday-open-only", action="store_true")
    parser.add_argument("--current-held-only", action="store_true")
    parser.add_argument("--ppo-verbose", type=int, default=0)
    parser.add_argument("--model-tag", default="")
    args = parser.parse_args()
    if args.daily_open_only and args.monday_open_only:
        raise ValueError("Choose only one of --daily-open-only or --monday-open-only")

    use_market_regime_features = not args.disable_market_regime_features
    tickers = (
        [ticker for ticker in ALL_TICKERS if int(PORTFOLIO_HOLDINGS.get(ticker, {}).get("shares", 0)) > 0]
        if args.current_held_only
        else list(ALL_TICKERS)
    )
    execution_mode = _execution_mode(args)

    print("=" * 72)
    print("All holdings full-stack portfolio PPO training/backtest")
    print(f"Tickers:  {', '.join(tickers)}")
    print(f"Train:    {args.train_start} ~ {args.train_end}")
    print(f"Backtest: {args.backtest_start} ~ {args.backtest_end}")
    print(f"Download: {args.download_end}")
    print(f"Steps:    {args.timesteps:,}")
    print(f"Seed:     {args.seed}")
    print(
        "Config:   "
        f"turnover={args.turnover_penalty}, min_rebalance={args.min_rebalance_days}, "
        f"eq_bh={args.equal_benchmark_weight}, actual_bh={args.actual_benchmark_weight}, "
        f"under_0050={args.underperform_0050_weight}, drawdown={args.drawdown_penalty_weight}, "
        f"shortfall_penalty={args.benchmark_shortfall_penalty_weight}, "
        f"enable_dca={args.enable_dca}, dca_mode={args.dca_mode}, "
        f"enable_range={args.enable_range_harvest}, enable_pva={args.enable_pva_sigmoid}, "
        f"execution_mode={execution_mode}, "
        f"use_market_regime={use_market_regime_features}, use_rsi={args.use_rsi_features}"
    )
    print("=" * 72)

    stock_data = download_all_stocks(tickers, args.train_start, args.download_end)
    missing = [ticker for ticker in tickers if ticker not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    train_panel = _align_panel(stock_data, tickers, args.train_start, args.train_end)
    test_panel = _align_panel(stock_data, tickers, args.backtest_start, args.backtest_end)
    if len(train_panel) < 100 or len(test_panel) < 100:
        raise RuntimeError("Not enough aligned train/backtest rows")

    print(f"Loaded rows: train={len(train_panel)}, backtest={len(test_panel)}")
    print(
        "Actual ranges: "
        f"train={train_panel['date'].min().date()}~{train_panel['date'].max().date()}, "
        f"backtest={test_panel['date'].min().date()}~{test_panel['date'].max().date()}"
    )

    env_kwargs = build_env_kwargs(
        turnover_penalty=args.turnover_penalty,
        equal_benchmark_weight=args.equal_benchmark_weight,
        actual_benchmark_weight=args.actual_benchmark_weight,
        underperform_0050_weight=args.underperform_0050_weight,
        drawdown_penalty_weight=args.drawdown_penalty_weight,
        benchmark_shortfall_penalty_weight=args.benchmark_shortfall_penalty_weight,
        benchmark_shortfall_penalty_cap=args.benchmark_shortfall_penalty_cap,
        benchmark_shortfall_stress_scale=args.benchmark_shortfall_stress_scale,
        stress_budget_caution_invested_cap=args.stress_budget_caution_invested_cap,
        stress_budget_caution_0050_cap=args.stress_budget_caution_0050_cap,
        stress_budget_risk_off_invested_cap=args.stress_budget_risk_off_invested_cap,
        stress_budget_risk_off_0050_cap=args.stress_budget_risk_off_0050_cap,
        stress_budget_deep_risk_off_invested_cap=args.stress_budget_deep_risk_off_invested_cap,
        stress_budget_deep_risk_off_0050_cap=args.stress_budget_deep_risk_off_0050_cap,
        min_rebalance_days=args.min_rebalance_days,
        stress_rebalance_cooldown_days=args.stress_rebalance_cooldown_days,
        stress_confirm_days=args.stress_confirm_days,
        use_rsi_features=args.use_rsi_features,
        use_market_regime_features=use_market_regime_features,
        enable_range_harvest=args.enable_range_harvest,
        range_drift_threshold=args.range_drift_threshold,
        enable_pva_sigmoid=args.enable_pva_sigmoid,
        pva_weight=args.pva_weight,
        pva_drift_threshold=args.pva_drift_threshold,
        leverage_block_trend_threshold=args.leverage_block_trend_threshold,
        leverage_positive_trend_threshold=args.leverage_positive_trend_threshold,
        leverage_strong_trend_threshold=args.leverage_strong_trend_threshold,
        leverage_positive_stress_cap=args.leverage_positive_stress_cap,
        leverage_strong_stress_cap=args.leverage_strong_stress_cap,
        daily_open_only=args.daily_open_only,
        monday_open_only=args.monday_open_only,
    )

    train_env = AllHoldingsPortfolioEnv(train_panel, tickers, **env_kwargs)
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

    model_path = PROJECT_ROOT / "models" / "portfolio" / _build_model_stem(args)
    if len(str(model_path)) >= 240:
        model_path = PROJECT_ROOT / "models" / "portfolio" / (
            f"portfolio_all_holdings_{args.train_start.replace('-', '')}_{args.train_end.replace('-', '')}_"
            f"seed{args.seed}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))

    train_eval = _run_model(model, train_panel, tickers, env_kwargs)
    eval_env_kwargs = dict(env_kwargs)
    actual_weights = _actual_holdings_weights(tickers, _prices(test_panel, tickers)[0])
    dca_monthly_amounts = _build_dca_monthly_amounts(
        tickers,
        args.dca_total_monthly,
        args.dca_mode,
        actual_weights,
    )
    if args.enable_dca:
        eval_env_kwargs = build_env_kwargs(
            turnover_penalty=args.turnover_penalty,
            equal_benchmark_weight=args.equal_benchmark_weight,
            actual_benchmark_weight=args.actual_benchmark_weight,
            underperform_0050_weight=args.underperform_0050_weight,
            drawdown_penalty_weight=args.drawdown_penalty_weight,
            benchmark_shortfall_penalty_weight=args.benchmark_shortfall_penalty_weight,
            benchmark_shortfall_penalty_cap=args.benchmark_shortfall_penalty_cap,
            benchmark_shortfall_stress_scale=args.benchmark_shortfall_stress_scale,
            stress_budget_caution_invested_cap=args.stress_budget_caution_invested_cap,
            stress_budget_caution_0050_cap=args.stress_budget_caution_0050_cap,
            stress_budget_risk_off_invested_cap=args.stress_budget_risk_off_invested_cap,
            stress_budget_risk_off_0050_cap=args.stress_budget_risk_off_0050_cap,
            stress_budget_deep_risk_off_invested_cap=args.stress_budget_deep_risk_off_invested_cap,
            stress_budget_deep_risk_off_0050_cap=args.stress_budget_deep_risk_off_0050_cap,
            min_rebalance_days=args.min_rebalance_days,
            stress_rebalance_cooldown_days=args.stress_rebalance_cooldown_days,
            stress_confirm_days=args.stress_confirm_days,
            use_rsi_features=args.use_rsi_features,
            use_market_regime_features=use_market_regime_features,
            enable_range_harvest=args.enable_range_harvest,
            range_drift_threshold=args.range_drift_threshold,
            enable_pva_sigmoid=args.enable_pva_sigmoid,
            pva_weight=args.pva_weight,
            pva_drift_threshold=args.pva_drift_threshold,
            leverage_block_trend_threshold=args.leverage_block_trend_threshold,
            leverage_positive_trend_threshold=args.leverage_positive_trend_threshold,
            leverage_strong_trend_threshold=args.leverage_strong_trend_threshold,
            leverage_positive_stress_cap=args.leverage_positive_stress_cap,
            leverage_strong_stress_cap=args.leverage_strong_stress_cap,
            daily_open_only=args.daily_open_only,
            monday_open_only=args.monday_open_only,
            dca_monthly_amounts=dca_monthly_amounts,
            dca_day=args.dca_day,
        )
    result = _run_model(model, test_panel, tickers, eval_env_kwargs)
    benchmark_dca_total = args.dca_total_monthly if args.enable_dca else 0.0
    equal_bh = _buy_and_hold(
        test_panel,
        tickers,
        np.ones(len(tickers)) / len(tickers),
        dca_total_monthly=benchmark_dca_total,
        dca_day=args.dca_day,
        daily_open_only=args.daily_open_only,
        monday_open_only=args.monday_open_only,
    )
    actual_bh = _buy_and_hold(
        test_panel,
        tickers,
        actual_weights,
        dca_total_monthly=benchmark_dca_total,
        dca_day=args.dca_day,
        daily_open_only=args.daily_open_only,
        monday_open_only=args.monday_open_only,
    )
    bh_0050 = _buy_and_hold(
        test_panel,
        tickers,
        _weights_for_existing(tickers, {BENCHMARK_TICKER: 1.0}),
        dca_total_monthly=benchmark_dca_total,
        dca_day=args.dca_day,
        daily_open_only=args.daily_open_only,
        monday_open_only=args.monday_open_only,
    )

    excess_vs_equal_on_total_invested = None
    excess_vs_actual_on_total_invested = None
    excess_vs_0050_on_total_invested = None
    if args.enable_dca:
        result_roi = float(result["investment_summary"]["simple_return_on_total_invested"])
        excess_vs_equal_on_total_invested = result_roi - float(
            equal_bh["investment_summary"]["simple_return_on_total_invested"]
        )
        excess_vs_actual_on_total_invested = result_roi - float(
            actual_bh["investment_summary"]["simple_return_on_total_invested"]
        )
        excess_vs_0050_on_total_invested = result_roi - float(
            bh_0050["investment_summary"]["simple_return_on_total_invested"]
        )

    payload = {
        "tickers": tickers,
        "train_start": args.train_start,
        "train_end": args.train_end,
        "backtest_start": args.backtest_start,
        "backtest_end": args.backtest_end,
        "download_end": args.download_end,
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
            "min_trade_shares": int(MIN_TRADE_SHARES),
            "daily_open_only": bool(args.daily_open_only),
            "monday_open_only": bool(args.monday_open_only),
        },
        "reward_config": {
            "equal_benchmark_weight": args.equal_benchmark_weight,
            "actual_benchmark_weight": args.actual_benchmark_weight,
            "underperform_0050_weight": args.underperform_0050_weight,
            "drawdown_penalty_weight": args.drawdown_penalty_weight,
            "benchmark_shortfall_penalty_weight": args.benchmark_shortfall_penalty_weight,
            "benchmark_shortfall_penalty_cap": args.benchmark_shortfall_penalty_cap,
            "benchmark_shortfall_stress_scale": args.benchmark_shortfall_stress_scale,
        },
        "dca_enabled": bool(args.enable_dca),
        "dca_config": {
            "dca_day": args.dca_day,
            "dca_total_monthly": args.dca_total_monthly,
            "dca_mode": args.dca_mode,
            "monthly_amounts": dca_monthly_amounts if args.enable_dca else {},
        },
        "range_harvest_config": {
            "enabled": bool(args.enable_range_harvest),
            "range_drift_threshold": args.range_drift_threshold,
            "target_weights": DEFAULT_RANGE_TARGET,
        },
        "pva_sigmoid_config": {
            "enabled": bool(args.enable_pva_sigmoid),
            "pva_weight": args.pva_weight,
            "pva_drift_threshold": args.pva_drift_threshold,
        },
        "stress_guardrail_config": {
            "enabled": True,
            "stress_rebalance_cooldown_days": int(args.stress_rebalance_cooldown_days),
            "stress_confirm_days": int(args.stress_confirm_days),
            "risk_off_target": DEFAULT_RISK_OFF_TARGET,
            "deep_risk_off_target": DEFAULT_DEEP_RISK_OFF_TARGET,
        },
        "execution_config": {
            "mode": execution_mode,
            "daily_open_only": bool(args.daily_open_only),
            "monday_open_only": bool(args.monday_open_only),
            "commission_rate": float(COMMISSION_RATE),
            "min_commission_fee": float(MIN_COMMISSION_FEE),
            "sell_transaction_tax_rate": float(TRANSACTION_TAX_RATE),
            "min_trade_shares": int(MIN_TRADE_SHARES),
            "trade_price": "daily_open" if args.daily_open_only else ("monday_open" if args.monday_open_only else "daily_close"),
        },
        "risk_budget_config": {
            "caution_invested_cap": args.stress_budget_caution_invested_cap,
            "caution_0050_cap": args.stress_budget_caution_0050_cap,
            "risk_off_invested_cap": args.stress_budget_risk_off_invested_cap,
            "risk_off_0050_cap": args.stress_budget_risk_off_0050_cap,
            "deep_risk_off_invested_cap": args.stress_budget_deep_risk_off_invested_cap,
            "deep_risk_off_0050_cap": args.stress_budget_deep_risk_off_0050_cap,
        },
        "feature_config": {
            "base_features_per_ticker": FEATURE_COLUMNS,
            "available_derived_portfolio_features": DERIVED_FEATURE_COLUMNS,
            "active_derived_portfolio_features": train_env.active_derived_features,
            "rsi_features_enabled": bool(args.use_rsi_features),
            "market_regime_features_enabled": bool(use_market_regime_features),
            "shared_market_inputs": SHARED_MARKET_FEATURE_COLUMNS,
            "market_context_inputs_per_ticker": PER_TICKER_CONTEXT_COLUMNS,
            "observation_dim": int(train_env.observation_space.shape[0]),
        },
        "action_space": {str(action): label for action, label in ACTION_LABELS.items()},
        "reward_note": (
            "daily_return + equal_benchmark_weight*excess_vs_equal_bh + "
            "actual_benchmark_weight*excess_vs_actual_bh - underperform_0050_weight*underperform_0050 "
            "- drawdown_penalty_weight*current_drawdown - optional benchmark shortfall penalty"
        ),
        "price_note": "raw OHLC from yfinance auto_adjust=False plus explicit dividends cashflow",
        "train_eval": train_eval,
        **result,
        "equal_weight_buy_and_hold": equal_bh,
        "actual_holdings_buy_and_hold": actual_bh,
        "buy_and_hold_0050": bh_0050,
        "excess_return_vs_equal_bh": result["rl_metrics"]["total_return"] - equal_bh["metrics"]["total_return"],
        "excess_return_vs_actual_bh": result["rl_metrics"]["total_return"] - actual_bh["metrics"]["total_return"],
        "excess_return_vs_0050_bh": result["rl_metrics"]["total_return"] - bh_0050["metrics"]["total_return"],
        "excess_return_on_total_invested_vs_equal_bh": excess_vs_equal_on_total_invested,
        "excess_return_on_total_invested_vs_actual_bh": excess_vs_actual_on_total_invested,
        "excess_return_on_total_invested_vs_0050_bh": excess_vs_0050_on_total_invested,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = PROJECT_ROOT / "results" / (
        f"{_build_model_stem(args)}_backtest_{args.backtest_start.replace('-', '')}_{args.backtest_end.replace('-', '')}_"
        f"{timestamp}.json"
    )
    if len(str(output_file)) >= 240:
        output_file = PROJECT_ROOT / "results" / (
            f"portfolio_all_holdings_backtest_{args.backtest_start.replace('-', '')}_"
            f"{args.backtest_end.replace('-', '')}_{timestamp}.json"
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
    print(f"Actual holdings B&H final value: {actual_bh['final_value']:,.0f}")
    print(f"0050 B&H final value: {bh_0050['final_value']:,.0f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
