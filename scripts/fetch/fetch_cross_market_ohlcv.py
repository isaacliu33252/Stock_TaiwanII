#!/usr/bin/env python3
"""Refresh the small set of yfinance closes backing the 00631L crash-risk
alert's cross_market_shock family: VIX, SOXX, QQQ, TWII, TSM ADR, USD/TWD,
plus S&P500/Nasdaq/10Y yield/13-week bill/gold.

Unlike scripts/fetch/fetch_ncf_2330_checklist_external_cache.py, this always
attempts a live download (not gated behind --refresh-external-cache /
NCF_EXTERNAL_ALLOW_DOWNLOAD). These are lightweight daily closes, and
build_00631l_crash_risk_alert.py's freshness check needs them to actually
update every day the pipeline runs, or the cross_market_shock family will be
reported degraded indefinitely.

2026-08-04: added ^GSPC/^IXIC/^TNX/^IRX/GC=F. These five were only refreshed
as a side effect of the flag-gated NCF model steps (NCF_EXTERNAL_ALLOW_DOWNLOAD)
and had silently drifted 6-8 calendar days stale (check_ohlcv_freshness.py's
external_error_tickers) despite --refresh-external-cache running daily --
the other six tickers stayed fresh precisely because this script fetches them
unconditionally. See
[[project_external_cross_market_ticker_staleness_fix_20260804]].

This only writes to `external_market_ohlcv` through the existing
ncf_external_cache helper. It does not change model outputs or portfolio
weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ncf_external_cache import fetch_yf_close_cached

DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / f"cross_market_ohlcv_{date.today().strftime('%Y%m%d')}.json"

DEFAULT_TICKERS = [
    "^VIX",
    "SOXX",
    "QQQ",
    "^TWII",
    "TSM",
    "TWD=X",
    "^GSPC",
    "^IXIC",
    "^TNX",
    "^IRX",
    "GC=F",
    # 2026-08-07: found stuck at 2026-07-31 (7 days stale) by
    # check_ohlcv_freshness.py's external_market_ohlcv check. Same bug class
    # as the 2026-08-04 fix for ^GSPC/^IXIC/^TNX/^IRX/GC=F above -- its only
    # write path was bundled inside an ncf_2330 pipeline step, which
    # `run_ncf_daily_pipeline.py --only-refresh` (the scheduled data-only
    # daily run) intentionally skips. Several downstream tools already
    # depend on this being fresh: group_a_plus/ncf_2330/dates.py's
    # resolve_end_date(), scripts/evaluate/letf_close_auction_overshoot_reversal_test.py,
    # and scripts/evaluate/build_market_aligned_sentiment_shadow.py's
    # 2330 price lookup (external_market_ohlcv override in that script's
    # _price_table()).
    "2330.TW",
    # 2026-08-09: found stuck at 2026-07-15 (found while building
    # group_a_plus/integrations/tsmc_concentration_divergence.py's top-5
    # breadth proxy) -- same bug class as above. These 4 were populated
    # once by an unrelated research backtest (evaluate_stockmixer_atfnet_shadow.py
    # / evaluate_cross_market_directed_graph_shadow.py) into `ohlcv`, then
    # never refreshed again. Written here into external_market_ohlcv
    # (not ohlcv) via this script's existing fetch_yf_close_cached() path --
    # tsmc_concentration_divergence.py reads all 5 top-5-proxy tickers from
    # external_market_ohlcv now, matching 2330.TW's existing source. The
    # stale historical rows in `ohlcv` for these 4 tickers are left alone
    # (not deleted) but are no longer read by that module.
    "2317.TW",
    "2454.TW",
    "2308.TW",
    "2382.TW",
    # 2026-08-16: found stale during the 2607.09537 (GatedLinear) review
    # session -- these 11 were only ever fetched manually (never through
    # this schedule), so they drift stale between manual backfills. User
    # confirmed adding them to the daily schedule.
    "AMD",
    "ASML",
    "AVGO",
    "DX-Y.NYB",
    "EWT",
    "HYG",
    "NVDA",
    "SHY",
    "^HSI",
    "^KS11",
    "^N225",
]


def refresh_cross_market_ohlcv(
    *,
    db_path: Path = DEFAULT_DB,
    start: str,
    end: str,
    tickers: list[str] | None = None,
) -> dict:
    tickers = tickers or DEFAULT_TICKERS
    results = {}
    for ticker in tickers:
        close = fetch_yf_close_cached(
            ticker,
            start,
            end,
            db_path,
            purpose="00631l_crash_risk_cross_market_shock",
            allow_download=True,
        )
        valid = close.dropna()
        results[ticker] = {
            "rows": int(len(valid)),
            "first_date": str(valid.index.min().date()) if not valid.empty else None,
            "last_date": str(valid.index.max().date()) if not valid.empty else None,
            "status": "available" if not valid.empty else "missing",
        }
    return {
        "schema_version": 1,
        "report": "cross_market_ohlcv_refresh",
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "tickers": results,
    }


def main() -> None:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start", default=(today - timedelta(days=365 * 3)).isoformat())
    parser.add_argument("--end", default=(today + timedelta(days=1)).isoformat())
    parser.add_argument(
        "--tickers",
        default=",".join(DEFAULT_TICKERS),
        help="Comma-separated yfinance tickers to refresh.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    tickers = [item.strip() for item in args.tickers.split(",") if item.strip()]
    report = refresh_cross_market_ohlcv(db_path=args.db_path, start=args.start, end=args.end, tickers=tickers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
