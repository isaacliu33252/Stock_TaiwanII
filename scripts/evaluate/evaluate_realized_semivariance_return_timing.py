#!/usr/bin/env python3
"""Test a daily-data proxy for Bollerslev, Li, and Zhao (2019, JFQA), "Good
Volatility, Bad Volatility, and the Cross Section of Stock Returns", on
0050.TW and 00631L.TW.

Research-only. The paper decomposes each stock's realized variation into
"good" (up) and "bad" (down) semivariance using 5-minute intraday prices,
defines the relative signed jump variation

    RSJ = (RV+ - RV-) / RV

and shows that, cross-sectionally across ~20,000 US stocks (1993-2013),
high-RSJ stocks (recent volatility skewed toward up-moves) significantly
UNDERPERFORM low-RSJ stocks over the subsequent week (value-weighted
High-Low FFC4 alpha = -28.80 bps/week, t=-5.77). The paper attributes this to
investor overreaction to positive jumps, reversing.

Two structural caveats, both discussed with the user before running this:

1. Data: this project has no intraday price history (stock_db.py only
   ingests daily bars). The paper's RSJ formally isolates jump variation --
   that separation is only valid at high sampling frequency. This script's
   `_realized_semivariance_asymmetry` uses daily up/down squared returns
   instead, which is the same up/down split but computed at a much coarser
   frequency (no jump-vs-diffusion decomposition). It is a proxy of the
   general "good vs bad volatility" idea, not a replication of RSJ.
2. Design: the paper's effect is fundamentally CROSS-SECTIONAL (a stock's
   RSJ relative to ~20,000 peers that week). This script instead asks a
   different, weaker question: does a single ticker's OWN lagged
   good-minus-bad volatility predict its OWN future return (pure
   time-series). This is not what the paper's significance results
   established.

Reuses the same Newey-West/Bartlett-HAC regression test (same style as
diebold_mariano_test and evaluate_downside_vol_return_timing.py) so results
are directly comparable to the two related, already-null tests on these same
tickers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_downside_vol_return_timing import (
    _hac_ols_slope_tstat,
    _load_close,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "realized_semivariance_return_timing_latest.json"
HORIZONS = (5, 10, 20)
WEEK_WINDOW = 5  # trading days, proxy for the paper's calendar week


def _realized_semivariance_asymmetry(returns: pd.Series, window: int = WEEK_WINDOW) -> pd.Series:
    """Daily-return proxy for RSJ: (RV+ - RV-) / RV over a rolling `window`.

    RV+ / RV- are rolling sums of squared returns restricted to up/down days.
    Bounded in [-1, 1] by construction, matching the paper's RSJ scale.
    """
    sq = returns**2
    rv_plus = sq.where(returns > 0, 0.0).rolling(window, min_periods=window).sum()
    rv_minus = sq.where(returns < 0, 0.0).rolling(window, min_periods=window).sum()
    total = rv_plus + rv_minus
    return (rv_plus - rv_minus) / total.replace(0.0, np.nan)


def evaluate(ticker: str, start: str, end: str) -> dict:
    close = _load_close(DB_PATH, ticker)
    close = close.loc[start:end]
    returns = close.pct_change().fillna(0.0)

    rsj_proxy = _realized_semivariance_asymmetry(returns)

    results: dict[str, dict] = {}
    for h in HORIZONS:
        forward_return = close.pct_change(h).shift(-h)
        lagged_rsj = rsj_proxy.shift(1)

        valid = forward_return.notna() & lagged_rsj.notna()
        n = int(valid.sum())
        if n < 60:
            results[str(h)] = {"status": "insufficient_data", "n": n}
            continue

        y = forward_return[valid].to_numpy(dtype=float)
        x = lagged_rsj[valid].to_numpy(dtype=float)

        fit = _hac_ols_slope_tstat(x, y, lag=h - 1)
        results[str(h)] = {
            "n": n,
            "rsj_proxy": fit,
            "matches_paper_direction_and_significant": bool(
                fit["slope"] < 0 and fit["p_value"] < 0.10
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
        f = res["rsj_proxy"]
        print(
            f"h={h}: n={res['n']} | "
            f"rsj_proxy slope={f['slope']:+.4f} t={f['t_stat']:+.2f} p={f['p_value']:.3f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
