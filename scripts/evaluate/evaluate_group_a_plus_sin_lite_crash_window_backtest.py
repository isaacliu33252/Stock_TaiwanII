#!/usr/bin/env python3
"""Backtest the GroupA+ SIN-lite proxy on crash/stress windows.

This validates only the weak daily-OHLCV proxy. It does not validate the full
HMM + transfer-entropy Speculative Influence Network from arXiv 1510.08162.
"""

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

from scripts.evaluate.build_group_a_plus_sin_lite_proxy import (
    DEFAULT_DB,
    _float_or_none,
    _load_close_panel,
    _load_metadata,
    _pair_edges,
    _state,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_crash_window_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/sin_lite_crash_window_backtest/history"

DEFAULT_WINDOWS = [
    {
        "name": "taiwan_2015_china_crash",
        "start": "2015-06-01",
        "end": "2016-02-29",
        "type": "crash_window",
    },
    {
        "name": "taiwan_2018_trade_war_correction",
        "start": "2018-01-02",
        "end": "2018-12-31",
        "type": "stress_window",
    },
    {
        "name": "taiwan_2020_covid_crash",
        "start": "2020-01-02",
        "end": "2020-06-30",
        "type": "crash_window",
    },
    {
        "name": "taiwan_2022_rate_hike_stress",
        "start": "2022-01-03",
        "end": "2022-10-31",
        "type": "stress_window",
    },
    {
        "name": "taiwan_2026_q1q2_stress",
        "start": "2026-02-02",
        "end": "2026-04-30",
        "type": "stress_window",
    },
    {
        "name": "taiwan_2026_recent",
        "start": "2026-05-15",
        "end": "2026-07-20",
        "type": "recent_window",
    },
]

STATE_RANK = {
    "unavailable": -1,
    "normal": 0,
    "watch": 1,
    "elevated": 2,
    "blocked_for_leverage_add": 3,
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _at_or_above(series: pd.Series, state: str) -> pd.Series:
    threshold = STATE_RANK[state]
    return series.map(lambda value: STATE_RANK.get(str(value), -1) >= threshold)


def _score_window(
    close: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    end_pos: int,
    lookback: int,
    min_history: int,
    min_tickers: int,
    edge_threshold: float,
) -> dict[str, Any]:
    dt = returns.index[end_pos]
    window = returns.iloc[max(0, end_pos - lookback + 1) : end_pos + 1].copy()
    usable = [ticker for ticker in window.columns if int(window[ticker].notna().sum()) >= min_history]
    sub = window[usable].dropna(how="all")
    if len(usable) < 2 or len(sub) < min_history:
        return {
            "dt": pd.Timestamp(dt),
            "state": "unavailable",
            "sin_lite_score": np.nan,
            "usable_ticker_count": len(usable),
            "lookback_observations": int(len(sub)),
            "edge_count": 0,
            "state_reasons": ["insufficient_history_or_tickers"],
        }

    corr = sub.corr()
    mask = ~np.eye(len(corr), dtype=bool)
    values = corr.to_numpy(dtype=float)[mask]
    values = values[np.isfinite(values)]
    avg_abs_corr = float(np.mean(np.abs(values))) if len(values) else np.nan
    max_abs_corr = float(np.max(np.abs(values))) if len(values) else np.nan
    edges = _pair_edges(sub, threshold=edge_threshold)
    possible_edges = max(len(usable) * (len(usable) - 1), 1)
    edge_density = len(edges) / possible_edges
    influence_concentration = max((abs(float(edge["value"] or 0.0)) for edge in edges), default=np.nan)

    downside_density = np.nan
    if "0050.TW" in sub:
        downside_frame = sub.loc[sub["0050.TW"] < 0.0]
        if not downside_frame.empty:
            downside_density = float((downside_frame < 0.0).mean(axis=1).mean())
    else:
        market_proxy = sub.mean(axis=1)
        downside_frame = sub.loc[market_proxy < 0.0]
        if not downside_frame.empty:
            downside_density = float((downside_frame < 0.0).mean(axis=1).mean())

    lead_2330_to_0050 = (
        sub["2330.TW"].shift(1).corr(sub["0050.TW"]) if {"2330.TW", "0050.TW"} <= set(sub.columns) else np.nan
    )
    lead_2330_to_00631l = (
        sub["2330.TW"].shift(1).corr(sub["00631L.TW"])
        if {"2330.TW", "00631L.TW"} <= set(sub.columns)
        else np.nan
    )
    recent_2330_ret5 = np.nan
    if "2330.TW" in close:
        s2330 = close["2330.TW"].loc[:dt].dropna()
        if len(s2330) >= 6:
            recent_2330_ret5 = float(s2330.iloc[-1] / s2330.iloc[-6] - 1.0)

    lead_corr_values = [abs(float(x)) for x in (lead_2330_to_0050, lead_2330_to_00631l) if pd.notna(x)]
    lead_2330_score = max(lead_corr_values) if lead_corr_values else np.nan
    if pd.notna(recent_2330_ret5) and float(recent_2330_ret5) < -0.03:
        lead_2330_score = min(1.0, (0.0 if pd.isna(lead_2330_score) else lead_2330_score) + 0.15)

    components = {
        "correlation_density": min(avg_abs_corr / 0.75, 1.0) if pd.notna(avg_abs_corr) else np.nan,
        "edge_density": min(edge_density / 0.25, 1.0),
        "downside_comovement": downside_density,
        "influence_concentration": influence_concentration,
        "tsmc_lead_risk": lead_2330_score,
    }
    component_values = [float(value) for value in components.values() if pd.notna(value) and np.isfinite(float(value))]
    score = float(np.mean(component_values)) if component_values else np.nan
    state_payload = _state(score if pd.notna(score) else None)
    reasons = list(state_payload["state_reasons"])
    if len(usable) < min_tickers:
        reasons.append(f"limited_usable_ticker_count:{len(usable)}<{min_tickers}")
    return {
        "dt": pd.Timestamp(dt),
        "state": state_payload["state"],
        "manual_review_required": bool(state_payload["manual_review_required"]),
        "sin_lite_score": score,
        "usable_ticker_count": len(usable),
        "lookback_observations": int(len(sub)),
        "avg_abs_corr": avg_abs_corr,
        "max_abs_corr": max_abs_corr,
        "edge_count": len(edges),
        "edge_density": edge_density,
        "downside_density": downside_density,
        "lead_2330_to_0050_corr": lead_2330_to_0050,
        "lead_2330_to_00631l_corr": lead_2330_to_00631l,
        "recent_2330_ret5": recent_2330_ret5,
        "state_reasons": reasons,
    }


def build_daily_scores(
    *,
    db_path: Path,
    as_of: str | None,
    lookback: int,
    min_history: int,
    min_tickers: int,
    edge_threshold: float,
) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        metadata = _load_metadata(conn)
        tickers = metadata["ticker"].astype(str).tolist() if not metadata.empty else []
        close = _load_close_panel(conn, tickers, as_of)
    if close.empty:
        return pd.DataFrame()
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    rows = [
        _score_window(
            close,
            returns,
            end_pos=pos,
            lookback=lookback,
            min_history=min_history,
            min_tickers=min_tickers,
            edge_threshold=edge_threshold,
        )
        for pos in range(len(returns))
    ]
    return pd.DataFrame(rows)


def _window_summary(scores: pd.DataFrame, window: dict[str, str]) -> dict[str, Any]:
    start = pd.Timestamp(window["start"])
    end = pd.Timestamp(window["end"])
    subset = scores[(scores["dt"] >= start) & (scores["dt"] <= end)].copy()
    if subset.empty:
        return {**window, "status": "no_data", "available_days": 0}
    watch = _at_or_above(subset["state"], "watch")
    elevated = _at_or_above(subset["state"], "elevated")
    return {
        **window,
        "status": "available",
        "available_days": int(len(subset)),
        "usable_ticker_count_min": int(subset["usable_ticker_count"].min()),
        "usable_ticker_count_median": _float_or_none(subset["usable_ticker_count"].median()),
        "sin_lite_score_mean": _float_or_none(subset["sin_lite_score"].mean()),
        "sin_lite_score_max": _float_or_none(subset["sin_lite_score"].max()),
        "state_counts": {str(k): int(v) for k, v in subset["state"].value_counts().to_dict().items()},
        "watch_or_worse_days": int(watch.sum()),
        "elevated_or_worse_days": int(elevated.sum()),
        "watch_or_worse_rate": _float_or_none(watch.mean()),
        "elevated_or_worse_rate": _float_or_none(elevated.mean()),
        "top_days": [
            {
                "dt": str(row.dt.date()),
                "sin_lite_score": _float_or_none(row.sin_lite_score),
                "state": str(row.state),
                "usable_ticker_count": int(row.usable_ticker_count),
                "edge_density": _float_or_none(row.edge_density),
            }
            for row in subset.sort_values("sin_lite_score", ascending=False).head(10).itertuples(index=False)
        ],
    }


def build_backtest(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    windows: list[dict[str, str]] | None = None,
    lookback: int = 120,
    min_history: int = 80,
    min_tickers: int = 8,
    edge_threshold: float = 0.35,
) -> dict[str, Any]:
    windows = windows or DEFAULT_WINDOWS
    scores = build_daily_scores(
        db_path=db_path,
        as_of=as_of,
        lookback=lookback,
        min_history=min_history,
        min_tickers=min_tickers,
        edge_threshold=edge_threshold,
    )
    if scores.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_sin_lite_crash_window_backtest",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "policy": "research_only_sin_lite_backtest_no_weight_change",
            "status": "blocked",
            "blocking_reasons": ["sin_lite_daily_scores_unavailable"],
            "decision": {
                "promotion_allowed": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
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

    blockers = [
        "sin_lite_proxy_not_paper_equivalent",
        "hmm_bubble_state_not_used",
        "transfer_entropy_not_used",
        "no_live_weight_change_allowed",
    ]
    if not inside.empty and float(inside_watch.mean()) < 0.20:
        blockers.append("low_watch_or_worse_recall_in_stress_windows")
    if not outside.empty and float(outside_elevated.mean()) > 0.10:
        blockers.append("elevated_or_worse_false_positive_rate_above_10pct")

    limited_windows = [
        item["name"]
        for item in (_window_summary(scores, window) for window in windows)
        if item.get("status") == "available" and int(item.get("usable_ticker_count_min") or 0) < min_tickers
    ]
    if limited_windows:
        blockers.append("limited_ticker_coverage_in_some_windows")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_sin_lite_crash_window_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_start": str(scores["dt"].min().date()),
        "actual_data_end": str(scores["dt"].max().date()),
        "policy": "research_only_sin_lite_backtest_no_weight_change",
        "status": "blocked",
        "method": {
            "paper_equivalent": False,
            "lookback": lookback,
            "min_history": min_history,
            "min_tickers": min_tickers,
            "edge_threshold": edge_threshold,
        },
        "windows": [_window_summary(scores, window) for window in windows],
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
        "limitations": [
            "Daily OHLCV correlation and lagged correlation are not transfer entropy.",
            "No HMM bubble-state filtering is applied.",
            "Early windows have limited ticker coverage because many ETFs start after 2020.",
            "This backtest is for research governance only.",
        ],
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
    return history_dir / f"sin_lite_crash_window_backtest_{stamp}.json"


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
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--lookback", type=int, default=120)
    parser.add_argument("--min-history", type=int, default=80)
    parser.add_argument("--min-tickers", type=int, default=8)
    parser.add_argument("--edge-threshold", type=float, default=0.35)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_backtest(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        lookback=int(args.lookback),
        min_history=int(args.min_history),
        min_tickers=int(args.min_tickers),
        edge_threshold=float(args.edge_threshold),
    )
    write_backtest(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"SIN-lite crash-window backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "actual_data_end": payload.get("actual_data_end"),
                "stress_window_watch_or_worse_rate": (payload.get("aggregate") or {}).get(
                    "stress_window_watch_or_worse_rate"
                ),
                "non_window_elevated_or_worse_rate": (payload.get("aggregate") or {}).get(
                    "non_window_elevated_or_worse_rate"
                ),
                "promotion_allowed": payload["decision"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
