#!/usr/bin/env python3
"""Validate HAR-RV forecast quality for 0050.TW before using it for anything.

Research-only. Compares group_a_plus.integrations.volatility_forecast
(HAR-RV walk-forward forecast of average future Garman-Klass variance at
h=5/10/20) against a naive persistence baseline (22d trailing average
variance), using QLIKE loss -- the same loss used by arXiv 2604.10402v4.

This must show genuine forecast skill (QLIKE improvement over naive) before
any position-sizing rule is built on top of it. If it does not, wiring a
decision rule on top is pointless -- garbage in, garbage out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.risk_sensitive_loss import qlike_loss
from group_a_plus.integrations.volatility_forecast import (
    HORIZONS,
    _future_avg_variance,
    garman_klass_variance,
    har_rv_walkforward_forecast,
    naive_persistence_forecast,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_volatility_forecast_quality_latest.json"


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, open, high, low, close FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def evaluate(ticker: str, start: str, end: str, *, rolling_window: int | None) -> dict:
    ohlc = _load_ohlc(DB_PATH, ticker, start, end)
    gk_variance = garman_klass_variance(ohlc)

    results = {}
    for h in HORIZONS:
        har_forecast = har_rv_walkforward_forecast(gk_variance, horizon=h, rolling_window=rolling_window)
        naive_forecast = naive_persistence_forecast(gk_variance, horizon=h)
        actual = _future_avg_variance(gk_variance, h)

        valid = har_forecast.notna() & naive_forecast.notna() & actual.notna()
        n = int(valid.sum())
        if n < 30:
            results[str(h)] = {"status": "insufficient_data", "n": n}
            continue

        har_loss = qlike_loss(actual[valid], har_forecast[valid])
        naive_loss = qlike_loss(actual[valid], naive_forecast[valid])

        har_mean = float(har_loss.mean())
        naive_mean = float(naive_loss.mean())
        win_rate = float((har_loss.to_numpy() < naive_loss.to_numpy()).mean())

        results[str(h)] = {
            "n": n,
            "har_rv_qlike_mean": har_mean,
            "naive_persistence_qlike_mean": naive_mean,
            "qlike_improvement_pct": (naive_mean - har_mean) / naive_mean * 100.0 if naive_mean else None,
            "har_win_rate_vs_naive": win_rate,
            "har_rv_r2_log_variance": _log_r2(actual[valid], har_forecast[valid]),
            "naive_r2_log_variance": _log_r2(actual[valid], naive_forecast[valid]),
        }
    return {"ticker": ticker, "window": {"start": start, "end": end}, "rolling_window": rolling_window, "results": results}


def _log_r2(actual: pd.Series, forecast: pd.Series) -> float:
    y = np.log(actual.clip(lower=1e-12))
    yhat = np.log(forecast.clip(lower=1e-12))
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--rolling-window", type=int, default=None)
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end, rolling_window=args.rolling_window)
    for h, res in payload["results"].items():
        if res.get("status") == "insufficient_data":
            print(f"h={h}: insufficient data (n={res['n']})")
            continue
        print(
            f"h={h}: n={res['n']} HAR-RV QLIKE={res['har_rv_qlike_mean']:.4f} "
            f"naive QLIKE={res['naive_persistence_qlike_mean']:.4f} "
            f"improvement={res['qlike_improvement_pct']:.2f}% "
            f"win_rate={res['har_win_rate_vs_naive']:.3f} "
            f"HAR R2={res['har_rv_r2_log_variance']:.3f} naive R2={res['naive_r2_log_variance']:.3f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
