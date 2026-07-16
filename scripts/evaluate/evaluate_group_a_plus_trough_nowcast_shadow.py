#!/usr/bin/env python3
"""Shadow audit for the GroupA+ market-trough nowcast.

Research-only. This script evaluates the trough nowcast as a post-warning
re-entry timing diagnostic. It does not change live target weights, manifests,
or execution plans.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.operations.market_state import classify_market_state
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_00631l_multisource_crash_risk import build_multisource_features

PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"

DEFAULT_WINDOWS = [
    ("active_2025_2026", "2025-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "stress_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "stress_window"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
]

COMMON_A2118_KW = dict(
    h20_max=0.33,
    conf_min=0.55,
    h5_reentry_min=0.55,
    chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
    momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
    momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
)

FORWARD_HORIZONS = (1, 3, 5, 10)
TROUGH_STATES = ("NO_TROUGH", "CAPITULATION_WARNING", "PARTIAL_REENTRY", "FULL_REENTRY")


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    values = close.astype(float)
    return values.shift(-int(horizon)).div(values).sub(1.0)


def _forward_max_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    values = close.astype(float)
    out = pd.Series(index=values.index, dtype=float)
    for pos, dt in enumerate(values.index):
        future = values.iloc[pos : pos + int(horizon) + 1].dropna()
        if len(future) <= 1:
            continue
        start = float(future.iloc[0])
        if start <= 0.0:
            continue
        out.loc[dt] = float(future.min() / start - 1.0)
    return out


def _zscore(series: pd.Series, window: int = 60) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window, min_periods=max(10, window // 4)).mean()
    std = values.rolling(window, min_periods=max(10, window // 4)).std().replace(0.0, float("nan"))
    return (values - mean) / std


def _load_ohlcv_frame(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    import duckdb

    start = pd.Timestamp(index.min()) - pd.Timedelta(days=220)
    end = pd.Timestamp(index.max())
    placeholders = ", ".join(["?"] * len(TICKERS))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT ticker, dt, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*TICKERS, str(start.date()), str(end.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame(index=index)
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()
    volume = rows.pivot_table(index="dt", columns="ticker", values="volume", aggfunc="last").sort_index()
    out = pd.DataFrame(index=close.index)
    close_0050 = close.get("0050.TW", pd.Series(dtype=float)).astype(float)
    close_631l = close.get("00631L.TW", pd.Series(dtype=float)).astype(float)
    volume_0050 = volume.get("0050.TW", pd.Series(dtype=float)).astype(float)
    out["ret_0050_1d"] = close_0050.pct_change(1)
    out["rebound_0050_from_5d_low"] = close_0050.div(close_0050.rolling(6, min_periods=2).min()).sub(1.0)
    out["rebound_00631l_from_5d_low"] = close_631l.div(close_631l.rolling(6, min_periods=2).min()).sub(1.0)
    out["volume_z60"] = _zscore(volume_0050, 60)
    amihud = close_0050.pct_change().abs() / (close_0050 * volume_0050).replace(0.0, float("nan"))
    out["amihud_z60"] = _zscore(amihud, 60)
    avg_first = volume_0050.rolling(10, min_periods=6).apply(lambda x: float(pd.Series(x[:5]).mean()), raw=False)
    max_10 = volume_0050.rolling(10, min_periods=6).max()
    mean_5 = volume_0050.rolling(5, min_periods=3).mean()
    out["panic_volume_contracting"] = (max_10 > avg_first * 1.5) & (volume_0050 < mean_5)

    returns_by_ticker = close.pct_change()
    out["breadth_up_fraction_groupa"] = returns_by_ticker.reindex(columns=list(TICKERS)).gt(0.0).mean(axis=1)
    out["limit_down_count_groupa"] = returns_by_ticker.reindex(columns=list(TICKERS)).le(-0.095).sum(axis=1)
    return out.reindex(index)


def _load_external_rebound_frame(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    import duckdb

    start = pd.Timestamp(index.min()) - pd.Timedelta(days=80)
    end = pd.Timestamp(index.max())
    tickers = ["SOXX", "TSM", "TWD=X", "2330.TW"]
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "external_market_ohlcv" not in tables:
            return pd.DataFrame(index=index)
        rows = con.execute(
            f"""
            SELECT ticker, dt, close
            FROM external_market_ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, str(start.date()), str(end.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame(index=index)
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()
    out = pd.DataFrame(index=close.index)
    for ticker, key in (("SOXX", "soxx"), ("TSM", "tsm_adr"), ("2330.TW", "tw_2330")):
        if ticker in close:
            out[f"{key}_rebound_from_5d_low"] = close[ticker].astype(float).div(
                close[ticker].astype(float).rolling(6, min_periods=2).min()
            ).sub(1.0)
    if "TWD=X" in close:
        out["usdtwd_ret1"] = close["TWD=X"].astype(float).pct_change(1)
    return out.reindex(index).ffill(limit=2)


def _frame_features(row: pd.Series) -> dict[str, Any]:
    return {
        "ma_gap": float(row.get("ma_gap", 0.0) or 0.0),
        "drawdown": float(row.get("drawdown", 0.0) or 0.0),
        "exit_momentum_5d": float(row.get("exit_momentum", row.get("exit_momentum_5d", 0.0)) or 0.0),
        "chip_score": int(row.get("chip_score", 0) or 0),
        "derivative_score": int(row.get("derivative_score", 0) or 0),
        "total_risk_score": int(row.get("total_risk_score", 0) or 0),
        "tail_risk_score": int(row.get("tail_risk_score", 0) or 0),
    }


def _context_overlay(row: pd.Series, market_state: dict[str, Any]) -> dict[str, Any]:
    regime = str(row.get("execution_regime", row.get("regime", "")))
    h20_prob = row.get("ncf_h20_prob_up", row.get("h20_prob_up", None))
    mdd_prob = row.get("prob_fwd_mdd_gt5_h20", None)
    h20_extreme = False
    try:
        h20_extreme = h20_prob is not None and float(h20_prob) <= 0.22 and mdd_prob is not None and float(mdd_prob) >= 0.85
    except Exception:
        h20_extreme = False
    return {
        "current_regime": "golden1" if regime == "golden1" else regime,
        "a2118_late_bull_hard_overlay_applied": regime.startswith("ncf_late_bull"),
        "a2118_extreme_risk_warning": {
            "active": h20_extreme or str(market_state.get("state")) == "crash_risk",
            "policy": "shadow_context_only",
        },
    }


def _has_warning_context(features: dict[str, Any], market_state: dict[str, Any], overlay: dict[str, Any]) -> bool:
    return bool(
        overlay.get("a2118_late_bull_hard_overlay_applied")
        or (overlay.get("a2118_extreme_risk_warning") or {}).get("active") is True
        or str(market_state.get("state")) in {"crash_risk", "bear_breakdown"}
        or str(market_state.get("risk_level")) in {"severe", "risk_off"}
        or (int(features.get("total_risk_score", 0) or 0) >= 8 and float(features.get("drawdown", 0.0) or 0.0) <= -0.04)
    )


def build_trough_state_frame(
    *,
    db_path: Path,
    strategy_frame: pd.DataFrame,
) -> pd.DataFrame:
    index = pd.DatetimeIndex(strategy_frame.index)
    market_proxy = _load_ohlcv_frame(db_path, index)
    external = _load_external_rebound_frame(db_path, index)
    try:
        multisource = build_multisource_features(db_path, pd.bdate_range(index.min() - pd.Timedelta(days=420), index.max()))
    except Exception:
        multisource = pd.DataFrame(index=index)
    multisource = multisource.reindex(index)
    if "txo_pcr_volume_z20" in multisource:
        multisource["txo_pcr_volume_z20_chg5"] = multisource["txo_pcr_volume_z20"].diff(5)
    if "usdtwd_ret5_z60" in multisource:
        multisource["usdtwd_ret5_z60_chg5"] = multisource["usdtwd_ret5_z60"].diff(5)
    rows: list[dict[str, Any]] = []
    for dt, row in strategy_frame.iterrows():
        features = _frame_features(row)
        regime = str(row.get("execution_regime", row.get("regime", "golden1")))
        market_state = classify_market_state(regime, features)
        overlay = _context_overlay(row, market_state)
        if not _has_warning_context(features, market_state, overlay):
            nowcast = {
                "state": "NO_TROUGH",
                "context_active": False,
                "capitulation_score": 0,
                "reentry_confirmation_score": 0,
                "capitulation_reasons": [],
                "reentry_confirmation_reasons": [],
            }
        else:
            mp = market_proxy.loc[dt] if dt in market_proxy.index else pd.Series(dtype=float)
            ms = multisource.loc[dt] if dt in multisource.index else pd.Series(dtype=float)
            ex = external.loc[dt] if dt in external.index else pd.Series(dtype=float)
            cap_reasons: list[str] = []
            reentry_reasons: list[str] = []

            def val(series: pd.Series, key: str, default: float = 0.0) -> float:
                try:
                    out = float(series.get(key, default))
                    return default if pd.isna(out) else out
                except Exception:
                    return default

            def cap(condition: bool, reason: str) -> None:
                if condition:
                    cap_reasons.append(reason)

            def reentry(condition: bool, reason: str) -> None:
                if condition:
                    reentry_reasons.append(reason)

            cap(float(features.get("drawdown", 0.0)) <= -0.06, "0050_strategy_drawdown_le_6pct")
            cap(int(features.get("tail_risk_score", 0)) >= 2, "tail_risk_score_ge_2")
            cap((overlay.get("a2118_extreme_risk_warning") or {}).get("active") is True, "h20_extreme_warning_active")
            cap(val(mp, "volume_z60") >= 1.0, "0050_volume_z60_ge_1")
            cap(val(mp, "amihud_z60") >= 1.0, "0050_amihud_z60_ge_1")
            cap(bool(mp.get("panic_volume_contracting", False)), "panic_volume_expanded_then_contracting")
            cap(val(ms, "txo_pcr_volume_z20") >= 1.0, "txo_pcr_volume_z20_ge_1")
            cap(val(ms, "txo_pcr_oi_z20") >= 1.0, "txo_pcr_oi_z20_ge_1")
            cap(val(ms, "txo_foreign_put_call_net_oi_chg5_z60") >= 1.0, "foreign_txo_put_call_oi_chg5_z60_ge_1")
            cap(val(ms, "market_margin_forced_repay_z60") >= 1.0, "market_margin_forced_repay_z60_ge_1")
            cap(val(ms, "market_margin_balance_chg20_z252") <= -1.0, "market_margin_balance_chg20_z252_le_minus_1")
            cap(val(ms, "soxx_put_call_iv_skew_z252") >= 1.0, "soxx_put_call_iv_skew_z252_ge_1")
            cap(val(ms, "usdtwd_ret5_z60") >= 1.0, "usdtwd_ret5_z60_ge_1")

            reentry(val(mp, "ret_0050_1d") >= 0.01, "0050_1d_rebound_ge_1pct")
            reentry(val(mp, "rebound_0050_from_5d_low") >= 0.02, "0050_rebound_from_5d_low_ge_2pct")
            reentry(val(mp, "rebound_00631l_from_5d_low") >= 0.04, "00631l_rebound_from_5d_low_ge_4pct")
            reentry(val(mp, "breadth_up_fraction_groupa") >= 0.5, "groupa_breadth_up_fraction_ge_50pct")
            reentry(val(ex, "soxx_rebound_from_5d_low") >= 0.03, "soxx_rebound_from_5d_low_ge_3pct")
            reentry(val(ex, "tsm_adr_rebound_from_5d_low") >= 0.03, "tsm_adr_rebound_from_5d_low_ge_3pct")
            reentry(val(ex, "tw_2330_rebound_from_5d_low") >= 0.02, "2330_rebound_from_5d_low_ge_2pct")
            reentry(val(ex, "usdtwd_ret1") <= -0.002, "usdtwd_1d_turns_lower")
            reentry(val(ms, "txo_pcr_volume_z20_chg5") <= -0.5, "txo_pcr_volume_z20_falling")
            reentry(val(ms, "usdtwd_ret5_z60_chg5") <= -0.5, "usdtwd_riskoff_z_falling")
            cap_score = len(cap_reasons)
            reentry_score = len(reentry_reasons)
            local_price_confirm = bool(
                ("0050_1d_rebound_ge_1pct" in reentry_reasons or "0050_rebound_from_5d_low_ge_2pct" in reentry_reasons)
                and "groupa_breadth_up_fraction_ge_50pct" in reentry_reasons
            )
            risk_unwind_confirm = bool(
                "txo_pcr_volume_z20_falling" in reentry_reasons
                or "usdtwd_riskoff_z_falling" in reentry_reasons
                or "usdtwd_1d_turns_lower" in reentry_reasons
            )
            cross_market_confirm = bool(
                "soxx_rebound_from_5d_low_ge_3pct" in reentry_reasons
                or "tsm_adr_rebound_from_5d_low_ge_3pct" in reentry_reasons
                or "2330_rebound_from_5d_low_ge_2pct" in reentry_reasons
            )
            full_reentry_confirmed = False
            full_reentry_candidate = bool(
                cap_score >= 4
                and reentry_score >= 6
                and local_price_confirm
                and risk_unwind_confirm
                and cross_market_confirm
                and "00631l_rebound_from_5d_low_ge_4pct" in reentry_reasons
            )
            partial_reentry_confirmed = bool(
                cap_score >= 3
                and reentry_score >= 4
                and local_price_confirm
                and (risk_unwind_confirm or cross_market_confirm)
                and not full_reentry_candidate
            )
            if full_reentry_confirmed:
                state = "FULL_REENTRY"
            elif partial_reentry_confirmed:
                state = "PARTIAL_REENTRY"
            elif cap_score >= 2:
                state = "CAPITULATION_WARNING"
            else:
                state = "NO_TROUGH"
            nowcast = {
                "state": state,
                "context_active": True,
                "capitulation_score": cap_score,
                "reentry_confirmation_score": reentry_score,
                "capitulation_reasons": cap_reasons,
                "reentry_confirmation_reasons": reentry_reasons,
            }
        rows.append(
            {
                "date": pd.Timestamp(dt),
                "state": nowcast.get("state", "NO_TROUGH"),
                "context_active": bool(nowcast.get("context_active", False)),
                "capitulation_score": int(nowcast.get("capitulation_score", 0) or 0),
                "reentry_confirmation_score": int(nowcast.get("reentry_confirmation_score", 0) or 0),
                "market_state": market_state.get("state"),
                "execution_regime": regime,
                "capitulation_reasons": ";".join(nowcast.get("capitulation_reasons", []) or []),
                "reentry_confirmation_reasons": ";".join(nowcast.get("reentry_confirmation_reasons", []) or []),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["state"]).set_index(pd.DatetimeIndex([]))
    return out.set_index("date").sort_index()


def summarize_forward_returns(
    state_frame: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = FORWARD_HORIZONS,
    false_reentry_horizon: int = 10,
    false_reentry_drawdown_threshold: float = -0.03,
) -> dict[str, Any]:
    joined = state_frame.copy()
    for ticker in ("0050.TW", "00631L.TW"):
        if ticker not in prices:
            continue
        close = prices[ticker].astype(float).reindex(joined.index)
        for horizon in horizons:
            joined[f"{ticker}_fwd_return_{horizon}d"] = _forward_return(close, horizon).reindex(joined.index)
        joined[f"{ticker}_fwd_max_drawdown_{false_reentry_horizon}d"] = _forward_max_drawdown(
            close,
            false_reentry_horizon,
        ).reindex(joined.index)

    by_state: dict[str, Any] = {}
    for state in TROUGH_STATES:
        part = joined[joined["state"] == state]
        row: dict[str, Any] = {"days": int(len(part))}
        for ticker in ("0050.TW", "00631L.TW"):
            for horizon in horizons:
                col = f"{ticker}_fwd_return_{horizon}d"
                if col in part:
                    valid = part[col].dropna()
                    row[f"{ticker}_fwd_return_{horizon}d_mean"] = float(valid.mean()) if not valid.empty else None
                    row[f"{ticker}_fwd_return_{horizon}d_positive_rate"] = float((valid > 0.0).mean()) if not valid.empty else None
            dd_col = f"{ticker}_fwd_max_drawdown_{false_reentry_horizon}d"
            if dd_col in part:
                valid_dd = part[dd_col].dropna()
                row[f"{ticker}_false_reentry_rate_mdd_lt_{abs(false_reentry_drawdown_threshold):.0%}"] = (
                    float((valid_dd <= false_reentry_drawdown_threshold).mean()) if not valid_dd.empty else None
                )
        by_state[state] = row

    active = joined[joined["state"].isin(["PARTIAL_REENTRY", "FULL_REENTRY"])]
    false_events = []
    dd_event_col = f"00631L.TW_fwd_max_drawdown_{false_reentry_horizon}d"
    if dd_event_col in active:
        for dt, row in active[active[dd_event_col] <= false_reentry_drawdown_threshold].iterrows():
            false_events.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "state": row["state"],
                    dd_event_col: round(float(row[dd_event_col]), 6),
                    "00631L.TW_fwd_return_5d": (
                        round(float(row["00631L.TW_fwd_return_5d"]), 6)
                        if pd.notna(row.get("00631L.TW_fwd_return_5d"))
                        else None
                    ),
                }
            )
    return {
        "by_state": by_state,
        "false_reentry_events": false_events[:100],
        "false_reentry_event_count": len(false_events),
    }


def _target_weights_for_regime(report: dict[str, Any], regime: str) -> dict[str, float]:
    weights = report.get("base_weights") or report.get("weights") or {}
    if regime in weights:
        return _normalize(dict(weights[regime]))
    aliases = {"golden1": "golden1_0531_1m", "group_a_plus_defensive": "group_a_plus_defensive_1m"}
    alias = aliases.get(regime)
    if alias and alias in weights:
        return _normalize(dict(weights[alias]))
    raise KeyError(f"Missing weights for regime {regime}")


def simulate_staging_policy(
    prices: pd.DataFrame,
    regimes: pd.Series,
    state_frame: pd.DataFrame,
    report: dict[str, Any],
    *,
    initial_value: float = 1_000_000.0,
    base_buy_fraction: float = 0.4,
    partial_fraction: float = 0.7,
    full_fraction: float = 1.0,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> dict[str, Any]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    costs = 0.0
    turnover = 0.0
    events: list[dict[str, Any]] = []

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        regime = str(regimes.reindex(prices.index).loc[dt])
        state = str(state_frame.reindex(prices.index).loc[dt, "state"]) if dt in state_frame.index else "NO_TROUGH"
        if regime != current_regime:
            target_weights = _target_weights_for_regime(report, regime)
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            target_values_full = {ticker: gross_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
            if state == "FULL_REENTRY":
                buy_fraction = full_fraction
            elif state == "PARTIAL_REENTRY":
                buy_fraction = partial_fraction
            else:
                buy_fraction = base_buy_fraction
            staged_target_values = {}
            for ticker in TICKERS:
                current = current_values.get(ticker, 0.0)
                target = target_values_full.get(ticker, 0.0)
                staged_target_values[ticker] = target if target <= current else current + (target - current) * buy_fraction
            cost, traded = _trade_cost(current_values, staged_target_values, commission_rate, slippage_rate, equity_etf_sell_tax)
            net_value = max(gross_value - cost, 0.0)
            scale = net_value / gross_value if gross_value > 0.0 else 0.0
            shares = {
                ticker: staged_target_values.get(ticker, 0.0) * scale / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = max(net_value - sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS), 0.0)
            costs += cost
            turnover += traded
            current_regime = regime
            if buy_fraction > base_buy_fraction:
                events.append(
                    {
                        "date": str(pd.Timestamp(dt).date()),
                        "state": state,
                        "regime": regime,
                        "buy_fraction": float(buy_fraction),
                        "turnover": float(traded),
                    }
                )
            gross_value = net_value
        values.append(gross_value)

    curve = pd.Series(values, index=prices.index, dtype=float)
    return {
        "metrics": _metrics(curve, initial_value),
        "execution": {
            "transaction_cost": float(costs),
            "turnover_value": float(turnover),
            "accelerated_event_count": len(events),
            "accelerated_events": events[:100],
        },
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
) -> dict[str, Any]:
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=panel,
        **COMMON_A2118_KW,
    )
    prices, _coverage = _load_total_return_prices(db_path, frame.index)
    prices = prices.reindex(frame.index).dropna()
    frame = frame.reindex(prices.index)
    state_frame = build_trough_state_frame(db_path=db_path, strategy_frame=frame)
    forward = summarize_forward_returns(state_frame, prices)
    baseline = simulate_staging_policy(
        prices,
        frame["execution_regime"].astype(str),
        state_frame.assign(state="NO_TROUGH"),
        report,
        initial_value=initial_value,
    )
    accelerated = simulate_staging_policy(
        prices,
        frame["execution_regime"].astype(str),
        state_frame,
        report,
        initial_value=initial_value,
    )
    delta = {
        key: float(accelerated["metrics"][key] - baseline["metrics"][key])
        for key in ("final_value", "sharpe_ratio", "max_drawdown")
        if key in accelerated["metrics"] and key in baseline["metrics"]
    }
    return {
        "label": label,
        "kind": kind,
        "start": start,
        "end": end,
        "panel": panel,
        "state_counts": {state: int((state_frame["state"] == state).sum()) for state in TROUGH_STATES},
        "forward_return_audit": forward,
        "staging_counterfactual": {
            "policy": "execution_staging_approximation_only_target_weights_unchanged",
            "baseline": baseline,
            "accelerated": accelerated,
            "delta_accelerated_minus_baseline": delta,
        },
    }


def _parse_windows(raw: str) -> list[tuple[str, str, str, str, str]]:
    if raw == "default":
        return DEFAULT_WINDOWS
    windows = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 5:
            raise ValueError("Each window must be label,start,end,panel,kind")
        windows.append(tuple(parts))  # type: ignore[arg-type]
    return windows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default", help="default or semicolon-separated label,start,end,panel,kind")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "group_a_plus_trough_nowcast_shadow_20260714.json"))
    args = parser.parse_args()

    db_path = Path(args.db)
    windows = _parse_windows(args.windows)
    payload = {
        "experiment": "group_a_plus_trough_nowcast_shadow",
        "research_only": True,
        "policy": "diagnostic_reentry_timing_only_no_target_weight_change",
        "windows": [],
    }
    for label, start, end, panel, kind in windows:
        print(f"Evaluating {label}: {start}..{end}")
        try:
            payload["windows"].append(
                evaluate_window(
                    label=label,
                    start=start,
                    end=end,
                    panel=panel,
                    kind=kind,
                    db_path=db_path,
                    initial_value=args.initial_value,
                )
            )
        except Exception as exc:
            payload["windows"].append(
                {"label": label, "kind": kind, "start": start, "end": end, "panel": panel, "status": "failed", "error": str(exc)}
            )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
