"""LETF liquidity feedback shadow diagnostics inspired by arXiv 2603.05862."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _zscore(series: pd.Series, window: int = 60) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    mean = series.rolling(window, min_periods=max(10, window // 3)).mean()
    std = series.rolling(window, min_periods=max(10, window // 3)).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-horizon) / close - 1.0


def _forward_mdd(close: pd.Series, horizon: int) -> pd.Series:
    values: list[float | None] = []
    raw = close.astype(float).tolist()
    for idx, start in enumerate(raw):
        future = raw[idx + 1 : idx + horizon + 1]
        if not future or not start or math.isnan(start):
            values.append(None)
            continue
        valid_future = [price for price in future if price and not math.isnan(price)]
        values.append(min(price / start - 1.0 for price in valid_future) if valid_future else None)
    return pd.Series(values, index=close.index, dtype=float)


def _summary(values: pd.Series) -> dict[str, Any]:
    clean = values.dropna().astype(float)
    if clean.empty:
        return {"n": 0}
    return {
        "n": int(len(clean)),
        "mean": float(clean.mean()),
        "p05": float(clean.quantile(0.05)),
        "p50": float(clean.quantile(0.50)),
        "p95": float(clean.quantile(0.95)),
        "negative_rate": float((clean < 0).mean()),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_daily_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    required = {"ticker", "dt", "open", "high", "low", "close", "volume"}
    missing = required - set(ohlcv.columns)
    if missing:
        raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    frame = ohlcv.copy()
    frame["dt"] = pd.to_datetime(frame["dt"])
    frame = frame.sort_values(["ticker", "dt"])
    wide = frame.pivot(index="dt", columns="ticker", values=["open", "high", "low", "close", "volume"])
    close = wide["close"].astype(float)
    high = wide["high"].astype(float)
    low = wide["low"].astype(float)
    volume = wide["volume"].astype(float)

    out = pd.DataFrame(index=close.index)
    for ticker in ("0050.TW", "00631L.TW", "00632R.TW"):
        if ticker not in close:
            continue
        ret = close[ticker].pct_change(fill_method=None)
        true_range = (high[ticker] - low[ticker]) / close[ticker].shift(1)
        amihud = ret.abs() / volume[ticker].replace(0.0, np.nan)
        out[f"ret_{ticker}"] = ret
        out[f"true_range_{ticker}"] = true_range
        out[f"volume_z_{ticker}"] = _zscore(volume[ticker])
        out[f"amihud_z_{ticker}"] = _zscore(amihud)
        out[f"drawdown_20d_{ticker}"] = close[ticker] / close[ticker].rolling(20, min_periods=5).max() - 1.0

    if {"0050.TW", "00631L.TW"} <= set(close.columns):
        out["dislocation_00631l_vs_2x_0050"] = close["00631L.TW"].pct_change(fill_method=None) - 2.0 * close[
            "0050.TW"
        ].pct_change(fill_method=None)
        out["dislocation_z_00631l"] = _zscore(out["dislocation_00631l_vs_2x_0050"].abs())
    if {"0050.TW", "00632R.TW"} <= set(close.columns):
        out["dislocation_00632r_vs_inverse_0050"] = close["00632R.TW"].pct_change(fill_method=None) + close[
            "0050.TW"
        ].pct_change(fill_method=None)
        out["dislocation_z_00632r"] = _zscore(out["dislocation_00632r_vs_inverse_0050"].abs())

    return out


def _flag_reason(row: pd.Series, ticker: str, *, range_z_min: float, volume_z_min: float, dislocation_z_min: float) -> list[str]:
    reasons: list[str] = []
    if _safe_float(row.get(f"true_range_{ticker}")) >= range_z_min:
        reasons.append(f"{ticker}_true_range_ge_{range_z_min}")
    if _safe_float(row.get(f"volume_z_{ticker}")) >= volume_z_min:
        reasons.append(f"{ticker}_volume_z_ge_{volume_z_min}")
    dislocation_key = "dislocation_z_00631l" if ticker == "00631L.TW" else "dislocation_z_00632r"
    if _safe_float(row.get(dislocation_key)) >= dislocation_z_min:
        reasons.append(f"{ticker}_tracking_dislocation_z_ge_{dislocation_z_min}")
    if _safe_float(row.get("ret_0050.TW")) < 0.0 and _safe_float(row.get("drawdown_20d_0050.TW")) <= -0.03:
        reasons.append("0050_down_in_20d_drawdown_ge_3pct")
    return reasons


def build_letf_liquidity_feedback_backtest(
    *,
    ohlcv: pd.DataFrame,
    as_of: str | None = None,
    start: str = "2015-01-01",
    range_threshold: float = 0.035,
    volume_z_min: float = 1.5,
    dislocation_z_min: float = 1.5,
    min_trigger_count: int = 20,
) -> dict[str, Any]:
    features = build_daily_features(ohlcv)
    features = features.loc[features.index >= pd.Timestamp(start)].copy()
    if as_of:
        features = features.loc[features.index <= pd.Timestamp(as_of)].copy()
    close = (
        ohlcv.assign(dt=pd.to_datetime(ohlcv["dt"]))
        .pivot(index="dt", columns="ticker", values="close")
        .sort_index()
        .astype(float)
    )
    close = close.reindex(features.index)
    forward: dict[str, dict[str, pd.Series]] = {}
    for ticker in ("00631L.TW", "00632R.TW"):
        if ticker not in close:
            continue
        forward[ticker] = {}
        for horizon in (1, 5, 10, 20):
            forward[ticker][f"return_{horizon}d"] = _forward_return(close[ticker], horizon)
            forward[ticker][f"mdd_{horizon}d"] = _forward_mdd(close[ticker], horizon)

    events: list[dict[str, Any]] = []
    for dt, row in features.iterrows():
        event_reasons: dict[str, list[str]] = {}
        for ticker in ("00631L.TW", "00632R.TW"):
            reasons = _flag_reason(
                row,
                ticker,
                range_z_min=range_threshold,
                volume_z_min=volume_z_min,
                dislocation_z_min=dislocation_z_min,
            )
            if len(reasons) >= 2:
                event_reasons[ticker] = reasons
        if not event_reasons:
            continue
        record: dict[str, Any] = {
            "date": str(pd.Timestamp(dt).date()),
            "tickers": sorted(event_reasons),
            "reasons": event_reasons,
        }
        for ticker in ("00631L.TW", "00632R.TW"):
            if ticker not in forward:
                continue
            for horizon in (1, 5, 10, 20):
                fwd_ret = forward[ticker][f"return_{horizon}d"].loc[dt]
                fwd_mdd = forward[ticker][f"mdd_{horizon}d"].loc[dt]
                record[f"{ticker}_fwd_return_{horizon}d"] = float(fwd_ret) if pd.notna(fwd_ret) else None
                record[f"{ticker}_fwd_mdd_{horizon}d"] = float(fwd_mdd) if pd.notna(fwd_mdd) else None
        events.append(record)

    event_frame = pd.DataFrame(events)
    metrics: dict[str, Any] = {}
    for ticker in ("00631L.TW", "00632R.TW"):
        ticker_events = event_frame[event_frame["tickers"].apply(lambda xs, t=ticker: t in xs)] if not event_frame.empty else pd.DataFrame()
        metrics[ticker] = {}
        for horizon in (1, 5, 10, 20):
            if ticker_events.empty:
                metrics[ticker][f"fwd_return_{horizon}d"] = {"n": 0}
                metrics[ticker][f"fwd_mdd_{horizon}d"] = {"n": 0}
            else:
                metrics[ticker][f"fwd_return_{horizon}d"] = _summary(ticker_events[f"{ticker}_fwd_return_{horizon}d"])
                metrics[ticker][f"fwd_mdd_{horizon}d"] = _summary(ticker_events[f"{ticker}_fwd_mdd_{horizon}d"])

    trigger_count = len(events)
    ready = trigger_count >= min_trigger_count
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_letf_liquidity_feedback_watch_shadow_backtest",
        "policy": "shadow_backtest_only_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2603.05862.pdf",
            "title": "Impact of arbitrage between leveraged ETF and futures on market liquidity during market crash",
            "imported_concept": "LETF/futures liquidity linkage and rebalancing feedback-loop watch",
        },
        "as_of": as_of or (str(features.index[-1].date()) if not features.empty else None),
        "input_coverage": {
            "start": start,
            "date_start": str(features.index[0].date()) if not features.empty else None,
            "date_end": str(features.index[-1].date()) if not features.empty else None,
            "row_count": int(len(features)),
            "trigger_count": int(trigger_count),
            "min_trigger_count": int(min_trigger_count),
        },
        "thresholds": {
            "range_threshold": float(range_threshold),
            "volume_z_min": float(volume_z_min),
            "dislocation_z_min": float(dislocation_z_min),
        },
        "event_metrics": metrics,
        "events": events[:200],
        "summary": {
            "ready_for_manual_review": bool(ready),
            "recommendation": "manual_review_shadow_candidate" if ready else "needs_more_trigger_history",
            "primary_use": "warn_on_large_00631l_or_00632r_adds_during_liquidity_feedback_stress",
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "code_change_allowed": False,
            "guarded_candidate_allowed": False,
            "promote_to_live": False,
            "requires_signed_approval_before_any_candidate": True,
        },
    }
