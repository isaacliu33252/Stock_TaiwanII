#!/usr/bin/env python3
"""Backtest the weak reduced-rank correlation proxy on stress windows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_reduced_rank_correlation_proxy import (  # noqa: E402
    DEFAULT_DB,
    _float_or_none,
    _load_close_panel,
    _reduced_rank_matrix,
    _state,
)
from scripts.evaluate.evaluate_group_a_plus_sin_lite_crash_window_backtest import (  # noqa: E402
    DEFAULT_WINDOWS,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/reduced_rank_correlation_crash_window_backtest/history"
STATE_RANK = {"unavailable": -1, "normal": 0, "watch": 1, "elevated_fragility": 2}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _at_or_above(series: pd.Series, state: str) -> pd.Series:
    threshold = STATE_RANK[state]
    return series.map(lambda value: STATE_RANK.get(str(value), -1) >= threshold)


def _prepare_returns(
    close: pd.DataFrame,
    *,
    min_history: int,
    max_stale_days: int,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    if close.empty:
        return pd.DataFrame(), [], []
    latest_panel_dt = close.index.max()
    last_valid_by_ticker = close.apply(lambda series: series.last_valid_index())
    stale_cutoff = latest_panel_dt - pd.Timedelta(days=max_stale_days)
    fresh_tickers = [
        ticker
        for ticker, last_valid in last_valid_by_ticker.items()
        if last_valid is not None and pd.Timestamp(last_valid) >= stale_cutoff
    ]
    stale_tickers = sorted(set(close.columns) - set(fresh_tickers))
    returns_all = close.ffill(limit=3).pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    counts = returns_all.notna().sum()
    usable = [ticker for ticker in fresh_tickers if int(counts.get(ticker, 0)) >= min_history]
    return returns_all[usable].fillna(0.0), usable, stale_tickers


def build_daily_scores(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = "2026-07-20",
    window: int = 42,
    min_history: int = 63,
    min_tickers: int = 12,
    max_stale_days: int = 10,
    baseline_lookback: int = 252,
) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        close = _load_close_panel(conn, as_of)
    returns, usable, _stale = _prepare_returns(close, min_history=min_history, max_stale_days=max_stale_days)
    if returns.empty or len(usable) < min_tickers or len(returns) < window + 1:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    matrices: list[np.ndarray] = []
    for end_idx in range(window, len(returns) + 1):
        frame = returns.iloc[end_idx - window : end_idx]
        reduced, lambda1, lambda1_share = _reduced_rank_matrix(frame)
        distance = float(np.linalg.norm(reduced - matrices[-1], ord="fro") / max(reduced.shape[0], 1)) if matrices else np.nan
        matrices.append(reduced)
        reduced_mean = _offdiag_mean(reduced)
        rows.append(
            {
                "dt": returns.index[end_idx - 1],
                "ticker_count": len(usable),
                "window_observations": int(len(frame)),
                "lambda1": lambda1,
                "lambda1_share": lambda1_share,
                "reduced_rank_mean_corr": reduced_mean,
                "averaged_distance": distance,
            }
        )

    scores = pd.DataFrame(rows)
    states: list[str] = []
    manual_flags: list[bool] = []
    reasons: list[list[str]] = []
    for idx, row in scores.iterrows():
        base = scores.iloc[max(0, idx - baseline_lookback + 1) : idx + 1]
        distances = base["averaged_distance"].replace([np.inf, -np.inf], np.nan).dropna()
        distance_percentile = float((distances <= row["averaged_distance"]).mean()) if len(distances) else np.nan
        means = base["reduced_rank_mean_corr"].replace([np.inf, -np.inf], np.nan).dropna()
        reduced_mean_p25 = float(means.quantile(0.25)) if len(means) else np.nan
        payload = _state(
            distance_percentile if pd.notna(distance_percentile) else None,
            row["reduced_rank_mean_corr"] if pd.notna(row["reduced_rank_mean_corr"]) else None,
            reduced_mean_p25 if pd.notna(reduced_mean_p25) else None,
        )
        states.append(payload["state"])
        manual_flags.append(bool(payload["manual_review_required"]))
        reasons.append(payload["state_reasons"])
        scores.loc[idx, "distance_percentile"] = distance_percentile
        scores.loc[idx, "reduced_rank_mean_corr_p25"] = reduced_mean_p25
    scores["state"] = states
    scores["manual_review_required"] = manual_flags
    scores["state_reasons"] = reasons
    return scores


def _offdiag_mean(matrix: np.ndarray) -> float | None:
    if matrix.shape[0] < 2:
        return None
    values = matrix[~np.eye(matrix.shape[0], dtype=bool)]
    values = values[np.isfinite(values)]
    return float(np.mean(values)) if len(values) else None


def _window_summary(scores: pd.DataFrame, window: dict[str, str]) -> dict[str, Any]:
    start = pd.Timestamp(window["start"])
    end = pd.Timestamp(window["end"])
    subset = scores[(scores["dt"] >= start) & (scores["dt"] <= end)].copy()
    if subset.empty:
        return {**window, "status": "no_data", "available_days": 0}
    watch = _at_or_above(subset["state"], "watch")
    elevated = _at_or_above(subset["state"], "elevated_fragility")
    return {
        **window,
        "status": "available",
        "available_days": int(len(subset)),
        "ticker_count_min": int(subset["ticker_count"].min()),
        "ticker_count_median": _float_or_none(subset["ticker_count"].median()),
        "distance_percentile_mean": _float_or_none(subset["distance_percentile"].mean()),
        "distance_percentile_max": _float_or_none(subset["distance_percentile"].max()),
        "reduced_rank_mean_corr_mean": _float_or_none(subset["reduced_rank_mean_corr"].mean()),
        "state_counts": {str(k): int(v) for k, v in subset["state"].value_counts().to_dict().items()},
        "watch_or_worse_days": int(watch.sum()),
        "elevated_or_worse_days": int(elevated.sum()),
        "watch_or_worse_rate": _float_or_none(watch.mean()),
        "elevated_or_worse_rate": _float_or_none(elevated.mean()),
        "top_days": [
            {
                "dt": str(row.dt.date()),
                "state": str(row.state),
                "distance_percentile": _float_or_none(row.distance_percentile),
                "averaged_distance": _float_or_none(row.averaged_distance),
                "reduced_rank_mean_corr": _float_or_none(row.reduced_rank_mean_corr),
            }
            for row in subset.sort_values("distance_percentile", ascending=False).head(10).itertuples(index=False)
        ],
    }


def build_backtest(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = "2026-07-20",
    windows: list[dict[str, str]] | None = None,
    window: int = 42,
    min_history: int = 63,
    min_tickers: int = 12,
    max_stale_days: int = 10,
    baseline_lookback: int = 252,
) -> dict[str, Any]:
    windows = windows or DEFAULT_WINDOWS
    scores = build_daily_scores(
        db_path=db_path,
        as_of=as_of,
        window=window,
        min_history=min_history,
        min_tickers=min_tickers,
        max_stale_days=max_stale_days,
        baseline_lookback=baseline_lookback,
    )
    if scores.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_reduced_rank_correlation_crash_window_backtest",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "policy": "research_only_reduced_rank_proxy_backtest_no_weight_change",
            "status": "blocked",
            "blocking_reasons": ["reduced_rank_proxy_daily_scores_unavailable"],
            "decision": {
                "promotion_allowed": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        }

    window_mask = pd.Series(False, index=scores.index)
    for item in windows:
        window_mask |= (scores["dt"] >= pd.Timestamp(item["start"])) & (scores["dt"] <= pd.Timestamp(item["end"]))
    inside = scores[window_mask].copy()
    outside = scores[~window_mask].copy()
    inside_watch = _at_or_above(inside["state"], "watch") if not inside.empty else pd.Series(dtype=bool)
    inside_elevated = _at_or_above(inside["state"], "elevated_fragility") if not inside.empty else pd.Series(dtype=bool)
    outside_watch = _at_or_above(outside["state"], "watch") if not outside.empty else pd.Series(dtype=bool)
    outside_elevated = _at_or_above(outside["state"], "elevated_fragility") if not outside.empty else pd.Series(dtype=bool)

    blockers = [
        "reduced_rank_proxy_not_paper_equivalent",
        "broad_sector_stock_universe_not_used",
        "kmeans_market_state_snapshot_not_used",
        "no_live_weight_change_allowed",
    ]
    stress_watch_rate = float(inside_watch.mean()) if not inside.empty else 0.0
    non_watch_rate = float(outside_watch.mean()) if not outside.empty else 0.0
    if stress_watch_rate < 0.20:
        blockers.append("low_watch_or_worse_recall_in_stress_windows")
    if non_watch_rate > stress_watch_rate:
        blockers.append("watch_false_positive_rate_exceeds_stress_recall")
    if not outside.empty and float(outside_elevated.mean()) > 0.10:
        blockers.append("elevated_false_positive_rate_above_10pct")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_reduced_rank_correlation_crash_window_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_start": str(scores["dt"].min().date()),
        "actual_data_end": str(scores["dt"].max().date()),
        "policy": "research_only_reduced_rank_proxy_backtest_no_weight_change",
        "status": "blocked",
        "method": {
            "paper_equivalent": False,
            "window": window,
            "min_history": min_history,
            "min_tickers": min_tickers,
            "max_stale_days": max_stale_days,
            "baseline_lookback": baseline_lookback,
            "state_rule": "watch_if_distance_percentile_ge_0p75_elevated_if_ge_0p90_and_reduced_rank_mean_below_p25",
        },
        "windows": [_window_summary(scores, item) for item in windows],
        "aggregate": {
            "total_days": int(len(scores)),
            "stress_window_days": int(len(inside)),
            "non_window_days": int(len(outside)),
            "stress_window_watch_or_worse_rate": _float_or_none(inside_watch.mean()) if not inside.empty else None,
            "stress_window_elevated_or_worse_rate": _float_or_none(inside_elevated.mean()) if not inside.empty else None,
            "non_window_watch_or_worse_rate": _float_or_none(outside_watch.mean()) if not outside.empty else None,
            "non_window_elevated_or_worse_rate": _float_or_none(outside_elevated.mean()) if not outside.empty else None,
            "state_counts_all": {str(k): int(v) for k, v in scores["state"].value_counts().to_dict().items()},
            "distance_percentile_max": _float_or_none(scores["distance_percentile"].max()),
            "reduced_rank_mean_corr_min": _float_or_none(scores["reduced_rank_mean_corr"].min()),
        },
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None, actual_data_end: str | None) -> Path:
    stamp = str(as_of or actual_data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"reduced_rank_correlation_crash_window_backtest_{stamp}.json"


def write_backtest(payload: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
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
    parser.add_argument("--min-history", type=int, default=63)
    parser.add_argument("--min-tickers", type=int, default=12)
    parser.add_argument("--max-stale-days", type=int, default=10)
    parser.add_argument("--baseline-lookback", type=int, default=252)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_backtest(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        window=int(args.window),
        min_history=int(args.min_history),
        min_tickers=int(args.min_tickers),
        max_stale_days=int(args.max_stale_days),
        baseline_lookback=int(args.baseline_lookback),
    )
    write_backtest(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"Reduced-rank correlation crash-window backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "stress_watch_or_worse_rate": (payload.get("aggregate") or {}).get(
                    "stress_window_watch_or_worse_rate"
                ),
                "non_window_watch_or_worse_rate": (payload.get("aggregate") or {}).get(
                    "non_window_watch_or_worse_rate"
                ),
                "allow_00631l_add": payload["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
