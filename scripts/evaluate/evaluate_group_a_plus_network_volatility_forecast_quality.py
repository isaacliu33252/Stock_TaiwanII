#!/usr/bin/env python3
"""Validate GNHAR-RV forecast quality for 0050.TW before using it for anything.

Research-only. Compares group_a_plus.integrations.network_volatility_forecast_shadow
(GNHAR-RV pooled, global-alpha, network order (1,0,1) walk-forward forecast of
average future Garman-Klass variance at h=5/10/20) against two baselines:

- the existing univariate HAR-RV walk-forward forecast for 0050.TW already
  validated and used in this project (volatility_forecast.py) -- this is the
  real question: does pooling neighbour realized-variance information beat
  what 0050.TW's own history already gives us?
- naive persistence (22d trailing average variance), for context.

Uses QLIKE loss, the same loss used by arXiv 2604.10402v4 and by
evaluate_group_a_plus_volatility_forecast_quality.py.

This must show genuine forecast skill over the univariate HAR-RV baseline
before any position-sizing or alert rule is built on top of it.
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

from group_a_plus.integrations.network_volatility_forecast_shadow import (
    DEFAULT_TICKERS,
    NETWORK_ORDER,
    build_gk_variance_panel,
    gnhar_rv_walkforward_forecast,
)
from group_a_plus.integrations.risk_sensitive_loss import diebold_mariano_test, qlike_loss
from group_a_plus.integrations.volatility_forecast import (
    HORIZONS,
    _future_avg_variance,
    har_rv_walkforward_forecast,
    naive_persistence_forecast,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_network_volatility_forecast_quality_latest.json"


def _load_ohlcv(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, open, high, low, close FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    return rows


def _log_r2(actual: pd.Series, forecast: pd.Series) -> float:
    y = np.log(actual.clip(lower=1e-12))
    yhat = np.log(forecast.clip(lower=1e-12))
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def evaluate(
    tickers: tuple[str, ...],
    target: str,
    start: str,
    end: str,
    *,
    network_order: tuple[int, int, int],
    rolling_window: int | None,
) -> dict:
    ohlcv = _load_ohlcv(DB_PATH, tickers, start, end)
    gk_panel = build_gk_variance_panel(ohlcv, tickers=tickers)
    available = tuple(col for col in tickers if col in gk_panel.columns and gk_panel[col].notna().any())
    gk_panel = gk_panel[list(available)].dropna(how="all").ffill()
    if target not in gk_panel.columns:
        raise RuntimeError(f"target {target} missing from loaded OHLCV panel")
    target_gk = gk_panel[target]

    results = {}
    for h in HORIZONS:
        gnhar_forecast = gnhar_rv_walkforward_forecast(
            gk_panel, target=target, horizon=h, network_order=network_order, rolling_window=rolling_window
        )
        har_forecast = har_rv_walkforward_forecast(target_gk, horizon=h, rolling_window=rolling_window)
        naive_forecast = naive_persistence_forecast(target_gk, horizon=h)
        actual = _future_avg_variance(target_gk, h)

        valid = gnhar_forecast.notna() & har_forecast.notna() & naive_forecast.notna() & actual.notna()
        n = int(valid.sum())
        if n < 30:
            results[str(h)] = {"status": "insufficient_data", "n": n}
            continue

        gnhar_loss = qlike_loss(actual[valid], gnhar_forecast[valid])
        har_loss = qlike_loss(actual[valid], har_forecast[valid])
        naive_loss = qlike_loss(actual[valid], naive_forecast[valid])

        gnhar_mean = float(gnhar_loss.mean())
        har_mean = float(har_loss.mean())
        naive_mean = float(naive_loss.mean())
        dm_vs_har = diebold_mariano_test(gnhar_loss, har_loss, h=h)

        results[str(h)] = {
            "n": n,
            "gnhar_rv_qlike_mean": gnhar_mean,
            "har_rv_qlike_mean": har_mean,
            "naive_persistence_qlike_mean": naive_mean,
            "gnhar_improvement_vs_har_pct": (har_mean - gnhar_mean) / har_mean * 100.0 if har_mean else None,
            "gnhar_improvement_vs_naive_pct": (naive_mean - gnhar_mean) / naive_mean * 100.0 if naive_mean else None,
            "har_improvement_vs_naive_pct": (naive_mean - har_mean) / naive_mean * 100.0 if naive_mean else None,
            "gnhar_win_rate_vs_har": float((gnhar_loss.to_numpy() < har_loss.to_numpy()).mean()),
            "gnhar_r2_log_variance": _log_r2(actual[valid], gnhar_forecast[valid]),
            "har_r2_log_variance": _log_r2(actual[valid], har_forecast[valid]),
            "dm_test_gnhar_vs_har": dm_vs_har,
        }
    return {
        "target": target,
        "tickers": list(available),
        "network_order": list(network_order),
        "window": {"start": start, "end": end},
        "rolling_window": rolling_window,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="0050.TW")
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--network-order", type=int, nargs=3, default=list(NETWORK_ORDER))
    parser.add_argument("--rolling-window", type=int, default=504)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(
        tuple(args.tickers),
        args.target,
        args.start,
        args.end,
        network_order=tuple(args.network_order),
        rolling_window=args.rolling_window,
    )
    for h, res in payload["results"].items():
        if res.get("status") == "insufficient_data":
            print(f"h={h}: insufficient data (n={res['n']})")
            continue
        dm = res["dm_test_gnhar_vs_har"]
        if dm.get("status") == "ok":
            dm_str = f"DM p={dm['p_value']:.4f} ({'significant' if dm['significant_at_5pct'] else 'not significant'} at 5%)"
        else:
            dm_str = f"DM status={dm.get('status')}"
        print(
            f"h={h}: n={res['n']} "
            f"GNHAR-RV QLIKE={res['gnhar_rv_qlike_mean']:.4f} HAR-RV QLIKE={res['har_rv_qlike_mean']:.4f} "
            f"naive QLIKE={res['naive_persistence_qlike_mean']:.4f} | "
            f"GNHAR vs HAR={res['gnhar_improvement_vs_har_pct']:.2f}% "
            f"(win_rate={res['gnhar_win_rate_vs_har']:.3f}) "
            f"GNHAR vs naive={res['gnhar_improvement_vs_naive_pct']:.2f}% "
            f"HAR vs naive={res['har_improvement_vs_naive_pct']:.2f}% | {dm_str}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
