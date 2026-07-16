#!/usr/bin/env python3
"""Standalone test: does foreign TXO (TAIEX index options) net positioning
predict future 0050.TW / 00631L.TW returns?

Research-only, direction 3 of the good/bad-volatility follow-up session
(after direction 1 -- 0050-level chip flow as an A22 "confirms-immediately"
bypass trigger -- and direction 2 -- same bypass mechanism keyed on TSMC
foreign flow -- both came back net negative on the same 4 windows). Both of
those tests wired a chip signal into the A22 rule's persistence-bypass
mechanism, which itself may be the problem (three different trigger signals
all produced the same negative pattern). This script instead asks a simpler,
cleaner question with the same Newey-West/Bartlett-HAC regression test used
for the two prior downside/good-bad-volatility papers this session
(evaluate_downside_vol_return_timing.py, evaluate_realized_semivariance_
return_timing.py): does the raw signal -- foreign options positioning --
have any standalone return-predictive power at all, independent of how it
might later be wired into a trading rule.

Signal: txo_foreign_put_call_net_oi = foreign TXO put net OI - call net OI
(positive = foreign investors net long puts relative to calls, i.e.
positioned for downside) and its 5-day change, both already computed by
backtest_group_a_plus_switch_policy._load_chip_features.

HARD DATA CAVEAT: derivative_institutional_data only covers 2025-01-02
onward (~384 trading days as of 2026-07-09) -- there is no TXO institutional
positioning history for 2020 or 2022. This is roughly an order of magnitude
less history than the two prior tests in this session (which used 11-13
years of daily 0050/00631L data). A null result here is even less
informative than the already-underpowered downside-vol test; a "significant"
result should be treated with extra skepticism given the short window and
lack of any out-of-sample period to hold out.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "txo_foreign_positioning_return_timing_latest.json"
HORIZONS = (5, 10, 20)


def _load_txo_put_call_net_oi(db_path: Path) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, put_call, net_open_interest_balance_volume
            FROM derivative_institutional_data
            WHERE market = 'options' AND product_id = 'TXO' AND institutional_investors = '外資'
            ORDER BY dt
            """
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    pivot = rows.pivot_table(index="dt", columns="put_call", values="net_open_interest_balance_volume", aggfunc="sum")
    call_oi = pivot["買權"] if "買權" in pivot.columns else pd.Series(0.0, index=pivot.index)
    put_oi = pivot["賣權"] if "賣權" in pivot.columns else pd.Series(0.0, index=pivot.index)
    return (put_oi - call_oi).sort_index()


def evaluate(ticker: str) -> dict:
    close = _load_close(DB_PATH, ticker)
    put_call_net_oi = _load_txo_put_call_net_oi(DB_PATH)

    idx = close.index.intersection(put_call_net_oi.index)
    close = close.loc[idx].sort_index()
    level = put_call_net_oi.loc[idx].sort_index()
    chg_5d = level.diff(5)

    results: dict[str, dict] = {}
    for h in HORIZONS:
        forward_return = close.pct_change(h).shift(-h)
        lagged_level = level.shift(1)
        lagged_chg = chg_5d.shift(1)

        valid = forward_return.notna() & lagged_level.notna() & lagged_chg.notna()
        n = int(valid.sum())
        if n < 60:
            results[str(h)] = {"status": "insufficient_data", "n": n}
            continue

        y = forward_return[valid].to_numpy(dtype=float)
        x_level = lagged_level[valid].to_numpy(dtype=float)
        x_chg = lagged_chg[valid].to_numpy(dtype=float)

        level_fit = _hac_ols_slope_tstat(x_level, y, lag=h - 1)
        chg_fit = _hac_ols_slope_tstat(x_chg, y, lag=h - 1)
        results[str(h)] = {"n": n, "put_call_net_oi_level": level_fit, "put_call_net_oi_chg_5d": chg_fit}
    return {
        "ticker": ticker,
        "data_window": {"start": str(idx.min().date()) if len(idx) else None, "end": str(idx.max().date()) if len(idx) else None},
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker)
    print(f"data window: {payload['data_window']}")
    for h, res in payload["results"].items():
        if res.get("status") == "insufficient_data":
            print(f"h={h}: insufficient data (n={res['n']})")
            continue
        lvl = res["put_call_net_oi_level"]
        chg = res["put_call_net_oi_chg_5d"]
        print(
            f"h={h}: n={res['n']} | "
            f"level slope={lvl['slope']:+.6f} t={lvl['t_stat']:+.2f} p={lvl['p_value']:.3f} | "
            f"chg5d slope={chg['slope']:+.6f} t={chg['t_stat']:+.2f} p={chg['p_value']:.3f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
