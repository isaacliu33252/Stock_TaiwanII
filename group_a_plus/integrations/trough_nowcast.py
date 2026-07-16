"""Market-trough nowcast diagnostics for GroupA+ re-entry timing.

This module is diagnostic-first. It classifies a potential post-warning trough
state, but it does not compute target weights or execution regimes.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from scripts.evaluate.evaluate_00631l_multisource_crash_risk import (
    FAMILY_STRESS_CONDITIONS,
    build_multisource_features,
    evaluate_family_condition,
)

TROUGH_STATES = ("NO_TROUGH", "CAPITULATION_WARNING", "PARTIAL_REENTRY", "FULL_REENTRY")
REENTRY_STAGING_FRACTIONS = {
    "NO_TROUGH": None,
    "CAPITULATION_WARNING": None,
    "PARTIAL_REENTRY": 0.7,
    "FULL_REENTRY": 1.0,
}


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _zscore_latest(series: pd.Series, window: int = 60) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < max(10, window // 4):
        return None
    tail = values.tail(window)
    std = float(tail.std())
    if std <= 0.0 or math.isnan(std):
        return None
    return float((values.iloc[-1] - tail.mean()) / std)


def _load_ohlcv(db_path: Path, tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT ticker, dt, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, str(start.date()), str(end.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame(columns=["ticker", "dt", "close", "volume"])
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows


def _load_external_close(db_path: Path, tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "external_market_ohlcv" not in tables:
            return pd.DataFrame()
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
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _series_return(series: pd.Series, periods: int) -> float | None:
    values = series.astype(float).dropna()
    if len(values) <= periods or float(values.iloc[-1 - periods]) <= 0.0:
        return None
    return float(values.iloc[-1] / values.iloc[-1 - periods] - 1.0)


def _recent_rebound(series: pd.Series, lookback: int = 5) -> tuple[float | None, float | None]:
    values = series.astype(float).dropna()
    if len(values) < lookback + 1:
        return None, None
    tail = values.tail(lookback + 1)
    trough = float(tail.min())
    latest = float(tail.iloc[-1])
    if trough <= 0.0:
        return None, None
    return float(latest / trough - 1.0), _series_return(values, min(lookback, len(values) - 1))


def _market_proxy_features(db_path: Path, actual_date: pd.Timestamp) -> dict[str, Any]:
    start = actual_date - pd.Timedelta(days=180)
    rows = _load_ohlcv(db_path, list(TICKERS), start, actual_date)
    if rows.empty:
        return {"status": "unavailable", "reason": "missing_groupa_ohlcv"}

    by_ticker = {
        ticker: part.set_index("dt").sort_index()
        for ticker, part in rows.groupby("ticker")
    }
    close_0050 = by_ticker.get("0050.TW", pd.DataFrame()).get("close", pd.Series(dtype=float))
    close_631l = by_ticker.get("00631L.TW", pd.DataFrame()).get("close", pd.Series(dtype=float))
    if close_0050.empty:
        return {"status": "unavailable", "reason": "missing_0050_ohlcv"}

    ret_0050_1d = _series_return(close_0050, 1)
    ret_0050_5d = _series_return(close_0050, 5)
    rebound_0050, _ = _recent_rebound(close_0050, 5)
    close_0050_values = close_0050.astype(float).dropna()
    latest_0050_close = float(close_0050_values.iloc[-1]) if not close_0050_values.empty else None
    prior_0050_3d = close_0050_values.iloc[-4:-1] if len(close_0050_values) >= 4 else pd.Series(dtype=float)
    prior_0050_3d_low = float(prior_0050_3d.min()) if not prior_0050_3d.empty else None
    no_fresh_0050_lower_low_3d = (
        bool(latest_0050_close >= prior_0050_3d_low)
        if latest_0050_close is not None and prior_0050_3d_low is not None
        else None
    )
    rebound_631l, ret_631l_5d = _recent_rebound(close_631l, 5) if not close_631l.empty else (None, None)
    volume = by_ticker.get("0050.TW", pd.DataFrame()).get("volume", pd.Series(dtype=float))
    ret = close_0050.pct_change()
    dollar_volume = (close_0050 * volume).replace(0.0, pd.NA)
    amihud = (ret.abs() / dollar_volume).replace([float("inf"), -float("inf")], pd.NA)
    volume_z = _zscore_latest(volume, 60)
    amihud_z = _zscore_latest(amihud, 60)
    volume_tail = volume.astype(float).dropna().tail(10)
    panic_volume_contracting = False
    if len(volume_tail) >= 6:
        panic_volume_contracting = bool(volume_tail.max() > volume_tail.iloc[:5].mean() * 1.5 and volume_tail.iloc[-1] < volume_tail.tail(5).mean())

    latest_dt = close_0050.dropna().index.max()
    day = rows[rows["dt"] == latest_dt].copy()
    breadth_up_fraction = None
    limit_down_count = None
    if not day.empty:
        prev = rows[rows["dt"] < latest_dt].sort_values("dt").groupby("ticker").tail(1)[["ticker", "close"]]
        merged = day.merge(prev, on="ticker", suffixes=("", "_prev"))
        returns = merged["close"].astype(float) / merged["close_prev"].astype(float).replace(0.0, pd.NA) - 1.0
        breadth_up_fraction = float((returns > 0.0).mean()) if len(returns) else None
        limit_down_count = int((returns <= -0.095).sum()) if len(returns) else None

    return {
        "status": "ok",
        "ret_0050_1d": ret_0050_1d,
        "ret_0050_5d": ret_0050_5d,
        "ret_00631l_5d": ret_631l_5d,
        "latest_0050_close": latest_0050_close,
        "prior_0050_3d_low": prior_0050_3d_low,
        "no_fresh_0050_lower_low_3d": no_fresh_0050_lower_low_3d,
        "rebound_0050_from_5d_low": rebound_0050,
        "rebound_00631l_from_5d_low": rebound_631l,
        "volume_z60": volume_z,
        "amihud_z60": amihud_z,
        "panic_volume_contracting": panic_volume_contracting,
        "breadth_up_fraction_groupa": breadth_up_fraction,
        "limit_down_count_groupa": limit_down_count,
    }


def _multisource_snapshot(db_path: Path, actual_date: pd.Timestamp) -> dict[str, Any]:
    index = pd.bdate_range(actual_date - pd.Timedelta(days=420), actual_date)
    try:
        features = build_multisource_features(db_path, index)
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)}
    if features.empty:
        return {"status": "unavailable", "reason": "empty_multisource_features"}
    row = features.loc[features.index <= actual_date].tail(1)
    prev = features.loc[features.index < actual_date].tail(5)
    if row.empty:
        return {"status": "unavailable", "reason": "no_feature_row_at_or_before_date"}
    latest = row.iloc[0]
    out = {
        "status": "ok",
        "feature_date": str(pd.Timestamp(row.index[-1]).date()),
        "txo_pcr_volume_z20": _float_or_none(latest.get("txo_pcr_volume_z20")),
        "txo_pcr_oi_z20": _float_or_none(latest.get("txo_pcr_oi_z20")),
        "txo_foreign_put_call_net_oi_chg5_z60": _float_or_none(latest.get("txo_foreign_put_call_net_oi_chg5_z60")),
        "tx_foreign_net_oi_z60": _float_or_none(latest.get("tx_foreign_net_oi_z60")),
        "market_margin_forced_repay_z60": _float_or_none(latest.get("market_margin_forced_repay_z60")),
        "market_margin_balance_chg20_z252": _float_or_none(latest.get("market_margin_balance_chg20_z252")),
        "securities_lending_0050_volume_z60": _float_or_none(latest.get("securities_lending_0050_volume_z60")),
        "soxx_ret1": _float_or_none(latest.get("soxx_ret1")),
        "tsm_adr_ret1": _float_or_none(latest.get("tsm_adr_ret1")),
        "usdtwd_ret5_z60": _float_or_none(latest.get("usdtwd_ret5_z60")),
        "soxx_put_call_iv_skew_z252": _float_or_none(latest.get("soxx_put_call_iv_skew_z252")),
        "soxx_put_call_volume_ratio_z60": _float_or_none(latest.get("soxx_put_call_volume_ratio_z60")),
        "soxx_put_call_oi_ratio_z60": _float_or_none(latest.get("soxx_put_call_oi_ratio_z60")),
    }
    if not prev.empty:
        out["txo_pcr_volume_z20_chg5"] = _float_or_none(latest.get("txo_pcr_volume_z20") - prev.iloc[0].get("txo_pcr_volume_z20"))
        out["usdtwd_ret5_z60_chg5"] = _float_or_none(latest.get("usdtwd_ret5_z60") - prev.iloc[0].get("usdtwd_ret5_z60"))
    return out


def _cross_market_rebound(db_path: Path, actual_date: pd.Timestamp) -> dict[str, Any]:
    start = actual_date - pd.Timedelta(days=60)
    closes = _load_external_close(db_path, ["SOXX", "TSM", "TWD=X", "2330.TW"], start, actual_date)
    out: dict[str, Any] = {"status": "ok" if not closes.empty else "unavailable"}
    if closes.empty:
        out["reason"] = "missing_external_market_ohlcv"
        return out
    for ticker, key in (("SOXX", "soxx"), ("TSM", "tsm_adr"), ("2330.TW", "tw_2330")):
        if ticker in closes:
            rebound, ret5 = _recent_rebound(closes[ticker], 5)
            out[f"{key}_rebound_from_5d_low"] = rebound
            out[f"{key}_ret5"] = ret5
    if "TWD=X" in closes:
        out["usdtwd_ret5"] = _series_return(closes["TWD=X"], 5)
        out["usdtwd_ret1"] = _series_return(closes["TWD=X"], 1)
    return out


def _context_active(
    latest_features: dict[str, Any],
    ncf_live_overlay: dict[str, Any],
    market_state: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    extreme = (ncf_live_overlay.get("a2118_extreme_risk_warning") or {}).get("active") is True
    if extreme:
        reasons.append("a2118_extreme_risk_warning_active")
    if ncf_live_overlay.get("a2118_late_bull_hard_overlay_applied") is True:
        reasons.append("a2118_h20_late_bull_overlay_active")
    if str(market_state.get("state")) in {"crash_risk", "bear_breakdown"}:
        reasons.append(f"market_state={market_state.get('state')}")
    if str(market_state.get("risk_level")) in {"severe", "risk_off"}:
        reasons.append(f"market_risk_level={market_state.get('risk_level')}")
    if int(latest_features.get("total_risk_score", 0) or 0) >= 8 and float(latest_features.get("drawdown", 0.0) or 0.0) <= -0.04:
        reasons.append("high_total_risk_with_drawdown")
    return bool(reasons), reasons


def compute_trough_nowcast(
    *,
    db_path: Path,
    actual_date: pd.Timestamp,
    latest_features: dict[str, Any],
    ncf_live_overlay: dict[str, Any],
    market_state: dict[str, Any],
    signal_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a Taiwan-market trough nowcast for post-warning re-entry."""

    actual = pd.Timestamp(actual_date).normalize()
    context, context_reasons = _context_active(latest_features, ncf_live_overlay, market_state)
    market = _market_proxy_features(db_path, actual)
    multi = _multisource_snapshot(db_path, actual)
    cross = _cross_market_rebound(db_path, actual)

    cap_reasons: list[str] = []
    reentry_reasons: list[str] = []

    def add_cap(condition: bool, reason: str) -> None:
        if condition:
            cap_reasons.append(reason)

    def add_reentry(condition: bool, reason: str) -> None:
        if condition:
            reentry_reasons.append(reason)

    def shared_condition(family: str, name: str) -> bool:
        # Threshold lives in evaluate_00631l_multisource_crash_risk.FAMILY_STRESS_CONDITIONS
        # (single source of truth shared with build_00631l_crash_risk_alert.py --
        # see the Fable audit note there).
        column, comparator, threshold = FAMILY_STRESS_CONDITIONS[family][name]
        return evaluate_family_condition(multi.get(column), comparator, threshold)

    add_cap(float(latest_features.get("drawdown", 0.0) or 0.0) <= -0.06, "0050_strategy_drawdown_le_6pct")
    add_cap(int(latest_features.get("tail_risk_score", 0) or 0) >= 2, "tail_risk_score_ge_2")
    add_cap((ncf_live_overlay.get("a2118_extreme_risk_warning") or {}).get("active") is True, "h20_extreme_warning_active")
    add_cap((_float_or_none(market.get("volume_z60")) or 0.0) >= 1.0, "0050_volume_z60_ge_1")
    add_cap((_float_or_none(market.get("amihud_z60")) or 0.0) >= 1.0, "0050_amihud_z60_ge_1")
    add_cap(bool(market.get("panic_volume_contracting")), "panic_volume_expanded_then_contracting")
    add_cap(shared_condition("options_tail", "txo_pcr_volume_z20_ge_1"), "txo_pcr_volume_z20_ge_1")
    add_cap(shared_condition("options_tail", "txo_pcr_oi_z20_ge_1"), "txo_pcr_oi_z20_ge_1")
    add_cap(shared_condition("options_tail", "txo_foreign_put_call_net_oi_chg5_z60_ge_1"), "foreign_txo_put_call_oi_chg5_z60_ge_1")
    add_cap(shared_condition("liquidity_forced_selling", "market_margin_forced_repay_z60_ge_1"), "market_margin_forced_repay_z60_ge_1")
    add_cap(shared_condition("liquidity_forced_selling", "market_margin_balance_chg20_z252_le_minus_1"), "market_margin_balance_chg20_z252_le_minus_1")
    add_cap(shared_condition("cross_market_shock", "soxx_put_call_iv_skew_z252_ge_1"), "soxx_put_call_iv_skew_z252_ge_1")
    add_cap(shared_condition("cross_market_shock", "usdtwd_ret5_z60_ge_1"), "usdtwd_ret5_z60_ge_1")

    add_reentry((_float_or_none(market.get("ret_0050_1d")) or 0.0) >= 0.01, "0050_1d_rebound_ge_1pct")
    add_reentry((_float_or_none(market.get("rebound_0050_from_5d_low")) or 0.0) >= 0.02, "0050_rebound_from_5d_low_ge_2pct")
    add_reentry((_float_or_none(market.get("rebound_00631l_from_5d_low")) or 0.0) >= 0.04, "00631l_rebound_from_5d_low_ge_4pct")
    add_reentry((_float_or_none(market.get("breadth_up_fraction_groupa")) or 0.0) >= 0.5, "groupa_breadth_up_fraction_ge_50pct")
    add_reentry((_float_or_none(cross.get("soxx_rebound_from_5d_low")) or 0.0) >= 0.03, "soxx_rebound_from_5d_low_ge_3pct")
    add_reentry((_float_or_none(cross.get("tsm_adr_rebound_from_5d_low")) or 0.0) >= 0.03, "tsm_adr_rebound_from_5d_low_ge_3pct")
    add_reentry((_float_or_none(cross.get("tw_2330_rebound_from_5d_low")) or 0.0) >= 0.02, "2330_rebound_from_5d_low_ge_2pct")
    add_reentry((_float_or_none(cross.get("usdtwd_ret1")) or 0.0) <= -0.002, "usdtwd_1d_turns_lower")
    add_reentry((_float_or_none(multi.get("txo_pcr_volume_z20_chg5")) or 0.0) <= -0.5, "txo_pcr_volume_z20_falling")
    add_reentry((_float_or_none(multi.get("usdtwd_ret5_z60_chg5")) or 0.0) <= -0.5, "usdtwd_riskoff_z_falling")

    capitulation_score = len(cap_reasons)
    reentry_score = len(reentry_reasons)
    local_price_confirm = bool(
        "0050_1d_rebound_ge_1pct" in reentry_reasons
        or "0050_rebound_from_5d_low_ge_2pct" in reentry_reasons
    ) and "groupa_breadth_up_fraction_ge_50pct" in reentry_reasons
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
        capitulation_score >= 4
        and reentry_score >= 6
        and local_price_confirm
        and risk_unwind_confirm
        and cross_market_confirm
        and "00631l_rebound_from_5d_low_ge_4pct" in reentry_reasons
    )
    partial_reentry_confirmed = bool(
        capitulation_score >= 3
        and reentry_score >= 4
        and local_price_confirm
        and (risk_unwind_confirm or cross_market_confirm)
        and not full_reentry_candidate
    )
    if not context:
        state = "NO_TROUGH"
    elif full_reentry_confirmed:
        state = "FULL_REENTRY"
    elif partial_reentry_confirmed:
        state = "PARTIAL_REENTRY"
    elif capitulation_score >= 2:
        state = "CAPITULATION_WARNING"
    else:
        state = "NO_TROUGH"

    return {
        "state": state,
        "state_space": list(TROUGH_STATES),
        "policy": "diagnostic_reentry_timing_only_no_target_weight_change",
        "recommended_execution_staging_fraction": REENTRY_STAGING_FRACTIONS[state],
        "context_active": context,
        "context_reasons": context_reasons,
        "capitulation_score": capitulation_score,
        "reentry_confirmation_score": reentry_score,
        "capitulation_reasons": cap_reasons,
        "reentry_confirmation_reasons": reentry_reasons,
        "full_reentry_checks": {
            "local_price_confirm": local_price_confirm,
            "risk_unwind_confirm": risk_unwind_confirm,
            "cross_market_confirm": cross_market_confirm,
            "partial_reentry_confirmed": partial_reentry_confirmed,
            "full_reentry_candidate": full_reentry_candidate,
            "full_reentry_disabled_reason": "shadow_audit_false_reentry_rate_too_high",
            "full_reentry_confirmed": full_reentry_confirmed,
        },
        "inputs": {
            "latest_features": {
                key: latest_features.get(key)
                for key in ("ma_gap", "drawdown", "exit_momentum_5d", "total_risk_score", "tail_risk_score")
            },
            "market_proxy": market,
            "multisource": multi,
            "cross_market_rebound": cross,
            "signal_alignment": {
                "alignment": (signal_alignment or {}).get("alignment"),
                "dominant_direction": (signal_alignment or {}).get("dominant_direction"),
            },
        },
        "rationale": (
            "Rare-event trough nowcast adapted for Taiwan proxies: options tail demand, "
            "liquidity stress, breadth/liquidity capitulation, USD/TWD and SOXX/TSM/2330 rebound. "
            "It only activates after an H20/crash/defensive warning context."
        ),
    }
