#!/usr/bin/env python3
"""Prepare a reusable 2015 China-crash price/chip-feature dataset for GroupA+.

Unlike the 2008 and 2011-2014 folds (which need a synthetic TWII proxy because
0050.TW/00631L.TW/00632R.TW have no real OHLCV that far back), this fold needs
NO synthetic price data at all: stock_data.db has continuous real OHLCV for
0050.TW/00631L.TW/00632R.TW starting 2015-01-05 (00631L/00632R's real listing
date), covering both the June-September 2015 Shanghai/Shenzhen crash + August
11 RMB devaluation selloff and the January 2016 circuit-breaker crash that
followed it.

00679B.TWO (the fourth GroupA+ ticker) only has real prices from 2020-01-02
onward. Following the same precedent as
`scripts/misc/garch_specialist_routing_2020_fold_20260705.py`
(`_load_real_prices_with_00679b_backfill`), it is back-filled flat at its
first real price for this window; its weight in both golden1 and defensive
books is small, so a flat pre-2020 proxy price has negligible effect.

chip_features is built the same way every other crisis-fold prep script in
this repo builds it: via the real `backtest_group_a_plus_switch_policy.
_load_chip_features` against stock_data.db. Confirmed 2026-07-06:
institutional_data/margin_data only start 2020-01-02 (same as the 2020
fold), NOT 2015 -- they are zero-filled here, same limitation as the
2008/2011 folds. `shareholding_distribution` (backs tdcc_0050_minority_chg_1w
/tdcc_0050_major_chg_1w) has real coverage from 2015-04-30 onward, and
market_margin_data from 2007-07-02, so this fold's chip signal is a little
less thin than 2008/2011 (real TDCC data, in addition to market_margin), but
still far thinner than 2020+/2025+ folds. All other optional chip/derivative
tables only start 2020+ or 2025+ and are zero-filled by `_load_chip_features`
itself.

Research-only; does not touch any production file, model weight, or the DB
(read-only against stock_data.db).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _resolve

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_START = "2015-01-05"
DEFAULT_END = "2016-12-31"


def _load_real_prices_with_00679b_backfill(db_path: Path, start: str, end: str) -> pd.DataFrame:
    tickers = list(TICKERS)
    core_tickers = [t for t in tickers if t != "00679B.TWO"]
    placeholders = ", ".join(["?"] * len(core_tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*core_tickers, start, end],
        ).fetchdf()
        first_00679b = con.execute(
            "SELECT close FROM ohlcv WHERE ticker = '00679B.TWO' ORDER BY dt ASC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {core_tickers} between {start} and {end}")
    if first_00679b is None:
        raise RuntimeError("No 00679B.TWO OHLCV rows found in the DB at all")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    # 00679B.TWO has no real price at all until 2020-01-02, entirely after
    # this fold's window ends, so there is nothing in-range to bfill from.
    # Flat-fill the whole window at its first-ever real close instead (same
    # negligible-weight rationale as the 2020 GARCH fold script's bfill).
    prices["00679B.TWO"] = float(first_00679b[0])
    return prices.dropna(subset=tickers)


def _max_drawdown(close: pd.Series) -> float:
    running_max = close.cummax()
    return float((close / running_max - 1.0).min())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--crisis-start",
        default="2015-06-01",
        help="Window used only for the crash sanity-check print (main 2015 China A-share crash + Aug 11 RMB devaluation selloff).",
    )
    parser.add_argument("--crisis-end", default="2015-09-30")
    parser.add_argument(
        "--bonus-crisis-start",
        default="2016-01-01",
        help="Adjacent January 2016 circuit-breaker crash, same real-data window, printed separately.",
    )
    parser.add_argument("--bonus-crisis-end", default="2016-01-31")
    parser.add_argument("--output-prefix", default="results/real_2015_china_crash_prepared_20260706")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    prices = _load_real_prices_with_00679b_backfill(db_path, args.start, args.end)
    chip_features = _load_chip_features(db_path, prices.index, args.start, args.end)

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prices_path = prefix.with_name(prefix.name + "_prices.csv")
    chip_path = prefix.with_name(prefix.name + "_chip_features.csv")
    manifest_path = prefix.with_name(prefix.name + "_manifest.json")

    prices.to_csv(prices_path, encoding="utf-8-sig")
    chip_features.to_csv(chip_path, encoding="utf-8-sig")

    nonzero_chip_cols = [col for col in chip_features.columns if float(chip_features[col].abs().sum()) > 0.0]

    def _crash_summary(start: str, end: str) -> dict:
        crisis = prices.loc[start:end]
        if crisis.empty or len(crisis) < 2:
            return {"window": [start, end], "rows": int(len(crisis))}
        return {
            "window": [start, end],
            "rows": int(len(crisis)),
            "max_drawdown_by_ticker": {ticker: round(_max_drawdown(crisis[ticker]), 4) for ticker in prices.columns},
            "total_return_by_ticker": {
                ticker: round(float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0), 4)
                for ticker in prices.columns
            },
        }

    manifest = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": (
            "reusable 2015 China-crash proxy dataset for GroupA+ regime/specialist-routing "
            "research -- fourth independent real-crisis sample alongside the 2008/2011/2020 "
            "folds, not production data"
        ),
        "source": {
            "prices": "real ohlcv table in stock_data.db (0050.TW/00631L.TW/00632R.TW; 00679B.TWO back-filled flat from its first real 2020-01-02 price)",
            "chip_features": "real backtest_group_a_plus_switch_policy._load_chip_features against stock_data.db",
        },
        "nonzero_chip_feature_columns": nonzero_chip_cols,
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "crash_sanity_check": _crash_summary(args.crisis_start, args.crisis_end),
        "bonus_crash_sanity_check": {
            "note": "January 2016 A-share circuit-breaker crash, same real-data window, printed separately from the primary 2015 crisis window",
            **_crash_summary(args.bonus_crisis_start, args.bonus_crisis_end),
        },
        "limitations": [
            "00679B.TWO has no real price before 2020-01-02; it is back-filled flat at its first "
            "real price for this entire window. Its allocation weight in both golden1 and "
            "defensive books is small, so this is a negligible, not load-bearing, approximation "
            "(same precedent as the 2020 GARCH fold script).",
            "Chip/derivative features beyond institutional_data/margin_data are mostly zero for "
            "2015-2016 (most other optional tables only start 2020+ or 2025+); any GroupA+ logic "
            "requiring chip_score/derivative_score/total_risk_score to fire will behave "
            "differently than it would with the full real 2020+ chip data.",
        ],
        "outputs": {
            "prices_csv": str(prices_path.relative_to(PROJECT_ROOT)),
            "chip_features_csv": str(chip_path.relative_to(PROJECT_ROOT)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Prices: {prices_path} ({len(prices)} rows, {prices.index[0].date()}..{prices.index[-1].date()})")
    print(f"Chip features: {chip_path} (nonzero columns: {nonzero_chip_cols})")
    print(f"Manifest: {manifest_path}")
    print()
    print(f"Crash sanity check ({args.crisis_start}..{args.crisis_end}):")
    for ticker in prices.columns:
        crisis = prices.loc[args.crisis_start:args.crisis_end]
        if crisis.empty or len(crisis) < 2:
            break
        dd = _max_drawdown(crisis[ticker])
        ret = float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0)
        print(f"  {ticker}: max_drawdown={dd:.2%}, period_return={ret:.2%}")
    print()
    print(f"Bonus crash sanity check ({args.bonus_crisis_start}..{args.bonus_crisis_end}):")
    for ticker in prices.columns:
        crisis = prices.loc[args.bonus_crisis_start:args.bonus_crisis_end]
        if crisis.empty or len(crisis) < 2:
            break
        dd = _max_drawdown(crisis[ticker])
        ret = float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0)
        print(f"  {ticker}: max_drawdown={dd:.2%}, period_return={ret:.2%}")


if __name__ == "__main__":
    main()
