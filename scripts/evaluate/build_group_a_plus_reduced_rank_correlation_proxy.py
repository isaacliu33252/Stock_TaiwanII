#!/usr/bin/env python3
"""Build a weak reduced-rank correlation proxy for GroupA+.

This is inspired by arXiv 2107.09048 but is not paper-equivalent. It uses the
current daily local ETF and external market OHLCV cache, removes the first
correlation eigenmode, and reports reduced-rank mean-correlation plus rolling
matrix-distance diagnostics. The output is shadow/manual-review only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_proxy.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/reduced_rank_correlation_proxy/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _float_or_none(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_close_panel(conn: duckdb.DuckDBPyConnection, as_of: str | None) -> pd.DataFrame:
    date_filter = "WHERE dt <= ?" if as_of else ""
    params: list[Any] = [as_of] if as_of else []
    frames: list[pd.DataFrame] = []
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    if "ohlcv" in tables:
        frames.append(
            conn.execute(
                f"""
                SELECT ticker, dt, close, 'ohlcv' AS source_table
                FROM ohlcv
                {date_filter}
                """,
                params,
            ).fetchdf()
        )
    if "external_market_ohlcv" in tables:
        frames.append(
            conn.execute(
                f"""
                SELECT ticker, dt, close, 'external_market_ohlcv' AS source_table
                FROM external_market_ohlcv
                {date_filter}
                """,
                params,
            ).fetchdf()
        )
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if rows.empty:
        return pd.DataFrame()
    rows = rows.dropna(subset=["ticker", "dt", "close"]).copy()
    rows["dt"] = pd.to_datetime(rows["dt"])
    rows["_priority"] = rows["source_table"].map({"ohlcv": 0, "external_market_ohlcv": 1}).fillna(9)
    rows = rows.sort_values(["dt", "ticker", "_priority"]).drop_duplicates(["dt", "ticker"], keep="first")
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _reduced_rank_matrix(window_returns: pd.DataFrame) -> tuple[np.ndarray, float, float]:
    corr = window_returns.corr().to_numpy(dtype=float)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    corr = (corr + corr.T) / 2.0
    np.fill_diagonal(corr, 1.0)
    eigvals, eigvecs = np.linalg.eigh(corr)
    idx = int(np.argmax(eigvals))
    lambda1 = float(eigvals[idx])
    v1 = eigvecs[:, idx]
    reduced = corr - lambda1 * np.outer(v1, v1)
    reduced = (reduced + reduced.T) / 2.0
    return reduced, lambda1, float(lambda1 / max(corr.shape[0], 1))


def _offdiag_mean(matrix: np.ndarray) -> float | None:
    if matrix.shape[0] < 2:
        return None
    mask = ~np.eye(matrix.shape[0], dtype=bool)
    values = matrix[mask]
    values = values[np.isfinite(values)]
    return float(np.mean(values)) if len(values) else None


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    n = max(a.shape[0], 1)
    return float(np.linalg.norm(a - b, ord="fro") / n)


def _percentile_rank(values: list[float], latest: float | None) -> float | None:
    if latest is None or not values:
        return None
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if finite.size == 0:
        return None
    return float(np.mean(finite <= latest))


def _state(distance_percentile: float | None, reduced_mean: float | None, reduced_mean_p25: float | None) -> dict[str, Any]:
    if distance_percentile is None or reduced_mean is None or reduced_mean_p25 is None:
        return {"state": "unavailable", "manual_review_required": False, "state_reasons": ["proxy_metric_unavailable"]}
    reasons = [
        f"distance_percentile={distance_percentile:.4f}",
        f"reduced_rank_mean_corr={reduced_mean:.4f}",
        f"reduced_rank_mean_corr_p25={reduced_mean_p25:.4f}",
    ]
    if distance_percentile >= 0.90 and reduced_mean <= reduced_mean_p25:
        return {"state": "elevated_fragility", "manual_review_required": True, "state_reasons": reasons}
    if distance_percentile >= 0.75:
        return {"state": "watch", "manual_review_required": True, "state_reasons": reasons}
    return {"state": "normal", "manual_review_required": False, "state_reasons": reasons}


def build_proxy(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = "2026-07-20",
    window: int = 42,
    min_history: int = 84,
    analysis_lookback: int = 252,
    min_tickers: int = 12,
    max_stale_days: int = 10,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        with duckdb.connect(str(db_path), read_only=True) as conn:
            close = _load_close_panel(conn, as_of)

    if close.empty:
        blockers.append("price_panel_missing")
        returns = pd.DataFrame()
        usable = []
        stale_tickers: list[str] = []
    else:
        latest_panel_dt = close.index.max()
        last_valid_by_ticker = close.apply(lambda series: series.last_valid_index())
        stale_cutoff = latest_panel_dt - pd.Timedelta(days=max_stale_days)
        fresh_tickers = [
            ticker
            for ticker, last_valid in last_valid_by_ticker.items()
            if last_valid is not None and pd.Timestamp(last_valid) >= stale_cutoff
        ]
        stale_tickers = sorted(set(close.columns) - set(fresh_tickers))
        close = close.ffill(limit=3)
        returns_all = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
        counts = returns_all.notna().sum()
        usable = [ticker for ticker in fresh_tickers if int(counts.get(ticker, 0)) >= min_history]
        raw_returns = returns_all[usable].tail(analysis_lookback) if usable else pd.DataFrame()
        usable = [ticker for ticker in raw_returns.columns if int(raw_returns[ticker].notna().sum()) >= min_history]
        returns = raw_returns[usable].fillna(0.0) if usable else pd.DataFrame()
        if stale_tickers:
            warnings.append("stale_tickers_excluded_from_proxy")
    if len(usable) < min_tickers:
        blockers.append("insufficient_cross_market_ticker_breadth")
    if len(returns) < window + 1:
        blockers.append("insufficient_rolling_window_history")

    snapshots: list[dict[str, Any]] = []
    matrices: list[np.ndarray] = []
    if len(usable) >= min_tickers and len(returns) >= window + 1:
        for end_idx in range(window, len(returns) + 1):
            frame = returns.iloc[end_idx - window : end_idx]
            if len(usable) < min_tickers or len(frame) < max(int(window * 0.75), 2):
                continue
            reduced, lambda1, lambda1_share = _reduced_rank_matrix(frame)
            matrices.append(reduced)
            snapshots.append(
                {
                    "dt": str(returns.index[end_idx - 1].date()),
                    "ticker_count": len(usable),
                    "window_observations": int(len(frame)),
                    "lambda1": _float_or_none(lambda1),
                    "lambda1_share": _float_or_none(lambda1_share),
                    "reduced_rank_mean_corr": _float_or_none(_offdiag_mean(reduced)),
                }
            )

    distances: list[float] = []
    for prev, curr in zip(matrices, matrices[1:]):
        distances.append(_distance(prev, curr))
    for snapshot, distance in zip(snapshots[1:], distances):
        snapshot["averaged_distance"] = _float_or_none(distance)
    if snapshots:
        snapshots[0]["averaged_distance"] = None

    latest = snapshots[-1] if snapshots else {}
    if not snapshots:
        blockers.append("reduced_rank_proxy_scores_unavailable")
    distance_percentile = _percentile_rank(distances, latest.get("averaged_distance"))
    reduced_means = [
        float(item["reduced_rank_mean_corr"])
        for item in snapshots
        if item.get("reduced_rank_mean_corr") is not None
    ]
    reduced_mean_p25 = float(np.quantile(reduced_means, 0.25)) if reduced_means else None
    state_payload = _state(distance_percentile, latest.get("reduced_rank_mean_corr"), reduced_mean_p25)
    if state_payload["manual_review_required"]:
        warnings.append(f"reduced_rank_proxy_state:{state_payload['state']}")
    warnings.extend(
        [
            "weak_cross_market_proxy_not_paper_equivalent",
            "daily_close_proxy_uses_holiday_ffill_limit_3",
            "missing_cross_market_returns_filled_with_zero_after_ticker_filter",
            "research_only_no_live_weight_change",
        ]
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_reduced_rank_correlation_proxy",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": str(close.index.max().date()) if not close.empty else None,
        "status": "blocked" if blockers else "available_for_manual_review",
        "policy": "weak_cross_market_reduced_rank_proxy_no_crash_predictor_no_weight_change",
        "method": {
            "paper_equivalent": False,
            "source_paper": "C:/Users/isaac/Downloads/2107.09048.pdf",
            "window_trading_days": window,
            "analysis_lookback": analysis_lookback,
            "min_history": min_history,
            "min_tickers": min_tickers,
            "max_stale_days": max_stale_days,
            "market_mode_removed": "largest_correlation_eigenmode",
            "distance_metric": "frobenius_distance_between_consecutive_reduced_rank_correlation_matrices_divided_by_ticker_count",
        },
        "coverage": {
            "usable_tickers": usable,
            "usable_ticker_count": len(usable),
            "stale_tickers_excluded": stale_tickers,
            "return_observations": int(len(returns)),
            "snapshot_count": len(snapshots),
        },
        "latest": {
            **latest,
            "distance_percentile": _float_or_none(distance_percentile),
            "reduced_rank_mean_corr_p25": _float_or_none(reduced_mean_p25),
            "state": state_payload["state"],
            "manual_review_required": state_payload["manual_review_required"],
            "state_reasons": state_payload["state_reasons"],
        },
        "recent_snapshots": snapshots[-10:],
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "proxy_available_for_shadow_review": bool(snapshots),
            "paper_equivalent": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None, actual_data_end: str | None) -> Path:
    stamp = str(as_of or actual_data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"reduced_rank_correlation_proxy_{stamp}.json"


def write_proxy(payload: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload.get("as_of"), payload.get("actual_data_end")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--min-history", type=int, default=84)
    parser.add_argument("--analysis-lookback", type=int, default=252)
    parser.add_argument("--min-tickers", type=int, default=12)
    parser.add_argument("--max-stale-days", type=int, default=10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_proxy(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        window=int(args.window),
        min_history=int(args.min_history),
        analysis_lookback=int(args.analysis_lookback),
        min_tickers=int(args.min_tickers),
        max_stale_days=int(args.max_stale_days),
    )
    write_proxy(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"Reduced-rank correlation proxy: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "actual_data_end": payload["actual_data_end"],
                "state": payload["latest"].get("state"),
                "usable_ticker_count": payload["coverage"]["usable_ticker_count"],
                "allow_00631l_add": payload["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
