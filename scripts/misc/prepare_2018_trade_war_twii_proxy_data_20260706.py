#!/usr/bin/env python3
"""Prepare a reusable 2018-trade-war proxy price/chip-feature dataset for GroupA+.

stock_data.db's `ohlcv` table has a real gap for 0050.TW/00631L.TW/00632R.TW:
2016-12-30 -> 2020-01-02 has zero rows (confirmed 2026-07-06: 2017-2019 have
0 rows for all three tickers, even though 2015-2016 and 2020+ are both fully
real). So the 2018 US-China trade-war escalation (tariff waves in
Mar/Jun/Sep/Dec 2018, worst drawdown in the October-December selloff) has no
usable real ETF history locally, the same problem the 2011-2014 fold hit.

Unlike the 2011-2014 fold, no new DB fetch is needed here: `external_market_
ohlcv` already has continuous real ^TWII daily closes covering 2008-06-02 ..
2026-07-01 (confirmed 2026-07-06, 4421 rows, no gaps in the 2016-2019
window) -- the 2011-2014 prep script's own yfinance fetch already back-filled
and cached this range in an earlier session. This script only reads that
existing cache via the same `fetch_yf_close_cached` helper (a cache hit, not
a new network fetch).

Converts that real index history into the same leveraged-ETF-equivalent
proxy price series used for the 2008/2011-2014 folds (0050=1x, 00631L=2x,
00632R=-1x, 00679B.TWO=0.45x), reusing twii_proxy_utils' proxy-construction
functions directly (only the close-price path is used, same convention as
every other proxy fold in this repo). Builds a matching chip_features frame
the same way (real market_margin_data from 2007+, everything else
zero-filled since those source tables only start 2020+/2025+).

This is a fifth independent real-crisis sample (2018) alongside the
2008/2011/2015/2020 folds -- a slower, tariff-driven grind rather than a
liquidity-crisis or V-shaped shock, useful for checking whether any
regime/specialist-routing rule that works on the crash-shaped folds also
holds up on a trade-policy-driven drawdown. Research-only; does not touch
any production file or change any DB row (the ^TWII cache read here is a
cache hit against data written by an earlier session, no new write).
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
DEFAULT_START = "2016-01-04"
DEFAULT_END = "2019-12-31"
TWII_FETCH_PURPOSE = "2018_trade_war_regime_research"


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


def build_2018_proxy_prices(start: str, end: str, db_path: Path) -> pd.DataFrame:
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
    parser.add_argument(
        "--crisis-start",
        default="2018-01-01",
        help="Window used only for the crash sanity-check print (full 2018 trade-war escalation: tariff waves plus the Oct-Dec selloff).",
    )
    parser.add_argument("--crisis-end", default="2018-12-31")
    parser.add_argument("--output-prefix", default="results/twii_proxy_2018_trade_war_prepared_20260706")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    prices = build_2018_proxy_prices(args.start, args.end, db_path)
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
            "reusable 2018-trade-war proxy dataset for GroupA+ regime/specialist-routing "
            "research -- fifth independent real-crisis sample alongside the 2008/2011/2015/2020 "
            "folds, not production data"
        ),
        "source": {
            "index": "^TWII (real TAIEX daily returns, read from existing external_market_ohlcv cache -- no new fetch)",
            "fetch_purpose_tag": TWII_FETCH_PURPOSE,
            "cached_table": "external_market_ohlcv (provider='yfinance', ticker='^TWII')",
            "note": "Confirmed 2026-07-06: cache already covers 2008-06-02..2026-07-01 continuously, so this read is a cache hit, not a new network fetch.",
        },
        "proxy_method": {
            "0050.TW": "1x TWII daily returns",
            "00631L.TW": "2x TWII daily returns",
            "00632R.TW": "-1x TWII daily returns (inverse)",
            "00679B.TWO": "0.45x TWII daily returns, vol_scale=0.70 (same params as the 2008/2011-2014 folds and Group B TWII proxy)",
        },
        "chip_features_note": (
            "Built via the real backtest_group_a_plus_switch_policy._load_chip_features "
            "against stock_data.db. market_margin_data has real coverage back to "
            "2007-07-02, so market_margin_balance_chg_5d carries a real signal here too. "
            "institutional_data/margin_data have real coverage from 2015-01-02 onward, so "
            "those columns are also real for this window. All other chip/derivative columns "
            "are zero-filled (source tables start 2020+/2025+)."
        ),
        "nonzero_chip_feature_columns": nonzero_chip_cols,
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "crash_sanity_check": {
            "window": [args.crisis_start, args.crisis_end],
            "note": "2018 US-China trade-war escalation (real event, not synthetic): tariff waves in Mar/Jun/Sep/Dec 2018, worst drawdown in the Oct-Dec 2018 selloff",
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
            "0050.TW/00631L.TW/00632R.TW/00679B.TWO 2016-2019 prices are synthesized from real TWII "
            "index returns via fixed leverage/inverse/vol_scale assumptions, not true ETF histories "
            "(real ETF OHLCV has a hard gap 2017-2019; 2015-2016 and 2020+ are real but this proxy "
            "segment is standalone, not spliced to either real segment).",
            "Suitable for stress-testing current GroupA+ rule/regime logic reactions to a real "
            "trade-policy-driven drawdown shape, not for exact historical P&L claims.",
            "Chip/derivative features beyond market_margin_data/institutional_data/margin_data are "
            "zero for 2016-2019 (most other optional tables only start 2020+ or 2025+); any GroupA+ "
            "logic requiring chip_score/derivative_score/total_risk_score to fire will behave "
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
    print(f"Crash sanity check ({args.crisis_start}..{args.crisis_end}, {len(crisis)} rows):")
    for ticker in prices.columns:
        if crisis.empty:
            break
        dd = _max_drawdown(crisis[ticker])
        ret = float(crisis[ticker].iloc[-1] / crisis[ticker].iloc[0] - 1.0)
        print(f"  {ticker}: max_drawdown={dd:.2%}, period_return={ret:.2%}")


if __name__ == "__main__":
    main()
