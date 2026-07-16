#!/usr/bin/env python3
"""Refresh the small set of yfinance closes backing the 00631L crash-risk
alert's cross_market_shock family: VIX, SOXX, QQQ, TWII, TSM ADR, USD/TWD.

Unlike scripts/fetch/fetch_ncf_2330_checklist_external_cache.py, this always
attempts a live download (not gated behind --refresh-external-cache /
NCF_EXTERNAL_ALLOW_DOWNLOAD). These are 6 lightweight daily closes, and
build_00631l_crash_risk_alert.py's freshness check needs them to actually
update every day the pipeline runs, or the cross_market_shock family will be
reported degraded indefinitely.

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

DEFAULT_TICKERS = ["^VIX", "SOXX", "QQQ", "^TWII", "TSM", "TWD=X"]


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
