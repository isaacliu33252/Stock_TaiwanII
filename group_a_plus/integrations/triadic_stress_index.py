"""Research-only Triadic Stress Index shadow for GroupA+.

This implements a bounded subset of arXiv:2608.10788 for GroupA+ diagnostics:
rolling absolute-correlation network stress, asymmetric persistence memory, and
node attribution. It is a coincident state monitor, not a forecast, and never
emits target weights or execution regimes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


DEFAULT_WINDOW_DAYS = 20
DEFAULT_ALPHA_UP = 0.6
DEFAULT_ALPHA_DOWN = 0.08
DEFAULT_ALARM_PERCENTILE = 0.90
DEFAULT_MIN_OBSERVATIONS = 12

DEFAULT_TICKER_SOURCES: dict[str, tuple[str, str]] = {
    "0050.TW": ("ohlcv", "0050.TW"),
    "00631L.TW": ("ohlcv", "00631L.TW"),
    "00632R.TW": ("ohlcv", "00632R.TW"),
    "00679B.TWO": ("ohlcv", "00679B.TWO"),
    "^TWII": ("external_market_ohlcv", "^TWII"),
    "2330.TW": ("external_market_ohlcv", "2330.TW"),
    "2317.TW": ("external_market_ohlcv", "2317.TW"),
    "2454.TW": ("external_market_ohlcv", "2454.TW"),
    "2308.TW": ("external_market_ohlcv", "2308.TW"),
    "2382.TW": ("external_market_ohlcv", "2382.TW"),
    "SOXX": ("external_market_ohlcv", "SOXX"),
    "QQQ": ("external_market_ohlcv", "QQQ"),
    "NVDA": ("external_market_ohlcv", "NVDA"),
    "TSM": ("external_market_ohlcv", "TSM"),
    "^VIX": ("external_market_ohlcv", "^VIX"),
    "TWD=X": ("external_market_ohlcv", "TWD=X"),
    "^TNX": ("external_market_ohlcv", "^TNX"),
    "GC=F": ("external_market_ohlcv", "GC=F"),
}


@dataclass(frozen=True)
class NetworkMetrics:
    tsi: float
    clustering: float
    density: float
    spectral_gap: float
    inverse_spectral_gap: float
    degree_variance: float
    effective_rank: float
    node_triangle: dict[str, float]
    node_degree: dict[str, float]
    n_assets: int
    observations: int


def _normal_cdf_percentile(values: pd.Series, value: float) -> float | None:
    clean = values.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty or not isfinite(value):
        return None
    return float((clean <= value).mean())


def _asymmetric_memory(series: pd.Series, alpha_up: float, alpha_down: float) -> pd.Series:
    clean = series.astype(float)
    out: list[float] = []
    prev: float | None = None
    for value in clean:
        if not isfinite(value):
            out.append(np.nan)
            continue
        if prev is None or not isfinite(prev):
            prev = float(value)
        elif value > prev:
            prev = alpha_up * float(value) + (1.0 - alpha_up) * prev
        else:
            prev = alpha_down * float(value) + (1.0 - alpha_down) * prev
        out.append(prev)
    return pd.Series(out, index=series.index, name=f"{series.name or 'value'}_memory")


def _effective_rank_from_corr(corr: np.ndarray) -> float:
    eig = np.linalg.eigvalsh(corr)
    eig = np.clip(eig, 0.0, None)
    total = float(eig.sum())
    if total <= 0.0:
        return 0.0
    p = eig / total
    p = p[p > 0.0]
    entropy = -float(np.sum(p * np.log(p)))
    return float(np.exp(entropy))


def compute_network_metrics(returns: pd.DataFrame, *, min_observations: int = DEFAULT_MIN_OBSERVATIONS) -> NetworkMetrics:
    """Compute one TSI network snapshot from a returns window.

    Correlations are absolute-valued with zero diagonal, following the paper's
    financial-network construction. TSI uses C * D * degree_var / M, where M is
    inverse spectral gap, equivalently C * D * degree_var * spectral_gap.
    """
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna(axis=1, thresh=min_observations)
    if clean.shape[1] < 3:
        raise ValueError("TSI requires at least 3 assets with enough observations")
    corr_df = clean.corr(min_periods=min_observations)
    corr_df = corr_df.dropna(axis=0, how="any").dropna(axis=1, how="any")
    corr_df = corr_df.loc[corr_df.index.intersection(corr_df.columns), corr_df.index.intersection(corr_df.columns)]
    if corr_df.shape[0] < 3:
        raise ValueError("TSI correlation matrix has fewer than 3 valid assets")

    labels = [str(item) for item in corr_df.index]
    corr = corr_df.to_numpy(dtype=float)
    n = corr.shape[0]
    a = np.abs(corr)
    np.fill_diagonal(a, 0.0)

    a3 = a @ a @ a
    trace_a3 = float(np.trace(a3))
    clustering = trace_a3 / max(float(n * (n - 1) * (n - 2)), 1.0)
    density = float(a.sum() / max(float(n * (n - 1)), 1.0))
    degree = a.sum(axis=1)
    degree_variance = float(np.var(degree))
    laplacian = np.diag(degree) - a
    eig = np.linalg.eigvalsh(laplacian)
    spectral_gap = float(max(eig[1], 0.0)) if len(eig) > 1 else 0.0
    inverse_spectral_gap = float(1.0 / spectral_gap) if spectral_gap > 1e-12 else float("inf")
    tsi = clustering * density * degree_variance * spectral_gap
    node_triangle = {label: float(a3[i, i]) for i, label in enumerate(labels)}
    node_degree = {label: float(degree[i]) for i, label in enumerate(labels)}

    return NetworkMetrics(
        tsi=float(tsi),
        clustering=float(clustering),
        density=float(density),
        spectral_gap=float(spectral_gap),
        inverse_spectral_gap=inverse_spectral_gap,
        degree_variance=float(degree_variance),
        effective_rank=_effective_rank_from_corr(corr),
        node_triangle=node_triangle,
        node_degree=node_degree,
        n_assets=n,
        observations=int(clean.shape[0]),
    )


def rolling_tsi_frame(
    prices: pd.DataFrame,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    alpha_up: float = DEFAULT_ALPHA_UP,
    alpha_down: float = DEFAULT_ALPHA_DOWN,
) -> tuple[pd.DataFrame, dict[pd.Timestamp, NetworkMetrics]]:
    returns = prices.sort_index().pct_change(fill_method=None)
    rows: list[dict[str, Any]] = []
    metrics_by_date: dict[pd.Timestamp, NetworkMetrics] = {}
    for end_date in returns.index:
        window = returns.loc[:end_date].tail(window_days)
        try:
            metrics = compute_network_metrics(window, min_observations=min_observations)
        except ValueError:
            continue
        metrics_by_date[pd.Timestamp(end_date)] = metrics
        rows.append(
            {
                "date": pd.Timestamp(end_date),
                "tsi": metrics.tsi,
                "clustering": metrics.clustering,
                "density": metrics.density,
                "spectral_gap": metrics.spectral_gap,
                "inverse_spectral_gap": metrics.inverse_spectral_gap,
                "degree_variance": metrics.degree_variance,
                "effective_rank": metrics.effective_rank,
                "n_assets": metrics.n_assets,
                "observations": metrics.observations,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame, metrics_by_date
    frame = frame.set_index("date").sort_index()
    frame["tsi_memory"] = _asymmetric_memory(frame["tsi"], alpha_up, alpha_down)
    frame["tsi_zscore"] = (frame["tsi"] - frame["tsi"].expanding().mean()) / frame["tsi"].expanding().std(ddof=1)
    frame["tsi_memory_zscore"] = (
        (frame["tsi_memory"] - frame["tsi_memory"].expanding().mean())
        / frame["tsi_memory"].expanding().std(ddof=1)
    )
    frame["tsi_percentile"] = [
        _normal_cdf_percentile(frame["tsi"].iloc[: i + 1], float(value))
        for i, value in enumerate(frame["tsi"])
    ]
    frame["tsi_memory_percentile"] = [
        _normal_cdf_percentile(frame["tsi_memory"].iloc[: i + 1], float(value))
        for i, value in enumerate(frame["tsi_memory"])
    ]
    return frame, metrics_by_date


def _read_close_table(
    con: duckdb.DuckDBPyConnection,
    *,
    table: str,
    ticker: str,
    start: str,
    end: str,
) -> pd.Series:
    df = con.execute(
        f"SELECT dt, close FROM {table} WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
        [ticker, start, end],
    ).fetchdf()
    if df.empty:
        return pd.Series(dtype=float, name=ticker)
    df["dt"] = pd.to_datetime(df["dt"])
    return df.set_index("dt")["close"].astype(float).rename(ticker)


def load_tsi_price_panel(
    *,
    db_path: Path,
    start: str,
    end: str,
    ticker_sources: dict[str, tuple[str, str]] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    ticker_sources = ticker_sources or DEFAULT_TICKER_SOURCES
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        series = {
            label: _read_close_table(con, table=table, ticker=source_ticker, start=start, end=end)
            for label, (table, source_ticker) in ticker_sources.items()
        }
    finally:
        con.close()
    panel = pd.concat(series.values(), axis=1).sort_index()
    source_status = {}
    for label, close in series.items():
        valid = close.dropna()
        source_status[label] = {
            "source_table": ticker_sources[label][0],
            "source_ticker": ticker_sources[label][1],
            "rows": int(len(valid)),
            "first_date": str(valid.index.min().date()) if not valid.empty else None,
            "latest_date": str(valid.index.max().date()) if not valid.empty else None,
            "status": "available" if not valid.empty else "missing",
        }
    return panel, source_status


def latest_tsi_snapshot(
    prices: pd.DataFrame,
    *,
    source_status: dict[str, Any] | None = None,
    as_of: str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    alpha_up: float = DEFAULT_ALPHA_UP,
    alpha_down: float = DEFAULT_ALPHA_DOWN,
    alarm_percentile: float = DEFAULT_ALARM_PERCENTILE,
) -> dict[str, Any]:
    if prices.empty:
        return {
            "status": "unavailable",
            "reason": "empty_price_panel",
            "policy": "shadow_only_no_weight_change",
            "production_effect": "none",
        }
    clipped = prices.copy()
    if as_of:
        clipped = clipped.loc[clipped.index <= pd.Timestamp(as_of)]
    frame, metrics_by_date = rolling_tsi_frame(
        clipped,
        window_days=window_days,
        min_observations=min_observations,
        alpha_up=alpha_up,
        alpha_down=alpha_down,
    )
    if frame.empty:
        return {
            "status": "unavailable",
            "reason": "insufficient_price_history",
            "policy": "shadow_only_no_weight_change",
            "production_effect": "none",
            "source_status": source_status or {},
        }
    latest_date = pd.Timestamp(frame.index[-1])
    latest = frame.iloc[-1]
    metrics = metrics_by_date[latest_date]
    tri_total = sum(max(v, 0.0) for v in metrics.node_triangle.values()) or 1.0
    deg_total = sum(max(v, 0.0) for v in metrics.node_degree.values()) or 1.0
    attribution = [
        {
            "ticker": ticker,
            "triangle_contribution": value,
            "triangle_share": float(max(value, 0.0) / tri_total),
            "degree": metrics.node_degree.get(ticker, 0.0),
            "degree_share": float(max(metrics.node_degree.get(ticker, 0.0), 0.0) / deg_total),
        }
        for ticker, value in metrics.node_triangle.items()
    ]
    attribution.sort(key=lambda row: row["triangle_share"], reverse=True)
    alarm_active = bool(
        latest.get("tsi_memory_percentile") is not None
        and float(latest["tsi_memory_percentile"]) >= alarm_percentile
    )
    return {
        "schema_version": 1,
        "report": "group_a_plus_tsi_stress_shadow",
        "status": "available",
        "research_only": True,
        "policy": "shadow_only_no_weight_change",
        "production_effect": "none",
        "outputs_target_weights": False,
        "outputs_execution_regime": False,
        "date": str(latest_date.date()),
        "requested_as_of": as_of,
        "window_days": int(window_days),
        "min_observations": int(min_observations),
        "alpha_up": float(alpha_up),
        "alpha_down": float(alpha_down),
        "alarm_percentile_threshold": float(alarm_percentile),
        "alarm_active": alarm_active,
        "recommended_use": "manual_review_no_new_risk_adds" if alarm_active else "monitor_only",
        "scope_note": "Coincident correlation-network stress index; not a directional forecast.",
        "latest": {
            key: (None if pd.isna(latest[key]) else float(latest[key]))
            for key in (
                "tsi",
                "tsi_memory",
                "tsi_zscore",
                "tsi_memory_zscore",
                "tsi_percentile",
                "tsi_memory_percentile",
                "clustering",
                "density",
                "spectral_gap",
                "inverse_spectral_gap",
                "degree_variance",
                "effective_rank",
            )
        }
        | {"n_assets": int(latest["n_assets"]), "observations": int(latest["observations"])},
        "top_attribution": attribution[:8],
        "source_status": source_status or {},
    }
