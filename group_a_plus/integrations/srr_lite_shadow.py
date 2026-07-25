"""SRR-lite systemic fragility shadow diagnostic.

This is a lightweight correlation-layer proxy loosely inspired by the
Systemic Risk Radar paper (2512.17185v1) -- it only reuses the paper's
general framing (correlation-network fragility as a crash precursor), not
its multi-layer GNN+GRU architecture, which was never implemented here.

Evidence basis (Fable independent review, 2026-07-17): the source paper's
own prototype results are weak evidence on their own -- its single-layer
temporal-GNN backtest scored AUROC 0.232 in the GFC fold and degenerated to
a trivial all-positive classifier in the COVID fold (both worse than its own
logistic-regression baseline). This module's live thresholds
(NO_ADD_THRESHOLD etc. below) were NOT tuned or justified from the paper;
they come entirely from this project's own local crash-window backtest (see
docs/HANDOFF_SRR_LITE_SHADOW_20260716.md). Treat any future re-tuning of
these thresholds as resting on local forward/backtest evidence only -- do
not cite the source paper as support.

It is intentionally shadow-only: the output can warn about systemic
fragility and reference a 00631L no-add posture, but it does not directly
change target weights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH


DEFAULT_SYMBOLS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "00679B.TWO",
    "2330.TW",
    "SOXX",
    "TSM",
    "TWD=X",
)
CORE_SYMBOLS = ("0050.TW", "00631L.TW", "2330.TW", "SOXX", "TSM")
EDGE_THRESHOLD = 0.50
HIGH_FRAGILITY_THRESHOLD = 0.70
NO_ADD_THRESHOLD = 0.65
NO_ADD_DENSITY_THRESHOLD = 0.65
NO_ADD_VELOCITY_THRESHOLD = 0.18
CRASH_WATCH_THRESHOLD = 0.75
CRASH_WATCH_DENSITY_THRESHOLD = 0.65


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _safe_corr(returns: pd.DataFrame) -> pd.DataFrame:
    corr = returns.corr(method="spearman").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    # pandas 3 copy-on-write can hand back a read-only view from .values
    # depending on how the frame was constructed; force a writable copy
    # (see memory: pandas3_cow_readonly_numpy).
    diag = corr.to_numpy(copy=True)
    np.fill_diagonal(diag, 1.0)
    return pd.DataFrame(diag, index=corr.index, columns=corr.columns)


def _upper_triangle_values(matrix: pd.DataFrame) -> np.ndarray:
    if matrix.shape[0] < 2:
        return np.array([], dtype=float)
    arr = matrix.to_numpy(dtype=float)
    return arr[np.triu_indices_from(arr, k=1)]


def _density(matrix: pd.DataFrame, threshold: float = EDGE_THRESHOLD) -> float:
    vals = np.abs(_upper_triangle_values(matrix))
    return 0.0 if vals.size == 0 else float(np.mean(vals >= threshold))


def _avg_abs_corr(matrix: pd.DataFrame) -> float:
    vals = np.abs(_upper_triangle_values(matrix))
    return 0.0 if vals.size == 0 else float(np.mean(vals))


def _centrality(matrix: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    for col in matrix.columns:
        vals = matrix.loc[col].drop(labels=[col], errors="ignore").abs()
        out[str(col)] = float(vals.mean()) if len(vals) else 0.0
    return out


def _rolling_density_series(
    returns: pd.DataFrame,
    *,
    corr_window: int,
    threshold: float,
) -> pd.Series:
    values: list[tuple[pd.Timestamp, float]] = []
    for end in range(corr_window, len(returns) + 1):
        window = returns.iloc[end - corr_window:end]
        if window.notna().sum().min() < max(3, corr_window // 2):
            continue
        values.append((pd.Timestamp(returns.index[end - 1]), _density(_safe_corr(window), threshold)))
    if not values:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in values], index=[idx for idx, _ in values], dtype=float)


def build_srr_lite_shadow_from_prices(
    prices: pd.DataFrame,
    *,
    actual_date: str | pd.Timestamp | None = None,
    corr_window: int = 7,
    baseline_window: int = 60,
    edge_threshold: float = EDGE_THRESHOLD,
) -> dict[str, Any]:
    """Build a shadow systemic-fragility snapshot from close-price columns."""
    if prices.empty:
        return {"status": "unavailable", "reason": "empty_price_frame", "policy": "shadow_only_no_weight_change"}
    frame = prices.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    frame = frame.sort_index()
    if actual_date is not None:
        frame = frame.loc[frame.index <= pd.Timestamp(actual_date).normalize()]
    frame = frame.dropna(axis=1, thresh=max(corr_window + 1, 10))
    if frame.shape[1] < 3:
        return {
            "status": "unavailable",
            "reason": "fewer_than_three_symbols_with_data",
            "available_symbols": list(map(str, frame.columns)),
            "policy": "shadow_only_no_weight_change",
        }

    returns = frame.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    returns = returns.dropna(axis=1, thresh=max(corr_window, 6)).fillna(0.0)
    if len(returns) < corr_window + 1 or returns.shape[1] < 3:
        return {
            "status": "unavailable",
            "reason": "insufficient_return_history",
            "rows": int(len(returns)),
            "available_symbols": list(map(str, returns.columns)),
            "policy": "shadow_only_no_weight_change",
        }

    latest_returns = returns.iloc[-corr_window:]
    prev_returns = returns.iloc[-corr_window - 1:-1]
    corr = _safe_corr(latest_returns)
    prev_corr = _safe_corr(prev_returns).reindex_like(corr).fillna(0.0)
    density = _density(corr, edge_threshold)
    avg_corr = _avg_abs_corr(corr)
    velocity = float(np.mean(np.abs(corr.to_numpy(dtype=float) - prev_corr.to_numpy(dtype=float))))
    density_series = _rolling_density_series(returns, corr_window=corr_window, threshold=edge_threshold)
    history = density_series.iloc[-baseline_window:] if len(density_series) else pd.Series(dtype=float)
    hist_mean = float(history.mean()) if len(history) else density
    hist_std = float(history.std(ddof=0)) if len(history) else 0.0
    density_z = 0.0 if hist_std <= 1e-12 else float((density - hist_mean) / hist_std)
    centrality = _centrality(corr)
    core_centrality = max((centrality.get(symbol, 0.0) for symbol in CORE_SYMBOLS), default=0.0)

    components = {
        "density": _clip01((density - 0.35) / 0.35),
        "avg_abs_corr": _clip01((avg_corr - 0.35) / 0.35),
        "density_spike": _clip01(density_z / 3.0),
        "graph_velocity": _clip01(velocity / 0.35),
        "core_centrality": _clip01((core_centrality - 0.35) / 0.35),
    }
    score = (
        0.25 * components["density"]
        + 0.25 * components["avg_abs_corr"]
        + 0.20 * components["density_spike"]
        + 0.15 * components["graph_velocity"]
        + 0.15 * components["core_centrality"]
    )
    level = "high" if score >= HIGH_FRAGILITY_THRESHOLD else "elevated" if score >= 0.55 else "normal"
    no_add_active = bool(
        score >= NO_ADD_THRESHOLD
        and density >= NO_ADD_DENSITY_THRESHOLD
        and velocity >= NO_ADD_VELOCITY_THRESHOLD
    )
    crash_watch_active = bool(
        score >= CRASH_WATCH_THRESHOLD
        and density >= CRASH_WATCH_DENSITY_THRESHOLD
    )
    return {
        "status": "available",
        "policy": "shadow_only_no_weight_change",
        "actual_date": str(pd.Timestamp(returns.index[-1]).date()),
        "method": "srr_lite_correlation_layer",
        "systemic_fragility_score": round(float(score), 4),
        "fragility_level": level,
        "no_add_active": no_add_active,
        "crash_watch_active": crash_watch_active,
        "recommended_action": "pause_new_00631l_adds_manual_review" if no_add_active else "none",
        "crash_watch_recommended_action": (
            "manual_crash_risk_review_only" if crash_watch_active else "none"
        ),
        "allow_auto_weight_change": False,
        "allow_crash_watch_auto_weight_change": False,
        "allow_00631l_add_reference": not no_add_active,
        "thresholds": {
            "edge_abs_spearman": edge_threshold,
            "no_add_score": NO_ADD_THRESHOLD,
            "no_add_graph_density": NO_ADD_DENSITY_THRESHOLD,
            "no_add_graph_velocity": NO_ADD_VELOCITY_THRESHOLD,
            "crash_watch_score": CRASH_WATCH_THRESHOLD,
            "crash_watch_graph_density": CRASH_WATCH_DENSITY_THRESHOLD,
            "high_fragility_score": HIGH_FRAGILITY_THRESHOLD,
            "corr_window_days": corr_window,
            "baseline_window_days": baseline_window,
        },
        "metrics": {
            "graph_density": round(density, 4),
            "avg_abs_corr": round(avg_corr, 4),
            "density_z": round(density_z, 4),
            "graph_velocity": round(velocity, 4),
            "core_max_centrality": round(core_centrality, 4),
        },
        "score_components": {key: round(value, 4) for key, value in components.items()},
        "centrality": {key: round(value, 4) for key, value in sorted(centrality.items())},
        "available_symbols": list(map(str, returns.columns)),
        "rationale": (
            "SRR-lite tracks correlation-network density, co-movement strength, graph velocity, "
            "and centrality as a systemic fragility warning. It is diagnostic only."
        ),
    }


def _load_close_panel_from_db(
    db_path: Path,
    *,
    symbols: tuple[str, ...],
    end_date: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    start_date = end_date - pd.Timedelta(days=lookback_days)
    frames: list[pd.DataFrame] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        for table in ("ohlcv", "external_market_ohlcv"):
            if table not in tables:
                continue
            rows = con.execute(
                f"""
                SELECT dt, ticker, close
                FROM {table}
                WHERE ticker IN (SELECT * FROM UNNEST(?))
                  AND dt BETWEEN ? AND ?
                """,
                [list(symbols), str(start_date.date()), str(end_date.date())],
            ).fetchdf()
            if not rows.empty:
                frames.append(rows)
    finally:
        con.close()
    if not frames:
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    rows = rows.dropna(subset=["dt", "ticker", "close"])
    rows = rows.sort_values(["dt", "ticker"]).drop_duplicates(["dt", "ticker"], keep="last")
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index()


def compute_srr_lite_shadow(
    *,
    db_path: Path = DB_PATH,
    actual_date: str | pd.Timestamp,
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
    lookback_days: int = 180,
    corr_window: int = 7,
    baseline_window: int = 60,
) -> dict[str, Any]:
    end = pd.Timestamp(actual_date).normalize()
    try:
        prices = _load_close_panel_from_db(
            db_path,
            symbols=symbols,
            end_date=end,
            lookback_days=lookback_days,
        )
        snapshot = build_srr_lite_shadow_from_prices(
            prices,
            actual_date=end,
            corr_window=corr_window,
            baseline_window=baseline_window,
        )
        snapshot["source"] = {
            "db_path": str(db_path),
            "lookback_days": int(lookback_days),
            "requested_symbols": list(symbols),
        }
        return snapshot
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc),
            "policy": "shadow_only_no_weight_change",
            "source": {
                "db_path": str(db_path),
                "lookback_days": int(lookback_days),
                "requested_symbols": list(symbols),
            },
        }
