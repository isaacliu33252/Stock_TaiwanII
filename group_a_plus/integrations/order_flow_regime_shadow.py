"""Duration-aware order-flow regime shadow for GroupA++.

This module adapts arXiv:2609.07989 only as an execution advisory. It expects
signed intraday order-flow data and never uses daily OHLCV as a proxy.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW", "2330.TW")
DEFAULT_BUCKET = "30min"
DEFAULT_WINDOW = 20
DEFAULT_MIN_BUCKETS = 12
DEFAULT_Z_THRESHOLD = 2.25
DEFAULT_HAZARD_SCALE = 16.0
DEFAULT_HAZARD_SIGMA = 0.75


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _lognormal_hazard(run_length: int, *, scale: float = DEFAULT_HAZARD_SCALE, sigma: float = DEFAULT_HAZARD_SIGMA) -> float:
    """Discrete log-normal duration hazard H(r)=P(d=r+1 | d>r)."""
    if run_length < 0:
        return 0.0
    r0 = max(float(run_length), 1e-9)
    r1 = float(run_length + 1)
    if sigma <= 0 or scale <= 0:
        return 0.0

    def cdf(x: float) -> float:
        if x <= 0:
            return 0.0
        z = (np.log(x) - np.log(scale)) / (sigma * np.sqrt(2.0))
        return float(0.5 + 0.5 * math.erf(z))

    mass = max(0.0, cdf(r1) - cdf(r0))
    survival = max(1e-9, 1.0 - cdf(r0))
    return float(min(1.0, max(0.0, mass / survival)))


def _signed_volume_frame(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "ticker"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"missing required signed-flow columns: {sorted(missing)}")
    frame = raw.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    if "signed_volume" not in frame.columns:
        if {"side", "volume"} - set(frame.columns):
            raise ValueError("signed-flow data requires signed_volume or side+volume columns")
        side = frame["side"].astype(str).str.lower().map(
            {
                "buy": 1.0,
                "b": 1.0,
                "+1": 1.0,
                "1": 1.0,
                "sell": -1.0,
                "s": -1.0,
                "-1": -1.0,
            }
        )
        if side.isna().any():
            raise ValueError("side column contains values outside buy/sell/+1/-1")
        frame["signed_volume"] = side * pd.to_numeric(frame["volume"], errors="coerce")
    frame["signed_volume"] = pd.to_numeric(frame["signed_volume"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "ticker", "signed_volume"]).sort_values("timestamp")
    return frame


def _bucket_signed_flow(frame: pd.DataFrame, *, bucket: str) -> pd.DataFrame:
    grouped = (
        frame.set_index("timestamp")
        .groupby("ticker")["signed_volume"]
        .resample(bucket)
        .sum()
        .rename("signed_volume")
        .reset_index()
    )
    return grouped.sort_values(["ticker", "timestamp"])


def _ticker_shadow(series: pd.Series, *, window: int, z_threshold: float) -> dict[str, Any]:
    clean = series.astype(float).dropna()
    if len(clean) < max(DEFAULT_MIN_BUCKETS, window + 2):
        return {
            "status": "unavailable",
            "reason": "insufficient_signed_flow_buckets",
            "bucket_count": int(len(clean)),
        }

    rolling_mean = clean.shift(1).rolling(window, min_periods=max(5, window // 2)).mean()
    rolling_std = clean.shift(1).rolling(window, min_periods=max(5, window // 2)).std(ddof=0)
    z = ((clean - rolling_mean) / rolling_std.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)

    run_length = 0
    events: list[dict[str, Any]] = []
    latest: dict[str, Any] | None = None
    for ts, value in clean.items():
        z_value = _as_float(z.loc[ts])
        hazard = _lognormal_hazard(run_length)
        shock_prob = 0.0 if z_value is None else min(1.0, abs(z_value) / (z_threshold * 2.0))
        change_prob = max(hazard, shock_prob)
        is_break = bool(z_value is not None and abs(z_value) >= z_threshold and change_prob >= 0.50)
        direction = "buy_pressure" if value > 0 else ("sell_pressure" if value < 0 else "neutral")
        latest = {
            "timestamp": str(pd.Timestamp(ts)),
            "signed_volume": float(value),
            "z_score": z_value,
            "duration_hazard": round(hazard, 6),
            "change_probability_proxy": round(float(change_prob), 6),
            "regime_break_reference": is_break,
            "flow_direction": direction,
            "run_length_before_update": int(run_length),
        }
        if is_break:
            events.append(latest)
            run_length = 0
        else:
            run_length += 1

    assert latest is not None
    high_stress = bool(latest["regime_break_reference"] and latest["flow_direction"] == "sell_pressure")
    return {
        "status": "available",
        "bucket_count": int(len(clean)),
        "latest": latest,
        "recent_event_count": int(len(events)),
        "recent_events": events[-5:],
        "high_stress_execution_reference": high_stress,
    }


def build_order_flow_regime_shadow(
    signed_flow: pd.DataFrame,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    bucket: str = DEFAULT_BUCKET,
    window: int = DEFAULT_WINDOW,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> dict[str, Any]:
    """Build a duration-aware signed-order-flow advisory snapshot."""
    try:
        frame = _signed_volume_frame(signed_flow)
    except ValueError as exc:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_2609_07989_order_flow_regime_shadow",
            "status": "unavailable",
            "reason": str(exc),
            "policy": "execution_advisory_shadow_only",
            "decision": _decision(),
        }
    if frame.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_2609_07989_order_flow_regime_shadow",
            "status": "unavailable",
            "reason": "empty_signed_flow",
            "policy": "execution_advisory_shadow_only",
            "decision": _decision(),
        }

    bucketed = _bucket_signed_flow(frame[frame["ticker"].isin(tickers)], bucket=bucket)
    by_ticker: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        series = bucketed[bucketed["ticker"] == ticker].set_index("timestamp")["signed_volume"]
        by_ticker[ticker] = _ticker_shadow(series, window=window, z_threshold=z_threshold)

    available = {k: v for k, v in by_ticker.items() if v.get("status") == "available"}
    stress = sorted(k for k, v in available.items() if v.get("high_stress_execution_reference") is True)
    status = "available" if available else "unavailable"
    advisory_state = "execution_caution" if stress else ("normal_observation" if available else "no_observation")
    latest_times = [
        pd.Timestamp(v["latest"]["timestamp"])
        for v in available.values()
        if isinstance(v.get("latest"), dict) and v["latest"].get("timestamp")
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07989_order_flow_regime_shadow",
        "status": status,
        "reason": None if available else "no_available_ticker_shadow",
        "policy": "execution_advisory_shadow_only",
        "source_paper": "2609.07989",
        "as_of": str(max(latest_times)) if latest_times else None,
        "bucket": bucket,
        "window": int(window),
        "z_threshold": float(z_threshold),
        "data_contract": "requires signed intraday transaction/order-flow data; daily OHLCV proxies are intentionally rejected",
        "advisory_state": advisory_state,
        "stress_tickers": stress,
        "by_ticker": by_ticker,
        "decision": _decision(),
    }


def build_order_flow_regime_shadow_from_csv(
    csv_path: Path,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    bucket: str = DEFAULT_BUCKET,
    window: int = DEFAULT_WINDOW,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> dict[str, Any]:
    if not csv_path.exists():
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_2609_07989_order_flow_regime_shadow",
            "status": "unavailable",
            "reason": "missing_signed_flow_csv",
            "path": str(csv_path),
            "policy": "execution_advisory_shadow_only",
            "decision": _decision(),
        }
    return build_order_flow_regime_shadow(
        pd.read_csv(csv_path),
        tickers=tickers,
        bucket=bucket,
        window=window,
        z_threshold=z_threshold,
    )


def append_order_flow_regime_shadow_log(log_path: Path, shadow: dict[str, Any]) -> None:
    if shadow.get("status") == "unavailable":
        return
    row = dict(shadow)
    key = row.get("as_of")
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("as_of") != key:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("as_of") or ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n",
        encoding="utf-8",
    )


def _decision() -> dict[str, bool]:
    return {
        "creates_orders": False,
        "target_weight_change_allowed": False,
        "live_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "latest_strategy_change_allowed": False,
        "golden2_0830_change_allowed": False,
    }
