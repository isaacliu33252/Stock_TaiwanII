#!/usr/bin/env python3
"""Sweep SIN-lite proxy parameters for research-only crash-window validation."""

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

from scripts.evaluate.build_group_a_plus_sin_lite_proxy import _float_or_none, _load_close_panel, _load_metadata, _state
from scripts.evaluate.evaluate_group_a_plus_sin_lite_crash_window_backtest import (
    DEFAULT_DB,
    DEFAULT_WINDOWS,
    _at_or_above,
    _window_summary,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/sin_lite_param_sweep/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _parse_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _score_candidate(backtest: dict[str, Any]) -> dict[str, Any]:
    aggregate = backtest.get("aggregate") or {}
    windows = backtest.get("windows") or []
    post_2020 = [item for item in windows if str(item.get("name", "")) >= "taiwan_2020"]
    post_2020_watch_rates = [
        float(item.get("watch_or_worse_rate") or 0.0)
        for item in post_2020
        if item.get("status") == "available"
    ]
    stress_watch = float(aggregate.get("stress_window_watch_or_worse_rate") or 0.0)
    stress_elevated = float(aggregate.get("stress_window_elevated_or_worse_rate") or 0.0)
    non_watch = float(aggregate.get("non_window_watch_or_worse_rate") or 0.0)
    non_elevated = float(aggregate.get("non_window_elevated_or_worse_rate") or 0.0)
    post_2020_min_watch = min(post_2020_watch_rates) if post_2020_watch_rates else 0.0
    objective = stress_watch + 0.5 * stress_elevated + 0.5 * post_2020_min_watch - 0.75 * non_watch - 2.0 * non_elevated
    return {
        "objective": round(objective, 6),
        "stress_window_watch_or_worse_rate": round(stress_watch, 6),
        "stress_window_elevated_or_worse_rate": round(stress_elevated, 6),
        "non_window_watch_or_worse_rate": round(non_watch, 6),
        "non_window_elevated_or_worse_rate": round(non_elevated, 6),
        "post_2020_min_watch_or_worse_rate": round(post_2020_min_watch, 6),
    }


def _load_close_once(db_path: Path, as_of: str | None) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        metadata = _load_metadata(conn)
        tickers = metadata["ticker"].astype(str).tolist() if not metadata.empty else []
        return _load_close_panel(conn, tickers, as_of)


def _safe_corr_matrix(values: np.ndarray) -> np.ndarray:
    if values.shape[0] < 2 or values.shape[1] < 2:
        return np.empty((0, 0))
    std = np.nanstd(values, axis=0)
    keep = std > 0
    if int(keep.sum()) < 2:
        return np.empty((0, 0))
    clean = values[:, keep]
    return np.corrcoef(clean, rowvar=False)


def _fast_daily_scores_from_close(
    close: pd.DataFrame,
    *,
    windows: list[dict[str, str]],
    lookback: int,
    min_history: int,
    edge_threshold: float,
    non_window_sample_step: int,
) -> pd.DataFrame:
    if close.empty:
        return pd.DataFrame()
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    window_mask = pd.Series(False, index=returns.index)
    for window in windows:
        window_mask |= (returns.index >= pd.Timestamp(window["start"])) & (
            returns.index <= pd.Timestamp(window["end"])
        )
    sample_step = max(int(non_window_sample_step), 1)
    sampled_mask = pd.Series(np.arange(len(returns)) % sample_step == 0, index=returns.index)
    selected_positions = np.flatnonzero((window_mask | sampled_mask).to_numpy())
    rows: list[dict[str, Any]] = []
    columns = list(returns.columns)
    for end_pos in selected_positions:
        dt = returns.index[end_pos]
        window = returns.iloc[max(0, end_pos - lookback + 1) : end_pos + 1]
        usable = [ticker for ticker in columns if int(window[ticker].notna().sum()) >= min_history]
        sub = window[usable].dropna(how="all")
        complete = sub.dropna()
        if len(usable) < 2 or len(sub) < min_history or len(complete) < max(10, min_history // 2):
            rows.append(
                {
                    "dt": pd.Timestamp(dt),
                    "state": "unavailable",
                    "sin_lite_score": np.nan,
                    "usable_ticker_count": len(usable),
                    "edge_density": np.nan,
                    "limited_base_reason": "insufficient_history_or_complete_rows",
                }
            )
            continue

        corr = _safe_corr_matrix(complete.to_numpy(dtype=float))
        if corr.size:
            mask = ~np.eye(corr.shape[0], dtype=bool)
            corr_values = corr[mask]
            corr_values = corr_values[np.isfinite(corr_values)]
        else:
            corr_values = np.array([])
        avg_abs_corr = float(np.mean(np.abs(corr_values))) if len(corr_values) else np.nan

        lag_source = complete.shift(1).iloc[1:].to_numpy(dtype=float)
        lag_target = complete.iloc[1:].to_numpy(dtype=float)
        lag_corr = _safe_corr_matrix(np.concatenate([lag_source, lag_target], axis=1))
        edge_count = 0
        influence_concentration = np.nan
        n = len(complete.columns)
        if lag_corr.size and lag_corr.shape[0] == n * 2:
            lag_block = lag_corr[:n, n:]
            np.fill_diagonal(lag_block, np.nan)
            edge_values = np.abs(lag_block[np.isfinite(lag_block)])
            edge_count = int((edge_values >= edge_threshold).sum())
            influence_concentration = float(edge_values.max()) if len(edge_values) else np.nan
        possible_edges = max(n * (n - 1), 1)
        edge_density = edge_count / possible_edges

        if "0050.TW" in complete:
            downside_frame = complete.loc[complete["0050.TW"] < 0.0]
        else:
            downside_frame = complete.loc[complete.mean(axis=1) < 0.0]
        downside_density = float((downside_frame < 0.0).mean(axis=1).mean()) if not downside_frame.empty else np.nan

        lead_scores = []
        if "2330.TW" in complete and "0050.TW" in complete:
            value = complete["2330.TW"].shift(1).corr(complete["0050.TW"])
            if pd.notna(value):
                lead_scores.append(abs(float(value)))
        if "2330.TW" in complete and "00631L.TW" in complete:
            value = complete["2330.TW"].shift(1).corr(complete["00631L.TW"])
            if pd.notna(value):
                lead_scores.append(abs(float(value)))
        lead_2330_score = max(lead_scores) if lead_scores else np.nan
        if "2330.TW" in close:
            s2330 = close["2330.TW"].loc[:dt].dropna()
            if len(s2330) >= 6 and float(s2330.iloc[-1] / s2330.iloc[-6] - 1.0) < -0.03:
                lead_2330_score = min(1.0, (0.0 if pd.isna(lead_2330_score) else lead_2330_score) + 0.15)

        components = [
            min(avg_abs_corr / 0.75, 1.0) if pd.notna(avg_abs_corr) else np.nan,
            min(edge_density / 0.25, 1.0),
            downside_density,
            influence_concentration,
            lead_2330_score,
        ]
        valid_components = [float(value) for value in components if pd.notna(value) and np.isfinite(float(value))]
        score = float(np.mean(valid_components)) if valid_components else np.nan
        state_payload = _state(score if pd.notna(score) else None)
        rows.append(
            {
                "dt": pd.Timestamp(dt),
                "state": state_payload["state"],
                "sin_lite_score": score,
                "usable_ticker_count": len(usable),
                "edge_density": edge_density,
                "limited_base_reason": None,
            }
        )
    return pd.DataFrame(rows)


def _backtest_from_scores(
    scores: pd.DataFrame,
    *,
    as_of: str | None,
    windows: list[dict[str, str]],
    lookback: int,
    min_history: int,
    min_tickers: int,
    edge_threshold: float,
) -> dict[str, Any]:
    if scores.empty:
        return {
            "aggregate": {},
            "windows": [],
            "blocking_reasons": ["sin_lite_daily_scores_unavailable"],
        }
    window_mask = pd.Series(False, index=scores.index)
    for window in windows:
        window_mask |= (scores["dt"] >= pd.Timestamp(window["start"])) & (scores["dt"] <= pd.Timestamp(window["end"]))
    inside = scores[window_mask].copy()
    outside = scores[~window_mask].copy()
    inside_watch = _at_or_above(inside["state"], "watch") if not inside.empty else pd.Series(dtype=bool)
    inside_elevated = _at_or_above(inside["state"], "elevated") if not inside.empty else pd.Series(dtype=bool)
    outside_watch = _at_or_above(outside["state"], "watch") if not outside.empty else pd.Series(dtype=bool)
    outside_elevated = _at_or_above(outside["state"], "elevated") if not outside.empty else pd.Series(dtype=bool)
    window_summaries = [_window_summary(scores, window) for window in windows]
    limited_windows = [
        item["name"]
        for item in window_summaries
        if item.get("status") == "available" and int(item.get("usable_ticker_count_min") or 0) < min_tickers
    ]
    blockers = [
        "sin_lite_proxy_not_paper_equivalent",
        "hmm_bubble_state_not_used",
        "transfer_entropy_not_used",
        "no_live_weight_change_allowed",
    ]
    if limited_windows:
        blockers.append("limited_ticker_coverage_in_some_windows")
    return {
        "as_of": as_of,
        "method": {
            "paper_equivalent": False,
            "fast_sweep_complete_row_correlation": True,
            "lookback": lookback,
            "min_history": min_history,
            "min_tickers": min_tickers,
            "edge_threshold": edge_threshold,
        },
        "windows": window_summaries,
        "aggregate": {
            "total_days": int(len(scores)),
            "stress_window_days": int(len(inside)),
            "non_window_days": int(len(outside)),
            "stress_window_watch_or_worse_rate": _float_or_none(inside_watch.mean()) if not inside.empty else None,
            "stress_window_elevated_or_worse_rate": _float_or_none(inside_elevated.mean()) if not inside.empty else None,
            "non_window_watch_or_worse_rate": _float_or_none(outside_watch.mean()) if not outside.empty else None,
            "non_window_elevated_or_worse_rate": _float_or_none(outside_elevated.mean()) if not outside.empty else None,
            "state_counts_all": {str(k): int(v) for k, v in scores["state"].value_counts().to_dict().items()},
            "sin_lite_score_max": _float_or_none(scores["sin_lite_score"].max()),
            "sin_lite_score_mean": _float_or_none(scores["sin_lite_score"].mean()),
            "limited_coverage_windows": limited_windows,
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def run_sweep(
    *,
    db_path: Path,
    as_of: str | None,
    lookbacks: list[int],
    min_histories: list[int],
    min_tickers_values: list[int],
    edge_thresholds: list[float],
    non_window_sample_step: int = 5,
) -> dict[str, Any]:
    close = _load_close_once(db_path, as_of)
    windows = DEFAULT_WINDOWS
    score_cache: dict[tuple[int, int, float], pd.DataFrame] = {}
    candidates: list[dict[str, Any]] = []
    for lookback in lookbacks:
        for min_history in min_histories:
            if min_history > lookback:
                continue
            for min_tickers in min_tickers_values:
                for edge_threshold in edge_thresholds:
                    score_key = (lookback, min_history, edge_threshold)
                    if score_key not in score_cache:
                        score_cache[score_key] = _fast_daily_scores_from_close(
                            close,
                            windows=windows,
                            lookback=lookback,
                            min_history=min_history,
                            edge_threshold=edge_threshold,
                            non_window_sample_step=non_window_sample_step,
                        )
                    backtest = _backtest_from_scores(
                        score_cache[score_key],
                        as_of=as_of,
                        windows=windows,
                        lookback=lookback,
                        min_history=min_history,
                        min_tickers=min_tickers,
                        edge_threshold=edge_threshold,
                    )
                    metrics = _score_candidate(backtest)
                    candidates.append(
                        {
                            "params": {
                                "lookback": lookback,
                                "min_history": min_history,
                                "min_tickers": min_tickers,
                                "edge_threshold": edge_threshold,
                            },
                            "metrics": metrics,
                            "blocking_reasons": backtest.get("blocking_reasons", []),
                            "windows": [
                                {
                                    "name": item.get("name"),
                                    "watch_or_worse_rate": item.get("watch_or_worse_rate"),
                                    "elevated_or_worse_rate": item.get("elevated_or_worse_rate"),
                                    "usable_ticker_count_min": item.get("usable_ticker_count_min"),
                                }
                                for item in backtest.get("windows", [])
                            ],
                        }
                    )
    candidates = sorted(candidates, key=lambda item: item["metrics"]["objective"], reverse=True)
    best = candidates[0] if candidates else None
    promotion_blockers = [
        "sin_lite_sweep_research_only",
        "no_hmm_bubble_state",
        "no_transfer_entropy",
        "no_live_weight_change_allowed",
    ]
    if best:
        metrics = best["metrics"]
        if metrics["stress_window_watch_or_worse_rate"] < 0.35:
            promotion_blockers.append("best_stress_window_recall_below_35pct")
        if metrics["post_2020_min_watch_or_worse_rate"] < 0.05:
            promotion_blockers.append("best_post_2020_window_min_recall_below_5pct")
        if metrics["non_window_elevated_or_worse_rate"] > 0.10:
            promotion_blockers.append("best_false_positive_rate_too_high")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_sin_lite_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "research_only_sin_lite_param_sweep_no_weight_change",
        "status": "blocked",
        "grid": {
            "lookbacks": lookbacks,
            "min_histories": min_histories,
            "min_tickers_values": min_tickers_values,
            "edge_thresholds": edge_thresholds,
            "candidate_count": len(candidates),
            "sampled_non_window": True,
            "non_window_sample_step": non_window_sample_step,
        },
        "best_candidate": best,
        "top_candidates": candidates[:10],
        "blocking_reasons": sorted(set(promotion_blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"sin_lite_param_sweep_{stamp}.json"


def write_sweep(payload: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload.get("as_of")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--lookbacks", default="60,90,120,180")
    parser.add_argument("--min-histories", default="40,60,80")
    parser.add_argument("--min-tickers", default="6,8,10")
    parser.add_argument("--edge-thresholds", default="0.2,0.3,0.35,0.45")
    parser.add_argument("--non-window-sample-step", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = run_sweep(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        lookbacks=_parse_ints(args.lookbacks),
        min_histories=_parse_ints(args.min_histories),
        min_tickers_values=_parse_ints(args.min_tickers),
        edge_thresholds=_parse_floats(args.edge_thresholds),
        non_window_sample_step=int(args.non_window_sample_step),
    )
    write_sweep(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    best = payload.get("best_candidate") or {}
    print(f"SIN-lite parameter sweep: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "candidate_count": payload["grid"]["candidate_count"],
                "best_params": best.get("params"),
                "best_metrics": best.get("metrics"),
                "promotion_allowed": payload["decision"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
