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

try:
    from .portfolio_config import COMMISSION_RATE, ETF_TAX_RATE
    from .portfolio_data_loader import MARKET_FEATURE_COLUMNS, download_all_stocks
    from .portfolio_train_v2 import calculate_backtest_metrics
except ImportError:
    from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE
    from portfolio_data_loader import MARKET_FEATURE_COLUMNS, download_all_stocks
    from portfolio_train_v2 import calculate_backtest_metrics


TICKERS = ["0050.TW", "0056.TW", "00713.TW", "00878.TW"]
TRAIN_START = "2009-01-01"
TRAIN_END = "2023-12-31"
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-05-15"
DOWNLOAD_END = "2026-05-22"
TIMESTEPS = 20_000
SEED = 42
BENCHMARK_WEIGHT = 2.0
BENCHMARK_SHORTFALL_PENALTY_WEIGHT = 0.0
BENCHMARK_SHORTFALL_PENALTY_CAP = 0.15
BENCHMARK_SHORTFALL_STRESS_SCALE = 0.50
STRESS_BUDGET_CAUTION_INVESTED_CAP = 0.92
STRESS_BUDGET_CAUTION_0050_CAP = 0.55
STRESS_BUDGET_RISK_OFF_INVESTED_CAP = 0.82
STRESS_BUDGET_RISK_OFF_0050_CAP = 0.45
STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP = 0.65
STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP = 0.30
DCA_DEFAULT_AMOUNTS = {
    "0050.TW": 5_000.0,
    "0056.TW": 5_000.0,
    "00713.TW": 5_000.0,
    "00878.TW": 10_000.0,
}

ACTION_LABELS = {
    0: "hold current weights",
    1: "25/25/25/25",
    2: "100% 0050",
    3: "50/30/10/10",
    4: "70/10/10/10 0050 core",
    5: "80/0/0/20 0050+00878 core",
    6: "15/25/25/35 high-dividend tilt",
    7: "0/40/30/30 defensive high-dividend tilt",
    8: "100% best 6M momentum ETF",
    9: "50/50 top-2 6M momentum ETFs",
    10: "35/20/10/10 +25% cash stress defense",
    11: "20/15/10/5 +50% cash deep defense",
}

RISK_ON_ACTIONS = {2, 4, 5, 8, 9}
DEFENSIVE_CASH_ACTIONS = {10, 11}


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


def get_active_derived_features(
    use_rsi_features: bool = False,
    use_market_regime_features: bool = False,
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
    benchmark_weight: float = BENCHMARK_WEIGHT,
    benchmark_shortfall_penalty_weight: float = BENCHMARK_SHORTFALL_PENALTY_WEIGHT,
    benchmark_shortfall_penalty_cap: float = BENCHMARK_SHORTFALL_PENALTY_CAP,
    benchmark_shortfall_stress_scale: float = BENCHMARK_SHORTFALL_STRESS_SCALE,
    stress_budget_caution_invested_cap: float = STRESS_BUDGET_CAUTION_INVESTED_CAP,
    stress_budget_caution_0050_cap: float = STRESS_BUDGET_CAUTION_0050_CAP,
    stress_budget_risk_off_invested_cap: float = STRESS_BUDGET_RISK_OFF_INVESTED_CAP,
    stress_budget_risk_off_0050_cap: float = STRESS_BUDGET_RISK_OFF_0050_CAP,
    stress_budget_deep_risk_off_invested_cap: float = STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP,
    stress_budget_deep_risk_off_0050_cap: float = STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP,
    min_rebalance_days: int = 20,
    stress_rebalance_cooldown_days: int | None = 0,
    stress_confirm_days: int = 3,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    use_rsi_features: bool = False,
    use_market_regime_features: bool = False,
    enable_range_harvest: bool = False,
    range_drift_threshold: float = 0.05,
    enable_pva_sigmoid: bool = False,
    pva_weight: float = 0.30,
    pva_drift_threshold: float = 0.05,
    dca_monthly_amounts: dict[str, float] | None = None,
    dca_day: int = 26,
) -> dict:
    env_kwargs = {
        "turnover_penalty": float(turnover_penalty),
        "benchmark_weight": float(benchmark_weight),
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
        "min_weight": float(min_weight),
        "max_weight": float(max_weight),
        "active_derived_features": get_active_derived_features(
            use_rsi_features,
            use_market_regime_features,
        ),
        "enable_range_harvest": bool(enable_range_harvest),
        "range_drift_threshold": float(range_drift_threshold),
        "enable_pva_sigmoid": bool(enable_pva_sigmoid),
        "pva_weight": float(pva_weight),
        "pva_drift_threshold": float(pva_drift_threshold),
    }
    if dca_monthly_amounts:
        env_kwargs.update(
            {
                "dca_monthly_amounts": {ticker: float(amount) for ticker, amount in dca_monthly_amounts.items()},
                "dca_day": int(dca_day),
            }
        )
    return env_kwargs


def env_kwargs_from_result_payload(payload: dict, *, include_dca: bool | None = None) -> dict:
    constraints = payload.get("constraints", {})
    range_cfg = payload.get("range_harvest_config", {})
    pva_cfg = payload.get("pva_sigmoid_config", {})
    stress_cfg = payload.get("stress_guardrail_config", {})
    feature_cfg = payload.get("feature_config", {})
    reward_cfg = payload.get("reward_config", {})
    risk_budget_cfg = payload.get("risk_budget_config", {})

    active_features = feature_cfg.get("active_derived_portfolio_features")
    use_rsi_features = bool(feature_cfg.get("rsi_features_enabled", False))
    use_market_regime_features = bool(feature_cfg.get("market_regime_features_enabled", False))
    stress_cooldown = (
        stress_cfg.get("stress_rebalance_cooldown_days")
        if stress_cfg
        else None
    )
    stress_confirm_days = (
        int(stress_cfg.get("stress_confirm_days", 1))
        if stress_cfg
        else 1
    )
    env_kwargs = build_env_kwargs(
        turnover_penalty=constraints.get("turnover_penalty", 0.001),
        benchmark_weight=reward_cfg.get("benchmark_weight", BENCHMARK_WEIGHT),
        benchmark_shortfall_penalty_weight=reward_cfg.get(
            "benchmark_shortfall_penalty_weight",
            BENCHMARK_SHORTFALL_PENALTY_WEIGHT,
        ),
        benchmark_shortfall_penalty_cap=reward_cfg.get(
            "benchmark_shortfall_penalty_cap",
            BENCHMARK_SHORTFALL_PENALTY_CAP,
        ),
        benchmark_shortfall_stress_scale=reward_cfg.get(
            "benchmark_shortfall_stress_scale",
            BENCHMARK_SHORTFALL_STRESS_SCALE,
        ),
        stress_budget_caution_invested_cap=risk_budget_cfg.get(
            "caution_invested_cap",
            STRESS_BUDGET_CAUTION_INVESTED_CAP,
        ),
        stress_budget_caution_0050_cap=risk_budget_cfg.get(
            "caution_0050_cap",
            STRESS_BUDGET_CAUTION_0050_CAP,
        ),
        stress_budget_risk_off_invested_cap=risk_budget_cfg.get(
            "risk_off_invested_cap",
            STRESS_BUDGET_RISK_OFF_INVESTED_CAP,
        ),
        stress_budget_risk_off_0050_cap=risk_budget_cfg.get(
            "risk_off_0050_cap",
            STRESS_BUDGET_RISK_OFF_0050_CAP,
        ),
        stress_budget_deep_risk_off_invested_cap=risk_budget_cfg.get(
            "deep_risk_off_invested_cap",
            STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP,
        ),
        stress_budget_deep_risk_off_0050_cap=risk_budget_cfg.get(
            "deep_risk_off_0050_cap",
            STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP,
        ),
        min_rebalance_days=constraints.get("min_rebalance_days", 20),
        stress_rebalance_cooldown_days=stress_cooldown,
        stress_confirm_days=stress_confirm_days,
        min_weight=constraints.get("min_weight", 0.0),
        max_weight=constraints.get("max_weight", 1.0),
        use_rsi_features=use_rsi_features,
        use_market_regime_features=use_market_regime_features,
        enable_range_harvest=bool(range_cfg.get("enabled", False)),
        range_drift_threshold=range_cfg.get("range_drift_threshold", 0.05),
        enable_pva_sigmoid=bool(pva_cfg.get("enabled", False)),
        pva_weight=pva_cfg.get("pva_weight", 0.30),
        pva_drift_threshold=pva_cfg.get("pva_drift_threshold", 0.05),
    )
    if active_features:
        env_kwargs["active_derived_features"] = list(active_features)

    if include_dca is None:
        include_dca = bool(payload.get("dca_enabled", False))
    if include_dca:
        dca_cfg = payload.get("dca_config", {})
        env_kwargs.update(
            {
                "dca_monthly_amounts": {
                    ticker: float(amount)
                    for ticker, amount in (dca_cfg.get("monthly_amounts") or {}).items()
                    if ticker in TICKERS
                },
                "dca_day": int(dca_cfg.get("dca_day", 26)),
            }
        )
    return env_kwargs


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
        cols.extend([c for c in PER_TICKER_CONTEXT_COLUMNS if c in df.columns])
        if "dividends" in df.columns:
            cols.append("dividends")
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")

    reference_df = _slice_by_date(stock_data[TICKERS[0]], start, end)
    shared_market_cols = ["date"] + [c for c in SHARED_MARKET_FEATURE_COLUMNS if c in reference_df.columns]
    if len(shared_market_cols) > 1:
        panel = panel.merge(reference_df[shared_market_cols].copy(), on="date", how="left")

    panel = panel.sort_values("date").reset_index(drop=True)
    panel = panel.ffill().bfill().fillna(0.0)
    panel = _add_portfolio_features(panel)
    return panel


def _safe_col(panel: pd.DataFrame, ticker: str, feature: str, default: float = 0.0) -> pd.Series:
    col = f"{ticker}_{feature}"
    if col in panel.columns:
        return panel[col].astype(float)
    return pd.Series(default, index=panel.index, dtype=float)


def _shared_market_col(panel: pd.DataFrame, feature: str, default: float = 0.0) -> pd.Series:
    if feature in panel.columns:
        return panel[feature].astype(float)
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
    panel["0050_sector_correlation"] = _safe_col(panel, "0050.TW", "sector_correlation")
    high_dividend_sector_corr = pd.concat(
        [_safe_col(panel, ticker, "sector_correlation") for ticker in high_dividend],
        axis=1,
    )
    panel["high_dividend_sector_correlation_avg"] = high_dividend_sector_corr.mean(axis=1)
    panel["0050_vs_high_dividend_corr_gap"] = (
        panel["0050_sector_correlation"] - panel["high_dividend_sector_correlation_avg"]
    )

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

    # Shared market features are merged only once into the panel, then converted
    # into low-dimensional regime signals so PPO can react to broad risk-on/off
    # conditions without duplicating the same macro columns per ETF.
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
        benchmark_weight: float = BENCHMARK_WEIGHT,
        benchmark_shortfall_penalty_weight: float = BENCHMARK_SHORTFALL_PENALTY_WEIGHT,
        benchmark_shortfall_penalty_cap: float = BENCHMARK_SHORTFALL_PENALTY_CAP,
        benchmark_shortfall_stress_scale: float = BENCHMARK_SHORTFALL_STRESS_SCALE,
        stress_budget_caution_invested_cap: float = STRESS_BUDGET_CAUTION_INVESTED_CAP,
        stress_budget_caution_0050_cap: float = STRESS_BUDGET_CAUTION_0050_CAP,
        stress_budget_risk_off_invested_cap: float = STRESS_BUDGET_RISK_OFF_INVESTED_CAP,
        stress_budget_risk_off_0050_cap: float = STRESS_BUDGET_RISK_OFF_0050_CAP,
        stress_budget_deep_risk_off_invested_cap: float = STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP,
        stress_budget_deep_risk_off_0050_cap: float = STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP,
        min_rebalance_days: int = 20,
        stress_rebalance_cooldown_days: int | None = 0,
        stress_confirm_days: int = 3,
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
        self._default_array_cache: dict[float, np.ndarray] = {}
        self._column_array_cache: dict[tuple[str, float], np.ndarray] = {}
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.tax_rate = float(tax_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.benchmark_weight = float(benchmark_weight)
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
        self.min_weight = float(min_weight)
        self.max_weight = float(max_weight)
        self.active_derived_features = active_derived_features or ACTIVE_DERIVED_FEATURE_COLUMNS
        self.dca_monthly_amounts = dca_monthly_amounts or {}
        self.dca_amount_array = np.array([float(self.dca_monthly_amounts.get(ticker, 0.0)) for ticker in TICKERS])
        self.dca_day = int(dca_day)
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
        self._prepare_runtime_views()
        self.dca_schedule = self._build_dca_schedule()

        self.portfolio_state_dim = len(TICKERS) + 6
        obs_dim = len(self.feature_cols) + self.portfolio_state_dim
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(len(ACTION_LABELS))
        self.reset()

    def _default_array(self, value: float) -> np.ndarray:
        value = float(value)
        array = self._default_array_cache.get(value)
        if array is None:
            array = np.full(len(self.panel), value, dtype=float)
            self._default_array_cache[value] = array
        return array

    def _column_array(self, column: str, default: float = 0.0) -> np.ndarray:
        key = (column, float(default))
        array = self._column_array_cache.get(key)
        if array is not None:
            return array
        if column in self.panel.columns:
            array = (
                pd.to_numeric(self.panel[column], errors="coerce")
                .fillna(default)
                .to_numpy(dtype=float, copy=False)
            )
        else:
            array = self._default_array(default)
        self._column_array_cache[key] = array
        return array

    def _ticker_matrix(self, feature: str, default: float = 0.0) -> np.ndarray:
        return np.column_stack([self._column_array(f"{ticker}_{feature}", default) for ticker in TICKERS])

    def _prepare_runtime_views(self) -> None:
        self.date_series = pd.to_datetime(self.panel["date"]).reset_index(drop=True)
        self.date_values = self.date_series.to_numpy(dtype="datetime64[ns]")
        self.date_strings = self.date_series.dt.strftime("%Y-%m-%d").to_numpy()

        if self.feature_cols:
            self.feature_matrix = np.column_stack([self._column_array(col, 0.0) for col in self.feature_cols])
        else:
            self.feature_matrix = np.empty((len(self.panel), 0), dtype=float)

        self.momentum_126_matrix = self._ticker_matrix("momentum_126", 0.0)
        self.pva_close_ma120_matrix = self._ticker_matrix("close_ma120_ratio", 0.0)
        self.pva_momentum_63_matrix = self._ticker_matrix("momentum_63", 0.0)
        self.pva_close_ma240_matrix = self._ticker_matrix("close_ma240_ratio", 0.0)

        self.pva_p_array = self._column_array("0050_pva_p", 0.0)
        self.pva_v_array = self._column_array("0050_pva_v", 0.0)
        self.pva_a_array = self._column_array("0050_pva_a", 0.0)
        self.pva_p_z_array = self._column_array("0050_pva_p_z", 0.0)
        self.pva_v_z_array = self._column_array("0050_pva_v_z", 0.0)
        self.pva_a_z_array = self._column_array("0050_pva_a_z", 0.0)
        self.local_trend_score_array = self._column_array("0050_trend_score", 1.0)
        self.drawdown_risk_array = self._column_array("0050_drawdown_risk", 0.0)

        near_ma120 = np.abs(self._column_array("0050.TW_close_ma120_ratio", 0.0)) <= 0.08
        near_ma240 = np.abs(self._column_array("0050.TW_close_ma240_ratio", 0.0)) <= 0.10
        muted_momentum = np.abs(self._column_array("0050.TW_momentum_126", 0.0)) <= 0.12
        volatility_ok = self._column_array("0050_volatility_rank_252", 0.5) <= 0.65
        drawdown_ok = self.drawdown_risk_array <= 0.15
        dispersion_ok = np.abs(self._column_array("momentum_dispersion_126", 0.0)) <= 0.12
        self.range_bound_mask = (near_ma120 | near_ma240) & muted_momentum & volatility_ok & drawdown_ok & dispersion_ok

        self.sjm_state_code_array = np.zeros(len(self.panel), dtype=np.int8)
        greed_mask = (self.pva_v_z_array > 1.0) & (self.pva_a_z_array > 0.0)
        panic_mask = (self.pva_a_z_array < -2.0) | (self.pva_v_z_array < -2.0)
        self.sjm_state_code_array[greed_mask] = 1
        self.sjm_state_code_array[panic_mask] = -1

        self.market_stress_score_array = self._column_array("market_stress_score", 0.0)
        self.market_trend_score_array = self._column_array("market_trend_score", 0.0)
        self.cross_market_gap_array = self._column_array("cross_market_momentum_gap", 0.0)
        deep_risk_off_mask = (
            (self.market_stress_score_array >= 0.60)
            | (
                (self.market_stress_score_array >= 0.45)
                & (self.market_trend_score_array <= -0.25)
            )
        )
        risk_off_mask = (
            (self.market_stress_score_array >= 0.35)
            | (
                (self.market_stress_score_array >= 0.20)
                & (self.market_trend_score_array < -0.10)
            )
            | (self.market_trend_score_array <= -0.35)
        )
        self.market_stress_level_array = np.full(len(self.panel), "normal", dtype=object)
        self.market_stress_level_array[risk_off_mask] = "risk_off"
        self.market_stress_level_array[deep_risk_off_mask] = "deep_risk_off"

        self.stress_risk_off_streak = np.zeros(len(self.panel), dtype=np.int32)
        self.stress_deep_risk_off_streak = np.zeros(len(self.panel), dtype=np.int32)
        for idx in range(len(self.panel)):
            if risk_off_mask[idx]:
                self.stress_risk_off_streak[idx] = 1 + (self.stress_risk_off_streak[idx - 1] if idx > 0 else 0)
            if deep_risk_off_mask[idx]:
                self.stress_deep_risk_off_streak[idx] = 1 + (
                    self.stress_deep_risk_off_streak[idx - 1] if idx > 0 else 0
                )

    def _constrain_weights(self, weights: np.ndarray, target_total: float = 1.0) -> np.ndarray:
        weights = np.asarray(weights, dtype=float)
        weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)
        weights = np.clip(weights, 0.0, None)
        target_total = float(np.clip(target_total, 0.0, 1.0))
        min_total = min(1.0, self.min_weight * len(TICKERS))
        if 0.0 < target_total < min_total:
            target_total = min_total
        if target_total <= 0.0:
            return np.zeros(len(TICKERS), dtype=float)

        if weights.sum() <= 0:
            weights = np.ones(len(TICKERS), dtype=float)
        weights = weights / weights.sum() * target_total

        if self.min_weight <= 0 and self.max_weight >= 1:
            return weights
        if self.min_weight * len(TICKERS) > 1.0:
            raise ValueError("min_weight is too high for the number of assets")
        if self.max_weight * len(TICKERS) < target_total:
            raise ValueError("max_weight is too low for the target invested weight")

        weights = np.maximum(weights, self.min_weight)
        weights = weights / weights.sum() * target_total
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
        total = float(weights.sum())
        if total <= 0:
            return np.zeros(len(TICKERS), dtype=float)
        return weights / total * target_total

    @staticmethod
    def _cash_weight_from_asset_weights(weights: np.ndarray) -> float:
        return float(max(0.0, 1.0 - float(np.asarray(weights, dtype=float).sum())))

    def _blend_target_weights(self, base_weights: np.ndarray, defensive_weights: np.ndarray, defensive_mix: float) -> np.ndarray:
        defensive_mix = float(np.clip(defensive_mix, 0.0, 1.0))
        blended = (1.0 - defensive_mix) * np.asarray(base_weights, dtype=float) + defensive_mix * np.asarray(
            defensive_weights,
            dtype=float,
        )
        target_total = float(np.clip(blended.sum(), min(1.0, self.min_weight * len(TICKERS)), 1.0))
        return self._constrain_weights(blended, target_total=target_total)

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _is_range_bound(self, idx: int) -> bool:
        return bool(self.range_bound_mask[idx])

    def _sjm_state(self, idx: int) -> tuple[str, dict]:
        # SJM 是刻意保持很小的狀態機：
        # - M（恐慌）：動能或加速度落在近期統計極端。
        # - J（貪婪）：動能偏強，而且仍在向上加速。
        # - S（平靜）：其他全部情況。S 本來就會佔大多數，2026-05-10
        #   修正後不再讓 S 觸發 PVA overlay，因為先前測試證明 S 狀態
        #   再平衡容易製造錯誤買點。
        state_code = int(self.sjm_state_code_array[idx])
        if state_code < 0:
            state = "M"
        elif state_code > 0:
            state = "J"
        else:
            state = "S"
        p_z = float(self.pva_p_z_array[idx])
        v_z = float(self.pva_v_z_array[idx])
        a_z = float(self.pva_a_z_array[idx])
        return state, {
            "p": float(self.pva_p_array[idx]),
            "v": float(self.pva_v_array[idx]),
            "a": float(self.pva_a_array[idx]),
            "p_z": p_z,
            "v_z": v_z,
            "a_z": a_z,
            "state": state,
        }

    def _pva_sigmoid_weights(self, idx: int) -> tuple[np.ndarray, dict]:
        sjm_state, sjm_details = self._sjm_state(idx)
        scores = []
        details = {}
        p_row = self.pva_close_ma120_matrix[idx]
        v_row = self.pva_momentum_63_matrix[idx]
        v_prev_row = self.pva_momentum_63_matrix[max(idx - 20, 0)]
        long_trend_row = self.pva_close_ma240_matrix[idx]
        for asset_idx, ticker in enumerate(TICKERS):
            p = float(p_row[asset_idx])
            v = float(v_row[asset_idx])
            v_prev = float(v_prev_row[asset_idx])
            a = v - v_prev
            long_trend = float(long_trend_row[asset_idx])

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
        start = self.date_series.min().to_period("M")
        end = self.date_series.max().to_period("M")
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
        current_date = pd.Timestamp(self.date_values[idx])
        current_date_str = self.date_strings[idx]
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
                    "date": current_date_str,
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

    def _benchmark_shortfall_penalty(self, idx: int, portfolio_value: float, stress_snapshot: dict) -> dict:
        equal_relative = portfolio_value / max(float(self.equal_bh_curve[idx]), 1.0) - 1.0
        bh_0050_relative = portfolio_value / max(float(self.bh_0050_curve[idx]), 1.0) - 1.0
        # 0050 remains the primary beta benchmark, but equal-weight B&H still
        # matters as a diversification floor. Use a half-weight penalty for the
        # equal-weight shortfall so PPO does not ignore it entirely.
        raw_shortfall = max(
            max(-bh_0050_relative, 0.0),
            0.5 * max(-equal_relative, 0.0),
        )
        capped_shortfall = min(float(raw_shortfall), self.benchmark_shortfall_penalty_cap)
        stress_score = float(np.clip(stress_snapshot.get("score", 0.0), 0.0, 1.0))
        stress_multiplier = 1.0 + self.benchmark_shortfall_stress_scale * stress_score
        penalty = self.benchmark_shortfall_penalty_weight * capped_shortfall * stress_multiplier
        return {
            "equal_relative": float(equal_relative),
            "bh_0050_relative": float(bh_0050_relative),
            "raw_shortfall": float(raw_shortfall),
            "capped_shortfall": float(capped_shortfall),
            "stress_multiplier": float(stress_multiplier),
            "penalty": float(penalty),
        }

    def _stress_risk_budget_profile(self, idx: int, stress_snapshot: dict) -> dict:
        score = float(stress_snapshot.get("score", 0.0))
        trend_score = float(stress_snapshot.get("trend_score", 0.0))
        level = str(stress_snapshot.get("level", "normal"))
        local_trend_score = float(self.local_trend_score_array[idx])
        drawdown_risk = float(self.drawdown_risk_array[idx])
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
        # Caution mode is intentionally softer than the cash guardrail. It
        # triggers earlier during slow negative regimes so the allocator can
        # trim beta before the full stress-confirmation path is satisfied.
        # It still requires local weakness in 0050; otherwise strong bull
        # windows like 2024 Q1 get over-trimmed by mild macro noise.
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
            "core_0050_cap": self.max_weight,
        }

    def _apply_stress_risk_budget(self, idx: int, weights: np.ndarray, stress_snapshot: dict) -> tuple[np.ndarray, dict]:
        profile = self._stress_risk_budget_profile(idx, stress_snapshot)
        budget_level = str(profile["budget_level"])
        original = np.clip(np.asarray(weights, dtype=float), 0.0, None)
        adjusted = original.copy()
        original_total = float(original.sum())
        original_0050 = float(original[0]) if len(original) else 0.0
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
            adjusted = np.zeros(len(TICKERS), dtype=float)

        if len(adjusted) > 0 and adjusted[0] > core_0050_cap:
            adjusted[0] = core_0050_cap

        room_to_target = max(target_total - float(adjusted.sum()), 0.0)
        if room_to_target > 1e-9 and len(adjusted) > 1:
            beneficiaries = np.arange(1, len(adjusted))
            base = adjusted[beneficiaries].copy()
            capacity = np.maximum(self.max_weight - adjusted[beneficiaries], 0.0)
            remaining = room_to_target
            for _ in range(4):
                active = capacity > 1e-9
                if remaining <= 1e-9 or not active.any():
                    break
                basis = base.copy()
                basis[~active] = 0.0
                if basis.sum() <= 0.0:
                    basis = active.astype(float)
                increments = remaining * basis / basis.sum()
                increments = np.minimum(increments, capacity)
                adjusted[beneficiaries] += increments
                remaining -= float(increments.sum())
                capacity = np.maximum(self.max_weight - adjusted[beneficiaries], 0.0)

        adjusted = np.clip(adjusted, 0.0, self.max_weight)
        if float(adjusted.sum()) > invested_cap and adjusted.sum() > 0.0:
            adjusted *= invested_cap / float(adjusted.sum())

        post_total = float(adjusted.sum())
        post_0050 = float(adjusted[0]) if len(adjusted) else 0.0
        applied = bool(
            abs(post_total - original_total) > 1e-9
            or abs(post_0050 - original_0050) > 1e-9
        )
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

    def _market_stress_snapshot(self, idx: int) -> dict:
        stress_score = float(self.market_stress_score_array[idx])
        trend_score = float(self.market_trend_score_array[idx])
        cross_market_gap = float(self.cross_market_gap_array[idx])
        level = str(self.market_stress_level_array[idx])
        return {
            "score": stress_score,
            "trend_score": trend_score,
            "cross_market_gap": cross_market_gap,
            "level": level,
        }

    @staticmethod
    def _cash_tier_action_from_weight(cash_weight: float) -> int:
        cash_weight = float(np.clip(cash_weight, 0.0, 1.0))
        if cash_weight >= 0.375:
            return 11
        if cash_weight >= 0.125:
            return 10
        return 0

    def _stress_confirmation_streak(self, idx: int, target_action: int) -> int:
        if target_action == 11:
            return int(self.stress_deep_risk_off_streak[idx])
        if target_action == 10:
            return int(self.stress_risk_off_streak[idx])
        return 0

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
        if action == 10:
            return self._constrain_weights(np.array([0.35, 0.20, 0.10, 0.10], dtype=float), target_total=0.75)
        if action == 11:
            return self._constrain_weights(np.array([0.20, 0.15, 0.10, 0.05], dtype=float), target_total=0.50)

        order = np.argsort(self.momentum_126_matrix[self.step_idx])[::-1]
        weights = np.zeros(len(TICKERS), dtype=float)
        if action == 8:
            weights[order[0]] = 1.0
        else:
            weights[order[:2]] = 0.5
        return self._constrain_weights(weights)

    def _stress_guardrail_target(
        self,
        action: int,
        base_target_weights: np.ndarray,
        current_weights: np.ndarray,
        stress_snapshot: dict,
    ) -> tuple[np.ndarray | None, dict]:
        level = stress_snapshot["level"]
        current_cash_weight = self._cash_weight_from_asset_weights(current_weights)
        current_cash_tier_action = self._cash_tier_action_from_weight(current_cash_weight)
        if level == "normal":
            return None, {
                "applied": False,
                "reason": "normal_market",
                "current_cash_tier_action": current_cash_tier_action,
                "current_cash_weight": current_cash_weight,
            }

        if level == "deep_risk_off" and action not in {11}:
            target_action = 11
        elif level == "risk_off":
            target_action = 10
        elif level == "deep_risk_off":
            target_action = 11
        else:
            return None, {
                "applied": False,
                "reason": "stress_guardrail_not_needed",
                "current_cash_tier_action": current_cash_tier_action,
                "current_cash_weight": current_cash_weight,
            }

        confirm_streak = self._stress_confirmation_streak(self.step_idx, target_action)
        if confirm_streak < self.stress_confirm_days:
            return None, {
                "applied": False,
                "reason": f"stress_wait_confirm_{confirm_streak}d",
                "target_action": target_action,
                "target_label": ACTION_LABELS[target_action],
                "level": level,
                "confirm_streak": int(confirm_streak),
                "required_confirm_days": int(self.stress_confirm_days),
                "current_cash_tier_action": current_cash_tier_action,
                "current_cash_weight": current_cash_weight,
            }

        if current_cash_tier_action == target_action:
            return None, {
                "applied": False,
                "reason": "stress_same_cash_tier",
                "target_action": target_action,
                "target_label": ACTION_LABELS[target_action],
                "level": level,
                "confirm_streak": int(confirm_streak),
                "required_confirm_days": int(self.stress_confirm_days),
                "current_cash_tier_action": current_cash_tier_action,
                "current_cash_weight": current_cash_weight,
            }

        return self._target_weights(target_action), {
            "applied": True,
            "reason": "market_stress_deep_risk_off" if target_action == 11 else "market_stress_cash_defense",
            "target_action": target_action,
            "target_label": ACTION_LABELS[target_action],
            "level": level,
            "confirm_streak": int(confirm_streak),
            "required_confirm_days": int(self.stress_confirm_days),
            "current_cash_tier_action": current_cash_tier_action,
            "current_cash_weight": current_cash_weight,
        }

    def _plan_trade(self, action: int) -> dict:
        action = int(action)
        current_weights = self.weights.copy()
        base_target_weights = self._target_weights(action)
        raw_action_turnover = float(np.abs(base_target_weights - current_weights).sum())
        current_date = self.date_strings[self.step_idx]
        if self.last_rebalance_idx <= -10**8:
            since_last_rebalance = self.min_rebalance_days
            cooldown_remaining = 0
            stress_cooldown_remaining = 0
            can_trade_by_schedule = True
            can_trade_by_stress_schedule = True
        else:
            since_last_rebalance = max(self.step_idx - self.last_rebalance_idx, 0)
            cooldown_remaining = max(self.min_rebalance_days - since_last_rebalance, 0)
            stress_cooldown_remaining = max(
                self.stress_rebalance_cooldown_days - since_last_rebalance,
                0,
            )
            can_trade_by_schedule = cooldown_remaining == 0
            can_trade_by_stress_schedule = stress_cooldown_remaining == 0

        sjm_state, sjm_details = self._sjm_state(self.step_idx)
        harvest_due, range_harvest_drift = self._range_harvest_due(self.step_idx)
        market_stress = self._market_stress_snapshot(self.step_idx)

        candidate_source = "hold"
        candidate_reason = "hold_action"
        candidate_target_weights = base_target_weights.copy()
        candidate_turnover = raw_action_turnover
        pva_allowed = False
        pva_weights = None
        pva_details = None
        pva_state_weight = 0.0
        pva_drift = 0.0
        stress_guardrail = {"applied": False, "reason": "not_evaluated"}
        stress_target_weights = None
        stress_blocks_ppo = False
        stress_risk_budget = {"applied": False, "reason": "not_evaluated"}

        if harvest_due:
            candidate_source = "range_harvest"
            candidate_reason = "range_bound_rebalance"
            candidate_target_weights = self.range_target_weights.copy()
            candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
        elif self.enable_pva_sigmoid:
            pva_allowed, _, _ = self._pva_overlay_allowed(self.step_idx)
            if pva_allowed:
                pva_weights, pva_details = self._pva_sigmoid_weights(self.step_idx)
                pva_state_weight = self.pva_weight
                if sjm_state == "M":
                    pva_state_weight = 1.0
                elif sjm_state == "J":
                    pva_state_weight = min(0.40, self.pva_weight)
                candidate_target_weights = self._constrain_weights(
                    (1.0 - pva_state_weight) * base_target_weights + pva_state_weight * pva_weights
                )
                pva_drift = float(np.abs(candidate_target_weights - current_weights).sum())
                candidate_turnover = pva_drift
                candidate_source = "pva_sigmoid"
                candidate_reason = f"pva_overlay_{sjm_state.lower()}"
        if candidate_source == "hold":
            stress_target_weights, stress_guardrail = self._stress_guardrail_target(
                action=action,
                base_target_weights=base_target_weights,
                current_weights=current_weights,
                stress_snapshot=market_stress,
            )
            if stress_guardrail.get("applied"):
                candidate_target_weights = stress_target_weights.copy()
                candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
                candidate_source = "market_stress"
                candidate_reason = str(stress_guardrail["reason"])
            elif stress_guardrail.get("target_action") is not None:
                stress_blocks_ppo = True
                candidate_reason = str(stress_guardrail["reason"])
            elif action != 0:
                candidate_source = "ppo_action"
                candidate_reason = ACTION_LABELS.get(action, f"action_{action}")

        risk_budget_input_weights = candidate_target_weights.copy()
        if stress_blocks_ppo:
            risk_budget_input_weights = current_weights.copy()
        risk_budget_weights, stress_risk_budget = self._apply_stress_risk_budget(
            self.step_idx,
            risk_budget_input_weights,
            market_stress,
        )
        if stress_risk_budget.get("applied"):
            candidate_target_weights = risk_budget_weights.copy()
            candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
            if stress_blocks_ppo or candidate_source == "hold":
                candidate_source = "stress_budget"
                candidate_reason = str(stress_risk_budget["reason"])
            else:
                candidate_reason = f"{candidate_reason}+{stress_risk_budget['budget_level']}"

        execute_trade = False
        execution_source = "hold"
        effective_target_weights = current_weights.copy()
        reward_turnover = 0.0
        final_reason = candidate_reason

        if harvest_due:
            if can_trade_by_schedule:
                execute_trade = True
                execution_source = "range_harvest"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"cooldown_{cooldown_remaining}d"
                reward_turnover = raw_action_turnover if action != 0 else 0.0
        elif self.enable_pva_sigmoid and pva_allowed:
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
        elif stress_guardrail.get("applied"):
            if can_trade_by_stress_schedule:
                execute_trade = True
                execution_source = "market_stress"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"stress_cooldown_{stress_cooldown_remaining}d"
                reward_turnover = candidate_turnover
        elif candidate_source == "stress_budget":
            if can_trade_by_stress_schedule:
                execute_trade = True
                execution_source = "stress_budget"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"stress_cooldown_{stress_cooldown_remaining}d"
                reward_turnover = candidate_turnover
        elif action != 0 and not stress_blocks_ppo:
            if can_trade_by_schedule:
                execute_trade = True
                execution_source = "ppo_action"
                effective_target_weights = candidate_target_weights.copy()
                reward_turnover = candidate_turnover
            else:
                final_reason = f"cooldown_{cooldown_remaining}d"
                reward_turnover = candidate_turnover
        else:
            if stress_blocks_ppo:
                final_reason = candidate_reason
            else:
                final_reason = "hold_action"

        return {
            "date": current_date,
            "step_idx": int(self.step_idx),
            "action": action,
            "action_label": ACTION_LABELS.get(action, f"action_{action}"),
            "sjm_state": sjm_state,
            "sjm_details": sjm_details,
            "market_stress": market_stress,
            "stress_guardrail": stress_guardrail,
            "stress_risk_budget": stress_risk_budget,
            "current_weights": current_weights,
            "base_target_weights": base_target_weights,
            "candidate_target_weights": candidate_target_weights,
            "effective_target_weights": effective_target_weights,
            "raw_action_turnover": float(raw_action_turnover),
            "candidate_turnover": float(candidate_turnover),
            "reward_turnover": float(reward_turnover),
            "days_since_last_rebalance": int(since_last_rebalance),
            "cooldown_remaining": int(cooldown_remaining),
            "stress_cooldown_remaining": int(stress_cooldown_remaining),
            "can_trade_by_schedule": bool(can_trade_by_schedule),
            "can_trade_by_stress_schedule": bool(can_trade_by_stress_schedule),
            "range_harvest_due": bool(harvest_due),
            "range_harvest_drift": float(range_harvest_drift),
            "pva_allowed": bool(pva_allowed),
            "pva_weights": pva_weights,
            "pva_details": pva_details,
            "pva_state_weight": float(pva_state_weight),
            "pva_drift": float(pva_drift),
            "candidate_source": candidate_source,
            "candidate_reason": candidate_reason,
            "execute_trade": bool(execute_trade),
            "execution_source": execution_source,
            "reason": final_reason,
        }

    def plan_action(self, action: int) -> dict:
        plan = self._plan_trade(action)

        def _weights_dict(weights: np.ndarray) -> dict[str, float]:
            return {ticker: float(weight) for ticker, weight in zip(TICKERS, weights)}

        price_row = self.price_array[self.step_idx]
        current_cash_weight = self._cash_weight_from_asset_weights(plan["current_weights"])
        base_target_cash_weight = self._cash_weight_from_asset_weights(plan["base_target_weights"])
        candidate_target_cash_weight = self._cash_weight_from_asset_weights(plan["candidate_target_weights"])
        effective_target_cash_weight = self._cash_weight_from_asset_weights(plan["effective_target_weights"])
        return {
            "date": plan["date"],
            "step_idx": plan["step_idx"],
            "action": plan["action"],
            "action_label": plan["action_label"],
            "candidate_source": plan["candidate_source"],
            "execution_source": plan["execution_source"],
            "reason": plan["reason"],
            "can_trade_now": bool(plan["execute_trade"]),
            "days_since_last_rebalance": int(plan["days_since_last_rebalance"]),
            "cooldown_remaining": int(plan["cooldown_remaining"]),
            "stress_cooldown_remaining": int(plan["stress_cooldown_remaining"]),
            "range_harvest_due": bool(plan["range_harvest_due"]),
            "range_harvest_drift": float(plan["range_harvest_drift"]),
            "can_trade_by_stress_schedule": bool(plan["can_trade_by_stress_schedule"]),
            "pva_allowed": bool(plan["pva_allowed"]),
            "pva_state_weight": float(plan["pva_state_weight"]),
            "pva_drift": float(plan["pva_drift"]),
            "sjm_state": plan["sjm_state"],
            "sjm_details": plan["sjm_details"],
            "market_stress": plan["market_stress"],
            "stress_guardrail": plan["stress_guardrail"],
            "stress_risk_budget": plan["stress_risk_budget"],
            "current_weights": _weights_dict(plan["current_weights"]),
            "current_cash_weight": current_cash_weight,
            "base_target_weights": _weights_dict(plan["base_target_weights"]),
            "base_target_cash_weight": base_target_cash_weight,
            "candidate_target_weights": _weights_dict(plan["candidate_target_weights"]),
            "candidate_target_cash_weight": candidate_target_cash_weight,
            "effective_target_weights": _weights_dict(plan["effective_target_weights"]),
            "effective_target_cash_weight": effective_target_cash_weight,
            "raw_action_turnover": float(plan["raw_action_turnover"]),
            "candidate_turnover": float(plan["candidate_turnover"]),
            "reward_turnover": float(plan["reward_turnover"]),
            "latest_prices": {ticker: float(price) for ticker, price in zip(TICKERS, price_row)},
            "pva_weights": (
                None
                if plan["pva_weights"] is None
                else {ticker: float(weight) for ticker, weight in zip(TICKERS, plan["pva_weights"])}
            ),
            "pva_details": plan["pva_details"],
        }

    def _get_obs(self) -> np.ndarray:
        features = self.feature_matrix[self.step_idx]
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
        prices = self.price_array[self.step_idx]
        value_before = self._portfolio_value(prices)
        fees = 0.0
        decision = self._plan_trade(int(action))
        turnover = float(decision["reward_turnover"])
        self.sjm_state_history.append(
            {
                "date": decision["date"],
                **decision["sjm_details"],
            }
        )
        if decision["execute_trade"]:
            fees = self._rebalance(decision["effective_target_weights"], prices)
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
                            "step_idx": int(self.step_idx),
                            "drift": float(decision["range_harvest_drift"]),
                            "target_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(TICKERS, decision["effective_target_weights"])
                            },
                        }
                    )
                elif decision["execution_source"] == "pva_sigmoid":
                    self.pva_sigmoid_count += 1
                    self.pva_sigmoid_history.append(
                        {
                            "date": decision["date"],
                            "step_idx": int(self.step_idx),
                            "sjm_state": decision["sjm_state"],
                            "drift": float(decision["pva_drift"]),
                            "pva_weight": float(decision["pva_state_weight"]),
                            "pva_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(TICKERS, decision["pva_weights"])
                            },
                            "target_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(TICKERS, decision["effective_target_weights"])
                            },
                            "details": decision["pva_details"],
                        }
                    )
                elif decision["execution_source"] == "market_stress":
                    self.market_stress_count += 1
                    self.market_stress_history.append(
                        {
                            "date": decision["date"],
                            "step_idx": int(self.step_idx),
                            "reason": decision["reason"],
                            "market_stress": decision["market_stress"],
                            "target_cash_weight": self._cash_weight_from_asset_weights(
                                decision["effective_target_weights"]
                            ),
                            "target_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(TICKERS, decision["effective_target_weights"])
                            },
                        }
                    )
                elif decision["execution_source"] == "stress_budget":
                    self.stress_budget_count += 1
                    self.stress_budget_history.append(
                        {
                            "date": decision["date"],
                            "step_idx": int(self.step_idx),
                            "market_stress": decision["market_stress"],
                            "risk_budget": decision["stress_risk_budget"],
                            "target_cash_weight": self._cash_weight_from_asset_weights(
                                decision["effective_target_weights"]
                            ),
                            "target_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(TICKERS, decision["effective_target_weights"])
                            },
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
        self.peak_value = max(self.peak_value, value_after)
        self.equity_curve.append(value_after)
        self.weight_history.append(self.weights.copy().tolist())

        daily_return = value_after / max(value_before, 1.0) - 1
        equal_return = self.equal_bh_curve[self.step_idx] / self.equal_bh_curve[self.step_idx - 1] - 1
        bh_0050_return = self.bh_0050_curve[self.step_idx] / self.bh_0050_curve[self.step_idx - 1] - 1
        benchmark_return = max(float(equal_return), float(bh_0050_return))
        excess_return = daily_return - benchmark_return
        benchmark_penalty = self._benchmark_shortfall_penalty(
            self.step_idx,
            value_after,
            decision["market_stress"],
        )
        reward = float(
            (
                daily_return
                + self.benchmark_weight * excess_return
                - benchmark_penalty["penalty"]
            )
            * 100.0
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
            "market_stress_count": self.market_stress_count,
            "stress_budget_count": self.stress_budget_count,
            "decision_source": decision["execution_source"],
            "decision_reason": decision["reason"],
            "benchmark_penalty": benchmark_penalty,
            "weights": self.weights.copy(),
        }
        return self._get_obs(), reward, terminated, False, info


def _simulate_model(model: PPO, panel: pd.DataFrame, env_kwargs: dict | None = None) -> tuple[ETFPortfolioEnv, dict]:
    env = ETFPortfolioEnv(panel, **(env_kwargs or {}))
    obs, _ = env.reset()
    done = False
    info = {}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    return env, info


def _run_model(model: PPO, panel: pd.DataFrame, env_kwargs: dict | None = None) -> dict:
    env, info = _simulate_model(model, panel, env_kwargs)
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
        "market_stress_history": env.market_stress_history,
        "stress_budget_history": env.stress_budget_history,
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
    parser.add_argument("--benchmark-weight", type=float, default=BENCHMARK_WEIGHT)
    parser.add_argument(
        "--benchmark-shortfall-penalty-weight",
        type=float,
        default=BENCHMARK_SHORTFALL_PENALTY_WEIGHT,
    )
    parser.add_argument(
        "--benchmark-shortfall-penalty-cap",
        type=float,
        default=BENCHMARK_SHORTFALL_PENALTY_CAP,
    )
    parser.add_argument(
        "--benchmark-shortfall-stress-scale",
        type=float,
        default=BENCHMARK_SHORTFALL_STRESS_SCALE,
        help="extra multiplier applied to benchmark shortfall penalties under stressed market regimes",
    )
    parser.add_argument("--stress-budget-caution-invested-cap", type=float, default=STRESS_BUDGET_CAUTION_INVESTED_CAP)
    parser.add_argument("--stress-budget-caution-0050-cap", type=float, default=STRESS_BUDGET_CAUTION_0050_CAP)
    parser.add_argument("--stress-budget-risk-off-invested-cap", type=float, default=STRESS_BUDGET_RISK_OFF_INVESTED_CAP)
    parser.add_argument("--stress-budget-risk-off-0050-cap", type=float, default=STRESS_BUDGET_RISK_OFF_0050_CAP)
    parser.add_argument(
        "--stress-budget-deep-risk-off-invested-cap",
        type=float,
        default=STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP,
    )
    parser.add_argument(
        "--stress-budget-deep-risk-off-0050-cap",
        type=float,
        default=STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP,
    )
    parser.add_argument("--min-rebalance-days", type=int, default=20)
    parser.add_argument(
        "--stress-rebalance-cooldown-days",
        type=int,
        default=0,
        help="cooldown used only for market-stress cash-defense overrides; 0 means no extra delay",
    )
    parser.add_argument(
        "--stress-confirm-days",
        type=int,
        default=3,
        help="number of consecutive stress days required before cash-defense can override PPO",
    )
    parser.add_argument("--min-weight", type=float, default=0.0)
    parser.add_argument("--max-weight", type=float, default=1.0)
    parser.add_argument("--use-rsi-features", action="store_true")
    parser.add_argument(
        "--disable-market-regime-features",
        action="store_true",
        help="fall back to the legacy feature set without shared market-regime signals",
    )
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
    use_market_regime_features = not args.disable_market_regime_features

    print("=" * 72)
    print("0050+0056+00713+00878 portfolio PPO training/backtest")
    print(f"Train:    {args.train_start} ~ {args.train_end}")
    print(f"Backtest: {args.backtest_start} ~ {args.backtest_end}")
    print(f"Steps:    {args.timesteps:,}")
    print(f"Seed:     {args.seed}")
    print(
        "Constraints: "
        f"turnover_penalty={args.turnover_penalty}, "
        f"benchmark_weight={args.benchmark_weight}, "
        f"benchmark_shortfall_penalty_weight={args.benchmark_shortfall_penalty_weight}, "
        f"benchmark_shortfall_penalty_cap={args.benchmark_shortfall_penalty_cap}, "
        f"benchmark_shortfall_stress_scale={args.benchmark_shortfall_stress_scale}, "
        f"stress_budget_caps=({args.stress_budget_caution_invested_cap:.2f}/"
        f"{args.stress_budget_risk_off_invested_cap:.2f}/"
        f"{args.stress_budget_deep_risk_off_invested_cap:.2f}), "
        f"min_rebalance_days={args.min_rebalance_days}, "
        f"stress_rebalance_cooldown_days={args.stress_rebalance_cooldown_days}, "
        f"stress_confirm_days={args.stress_confirm_days}, "
        f"min_weight={args.min_weight}, max_weight={args.max_weight}, "
        f"use_rsi_features={args.use_rsi_features}, "
        f"use_market_regime_features={use_market_regime_features}, "
        f"enable_dca={args.enable_dca}, "
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

    active_derived_features = get_active_derived_features(
        args.use_rsi_features,
        use_market_regime_features,
    )

    env_kwargs = build_env_kwargs(
        turnover_penalty=args.turnover_penalty,
        benchmark_weight=args.benchmark_weight,
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
        min_weight=args.min_weight,
        max_weight=args.max_weight,
        use_rsi_features=args.use_rsi_features,
        use_market_regime_features=use_market_regime_features,
        enable_range_harvest=args.enable_range_harvest,
        range_drift_threshold=args.range_drift_threshold,
        enable_pva_sigmoid=args.enable_pva_sigmoid,
        pva_weight=args.pva_weight,
        pva_drift_threshold=args.pva_drift_threshold,
    )
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
    feature_tag_parts = [
        "features_v5",
        "market" if use_market_regime_features else "legacy",
        "rsi" if args.use_rsi_features else "reduced",
    ]
    feature_tag = "_".join(feature_tag_parts)
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
        eval_env_kwargs = build_env_kwargs(
            turnover_penalty=args.turnover_penalty,
            benchmark_weight=args.benchmark_weight,
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
            min_weight=args.min_weight,
            max_weight=args.max_weight,
            use_rsi_features=args.use_rsi_features,
            use_market_regime_features=use_market_regime_features,
            enable_range_harvest=args.enable_range_harvest,
            range_drift_threshold=args.range_drift_threshold,
            enable_pva_sigmoid=args.enable_pva_sigmoid,
            pva_weight=args.pva_weight,
            pva_drift_threshold=args.pva_drift_threshold,
            dca_monthly_amounts=dca_monthly_amounts,
            dca_day=args.dca_day,
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
        "reward_config": {
            "benchmark_weight": args.benchmark_weight,
            "benchmark_shortfall_penalty_weight": args.benchmark_shortfall_penalty_weight,
            "benchmark_shortfall_penalty_cap": args.benchmark_shortfall_penalty_cap,
            "benchmark_shortfall_stress_scale": args.benchmark_shortfall_stress_scale,
            "note": "Optional reward overlay. When benchmark_shortfall_penalty_weight > 0, reward subtracts a persistent shortfall penalty that prioritizes lagging 0050 and scales higher in stressed regimes.",
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
        "stress_guardrail_config": {
            "enabled": True,
            "stress_rebalance_cooldown_days": int(args.stress_rebalance_cooldown_days),
            "stress_confirm_days": int(args.stress_confirm_days),
            "risk_off_action": ACTION_LABELS[10],
            "deep_risk_off_action": ACTION_LABELS[11],
            "note": "Market-stress guardrails can use a shorter cooldown than the normal rebalance schedule.",
        },
        "risk_budget_config": {
            "caution_invested_cap": args.stress_budget_caution_invested_cap,
            "caution_0050_cap": args.stress_budget_caution_0050_cap,
            "risk_off_invested_cap": args.stress_budget_risk_off_invested_cap,
            "risk_off_0050_cap": args.stress_budget_risk_off_0050_cap,
            "deep_risk_off_invested_cap": args.stress_budget_deep_risk_off_invested_cap,
            "deep_risk_off_0050_cap": args.stress_budget_deep_risk_off_0050_cap,
            "note": "Softer than the cash guardrail. This layer trims total invested weight and caps 0050 concentration during caution/risk-off regimes before or alongside full cash-defense actions.",
        },
        "feature_config": {
            "base_features_per_ticker": FEATURE_COLUMNS,
            "available_derived_portfolio_features": DERIVED_FEATURE_COLUMNS,
            "active_derived_portfolio_features": active_derived_features,
            "rsi_features_enabled": bool(args.use_rsi_features),
            "market_regime_features_enabled": bool(use_market_regime_features),
            "shared_market_inputs": SHARED_MARKET_FEATURE_COLUMNS,
            "market_context_inputs_per_ticker": PER_TICKER_CONTEXT_COLUMNS,
            "active_market_regime_features": [
                feature for feature in active_derived_features if feature in ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS
            ],
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
        "action_space": {str(action): label for action, label in ACTION_LABELS.items()},
        "reward_note": "daily_return + benchmark_weight * excess daily return versus max(equal-weight B&H, 0050 B&H); optional benchmark shortfall penalty can be enabled by setting benchmark_shortfall_penalty_weight > 0. Observation includes relative momentum, market regime, and portfolio-vs-benchmark state features.",
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
