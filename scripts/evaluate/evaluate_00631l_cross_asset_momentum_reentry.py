#!/usr/bin/env python3
"""Does short-term momentum recovery in 0050/2330/SOXX lead 00631L's own
subsequent return -- the premise behind a proposed re-entry accelerator?

Research-only, 2026-07-12. User's proposal: after de-risking 00631L, use
short-term momentum repair in 0050 (the underlying index), 2330.TW (TSMC,
~55-58% of 0050 by weight), and SOXX (US semiconductor sector proxy, already
used as a leading diagnostic in ncf_2330_checklist's global_semiconductor
layer) as the trigger to stage 00631L back in (0% -> 10% -> 20%), motivated
by time-series momentum literature (Hurst/Ooi/Pedersen 2017) and dynamic
multi-speed momentum models.

Distinct from the already-tested a2124 rebound-recapture overlay
(GROUP_A_PLUS_OPS_FIXES_AND_REENTRY_ACCELERATOR_HANDOFF_20260710.md /
project_a2124_rebound_recapture_20260710.md): a2124's trigger is 0050's OWN
single-day shock+rebound event detection (tail_risk_score + return
thresholds), never used 2330/SOXX, and boosts for a single day rather than
staging a persistent ladder. This script tests the cross-asset momentum
premise directly (does 0050/2330/SOXX short-term momentum lead 00631L's
subsequent return) before building any staged re-entry mechanism -- same
"test the mechanism cheaply before building trading-curve machinery"
discipline used for every other paper/idea this session.

2330.TW and SOXX daily prices come from external_market_ohlcv (provider=
yfinance), not the main ohlcv table (which only covers the Group A+ ETF
universe) -- confirmed present 2014-01-02 onward for both.

Method: same Newey-West/Bartlett-HAC regression used throughout this
session. Predictor: trailing 5-day return of 0050/2330/SOXX individually,
plus their simple average ("combined momentum"). Target: 00631L's forward
h-day return (h=5/10/20).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_downside_vol_return_timing import _hac_ols_slope_tstat, _load_close

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_cross_asset_momentum_reentry_latest.json"
MOMENTUM_LOOKBACK = 5
HORIZONS = (5, 10, 20)


def _load_external_close(ticker: str) -> pd.Series:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM external_market_ohlcv WHERE ticker = ? AND provider = 'yfinance' ORDER BY dt",
            [ticker],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float)


def evaluate(start: str, end: str) -> dict:
    close_00631l = _load_close(DB_PATH, "00631L.TW").loc[start:end]
    close_0050 = _load_close(DB_PATH, "0050.TW")
    close_2330 = _load_external_close("2330.TW")
    close_soxx = _load_external_close("SOXX")

    mom_0050 = close_0050.pct_change(MOMENTUM_LOOKBACK)
    mom_2330 = close_2330.pct_change(MOMENTUM_LOOKBACK)
    mom_soxx = close_soxx.pct_change(MOMENTUM_LOOKBACK)

    idx = close_00631l.index
    frame = pd.DataFrame(index=idx)
    frame["mom_0050"] = mom_0050.reindex(idx)
    frame["mom_2330"] = mom_2330.reindex(idx)
    frame["mom_soxx"] = mom_soxx.reindex(idx)
    frame["mom_combined"] = frame[["mom_0050", "mom_2330", "mom_soxx"]].mean(axis=1, skipna=False)

    results: dict[str, dict] = {}
    for signal_name in ("mom_0050", "mom_2330", "mom_soxx", "mom_combined"):
        results[signal_name] = {}
        lagged = frame[signal_name].shift(1)
        for h in HORIZONS:
            forward_return = close_00631l.pct_change(h).shift(-h)
            valid = forward_return.notna() & lagged.notna()
            n = int(valid.sum())
            if n < 60:
                results[signal_name][str(h)] = {"status": "insufficient_data", "n": n}
                continue
            y = forward_return[valid].to_numpy(dtype=float)
            x = lagged[valid].to_numpy(dtype=float)
            fit = _hac_ols_slope_tstat(x, y, lag=h - 1)
            results[signal_name][str(h)] = fit

    return {"window": {"start": start, "end": end}, "momentum_lookback_days": MOMENTUM_LOOKBACK, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.start, args.end)
    for signal_name, horizons in payload["results"].items():
        for h, res in horizons.items():
            if res.get("status") == "insufficient_data":
                print(f"{signal_name} h={h}: insufficient data (n={res['n']})")
                continue
            print(f"{signal_name} h={h}: n={res['n']} slope={res['slope']:+.4f} t={res['t_stat']:+.2f} p={res['p_value']:.3f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
