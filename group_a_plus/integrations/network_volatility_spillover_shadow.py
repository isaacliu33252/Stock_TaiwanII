"""Network volatility-spillover shadow features for GroupA+.

Inspired by arXiv:2606.03828v1's GNHAR framework. This first integration step
does not fit a full GNHAR model; it builds a lightweight directed volatility
network from rolling lagged realized-variance relations so downstream gates can
be evaluated before adding heavier model dependencies.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from group_a_plus.integrations.volatility_forecast import GK_FLOOR, garman_klass_variance


DEFAULT_TICKERS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "00679B.TWO",
    "00646.TW",
    "00713.TW",
    "00878.TW",
)
NETWORK_VOL_SCHEMA_VERSION = 1


def build_log_realized_variance_panel(
    ohlcv: pd.DataFrame,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> pd.DataFrame:
    """Convert a long OHLCV table into a wide log realized-variance panel."""

    required = {"dt", "ticker", "open", "high", "low", "close"}
    missing = sorted(required - set(ohlcv.columns))
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")

    frame = ohlcv.copy()
    frame["dt"] = pd.to_datetime(frame["dt"])
    out = pd.DataFrame(index=sorted(frame["dt"].dropna().unique()))
    for ticker in tickers:
        rows = frame.loc[frame["ticker"] == ticker].set_index("dt").sort_index()
        if rows.empty:
            continue
        variance = garman_klass_variance(rows[["open", "high", "low", "close"]])
        out[ticker] = np.log(variance.clip(lower=GK_FLOOR))
    return out.sort_index().ffill()


def _rolling_lagged_corr(source: pd.Series, target: pd.Series, window: int, min_periods: int) -> pd.Series:
    return source.shift(1).rolling(window, min_periods=min_periods).corr(target)


def build_spillover_network_frame(
    log_rv: pd.DataFrame,
    *,
    target: str = "0050.TW",
    window: int = 252,
    min_periods: int | None = None,
    edge_threshold: float = 0.25,
) -> pd.DataFrame:
    """Build rolling directed volatility-spillover metrics.

    Edge i -> j is approximated by corr(log RV_i,t-1, log RV_j,t) over the
    rolling window. This is intentionally a transparent shadow approximation of
    Granger-style volatility spillover, not a production forecast model.
    """

    if target not in log_rv.columns:
        raise ValueError(f"target ticker missing from log_rv: {target}")
    if len(log_rv.columns) < 2:
        raise ValueError("at least two volatility series are required")
    window = int(window)
    if window <= 5:
        raise ValueError("window must be > 5")
    min_periods = int(min_periods or max(30, window // 3))
    edge_threshold = float(edge_threshold)

    panel = log_rv.astype(float).replace([np.inf, -np.inf], np.nan).ffill()
    tickers = list(panel.columns)
    out = pd.DataFrame(index=panel.index)

    edge_cols: list[str] = []
    for source in tickers:
        for dest in tickers:
            if source == dest:
                continue
            col = f"spillover_corr__{source}__to__{dest}"
            out[col] = _rolling_lagged_corr(panel[source], panel[dest], window, min_periods).fillna(0.0)
            edge_cols.append(col)

    abs_edges = out[edge_cols].abs()
    active_edges = abs_edges >= edge_threshold
    possible_edges = max(len(edge_cols), 1)
    out["spillover_edge_density"] = active_edges.sum(axis=1) / possible_edges
    out["spillover_mean_abs_strength"] = abs_edges.mean(axis=1)
    out["spillover_systemic_score"] = out["spillover_edge_density"] * out["spillover_mean_abs_strength"]

    incoming_cols = [col for col in edge_cols if col.endswith(f"__to__{target}")]
    outgoing_cols = [col for col in edge_cols if col.startswith(f"spillover_corr__{target}__to__")]
    out[f"spillover_in_strength_{target}"] = out[incoming_cols].abs().mean(axis=1) if incoming_cols else 0.0
    out[f"spillover_out_strength_{target}"] = out[outgoing_cols].abs().mean(axis=1) if outgoing_cols else 0.0
    out[f"spillover_net_pressure_{target}"] = out[f"spillover_in_strength_{target}"] - out[f"spillover_out_strength_{target}"]

    score = out["spillover_systemic_score"]
    out["spillover_systemic_percentile_252d"] = score.rolling(252, min_periods=60).rank(pct=True).fillna(0.5)
    in_strength = out[f"spillover_in_strength_{target}"]
    out[f"spillover_in_percentile_252d_{target}"] = in_strength.rolling(252, min_periods=60).rank(pct=True).fillna(0.5)
    out["spillover_crisis_regime"] = (
        (out["spillover_systemic_percentile_252d"] >= 0.80)
        & (out[f"spillover_in_percentile_252d_{target}"] >= 0.80)
    ).astype(int)
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def latest_spillover_snapshot(frame: pd.DataFrame, *, target: str = "0050.TW") -> dict[str, Any]:
    if frame.empty:
        return {
            "schema_version": NETWORK_VOL_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "empty_frame",
        }
    row = frame.iloc[-1]
    return {
        "schema_version": NETWORK_VOL_SCHEMA_VERSION,
        "status": "available",
        "model_family": "rolling_lagged_vol_spillover_shadow",
        "target": target,
        "date": str(pd.Timestamp(frame.index[-1]).date()),
        "edge_density": float(row.get("spillover_edge_density", 0.0)),
        "mean_abs_strength": float(row.get("spillover_mean_abs_strength", 0.0)),
        "systemic_score": float(row.get("spillover_systemic_score", 0.0)),
        "systemic_percentile_252d": float(row.get("spillover_systemic_percentile_252d", 0.5)),
        "target_in_strength": float(row.get(f"spillover_in_strength_{target}", 0.0)),
        "target_out_strength": float(row.get(f"spillover_out_strength_{target}", 0.0)),
        "target_net_pressure": float(row.get(f"spillover_net_pressure_{target}", 0.0)),
        "target_in_percentile_252d": float(row.get(f"spillover_in_percentile_252d_{target}", 0.5)),
        "crisis_regime": bool(int(row.get("spillover_crisis_regime", 0))),
    }


def spillover_recovery_boost_gate(
    snapshot: dict[str, Any],
    *,
    max_systemic_percentile: float = 0.80,
    max_target_in_percentile: float = 0.80,
) -> dict[str, Any]:
    """Convert a spillover snapshot into a conservative recovery-boost gate."""

    if snapshot.get("status") != "available":
        return {"allow_recovery_boost": False, "reason": "snapshot_unavailable"}
    systemic = float(snapshot.get("systemic_percentile_252d", 1.0))
    target_in = float(snapshot.get("target_in_percentile_252d", 1.0))
    crisis = bool(snapshot.get("crisis_regime", False))
    allow = bool(systemic <= float(max_systemic_percentile) and target_in <= float(max_target_in_percentile) and not crisis)
    return {
        "allow_recovery_boost": allow,
        "reason": "spillover_ok" if allow else "spillover_blocked",
        "systemic_percentile_252d": systemic,
        "target_in_percentile_252d": target_in,
        "crisis_regime": crisis,
        "max_systemic_percentile": float(max_systemic_percentile),
        "max_target_in_percentile": float(max_target_in_percentile),
    }
