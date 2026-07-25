#!/usr/bin/env python3
"""Backtest the GroupA+ daily OHLCV illiquidity-stress proxy.

This is a research-only validation layer for the weak proxy introduced after
reviewing arXiv 2004.01917. It uses daily OHLCV only, so it does not validate
the paper's high-frequency illiquidity-network method.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_illiquidity_network_readiness_review import (
    PROXY_STATE_THRESHOLDS,
    _daily_proxy_state,
    _float_or_none,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/illiquidity_daily_proxy_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/illiquidity_daily_proxy_backtest/history"

DEFAULT_WINDOWS = [
    {
        "name": "taiwan_2015_china_devaluation_stress",
        "start": "2015-08-17",
        "end": "2015-09-30",
        "type": "stress_window",
    },
    {
        "name": "taiwan_2020_covid_crash",
        "start": "2020-02-17",
        "end": "2020-04-30",
        "type": "crash_window",
    },
    {
        "name": "taiwan_2022_inflation_rate_stress",
        "start": "2022-01-03",
        "end": "2022-10-31",
        "type": "stress_window",
    },
    {
        "name": "taiwan_2026_recent_groupa_plus_stress",
        "start": "2026-04-01",
        "end": "2026-07-20",
        "type": "recent_stress_window",
    },
]

STATE_RANK = {
    "unavailable": -1,
    "normal": 0,
    "watch": 1,
    "elevated": 2,
    "stress": 3,
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_daily_proxy_frame(db_path: Path, as_of: str | None) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    where = "WHERE dt <= ?" if as_of else ""
    params = [as_of] if as_of else []
    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "ohlcv" not in tables:
            return pd.DataFrame()
        frame = conn.execute(
            f"""
            SELECT ticker, dt, open, high, low, close, volume
            FROM ohlcv
            {where}
            ORDER BY ticker, dt
            """,
            params,
        ).fetchdf()
    if frame.empty:
        return pd.DataFrame()

    frame["dt"] = pd.to_datetime(frame["dt"])
    frame = frame.sort_values(["ticker", "dt"]).copy()
    grouped = frame.groupby("ticker", group_keys=False)
    frame["prev_close"] = grouped["close"].shift(1)
    frame["daily_return"] = frame["close"] / frame["prev_close"] - 1.0
    frame["range_pct"] = (frame["high"] - frame["low"]) / frame["prev_close"]
    frame["volume_ratio_20d"] = (
        frame["volume"]
        / grouped["volume"].rolling(20, min_periods=10).median().shift(1).reset_index(level=0, drop=True)
    )
    frame["range_p95_252d"] = (
        grouped["range_pct"].rolling(252, min_periods=60).quantile(0.95).shift(1).reset_index(level=0, drop=True)
    )
    frame["volume_drought_flag"] = frame["volume_ratio_20d"] < 0.50
    frame["range_spike_flag"] = frame["range_pct"] > frame["range_p95_252d"]
    frame["negative_return_flag"] = frame["daily_return"] <= -0.03
    frame["limit_down_proxy_flag"] = (frame["daily_return"] <= -0.095) | (
        frame["low"] <= frame["prev_close"] * 0.905
    )

    rows: list[dict[str, Any]] = []
    for dt, day in frame.groupby("dt"):
        coverage = int(day["ticker"].nunique())
        if coverage <= 0:
            continue
        component_counts = {
            "volume_drought": int(day["volume_drought_flag"].fillna(False).sum()),
            "range_spike": int(day["range_spike_flag"].fillna(False).sum()),
            "negative_return": int(day["negative_return_flag"].fillna(False).sum()),
            "limit_down_proxy": int(day["limit_down_proxy_flag"].fillna(False).sum()),
        }
        stress_score = (
            0.30 * component_counts["volume_drought"]
            + 0.25 * component_counts["range_spike"]
            + 0.25 * component_counts["negative_return"]
            + 0.20 * component_counts["limit_down_proxy"]
        ) / coverage
        state_payload = _daily_proxy_state(float(stress_score), component_counts)
        rows.append(
            {
                "dt": pd.Timestamp(dt),
                "coverage_tickers": coverage,
                "stress_score": float(stress_score),
                "stress_state": state_payload["stress_state"],
                "manual_review_required": state_payload["manual_review_required"],
                "component_counts": component_counts,
            }
        )
    return pd.DataFrame(rows)


def _state_at_or_above(series: pd.Series, state: str) -> pd.Series:
    threshold = STATE_RANK[state]
    return series.map(lambda value: STATE_RANK.get(str(value), -1) >= threshold)


def _window_summary(scores: pd.DataFrame, window: dict[str, str]) -> dict[str, Any]:
    start = pd.Timestamp(window["start"])
    end = pd.Timestamp(window["end"])
    subset = scores[(scores["dt"] >= start) & (scores["dt"] <= end)].copy()
    if subset.empty:
        return {
            **window,
            "available_days": 0,
            "status": "no_data",
        }
    state_counts = subset["stress_state"].value_counts().to_dict()
    elevated_or_worse = _state_at_or_above(subset["stress_state"], "elevated")
    watch_or_worse = _state_at_or_above(subset["stress_state"], "watch")
    return {
        **window,
        "status": "available",
        "available_days": int(len(subset)),
        "coverage_tickers_min": int(subset["coverage_tickers"].min()),
        "coverage_tickers_median": _float_or_none(subset["coverage_tickers"].median()),
        "stress_score_mean": _float_or_none(subset["stress_score"].mean()),
        "stress_score_max": _float_or_none(subset["stress_score"].max()),
        "state_counts": {str(k): int(v) for k, v in state_counts.items()},
        "watch_or_worse_days": int(watch_or_worse.sum()),
        "elevated_or_worse_days": int(elevated_or_worse.sum()),
        "watch_or_worse_rate": _float_or_none(watch_or_worse.mean()),
        "elevated_or_worse_rate": _float_or_none(elevated_or_worse.mean()),
        "top_days": [
            {
                "dt": str(row.dt.date()),
                "stress_score": _float_or_none(row.stress_score),
                "stress_state": str(row.stress_state),
                "coverage_tickers": int(row.coverage_tickers),
            }
            for row in subset.sort_values("stress_score", ascending=False).head(10).itertuples(index=False)
        ],
    }


def build_backtest(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    windows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    windows = windows or DEFAULT_WINDOWS
    scores = _load_daily_proxy_frame(db_path, as_of)
    if scores.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_illiquidity_daily_proxy_backtest",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "policy": "research_only_daily_ohlcv_proxy_backtest_no_weight_change",
            "status": "blocked",
            "blocking_reasons": ["ohlcv_proxy_scores_unavailable"],
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
        window_mask |= (scores["dt"] >= pd.Timestamp(window["start"])) & (
            scores["dt"] <= pd.Timestamp(window["end"])
        )
    outside = scores[~window_mask].copy()
    inside = scores[window_mask].copy()
    elevated_inside = _state_at_or_above(inside["stress_state"], "elevated") if not inside.empty else pd.Series(dtype=bool)
    elevated_outside = (
        _state_at_or_above(outside["stress_state"], "elevated") if not outside.empty else pd.Series(dtype=bool)
    )
    stress_outside = _state_at_or_above(outside["stress_state"], "stress") if not outside.empty else pd.Series(dtype=bool)
    blockers = [
        "daily_ohlcv_proxy_not_paper_equivalent",
        "high_frequency_bid_ask_not_validated",
        "full_market_failure_events_not_validated",
        "no_live_weight_change_allowed",
    ]
    if not inside.empty and float(elevated_inside.mean()) < 0.15:
        blockers.append("low_elevated_or_worse_recall_in_stress_windows")
    if not outside.empty and float(elevated_outside.mean()) > 0.10:
        blockers.append("elevated_or_worse_false_positive_rate_above_10pct")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_illiquidity_daily_proxy_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_start": str(scores["dt"].min().date()),
        "actual_data_end": str(scores["dt"].max().date()),
        "policy": "research_only_daily_ohlcv_proxy_backtest_no_weight_change",
        "status": "blocked",
        "state_thresholds": PROXY_STATE_THRESHOLDS,
        "windows": [_window_summary(scores, window) for window in windows],
        "aggregate": {
            "total_days": int(len(scores)),
            "stress_window_days": int(len(inside)),
            "non_window_days": int(len(outside)),
            "stress_window_elevated_or_worse_rate": _float_or_none(elevated_inside.mean())
            if not inside.empty
            else None,
            "non_window_elevated_or_worse_rate": _float_or_none(elevated_outside.mean())
            if not outside.empty
            else None,
            "non_window_stress_rate": _float_or_none(stress_outside.mean()) if not outside.empty else None,
            "state_counts_all": {str(k): int(v) for k, v in scores["stress_state"].value_counts().to_dict().items()},
            "coverage_tickers_min": int(scores["coverage_tickers"].min()),
            "coverage_tickers_median": _float_or_none(scores["coverage_tickers"].median()),
            "stress_score_max": _float_or_none(scores["stress_score"].max()),
        },
        "limitations": [
            "Daily OHLCV proxy cannot validate bid/ask-spread illiquidity networks.",
            "Stress windows are calendar labels, not tick-level liquidity-failure ground truth.",
            "ETF-only or small-universe history can understate market-wide contagion.",
            "This backtest is for manual research review only.",
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
    return history_dir / f"illiquidity_daily_proxy_backtest_{stamp}.json"


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
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    backtest = build_backtest(db_path=_resolve(args.db), as_of=args.as_of)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_backtest(backtest, _resolve(args.output), history_dir)
    print(f"Illiquidity daily proxy backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": backtest["status"],
                "actual_data_end": backtest.get("actual_data_end"),
                "stress_window_elevated_or_worse_rate": (backtest.get("aggregate") or {}).get(
                    "stress_window_elevated_or_worse_rate"
                ),
                "non_window_elevated_or_worse_rate": (backtest.get("aggregate") or {}).get(
                    "non_window_elevated_or_worse_rate"
                ),
                "promotion_allowed": backtest["decision"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
