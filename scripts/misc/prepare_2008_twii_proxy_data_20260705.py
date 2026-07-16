#!/usr/bin/env python3
"""Prepare a reusable 2008-crisis proxy price/chip-feature dataset for GroupA+.

Real 0050.TW/00631L.TW OHLCV in stock_data.db only starts 2009-01-02/2015-01-05
(see NCF_2330_FACTOR_QUALITY_00631L_TIER_HANDOFF_20260705.md), so there is no
true 2008 ETF history. This repo already has a real TAIEX (^TWII) index cache
covering 2003-01-02 .. 2010-12-31
(FinRL/data/portfolio_cache/TWII_20030101_20110101_1d_market_v2.parquet) --
genuine TAIEX daily returns, not synthetic data. This script converts that
real index history into leveraged-ETF-equivalent proxy price series
(0050=1x, 00631L=2x, 00632R=-1x, 00679B.TWO=0.45x low-correlation bond proxy,
matching twii_proxy_utils' existing Group A/B proxy conventions) into the same
wide "prices" DataFrame shape backtest_group_a_plus_switch_policy._load_prices
produces, plus a matching chip_features frame (real market_margin_data goes
back to 2007-07-02; every other chip/derivative source starts 2020+ and is
zero-filled by _load_chip_features itself -- same convention as every other
2008 proxy script in this repo).

Output is cached to results/ so downstream research scripts (e.g. extending
the GARCH-proxy walk-forward test with a real crash fold) can load it without
recomputing. Research-only; does not touch any production file or the DB.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _resolve
from twii_proxy_utils import (
    DEFAULT_TWII_MARKET_CACHE,
    _GROUP_B_TWII_PROXY_PARAMS,
    _build_group_b_single_proxy,
    build_twii_proxy_ohlcv,
    load_twii_market,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_START = "2003-01-02"
DEFAULT_END = "2010-12-31"


def build_2008_proxy_prices(start: str, end: str) -> pd.DataFrame:
    market = load_twii_market(start, end)
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
    prices = pd.DataFrame(
        {ticker: df.set_index("date")["close"] for ticker, df in proxies.items()}
    )
    prices.index = pd.to_datetime(prices.index)
    return prices.sort_index().dropna()


def _max_drawdown(close: pd.Series) -> float:
    running_max = close.cummax()
    return float((close / running_max - 1.0).min())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--crisis-start", default="2007-10-01", help="Window used only for the crash sanity-check print.")
    parser.add_argument("--crisis-end", default="2008-11-30", help="Window used only for the crash sanity-check print.")
    parser.add_argument("--output-prefix", default="results/twii_proxy_2008_prepared_20260705")
    args = parser.parse_args()

    prices = build_2008_proxy_prices(args.start, args.end)
    chip_features = _load_chip_features(_resolve(str(DB_PATH)), prices.index, args.start, args.end)

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prices_path = prefix.with_name(prefix.name + "_prices.csv")
    chip_path = prefix.with_name(prefix.name + "_chip_features.csv")
    manifest_path = prefix.with_name(prefix.name + "_manifest.json")

    prices.to_csv(prices_path, encoding="utf-8-sig")
    chip_features.to_csv(chip_path, encoding="utf-8-sig")

    nonzero_chip_cols = [
        col for col in chip_features.columns if float(chip_features[col].abs().sum()) > 0.0
    ]
    crisis = prices.loc[args.crisis_start:args.crisis_end]
    manifest = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "reusable 2008-crisis proxy dataset for GroupA+ regime/GARCH research (not production data)",
        "source": {
            "index": "^TWII (real TAIEX daily returns)",
            "cache_file": str(DEFAULT_TWII_MARKET_CACHE.relative_to(PROJECT_ROOT)),
            "cache_native_range": "2003-01-02 to 2010-12-31",
        },
        "proxy_method": {
            "0050.TW": "1x TWII daily returns",
            "00631L.TW": "2x TWII daily returns",
            "00632R.TW": "-1x TWII daily returns (inverse)",
            "00679B.TWO": "0.45x TWII daily returns, vol_scale=0.70 (low-correlation bond proxy, same params as Group B TWII proxy)",
        },
        "chip_features_note": (
            "Built via the real backtest_group_a_plus_switch_policy._load_chip_features "
            "against stock_data.db. market_margin_data has real coverage back to "
            "2007-07-02, so market_margin_balance_chg_5d carries a real 2008 signal. "
            "All other chip/derivative columns are zero-filled because their source "
            "tables only start 2020 or later -- same limitation as every other "
            "2008 proxy backtest in this repo."
        ),
        "nonzero_chip_feature_columns": nonzero_chip_cols,
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "crash_sanity_check": {
            "window": [args.crisis_start, args.crisis_end],
            "rows": int(len(crisis)),
            "max_drawdown_by_ticker": {
                ticker: round(_max_drawdown(crisis[ticker]), 4) for ticker in prices.columns
            } if not crisis.empty else {},
            "total_return_by_ticker": {
                ticker: round(float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0), 4)
                for ticker in prices.columns
            } if len(crisis) > 1 else {},
        },
        "limitations": [
            "0050.TW/00631L.TW/00632R.TW/00679B.TWO 2008 prices are synthesized from real TWII "
            "index returns via fixed leverage/inverse/vol_scale assumptions, not true ETF histories "
            "(00631L/00632R/00679B did not exist as listed products until well after 2008).",
            "Suitable for stress-testing current GroupA+ rule/regime logic reactions to a real crash "
            "shape, not for exact historical P&L claims.",
            "Chip/derivative features are almost entirely zero for 2008 (only market_margin_data is real); "
            "any GroupA+ logic that requires chip_score/derivative_score/total_risk_score to fire will "
            "behave differently than it would with real 2008 chip data.",
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
