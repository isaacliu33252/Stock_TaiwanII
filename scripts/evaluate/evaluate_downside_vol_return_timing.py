#!/usr/bin/env python3
"""Test the paper's core claim on 0050.TW: does downside volatility have more
"return-timing" power than total (symmetric) volatility?

Research-only. Wang & Yan (2021, J. Banking & Finance), "Downside risk and the
performance of volatility-managed portfolios", decompose volatility-managed
portfolio alpha into a volatility-timing component (persistence) and a
return-timing component (does lagged volatility predict future returns). They
find total volatility has near-zero/ambiguous return-timing power across 9
equity factors and 94 anomalies, while downside volatility (semivariance from
negative-return days only) reliably, negatively predicts future returns --
that difference is what makes downside-volatility-scaled portfolios
outperform total-volatility-scaled ones.

This script checks whether the same pattern holds for 0050.TW using the two
GARCH-proxy volatility measures already in
scripts/backtest/backtest_group_a_plus_financial_econometrics.py: the
existing symmetric proxy (_garch_proxy_vol) and the new downside-only variant
added alongside it (_garch_proxy_vol_downside, 2026-07-11). For each forecast
horizon, it regresses the forward h-day return on the lagged, causally-computed
rolling percentile of each vol proxy and reports the slope with a Newey-West
(Bartlett-kernel, lag=h-1) HAC t-statistic -- the same style of robust test
already used by diebold_mariano_test in risk_sensitive_loss.py, applied here
to a return-predictability regression instead of a loss differential.

This is diagnostic only. A significant result here would only justify
building (and separately walk-forward-testing) a downside-vol-based regime
gate in garch_regime_shadow.py -- it does not change any weight by itself.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backtest.backtest_group_a_plus_financial_econometrics import (
    _garch_proxy_vol,
    _garch_proxy_vol_downside,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "downside_vol_return_timing_latest.json"
HORIZONS = (5, 10, 20)
PERCENTILE_WINDOW = 252
PERCENTILE_MIN_PERIODS = 60


def _load_close(db_path: Path, ticker: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float)


def _rolling_percentile(vol: pd.Series) -> pd.Series:
    return vol.rolling(PERCENTILE_WINDOW, min_periods=PERCENTILE_MIN_PERIODS).rank(pct=True)


def _hac_ols_slope_tstat(x: np.ndarray, y: np.ndarray, lag: int) -> dict[str, float]:
    """Bartlett-kernel Newey-West HAC t-statistic for the slope of y = a + b*x + e.

    `lag` should be forecast_horizon - 1, matching the autocorrelation induced
    by overlapping h-step-ahead forward returns (same convention as
    diebold_mariano_test in risk_sensitive_loss.py).
    """
    n = len(x)
    x_bar = x.mean()
    y_bar = y.mean()
    x_dev = x - x_bar
    sxx = float(np.dot(x_dev, x_dev))
    b = float(np.dot(x_dev, y - y_bar)) / sxx
    a = y_bar - b * x_bar
    resid = y - (a + b * x)

    scores = x_dev * resid
    max_lag = max(int(lag), 0)
    gamma_0 = float(np.dot(scores, scores))
    long_run = gamma_0
    for l in range(1, max_lag + 1):
        weight = 1.0 - l / (max_lag + 1)
        gamma_l = float(np.dot(scores[l:], scores[:-l]))
        long_run += 2.0 * weight * gamma_l

    var_b = long_run / (sxx**2)
    se_b = math.sqrt(var_b) if var_b > 0 else float("nan")
    t_stat = b / se_b if se_b and math.isfinite(se_b) and se_b > 0 else float("nan")
    from scipy import stats as scipy_stats

    p_value = float(2.0 * scipy_stats.t.sf(abs(t_stat), df=n - 2)) if math.isfinite(t_stat) else float("nan")
    return {"n": n, "slope": b, "t_stat": t_stat, "p_value": p_value}


def evaluate(ticker: str, start: str, end: str) -> dict:
    close = _load_close(DB_PATH, ticker)
    close = close.loc[start:end]
    returns = close.pct_change().fillna(0.0)

    vol_total = _garch_proxy_vol(returns)
    vol_downside = _garch_proxy_vol_downside(returns)
    pct_total = _rolling_percentile(vol_total)
    pct_downside = _rolling_percentile(vol_downside)

    results: dict[str, dict] = {}
    for h in HORIZONS:
        forward_return = close.pct_change(h).shift(-h)
        lagged_total = pct_total.shift(1)
        lagged_downside = pct_downside.shift(1)

        valid = forward_return.notna() & lagged_total.notna() & lagged_downside.notna()
        n = int(valid.sum())
        if n < 60:
            results[str(h)] = {"status": "insufficient_data", "n": n}
            continue

        y = forward_return[valid].to_numpy(dtype=float)
        x_total = lagged_total[valid].to_numpy(dtype=float)
        x_downside = lagged_downside[valid].to_numpy(dtype=float)

        total_fit = _hac_ols_slope_tstat(x_total, y, lag=h - 1)
        downside_fit = _hac_ols_slope_tstat(x_downside, y, lag=h - 1)

        results[str(h)] = {
            "n": n,
            "total_vol": total_fit,
            "downside_vol": downside_fit,
            "downside_more_negative_and_significant": bool(
                downside_fit["slope"] < total_fit["slope"] and downside_fit["p_value"] < 0.10
            ),
        }
    return {"ticker": ticker, "window": {"start": start, "end": end}, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end)
    for h, res in payload["results"].items():
        if res.get("status") == "insufficient_data":
            print(f"h={h}: insufficient data (n={res['n']})")
            continue
        t = res["total_vol"]
        d = res["downside_vol"]
        print(
            f"h={h}: n={res['n']} | "
            f"total_vol slope={t['slope']:+.4f} t={t['t_stat']:+.2f} p={t['p_value']:.3f} | "
            f"downside_vol slope={d['slope']:+.4f} t={d['t_stat']:+.2f} p={d['p_value']:.3f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
