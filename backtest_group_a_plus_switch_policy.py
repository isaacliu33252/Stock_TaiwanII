#!/usr/bin/env python3
"""Backtest Golden1 <-> GroupA+ defensive switching rules."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from multi_agent_debate import DebateOrchestrator, decide_with_debate, VoteOption


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_LATEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "switch_backtest.json"


@dataclass(frozen=True)
class SwitchRule:
    name: str
    ma_window: int
    enter_ma_gap: float
    exit_ma_gap: float
    drawdown_window: int
    enter_drawdown: float
    exit_momentum_days: int
    min_hold_days: int
    require_chip_score: int = 0
    exit_max_chip_score: int | None = None
    require_derivative_score: int = 0
    exit_max_derivative_score: int | None = None
    require_total_risk_score: int = 0
    exit_max_total_risk_score: int | None = None
    enter_cost_gap_below: float | None = None
    enter_cost_gap_above: float | None = None
    exit_cost_gap_below: float | None = None
    require_tail_risk_score: int = 0
    exit_max_tail_risk_score: int | None = None
    # Risk Override Entry: bypass MA gap check when extreme risk + drawdown
    # Enter defensive if total_risk_score >= override_risk_score AND drawdown <= override_drawdown_threshold
    # regardless of whether ma_gap satisfies enter_ma_gap.  0 = disabled.
    override_risk_score: int = 0
    override_drawdown_threshold: float = -0.05
    # Low-risk fast exit: use a tighter exit_ma_gap when risk has dissipated
    # When total_risk_score <= low_risk_exit_score_threshold, require only low_risk_exit_ma_gap (not exit_ma_gap)
    # None = disabled (use exit_ma_gap always)
    low_risk_exit_ma_gap: float | None = None
    low_risk_exit_score_threshold: int = 1


RULES = (
    SwitchRule("ma20_dd5_hold5", 20, -0.02, 0.01, 20, -0.05, 5, 5),
    SwitchRule("ma20_dd7_hold5", 20, -0.03, 0.01, 20, -0.07, 5, 5),
    SwitchRule("ma60_dd8_hold10", 60, -0.02, 0.01, 60, -0.08, 10, 10),
    SwitchRule("ma60_dd10_hold10", 60, -0.03, 0.015, 60, -0.10, 10, 10),
    SwitchRule("ma90_dd12_hold5_eg020_xg010", 90, -0.02, 0.01, 90, -0.12, 5, 5),
    SwitchRule("ma120_dd12_hold15", 120, -0.03, 0.015, 120, -0.12, 15, 15),
    SwitchRule("chip_ma20_dd5_score1_hold5", 20, -0.02, 0.01, 20, -0.05, 5, 5, 1, 1),
    SwitchRule("chip_ma20_dd5_score2_hold5", 20, -0.02, 0.01, 20, -0.05, 5, 5, 2, 1),
    SwitchRule("chip_ma60_dd8_score1_hold10", 60, -0.02, 0.01, 60, -0.08, 10, 10, 1, 1),
    SwitchRule("deriv_ma20_dd5_score1_hold5", 20, -0.02, 0.01, 20, -0.05, 5, 5, 0, None, 1, 1),
    SwitchRule("deriv_ma60_dd8_score1_hold10", 60, -0.02, 0.01, 60, -0.08, 10, 10, 0, None, 1, 1),
    SwitchRule("risk_ma20_dd5_total2_hold5", 20, -0.02, 0.01, 20, -0.05, 5, 5, 0, None, 0, None, 2, 2),
    SwitchRule("risk_ma90_dd12_total6_hold5", 90, -0.02, 0.01, 90, -0.12, 5, 5, 0, None, 0, None, 6, 6),
    SwitchRule(
        "risk_ma80_dd11_total6_hold5_eg015_xg015",
        80,
        -0.015,
        0.015,
        80,
        -0.11,
        5,
        5,
        0,
        None,
        0,
        None,
        6,
        6,
    ),
    SwitchRule(
        "risk_ma75_dd11_total6_hold5_eg0175_xg020",
        75,
        -0.0175,
        0.02,
        75,
        -0.11,
        5,
        5,
        0,
        None,
        0,
        None,
        6,
        6,
    ),
    SwitchRule(
        "risk_ma90_dd12_total6_tail1_hold5",
        90,
        -0.02,
        0.01,
        90,
        -0.12,
        5,
        5,
        0,
        None,
        0,
        None,
        6,
        6,
        require_tail_risk_score=1,
        exit_max_tail_risk_score=1,
    ),
)


def _confirmation_strength(rule: dict[str, Any] | SwitchRule) -> int:
    if isinstance(rule, SwitchRule):
        total_risk = rule.require_total_risk_score
        chip = rule.require_chip_score
        derivative = rule.require_derivative_score
        tail = rule.require_tail_risk_score
    else:
        total_risk = rule.get("require_total_risk_score", 0)
        chip = rule.get("require_chip_score", 0)
        derivative = rule.get("require_derivative_score", 0)
        tail = rule.get("require_tail_risk_score", 0)
    return int(total_risk or 0) * 10 + int(tail or 0) * 5 + int(chip or 0) + int(derivative or 0)


def _load_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(subset=tickers)


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]).fetchone()[0])


def _load_chip_features(db_path: Path, index: pd.DatetimeIndex, start: str, end: str) -> pd.DataFrame:
    features = pd.DataFrame(index=index)
    features["inst_0050_5d"] = 0.0
    features["foreign_0050_5d"] = 0.0
    features["margin_0050_balance_chg_5d"] = 0.0
    features["market_margin_balance_chg_5d"] = 0.0
    features["tdcc_0050_minority_chg_1w"] = 0.0
    features["tdcc_0050_major_chg_1w"] = 0.0
    features["foreign_shareholding_0050_ratio_chg_5d"] = 0.0
    features["short_0050_margin_balance_chg_5d"] = 0.0
    features["short_0050_sbl_balance_chg_5d"] = 0.0
    features["securities_lending_0050_volume_5d"] = 0.0
    features["day_trade_0050_volume_5d"] = 0.0
    features["dealer_tx_volume_5d"] = 0.0
    features["dealer_txo_volume_5d"] = 0.0
    features["tx_foreign_net_oi"] = 0.0
    features["tx_foreign_net_oi_chg_5d"] = 0.0
    features["txo_foreign_call_net_oi"] = 0.0
    features["txo_foreign_put_net_oi"] = 0.0
    features["txo_foreign_put_call_net_oi"] = 0.0
    features["txo_foreign_put_call_net_oi_chg_5d"] = 0.0
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if _table_exists(con, "institutional_data"):
            inst = con.execute(
                """
                SELECT dt, foreign_net_buy, institutional_total_net_buy
                FROM institutional_data
                WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not inst.empty:
                inst["dt"] = pd.to_datetime(inst["dt"])
                inst = inst.set_index("dt").reindex(index).fillna(0.0)
                features["inst_0050_5d"] = inst["institutional_total_net_buy"].rolling(5, min_periods=1).sum()
                features["foreign_0050_5d"] = inst["foreign_net_buy"].rolling(5, min_periods=1).sum()
        if _table_exists(con, "margin_data"):
            margin = con.execute(
                """
                SELECT dt, margin_balance
                FROM margin_data
                WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not margin.empty:
                margin["dt"] = pd.to_datetime(margin["dt"])
                margin = margin.set_index("dt").reindex(index).ffill(limit=5)
                features["margin_0050_balance_chg_5d"] = margin["margin_balance"].diff(5).fillna(0.0)
        if _table_exists(con, "market_margin_data"):
            market_margin = con.execute(
                """
                SELECT dt, margin_balance
                FROM market_margin_data
                WHERE dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not market_margin.empty:
                market_margin["dt"] = pd.to_datetime(market_margin["dt"])
                market_margin = market_margin.set_index("dt").reindex(index).ffill(limit=5)
                features["market_margin_balance_chg_5d"] = market_margin["margin_balance"].diff(5).fillna(0.0)
        if _table_exists(con, "shareholding_distribution"):
            tdcc = con.execute(
                """
                SELECT dt,
                       sum(CASE WHEN holding_level BETWEEN 1 AND 5 THEN percent ELSE 0 END) AS minority_percent,
                       sum(CASE WHEN holding_level BETWEEN 12 AND 15 THEN percent ELSE 0 END) AS major_percent
                FROM shareholding_distribution
                WHERE stock_id = '0050' AND dt BETWEEN ? AND ?
                GROUP BY dt
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not tdcc.empty:
                tdcc["dt"] = pd.to_datetime(tdcc["dt"])
                tdcc = tdcc.set_index("dt").sort_index()
                observation_gap = tdcc.index.to_series().diff().dt.days
                valid_weekly_gap = observation_gap.le(21)
                tdcc["tdcc_0050_minority_chg_1w"] = (
                    tdcc["minority_percent"].diff().where(valid_weekly_gap, 0.0).fillna(0.0)
                )
                tdcc["tdcc_0050_major_chg_1w"] = (
                    tdcc["major_percent"].diff().where(valid_weekly_gap, 0.0).fillna(0.0)
                )
                # Weekly TDCC observations must not remain active across long source gaps.
                tdcc = tdcc.reindex(index).ffill(limit=10).fillna(0.0)
                features["tdcc_0050_minority_chg_1w"] = tdcc["tdcc_0050_minority_chg_1w"]
                features["tdcc_0050_major_chg_1w"] = tdcc["tdcc_0050_major_chg_1w"]
        if _table_exists(con, "foreign_shareholding_data"):
            foreign_holding = con.execute(
                """
                SELECT dt, foreign_investment_shares_ratio
                FROM foreign_shareholding_data
                WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not foreign_holding.empty:
                foreign_holding["dt"] = pd.to_datetime(foreign_holding["dt"])
                foreign_holding = foreign_holding.set_index("dt").reindex(index).ffill(limit=5)
                features["foreign_shareholding_0050_ratio_chg_5d"] = (
                    foreign_holding["foreign_investment_shares_ratio"].diff(5).fillna(0.0)
                )
        if _table_exists(con, "short_sale_balance_data"):
            short_balance = con.execute(
                """
                SELECT dt, margin_short_current_balance, sbl_short_current_balance
                FROM short_sale_balance_data
                WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not short_balance.empty:
                short_balance["dt"] = pd.to_datetime(short_balance["dt"])
                short_balance = short_balance.set_index("dt").reindex(index).ffill(limit=5)
                features["short_0050_margin_balance_chg_5d"] = short_balance["margin_short_current_balance"].diff(5).fillna(0.0)
                features["short_0050_sbl_balance_chg_5d"] = short_balance["sbl_short_current_balance"].diff(5).fillna(0.0)
        if _table_exists(con, "securities_lending_data"):
            lending = con.execute(
                """
                SELECT dt, sum(volume) AS volume
                FROM securities_lending_data
                WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
                GROUP BY dt
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not lending.empty:
                lending["dt"] = pd.to_datetime(lending["dt"])
                lending = lending.set_index("dt").reindex(index).fillna(0.0)
                features["securities_lending_0050_volume_5d"] = lending["volume"].rolling(5, min_periods=1).sum()
        if _table_exists(con, "day_trading_data"):
            day_trade = con.execute(
                """
                SELECT dt, day_trade_volume
                FROM day_trading_data
                WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not day_trade.empty:
                day_trade["dt"] = pd.to_datetime(day_trade["dt"])
                day_trade = day_trade.set_index("dt").reindex(index).fillna(0.0)
                features["day_trade_0050_volume_5d"] = day_trade["day_trade_volume"].rolling(5, min_periods=1).sum()
        if _table_exists(con, "dealer_futures_data"):
            dealer_fut = con.execute(
                """
                SELECT dt, sum(volume) AS volume
                FROM dealer_futures_data
                WHERE futures_id = 'TX' AND is_after_hour = 0 AND dt BETWEEN ? AND ?
                GROUP BY dt
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not dealer_fut.empty:
                dealer_fut["dt"] = pd.to_datetime(dealer_fut["dt"])
                dealer_fut = dealer_fut.set_index("dt").reindex(index).fillna(0.0)
                features["dealer_tx_volume_5d"] = dealer_fut["volume"].rolling(5, min_periods=1).sum()
        if _table_exists(con, "dealer_options_data"):
            dealer_opt = con.execute(
                """
                SELECT dt, sum(volume) AS volume
                FROM dealer_options_data
                WHERE option_id = 'TXO' AND is_after_hour = 0 AND dt BETWEEN ? AND ?
                GROUP BY dt
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not dealer_opt.empty:
                dealer_opt["dt"] = pd.to_datetime(dealer_opt["dt"])
                dealer_opt = dealer_opt.set_index("dt").reindex(index).fillna(0.0)
                features["dealer_txo_volume_5d"] = dealer_opt["volume"].rolling(5, min_periods=1).sum()
        if _table_exists(con, "derivative_institutional_data"):
            futures = con.execute(
                """
                SELECT dt, net_open_interest_balance_volume
                FROM derivative_institutional_data
                WHERE market = 'futures'
                  AND product_id = 'TX'
                  AND institutional_investors = '外資'
                  AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not futures.empty:
                futures["dt"] = pd.to_datetime(futures["dt"])
                futures = futures.set_index("dt").reindex(index).ffill(limit=5)
                features["tx_foreign_net_oi"] = futures["net_open_interest_balance_volume"].fillna(0.0)
                features["tx_foreign_net_oi_chg_5d"] = futures["net_open_interest_balance_volume"].diff(5).fillna(0.0)
            options = con.execute(
                """
                SELECT dt, put_call, net_open_interest_balance_volume
                FROM derivative_institutional_data
                WHERE market = 'options'
                  AND product_id = 'TXO'
                  AND institutional_investors = '外資'
                  AND dt BETWEEN ? AND ?
                ORDER BY dt
                """,
                [start, end],
            ).fetchdf()
            if not options.empty:
                options["dt"] = pd.to_datetime(options["dt"])
                pivot = options.pivot_table(
                    index="dt",
                    columns="put_call",
                    values="net_open_interest_balance_volume",
                    aggfunc="sum",
                ).sort_index()
                pivot = pivot.reindex(index).ffill(limit=5).fillna(0.0)
                call_oi = pivot["買權"] if "買權" in pivot.columns else pd.Series(0.0, index=index)
                put_oi = pivot["賣權"] if "賣權" in pivot.columns else pd.Series(0.0, index=index)
                features["txo_foreign_call_net_oi"] = call_oi
                features["txo_foreign_put_net_oi"] = put_oi
                features["txo_foreign_put_call_net_oi"] = put_oi - call_oi
                features["txo_foreign_put_call_net_oi_chg_5d"] = (put_oi - call_oi).diff(5).fillna(0.0)
    finally:
        con.close()
    features = _attach_smart_money_cost_proxy(db_path, features, index, start, end)
    return features.fillna(0.0)


def _attach_smart_money_cost_proxy(
    db_path: Path,
    features: pd.DataFrame,
    index: pd.DatetimeIndex,
    start: str,
    end: str,
) -> pd.DataFrame:
    """用本地台股資料近似 FinGenius 主力成本乖離率。"""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT o.dt, o.close,
                   coalesce(i.institutional_total_net_buy, 0.0) AS inst_net_buy,
                   coalesce(i.foreign_net_buy, 0.0) AS foreign_net_buy,
                   coalesce(m.margin_buy, 0.0) AS margin_buy,
                   coalesce(m.margin_sell, 0.0) AS margin_sell
            FROM ohlcv o
            LEFT JOIN institutional_data i ON i.ticker = o.ticker AND i.dt = o.dt
            LEFT JOIN margin_data m ON m.ticker = o.ticker AND m.dt = o.dt
            WHERE o.ticker = '0050.TW' AND o.dt BETWEEN ? AND ?
            ORDER BY o.dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        features["smart_money_cost_20d"] = 0.0
        features["smart_money_cost_60d"] = 0.0
        features["smart_money_cost_gap_20d"] = 0.0
        features["smart_money_cost_gap_60d"] = 0.0
        features["smart_money_pressure_20d"] = 0.0
        features["smart_money_cost_risk"] = 0
        return features

    rows["dt"] = pd.to_datetime(rows["dt"])
    frame = rows.set_index("dt").reindex(index).ffill().fillna(0.0)
    close = frame["close"].astype(float)
    inst_accum = frame["inst_net_buy"].clip(lower=0.0)
    foreign_accum = frame["foreign_net_buy"].clip(lower=0.0)
    margin_accum = (frame["margin_buy"] - frame["margin_sell"]).clip(lower=0.0)
    weights = inst_accum + foreign_accum + margin_accum

    def weighted_cost(window: int) -> pd.Series:
        weighted_close = (close * weights).rolling(window, min_periods=max(5, window // 4)).sum()
        weight_sum = weights.rolling(window, min_periods=max(5, window // 4)).sum()
        fallback = close.rolling(window, min_periods=max(5, window // 4)).mean()
        return (weighted_close / weight_sum.replace(0.0, pd.NA)).fillna(fallback).fillna(close)

    cost20 = weighted_cost(20)
    cost60 = weighted_cost(60)
    gap20 = close / cost20 - 1.0
    gap60 = close / cost60 - 1.0
    pressure20 = weights.rolling(20, min_periods=5).sum().fillna(0.0)
    pressure_threshold = pressure20.rolling(120, min_periods=20).quantile(0.75)
    features["smart_money_cost_20d"] = cost20
    features["smart_money_cost_60d"] = cost60
    features["smart_money_cost_gap_20d"] = gap20.fillna(0.0)
    features["smart_money_cost_gap_60d"] = gap60.fillna(0.0)
    features["smart_money_pressure_20d"] = pressure20
    features["smart_money_cost_risk"] = (
        ((gap20 < -0.02) & (pressure20 > pressure_threshold.fillna(float("inf"))))
        | (gap20 > 0.12)
    ).astype(int)
    return features


def _rebalance(value: float, price_row: pd.Series, weights: dict[str, float]) -> tuple[dict[str, float], float]:
    weights = _normalize(weights)
    shares = {
        ticker: value * float(weights.get(ticker, 0.0) or 0.0) / max(float(price_row[ticker]), 1e-12)
        for ticker in TICKERS
    }
    cash = value * float(weights.get("cash", 0.0) or 0.0)
    return shares, cash


def _mark_to_market(price_row: pd.Series, shares: dict[str, float], cash: float) -> float:
    value = float(cash)
    for ticker in TICKERS:
        value += float(shares.get(ticker, 0.0) or 0.0) * float(price_row[ticker])
    return value


def _simulate_regime_curve(
    prices: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
) -> pd.Series:
    values = []
    current_regime = str(regimes.iloc[0])
    shares, cash = _rebalance(initial_value, prices.iloc[0], weights_by_regime[current_regime])
    for dt, price_row in prices.iterrows():
        value = _mark_to_market(price_row, shares, cash)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:
            current_regime = next_regime
            shares, cash = _rebalance(value, price_row, weights_by_regime[current_regime])
            value = _mark_to_market(price_row, shares, cash)
        values.append(value)
    return pd.Series(values, index=prices.index, dtype=float)


def _metrics(values: pd.Series, initial_value: float) -> dict[str, Any]:
    returns = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / initial_value - 1.0)
    annual_return = float((values.iloc[-1] / initial_value) ** (1.0 / years) - 1.0)
    volatility = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    downside_returns = returns[returns < 0.0]
    downside_deviation = (
        float(math.sqrt((downside_returns.pow(2).mean())) * math.sqrt(252))
        if len(downside_returns) > 0
        else 0.0
    )
    sortino = (
        float((returns.mean() * 252) / downside_deviation)
        if len(returns) > 1 and downside_deviation > 0
        else 0.0
    )
    max_drawdown = float((values / values.cummax() - 1.0).min())
    value_at_risk_5pct = float(returns.quantile(0.05)) if len(returns) else 0.0
    tail_losses = returns[returns <= value_at_risk_5pct] if len(returns) else pd.Series(dtype=float)
    expected_tail_loss_5pct = float(tail_losses.mean()) if len(tail_losses) else 0.0
    starr_ratio_5pct = (
        float(returns.mean() / abs(expected_tail_loss_5pct))
        if len(returns) > 1 and expected_tail_loss_5pct < 0.0
        else 0.0
    )
    var_breach_count_5pct = int((returns <= value_at_risk_5pct).sum()) if len(returns) else 0
    var_breach_ratio_5pct = float(var_breach_count_5pct / len(returns)) if len(returns) else 0.0
    kupiec_lr_5pct, kupiec_pvalue_5pct = _kupiec_test(var_breach_count_5pct, len(returns), 0.05)
    ewma_vol = returns.pow(2).ewm(alpha=0.06, adjust=False, min_periods=20).mean().pow(0.5)
    current_ewma_vol = float(ewma_vol.dropna().iloc[-1]) if len(ewma_vol.dropna()) else 0.0
    vol_weighted_returns = (returns * current_ewma_vol / ewma_vol.replace(0.0, math.nan)).dropna()
    volatility_weighted_var_5pct = float(vol_weighted_returns.quantile(0.05)) if len(vol_weighted_returns) else 0.0
    volatility_weighted_tail = vol_weighted_returns[vol_weighted_returns <= volatility_weighted_var_5pct]
    volatility_weighted_etl_5pct = float(volatility_weighted_tail.mean()) if len(volatility_weighted_tail) else 0.0
    worst_daily_return = float(returns.min()) if len(returns) else 0.0
    rolling_20d_return = values.pct_change(20).dropna()
    worst_20d_return = float(rolling_20d_return.min()) if len(rolling_20d_return) else 0.0
    return {
        "initial_value": float(initial_value),
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": volatility,
        "downside_deviation": downside_deviation,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "value_at_risk_5pct": value_at_risk_5pct,
        "expected_tail_loss_5pct": expected_tail_loss_5pct,
        "starr_ratio_5pct": starr_ratio_5pct,
        "var_breach_count_5pct": var_breach_count_5pct,
        "var_breach_ratio_5pct": var_breach_ratio_5pct,
        "kupiec_lr_5pct": kupiec_lr_5pct,
        "kupiec_pvalue_5pct": kupiec_pvalue_5pct,
        "volatility_weighted_var_5pct": volatility_weighted_var_5pct,
        "volatility_weighted_etl_5pct": volatility_weighted_etl_5pct,
        "worst_daily_return": worst_daily_return,
        "worst_20d_return": worst_20d_return,
    }


def _kupiec_test(exceptions: int, observations: int, expected_prob: float) -> tuple[float, float]:
    if observations <= 0:
        return 0.0, 1.0
    exceptions = max(0, min(int(exceptions), int(observations)))
    expected_prob = min(max(float(expected_prob), 1e-12), 1.0 - 1e-12)
    observed_prob = min(max(exceptions / observations, 1e-12), 1.0 - 1e-12)
    log_null = (
        (observations - exceptions) * math.log(1.0 - expected_prob)
        + exceptions * math.log(expected_prob)
    )
    log_alt = (
        (observations - exceptions) * math.log(1.0 - observed_prob)
        + exceptions * math.log(observed_prob)
    )
    lr = max(0.0, -2.0 * (log_null - log_alt))
    pvalue = math.erfc(math.sqrt(lr / 2.0))
    return float(lr), float(pvalue)


def _regime_features(prices: pd.DataFrame, rule: SwitchRule, chip_features: pd.DataFrame | None = None) -> pd.DataFrame:
    close = prices["0050.TW"].astype(float)
    ma = close.rolling(rule.ma_window, min_periods=max(5, rule.ma_window // 3)).mean()
    ma_gap = close / ma - 1.0
    rolling_peak = close.rolling(rule.drawdown_window, min_periods=max(5, rule.drawdown_window // 3)).max()
    drawdown = close / rolling_peak - 1.0
    momentum = close.pct_change(rule.exit_momentum_days)
    frame = pd.DataFrame(
        {
            "0050_close": close,
            "ma_gap": ma_gap.fillna(0.0),
            "drawdown": drawdown.fillna(0.0),
            "exit_momentum": momentum.fillna(0.0),
        },
        index=prices.index,
    )
    if chip_features is not None:
        frame = frame.join(chip_features, how="left").fillna(0.0)
    else:
        frame["inst_0050_5d"] = 0.0
        frame["foreign_0050_5d"] = 0.0
        frame["margin_0050_balance_chg_5d"] = 0.0
        frame["market_margin_balance_chg_5d"] = 0.0
        frame["tdcc_0050_minority_chg_1w"] = 0.0
        frame["tdcc_0050_major_chg_1w"] = 0.0
        frame["foreign_shareholding_0050_ratio_chg_5d"] = 0.0
        frame["short_0050_margin_balance_chg_5d"] = 0.0
        frame["short_0050_sbl_balance_chg_5d"] = 0.0
        frame["securities_lending_0050_volume_5d"] = 0.0
        frame["day_trade_0050_volume_5d"] = 0.0
        frame["dealer_tx_volume_5d"] = 0.0
        frame["dealer_txo_volume_5d"] = 0.0
        frame["tx_foreign_net_oi"] = 0.0
        frame["tx_foreign_net_oi_chg_5d"] = 0.0
        frame["txo_foreign_call_net_oi"] = 0.0
        frame["txo_foreign_put_net_oi"] = 0.0
        frame["txo_foreign_put_call_net_oi"] = 0.0
        frame["txo_foreign_put_call_net_oi_chg_5d"] = 0.0
        frame["smart_money_cost_20d"] = 0.0
        frame["smart_money_cost_60d"] = 0.0
        frame["smart_money_cost_gap_20d"] = 0.0
        frame["smart_money_cost_gap_60d"] = 0.0
        frame["smart_money_pressure_20d"] = 0.0
        frame["smart_money_cost_risk"] = 0
    price_5d = close.pct_change(5).reindex(frame.index).fillna(0.0)
    return_1d = close.pct_change().reindex(frame.index).fillna(0.0)
    hist_var_20 = return_1d.rolling(20, min_periods=10).quantile(0.05).fillna(0.0)
    realized_vol_20 = return_1d.rolling(20, min_periods=10).std().fillna(0.0) * math.sqrt(252)
    realized_vol_60 = return_1d.rolling(60, min_periods=20).std().fillna(0.0) * math.sqrt(252)
    vol_ratio_20_60 = (realized_vol_20 / realized_vol_60.replace(0.0, math.nan)).replace([math.inf, -math.inf], math.nan).fillna(1.0)
    frame["return_0050_1d"] = return_1d
    frame["hist_var_0050_20d_5pct"] = hist_var_20
    frame["realized_vol_0050_20d"] = realized_vol_20
    frame["realized_vol_0050_60d"] = realized_vol_60
    frame["realized_vol_ratio_20_60"] = vol_ratio_20_60
    frame["tail_var_breach_risk"] = (return_1d <= hist_var_20).astype(int)
    frame["tail_vol_regime_risk"] = ((vol_ratio_20_60 >= 1.2) & (price_5d < 0.0)).astype(int)
    frame["tail_risk_score"] = frame[["tail_var_breach_risk", "tail_vol_regime_risk"]].sum(axis=1)
    frame["chip_inst_risk"] = (frame["inst_0050_5d"] < 0.0).astype(int)
    frame["chip_foreign_risk"] = (frame["foreign_0050_5d"] < 0.0).astype(int)
    frame["chip_margin_risk"] = ((frame["margin_0050_balance_chg_5d"] > 0.0) & (price_5d < 0.0)).astype(int)
    frame["chip_market_margin_risk"] = ((frame["market_margin_balance_chg_5d"] > 0.0) & (price_5d < 0.0)).astype(int)
    frame["chip_tdcc_risk"] = ((frame["tdcc_0050_minority_chg_1w"] > 0.0) & (frame["tdcc_0050_major_chg_1w"] < 0.0)).astype(int)
    frame["chip_foreign_shareholding_risk"] = (frame["foreign_shareholding_0050_ratio_chg_5d"] < 0.0).astype(int)
    frame["chip_short_balance_risk"] = (
        ((frame["short_0050_margin_balance_chg_5d"] > 0.0) | (frame["short_0050_sbl_balance_chg_5d"] > 0.0))
        & (price_5d < 0.0)
    ).astype(int)
    lending_threshold = frame["securities_lending_0050_volume_5d"].rolling(60, min_periods=20).quantile(0.8).fillna(float("inf"))
    frame["chip_securities_lending_risk"] = (
        (frame["securities_lending_0050_volume_5d"] > lending_threshold) & (price_5d < 0.0)
    ).astype(int)
    day_trade_threshold = frame["day_trade_0050_volume_5d"].rolling(60, min_periods=20).quantile(0.8).fillna(float("inf"))
    frame["chip_day_trading_risk"] = (
        (frame["day_trade_0050_volume_5d"] > day_trade_threshold) & (price_5d < 0.0)
    ).astype(int)
    dealer_tx_threshold = frame["dealer_tx_volume_5d"].rolling(60, min_periods=20).quantile(0.8).fillna(float("inf"))
    frame["chip_dealer_tx_risk"] = (
        (frame["dealer_tx_volume_5d"] > dealer_tx_threshold) & (price_5d < 0.0)
    ).astype(int)
    dealer_txo_threshold = frame["dealer_txo_volume_5d"].rolling(60, min_periods=20).quantile(0.8).fillna(float("inf"))
    frame["chip_dealer_txo_risk"] = (
        (frame["dealer_txo_volume_5d"] > dealer_txo_threshold) & (price_5d < 0.0)
    ).astype(int)
    frame["chip_score"] = frame[
        [
            "chip_inst_risk",
            "chip_foreign_risk",
            "chip_margin_risk",
            "chip_market_margin_risk",
            "chip_tdcc_risk",
            "chip_foreign_shareholding_risk",
            "chip_short_balance_risk",
            "chip_securities_lending_risk",
            "chip_day_trading_risk",
            "chip_dealer_tx_risk",
            "chip_dealer_txo_risk",
            "smart_money_cost_risk",
        ]
    ].sum(axis=1)
    frame["derivative_futures_foreign_risk"] = (
        (frame["tx_foreign_net_oi"] < 0.0) & (frame["tx_foreign_net_oi_chg_5d"] < 0.0)
    ).astype(int)
    frame["derivative_options_foreign_risk"] = (
        (frame["txo_foreign_put_call_net_oi"] > 0.0) & (frame["txo_foreign_put_call_net_oi_chg_5d"] > 0.0)
    ).astype(int)
    frame["derivative_score"] = frame[
        [
            "derivative_futures_foreign_risk",
            "derivative_options_foreign_risk",
        ]
    ].sum(axis=1)
    frame["total_risk_score"] = frame["chip_score"] + frame["derivative_score"]
    return frame


def _switch_returns(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame | None,
    rule: SwitchRule,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    features = _regime_features(prices, rule, chip_features)
    in_defense = False
    hold_days = 0
    events: list[dict[str, Any]] = []
    regimes = []
    for dt, row in features.iterrows():
        price_enter = row["ma_gap"] <= rule.enter_ma_gap or row["drawdown"] <= rule.enter_drawdown
        cost_enter = False
        if rule.enter_cost_gap_below is not None:
            cost_enter = cost_enter or float(row["smart_money_cost_gap_20d"]) <= float(rule.enter_cost_gap_below)
        if rule.enter_cost_gap_above is not None:
            cost_enter = cost_enter or float(row["smart_money_cost_gap_20d"]) >= float(rule.enter_cost_gap_above)
        # Risk Override: ignore MA gap when extreme risk score + drawdown both fire
        override_enter = (
            rule.override_risk_score > 0
            and int(row["total_risk_score"]) >= int(rule.override_risk_score)
            and float(row["drawdown"]) <= float(rule.override_drawdown_threshold)
        )
        chip_ok = int(row["chip_score"]) >= int(rule.require_chip_score)
        derivative_ok = int(row["derivative_score"]) >= int(rule.require_derivative_score)
        total_risk_ok = int(row["total_risk_score"]) >= int(rule.require_total_risk_score)
        tail_risk_ok = int(row["tail_risk_score"]) >= int(rule.require_tail_risk_score)
        enter = (price_enter or cost_enter or override_enter) and chip_ok and derivative_ok and total_risk_ok and tail_risk_ok
        effective_exit_ma_gap = rule.exit_ma_gap
        if (
            rule.low_risk_exit_ma_gap is not None
            and int(row["total_risk_score"]) <= int(rule.low_risk_exit_score_threshold)
        ):
            effective_exit_ma_gap = rule.low_risk_exit_ma_gap
        exit_ = row["ma_gap"] >= effective_exit_ma_gap and row["exit_momentum"] > 0.0
        if rule.exit_cost_gap_below is not None:
            exit_ = exit_ and float(row["smart_money_cost_gap_20d"]) >= float(rule.exit_cost_gap_below)
        if rule.exit_max_chip_score is not None:
            exit_ = exit_ and int(row["chip_score"]) <= int(rule.exit_max_chip_score)
        if rule.exit_max_derivative_score is not None:
            exit_ = exit_ and int(row["derivative_score"]) <= int(rule.exit_max_derivative_score)
        if rule.exit_max_total_risk_score is not None:
            exit_ = exit_ and int(row["total_risk_score"]) <= int(rule.exit_max_total_risk_score)
        if rule.exit_max_tail_risk_score is not None:
            exit_ = exit_ and int(row["tail_risk_score"]) <= int(rule.exit_max_tail_risk_score)
        if in_defense:
            hold_days += 1
            if hold_days >= rule.min_hold_days and exit_:
                in_defense = False
                hold_days = 0
                events.append(
                    {
                        "date": str(dt.date()),
                        "action": "switch_to_golden",
                        "ma_gap": float(row["ma_gap"]),
                        "drawdown": float(row["drawdown"]),
                        "exit_momentum": float(row["exit_momentum"]),
                        "chip_score": int(row["chip_score"]),
                        "inst_0050_5d": float(row["inst_0050_5d"]),
                        "foreign_0050_5d": float(row["foreign_0050_5d"]),
                        "margin_0050_balance_chg_5d": float(row["margin_0050_balance_chg_5d"]),
                        "market_margin_balance_chg_5d": float(row["market_margin_balance_chg_5d"]),
                        "tdcc_0050_minority_chg_1w": float(row["tdcc_0050_minority_chg_1w"]),
                        "tdcc_0050_major_chg_1w": float(row["tdcc_0050_major_chg_1w"]),
                        "foreign_shareholding_0050_ratio_chg_5d": float(row["foreign_shareholding_0050_ratio_chg_5d"]),
                        "short_0050_margin_balance_chg_5d": float(row["short_0050_margin_balance_chg_5d"]),
                        "short_0050_sbl_balance_chg_5d": float(row["short_0050_sbl_balance_chg_5d"]),
                        "securities_lending_0050_volume_5d": float(row["securities_lending_0050_volume_5d"]),
                        "day_trade_0050_volume_5d": float(row.get("day_trade_0050_volume_5d", 0.0)),
                        "dealer_tx_volume_5d": float(row.get("dealer_tx_volume_5d", 0.0)),
                        "dealer_txo_volume_5d": float(row.get("dealer_txo_volume_5d", 0.0)),
                        "smart_money_cost_20d": float(row.get("smart_money_cost_20d", 0.0)),
                        "smart_money_cost_gap_20d": float(row.get("smart_money_cost_gap_20d", 0.0)),
                        "smart_money_pressure_20d": float(row.get("smart_money_pressure_20d", 0.0)),
                        "smart_money_cost_risk": int(row.get("smart_money_cost_risk", 0)),
                        "derivative_score": int(row["derivative_score"]),
                        "total_risk_score": int(row["total_risk_score"]),
                        "tail_risk_score": int(row["tail_risk_score"]),
                        "hist_var_0050_20d_5pct": float(row["hist_var_0050_20d_5pct"]),
                        "realized_vol_0050_20d": float(row["realized_vol_0050_20d"]),
                        "realized_vol_0050_60d": float(row["realized_vol_0050_60d"]),
                        "realized_vol_ratio_20_60": float(row["realized_vol_ratio_20_60"]),
                        "tx_foreign_net_oi": float(row["tx_foreign_net_oi"]),
                        "tx_foreign_net_oi_chg_5d": float(row["tx_foreign_net_oi_chg_5d"]),
                        "txo_foreign_call_net_oi": float(row["txo_foreign_call_net_oi"]),
                        "txo_foreign_put_net_oi": float(row["txo_foreign_put_net_oi"]),
                        "txo_foreign_put_call_net_oi": float(row["txo_foreign_put_call_net_oi"]),
                        "txo_foreign_put_call_net_oi_chg_5d": float(row["txo_foreign_put_call_net_oi_chg_5d"]),
                    }
                )
        elif enter:
            in_defense = True
            hold_days = 1
            events.append(
                {
                    "date": str(dt.date()),
                    "action": "switch_to_group_a_plus_defensive",
                    "ma_gap": float(row["ma_gap"]),
                    "drawdown": float(row["drawdown"]),
                    "exit_momentum": float(row["exit_momentum"]),
                    "chip_score": int(row["chip_score"]),
                    "inst_0050_5d": float(row["inst_0050_5d"]),
                    "foreign_0050_5d": float(row["foreign_0050_5d"]),
                    "margin_0050_balance_chg_5d": float(row["margin_0050_balance_chg_5d"]),
                    "market_margin_balance_chg_5d": float(row["market_margin_balance_chg_5d"]),
                    "tdcc_0050_minority_chg_1w": float(row["tdcc_0050_minority_chg_1w"]),
                    "tdcc_0050_major_chg_1w": float(row["tdcc_0050_major_chg_1w"]),
                    "foreign_shareholding_0050_ratio_chg_5d": float(row["foreign_shareholding_0050_ratio_chg_5d"]),
                    "short_0050_margin_balance_chg_5d": float(row["short_0050_margin_balance_chg_5d"]),
                    "short_0050_sbl_balance_chg_5d": float(row["short_0050_sbl_balance_chg_5d"]),
                    "securities_lending_0050_volume_5d": float(row["securities_lending_0050_volume_5d"]),
                    "day_trade_0050_volume_5d": float(row.get("day_trade_0050_volume_5d", 0.0)),
                    "dealer_tx_volume_5d": float(row.get("dealer_tx_volume_5d", 0.0)),
                    "dealer_txo_volume_5d": float(row.get("dealer_txo_volume_5d", 0.0)),
                    "smart_money_cost_20d": float(row.get("smart_money_cost_20d", 0.0)),
                    "smart_money_cost_gap_20d": float(row.get("smart_money_cost_gap_20d", 0.0)),
                    "smart_money_pressure_20d": float(row.get("smart_money_pressure_20d", 0.0)),
                    "smart_money_cost_risk": int(row.get("smart_money_cost_risk", 0)),
                    "derivative_score": int(row["derivative_score"]),
                    "total_risk_score": int(row["total_risk_score"]),
                    "tail_risk_score": int(row["tail_risk_score"]),
                    "hist_var_0050_20d_5pct": float(row["hist_var_0050_20d_5pct"]),
                    "realized_vol_0050_20d": float(row["realized_vol_0050_20d"]),
                    "realized_vol_0050_60d": float(row["realized_vol_0050_60d"]),
                    "realized_vol_ratio_20_60": float(row["realized_vol_ratio_20_60"]),
                    "tx_foreign_net_oi": float(row["tx_foreign_net_oi"]),
                    "tx_foreign_net_oi_chg_5d": float(row["tx_foreign_net_oi_chg_5d"]),
                    "txo_foreign_call_net_oi": float(row["txo_foreign_call_net_oi"]),
                    "txo_foreign_put_net_oi": float(row["txo_foreign_put_net_oi"]),
                    "txo_foreign_put_call_net_oi": float(row["txo_foreign_put_call_net_oi"]),
                    "txo_foreign_put_call_net_oi_chg_5d": float(row["txo_foreign_put_call_net_oi_chg_5d"]),
                }
            )
        regimes.append("group_a_plus_defensive" if in_defense else "golden1")
    regime_frame = features.copy()
    regime_frame["regime"] = regimes
    return events, regime_frame


def _switch_returns_debate(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame | None,
    rule: SwitchRule,
    debate_rounds: int = 2,
) -> tuple[list[dict[str, Any]], pd.DataFrame, list[dict[str, Any]]]:
    """
    辯論版 switch_returns：用多 Agent 辯論取代 quantitative threshold

    與 _switch_returns 的差異：
    - 進 / 退防守的判斷不走固定閾值，改由 DebateOrchestrator 投票決定
    - 每個 Agent 根據自己的專業領域分析 features 並投票
    - 3票中需 2 票贊成（多數決）才切換
    - 持有期（min_hold_days）仍然遵守
    """
    features = _regime_features(prices, rule, chip_features)
    in_defense = False
    hold_days = 0
    events: list[dict[str, Any]] = []
    regimes = []
    debate_logs: list[dict[str, Any]] = []

    orchestrator = DebateOrchestrator()

    for dt, row in features.iterrows():
        # 把 row 轉成 dict（包含 date）
        row_dict: dict[str, float] = {"date": float(dt.timestamp()) if hasattr(dt, "timestamp") else 0.0, "date_str": str(dt.date())}
        for k, v in row.items():
            try:
                row_dict[k] = float(v)
            except (TypeError, ValueError):
                row_dict[k] = 0.0

        current_regime = "defensive" if in_defense else "golden"

        # ── 進防守檢查（使用 quantitative threshold，符合就直接進）────────────
        price_enter = row["ma_gap"] <= rule.enter_ma_gap or row["drawdown"] <= rule.enter_drawdown
        chip_ok = int(row["chip_score"]) >= int(rule.require_chip_score)
        derivative_ok = int(row["derivative_score"]) >= int(rule.require_derivative_score)
        total_risk_ok = int(row["total_risk_score"]) >= int(rule.require_total_risk_score)
        tail_risk_ok = int(row["tail_risk_score"]) >= int(rule.require_tail_risk_score)
        enter = price_enter and chip_ok and derivative_ok and total_risk_ok and tail_risk_ok

        # ── 退防守檢查（使用辯論引擎）──────────────────────────────────────
        exit_conditions_met = (
            row["ma_gap"] >= rule.exit_ma_gap
            and row["exit_momentum"] > 0.0
        )
        if rule.exit_max_chip_score is not None:
            exit_conditions_met = exit_conditions_met and int(row["chip_score"]) <= int(rule.exit_max_chip_score)
        if rule.exit_max_derivative_score is not None:
            exit_conditions_met = exit_conditions_met and int(row["derivative_score"]) <= int(rule.exit_max_derivative_score)
        if rule.exit_max_total_risk_score is not None:
            exit_conditions_met = exit_conditions_met and int(row["total_risk_score"]) <= int(rule.exit_max_total_risk_score)
        if rule.exit_max_tail_risk_score is not None:
            exit_conditions_met = exit_conditions_met and int(row["tail_risk_score"]) <= int(rule.exit_max_tail_risk_score)

        if in_defense:
            hold_days += 1
            # ── 持有期滿後，用辯論決定是否退出 ───────────────────────────
            if hold_days >= rule.min_hold_days and exit_conditions_met:
                # 只在即將退出時才叫用辯論（減少不必要的計算）
                debate_result = orchestrator.run(
                    features=row_dict,
                    current_regime="defensive",
                    debate_rounds=debate_rounds,
                    use_llm=False,
                )
                decision = debate_result["decision"]

                debate_logs.append({
                    "date": str(dt.date()),
                    "regime": "defensive",
                    "decision": decision,
                    "chip_vote": debate_result["chip_vote"],
                    "risk_vote": debate_result["risk_vote"],
                    "tech_vote": debate_result["tech_vote"],
                    "vote_counts": debate_result["vote_counts"],
                    "ma_gap": float(row["ma_gap"]),
                    "exit_momentum": float(row["exit_momentum"]),
                    "chip_score": int(row["chip_score"]),
                    "derivative_score": int(row["derivative_score"]),
                })

                if decision == "switch":
                    in_defense = False
                    hold_days = 0
                    events.append(
                        {
                            "date": str(dt.date()),
                            "action": "switch_to_golden",
                            "trigger": "debate",
                            "debate": {
                                "chip_vote": debate_result["chip_vote"],
                                "risk_vote": debate_result["risk_vote"],
                                "tech_vote": debate_result["tech_vote"],
                                "vote_counts": debate_result["vote_counts"],
                            },
                            "ma_gap": float(row["ma_gap"]),
                            "drawdown": float(row["drawdown"]),
                            "exit_momentum": float(row["exit_momentum"]),
                            "chip_score": int(row["chip_score"]),
                            "derivative_score": int(row["derivative_score"]),
                        }
                    )
        elif enter:
            in_defense = True
            hold_days = 1
            events.append(
                {
                    "date": str(dt.date()),
                    "action": "switch_to_group_a_plus_defensive",
                    "trigger": "threshold",
                    "ma_gap": float(row["ma_gap"]),
                    "drawdown": float(row["drawdown"]),
                    "exit_momentum": float(row["exit_momentum"]),
                    "chip_score": int(row["chip_score"]),
                    "derivative_score": int(row["derivative_score"]),
                }
            )

        regimes.append("group_a_plus_defensive" if in_defense else "golden1")

    regime_frame = features.copy()
    regime_frame["regime"] = regimes
    return events, regime_frame, debate_logs



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-17")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LATEST))
    parser.add_argument("--no-chip-features", action="store_true")
    parser.add_argument("--use-debate", action="store_true", help="使用多 Agent 辯論引擎取代 quantitative threshold 來決策 switch")
    parser.add_argument("--debate-rounds", type=int, default=2, help="辯論輪數（預設2）")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = None if args.no_chip_features else _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)

    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }
    curves = pd.DataFrame(index=prices.index)
    curves["golden1_0531_1m"] = _simulate_regime_curve(
        prices,
        pd.Series("golden1", index=prices.index),
        weights_by_regime,
        args.initial_value,
    )
    curves["group_a_plus_defensive_1m"] = _simulate_regime_curve(
        prices,
        pd.Series("group_a_plus_defensive", index=prices.index),
        weights_by_regime,
        args.initial_value,
    )
    summary: dict[str, Any] = {
        "golden1_0531_1m": _metrics(curves["golden1_0531_1m"], args.initial_value),
        "group_a_plus_defensive_1m": _metrics(curves["group_a_plus_defensive_1m"], args.initial_value),
    }
    rule_reports = []
    regime_outputs: dict[str, pd.DataFrame] = {}
    for rule in RULES:
        if args.use_debate:
            events, regime_frame, debate_logs = _switch_returns_debate(
                prices,
                chip_features,
                rule,
                debate_rounds=args.debate_rounds,
            )
        else:
            events, regime_frame = _switch_returns(
                prices,
                chip_features,
                rule,
            )
            debate_logs = []
        variant = f"switch_{rule.name}"
        curves[variant] = _simulate_regime_curve(
            prices,
            regime_frame["regime"],
            weights_by_regime,
            args.initial_value,
        )
        metrics = _metrics(curves[variant], args.initial_value)
        defense_days = int((regime_frame["regime"] == "group_a_plus_defensive").sum())
        summary[variant] = metrics
        rule_reports.append(
            {
                "variant": variant,
                "rule": rule.__dict__,
                "metrics": metrics,
                "defense_days": defense_days,
                "defense_day_ratio": defense_days / max(len(regime_frame), 1),
                "switch_count": len(events),
                "events": events,
                "debate_logs": debate_logs if args.use_debate else [],
            }
        )
        regime_outputs[variant] = regime_frame

    candidates = [item for item in rule_reports if item["metrics"]["total_return"] > summary["group_a_plus_defensive_1m"]["total_return"]]
    candidates.sort(
        key=lambda item: (
            item["metrics"]["sharpe_ratio"],
            item["metrics"]["max_drawdown"],
            item["metrics"]["total_return"],
            _confirmation_strength(item["rule"]),
        ),
        reverse=True,
    )
    recommended = candidates[0] if candidates else max(
        rule_reports,
        key=lambda item: (
            item["metrics"]["sharpe_ratio"],
            item["metrics"]["max_drawdown"],
            item["metrics"]["total_return"],
            _confirmation_strength(item["rule"]),
        ),
    )

    report = {
        "experiment": "group_a_plus_golden1_switch_policy",
        "method_note": (
            "Golden1 is the default regime. 0050 price-risk rules switch to GroupA+ defensive weights, "
            "then switch back after recovery. FinMind-style institutional, margin, market-margin, TDCC, "
            "foreign-shareholding, short-pressure, and derivative institutional features are loaded from local DuckDB tables "
            "for chip/derivative diagnostics and optional confirm rules. "
            "The simulator rebalances only on regime changes and otherwise holds shares."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "initial_value": float(args.initial_value),
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "chip_features": {
            "enabled": chip_features is not None,
            "source_tables": [
                "institutional_data",
                "margin_data",
                "market_margin_data",
                "shareholding_distribution",
                "foreign_shareholding_data",
                "short_sale_balance_data",
                "securities_lending_data",
                "derivative_institutional_data",
            ] if chip_features is not None else [],
        },
        "summary": summary,
        "rule_reports": rule_reports,
        "recommended": {
            "variant": recommended["variant"],
            "rule": recommended["rule"],
            "metrics": recommended["metrics"],
            "defense_days": recommended["defense_days"],
            "defense_day_ratio": recommended["defense_day_ratio"],
            "switch_count": recommended["switch_count"],
            "events": recommended["events"],
        },
    }

    stamp = report["generated_at"].replace("-", "").replace(":", "").replace("T", "_")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_a_plus_switch_policy_backtest_{stamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    regime_path = prefix.with_name(prefix.name + "_recommended_regime.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for name, metrics in summary.items():
        rows.append({"variant": name, **metrics})
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_path, encoding="utf-8-sig")
    regime_outputs[recommended["variant"]].to_csv(regime_path, encoding="utf-8-sig")
    latest_path = _resolve(args.latest_pointer)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "report_type": "switch_backtest",
                "generated_at": report["generated_at"],
                "json": str(json_path.relative_to(PROJECT_ROOT)),
                "csv": str(csv_path.relative_to(PROJECT_ROOT)),
                "curve_csv": str(curve_path.relative_to(PROJECT_ROOT)),
                "recommended_regime_csv": str(regime_path.relative_to(PROJECT_ROOT)),
                "recommended": report["recommended"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Recommended regime CSV: {regime_path}")
    print(f"Latest: {latest_path}")
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    print(f"Recommended: {recommended['variant']}")
    for name in ("golden1_0531_1m", "group_a_plus_defensive_1m", recommended["variant"]):
        metrics = summary[name]
        print(
            f"{name}: final={metrics['final_value']:,.0f}, return={metrics['total_return']:.2%}, "
            f"sharpe={metrics['sharpe_ratio']:.3f}, mdd={metrics['max_drawdown']:.2%}"
        )
    if recommended["events"]:
        print("Switch events:")
        for event in recommended["events"]:
            print(f"  {event['date']} {event['action']} ma_gap={event['ma_gap']:.2%} drawdown={event['drawdown']:.2%}")


if __name__ == "__main__":
    main()
