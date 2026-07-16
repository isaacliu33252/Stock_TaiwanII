#!/usr/bin/env python3
"""Prepare a reusable 2011-2014 proxy price/chip-feature dataset for GroupA+.

stock_data.db's `ohlcv` table has a real four-year hole for 0050.TW:
2010-12-30 -> 2015-01-05 has zero rows (00631L.TW/00632R.TW never existed
before 2015 anyway). `external_market_ohlcv`'s ^TWII similarly only started
2014-01-02, and the old TWII proxy parquet cache
(FinRL/data/portfolio_cache/TWII_20030101_20110101_1d_market_v2.parquet, used
by scripts/misc/prepare_2008_twii_proxy_data_20260705.py) stops 2010-12-31.
So 2011-2014 -- including the real August-October 2011 European sovereign
debt crisis TAIEX selloff -- had no usable data locally at all.

This script:
1. Fetches real ^TWII daily closes via yfinance (scripts/fetch already do
   this pattern for other tickers; see ncf_external_cache.fetch_yf_close_cached)
   for 2008-06-02..2014-12-31, caching into external_market_ohlcv the same
   way every other external ticker in this repo is cached. Verified
   continuous with zero remaining gaps against the DB's existing
   2014-01-02+ ^TWII rows (identical yfinance source, values match at the
   overlap).
2. Converts that real index history into the same leveraged-ETF-equivalent
   proxy price series used for the 2008 fold (0050=1x, 00631L=2x,
   00632R=-1x, 00679B.TWO=0.45x), reusing twii_proxy_utils' proxy-construction
   functions directly (only the close-price path is used; volume/intraday
   synthesis inputs are zero-filled since this research never reads them).
3. Builds a matching chip_features frame the same way the 2008 prep script
   does (real market_margin_data from 2007+, everything else zero-filled).

This is a second, independent real-crisis sample (2011) alongside the 2008
one -- exists specifically to check whether the 2008 fold's GARCH-selector
result (24/24 grid variants beating ma20 OOS,
see project_garch_specialist_routing_2008_20260705 memory) replicates on a
different real crash, or was a one-off. Research-only; does not touch any
production file. Writing the fetched ^TWII rows to external_market_ohlcv IS
a real (small, reversible, well-precedented) DB write -- same table/provider
used for every other external ticker already cached in this repo.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _resolve
from ncf_external_cache import fetch_yf_close_cached
from twii_proxy_utils import _GROUP_B_TWII_PROXY_PARAMS, _build_group_b_single_proxy, build_twii_proxy_ohlcv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_START = "2008-06-02"
DEFAULT_END = "2014-12-31"
TWII_FETCH_PURPOSE = "2011_2014_gap_fill_research"


def _build_market_frame(twii_close: pd.Series) -> pd.DataFrame:
    twii_close = twii_close.sort_index()
    returns = twii_close.pct_change().fillna(0.0)
    return pd.DataFrame(
        {
            "date": twii_close.index,
            "twse_index_return_raw": returns.to_numpy(),
            # Not needed for the close-price proxy path (only used by
            # twii_proxy_utils for synthetic volume/intraday-range cosmetics,
            # which this research never reads); zero-filled rather than
            # estimated to avoid inventing a volume signal that doesn't exist.
            "twse_index_volume_change_raw": 0.0,
            "market_volatility_raw": 0.0,
        }
    )


def build_2011_2014_proxy_prices(start: str, end: str, db_path: Path) -> pd.DataFrame:
    twii_close = fetch_yf_close_cached("^TWII", start, end, db_path, purpose=TWII_FETCH_PURPOSE)
    if twii_close.empty:
        raise RuntimeError(f"No ^TWII data available for {start}..{end}")
    market = _build_market_frame(twii_close)

    proxies = {
        "0050.TW": build_twii_proxy_ohlcv(market, ticker="0050.TW", leverage=1.0, inverse=False),
        "00631L.TW": build_twii_proxy_ohlcv(market, ticker="00631L.TW", leverage=2.0, inverse=False),
        "00632R.TW": build_twii_proxy_ohlcv(market, ticker="00632R.TW", leverage=1.0, inverse=True),
        "00679B.TWO": _build_group_b_single_proxy(
            market,
            "00679B.TWO",
            vol_scale=_GROUP_B_TWII_PROXY_PARAMS["00679B.TWO"]["vol_scale"],
        ),
    }
    prices = pd.DataFrame({ticker: df.set_index("date")["close"] for ticker, df in proxies.items()})
    prices.index = pd.to_datetime(prices.index)
    return prices.sort_index().dropna()


def _max_drawdown(close: pd.Series) -> float:
    running_max = close.cummax()
    return float((close / running_max - 1.0).min())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--crisis-start", default="2011-07-01", help="Window used only for the crash sanity-check print.")
    parser.add_argument("--crisis-end", default="2011-12-31", help="Window used only for the crash sanity-check print.")
    parser.add_argument("--output-prefix", default="results/twii_proxy_2011_2014_prepared_20260705")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    prices = build_2011_2014_proxy_prices(args.start, args.end, db_path)
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
    crisis = prices.loc[args.crisis_start:args.crisis_end]
    manifest = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": (
            "reusable 2011-2014 proxy dataset for GroupA+ regime/GARCH research -- "
            "second independent real-crisis sample alongside the 2008 fold, not production data"
        ),
        "source": {
            "index": "^TWII (real TAIEX daily returns, fetched live via yfinance this session)",
            "fetch_purpose_tag": TWII_FETCH_PURPOSE,
            "cached_table": "external_market_ohlcv (provider='yfinance', ticker='^TWII')",
            "note": (
                "Extends the DB's existing ^TWII coverage (previously 2014-01-02 onward) "
                "backward; verified continuous (no remaining gaps) and consistent with the "
                "existing 2014-01-02+ rows at the overlap (same yfinance source)."
            ),
        },
        "proxy_method": {
            "0050.TW": "1x TWII daily returns",
            "00631L.TW": "2x TWII daily returns",
            "00632R.TW": "-1x TWII daily returns (inverse)",
            "00679B.TWO": "0.45x TWII daily returns, vol_scale=0.70 (same params as the 2008 fold and Group B TWII proxy)",
        },
        "chip_features_note": (
            "Built via the real backtest_group_a_plus_switch_policy._load_chip_features "
            "against stock_data.db. market_margin_data has real coverage back to "
            "2007-07-02, so market_margin_balance_chg_5d carries a real signal here too. "
            "All other chip/derivative columns are zero-filled (source tables start 2020+)."
        ),
        "nonzero_chip_feature_columns": nonzero_chip_cols,
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "crash_sanity_check": {
            "window": [args.crisis_start, args.crisis_end],
            "note": "2011-07~2011-12 European sovereign debt crisis TAIEX selloff (real event, not synthetic)",
            "rows": int(len(crisis)),
            "max_drawdown_by_ticker": (
                {ticker: round(_max_drawdown(crisis[ticker]), 4) for ticker in prices.columns} if not crisis.empty else {}
            ),
            "total_return_by_ticker": (
                {
                    ticker: round(float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0), 4)
                    for ticker in prices.columns
                }
                if len(crisis) > 1
                else {}
            ),
        },
        "limitations": [
            "0050.TW/00631L.TW/00632R.TW/00679B.TWO 2011-2014 prices are synthesized from real TWII "
            "index returns via fixed leverage/inverse/vol_scale assumptions, not true ETF histories "
            "(00631L/00632R did not exist as listed products until 2015; 0050 real prices exist for "
            "2009-2010 and 2015+ but not for this gap window, so this proxy segment is standalone, "
            "not spliced to the real 0050 series on either side).",
            "Suitable for stress-testing current GroupA+ rule/regime logic reactions to a real crash "
            "shape, not for exact historical P&L claims.",
            "Chip/derivative features are almost entirely zero for 2011-2014 (only market_margin_data "
            "is real); any GroupA+ logic requiring chip_score/derivative_score/total_risk_score to fire "
            "will behave differently than it would with real chip data from that era.",
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
    print(f"Crash sanity check ({args.crisis_start}..{args.crisis_end}, {len(crisis)} rows):")
    for ticker in prices.columns:
        if crisis.empty:
            break
        dd = _max_drawdown(crisis[ticker])
        ret = float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0)
        print(f"  {ticker}: max_drawdown={dd:.2%}, period_return={ret:.2%}")


if __name__ == "__main__":
    main()
