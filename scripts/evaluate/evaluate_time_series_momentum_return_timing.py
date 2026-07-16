#!/usr/bin/env python3
"""Does time-series momentum (an asset's own trailing return) predict its
own future return on 0050.TW / 00631L.TW?

Research-only, 2026-07-12, following a discussion of AQR's time-series
momentum / managed-futures literature (Hurst, Ooi, and Pedersen 2017,
"A Century of Evidence on Trend-Following Investing"; Baltas and Kosowski
2013; Hutchinson and O'Brien 2014). Time-series momentum asks whether an
asset's OWN sign of trailing return predicts its OWN future return -- a
different question from every other test run this session (which were all
about volatility asymmetry, tail risk, or chip/options positioning, never
plain own-asset return continuation).

Two caveats flagged to the user before running this:
1. The literature's main diversification story (low cross-correlation
   across 67 markets/4 asset classes) does not apply here -- 0050/00631L/
   00632R are direct/leveraged/inverse variants of the same TAIEX-50
   underlying, already established as highly correlated in this session's
   GNHAR feasibility discussion. Only the pure return-predictability claim
   (not the diversification claim) is testable with this project's universe.
2. Group A+ already implicitly relies on a trend/momentum premise via
   `ma_gap` (price vs moving average) regime classification (golden1 vs
   defensive), but that threshold was set by backtest optimization, not by
   a formal significance test of "does trailing return predict forward
   return." This script provides that formal test for the first time.

Method: same Newey-West/Bartlett-HAC regression test used throughout this
session (reusing `_hac_ols_slope_tstat` from
evaluate_downside_vol_return_timing.py). Predictor: trailing L-day return
(L=21/63/252, approximating 1/3/12-month lookbacks). Target: forward h-day
return (h=5/10/20, matching this session's convention). A positive,
significant slope would support time-series momentum (continuation); a
negative slope would support mean-reversion; a null result matches this
session's broader pattern of return predictability being weak on these
tickers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_downside_vol_return_timing import _hac_ols_slope_tstat, _load_close

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "time_series_momentum_return_timing_latest.json"
LOOKBACKS = {"1m": 21, "3m": 63, "12m": 252}
HORIZONS = (5, 10, 20)


def evaluate(ticker: str, start: str, end: str) -> dict:
    close = _load_close(DB_PATH, ticker).loc[start:end]

    results: dict[str, dict] = {}
    for lb_label, lb_days in LOOKBACKS.items():
        trailing_return = close.pct_change(lb_days)
        results[lb_label] = {}
        for h in HORIZONS:
            forward_return = close.pct_change(h).shift(-h)
            lagged = trailing_return.shift(1)  # causal: use trailing return known as of yesterday

            valid = forward_return.notna() & lagged.notna()
            n = int(valid.sum())
            if n < 60:
                results[lb_label][str(h)] = {"status": "insufficient_data", "n": n}
                continue

            y = forward_return[valid].to_numpy(dtype=float)
            x = lagged[valid].to_numpy(dtype=float)
            fit = _hac_ols_slope_tstat(x, y, lag=h - 1)
            results[lb_label][str(h)] = fit

    return {"ticker": ticker, "window": {"start": start, "end": end}, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end)
    for lb_label, horizons in payload["results"].items():
        for h, res in horizons.items():
            if res.get("status") == "insufficient_data":
                print(f"lookback={lb_label} h={h}: insufficient data (n={res['n']})")
                continue
            print(
                f"lookback={lb_label} h={h}: n={res['n']} slope={res['slope']:+.4f} "
                f"t={res['t_stat']:+.2f} p={res['p_value']:.3f}"
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
