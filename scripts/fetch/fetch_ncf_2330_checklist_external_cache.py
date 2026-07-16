#!/usr/bin/env python3
"""Refresh yfinance cache rows used by the ncf_2330 checklist.

This only writes to `external_market_ohlcv` / `external_data_version` through
the existing ncf_external_cache helper. It does not change model outputs or
portfolio weights.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / f"ncf_2330_checklist_external_cache_{date.today().strftime('%Y%m%d')}.json"

DEFAULT_TICKERS = {
    "NVDA": "global_semiconductor",
    "AMD": "global_semiconductor",
    "ASML": "global_semiconductor",
    "DX-Y.NYB": "dxy",
}


def refresh_checklist_external_cache(
    *,
    db_path: Path = DEFAULT_DB,
    start: str,
    end: str,
    allow_download: bool,
    tickers: dict[str, str] | None = None,
) -> dict:
    tickers = tickers or DEFAULT_TICKERS
    results = {}
    for ticker, layer in tickers.items():
        close = fetch_yf_close_cached(
            ticker,
            start,
            end,
            db_path,
            purpose=f"ncf_2330_checklist_{layer}",
            allow_download=allow_download,
        )
        valid = close.dropna()
        results[ticker] = {
            "layer": layer,
            "rows": int(len(valid)),
            "first_date": str(valid.index.min().date()) if not valid.empty else None,
            "last_date": str(valid.index.max().date()) if not valid.empty else None,
            "status": "available" if not valid.empty else "missing",
            "allow_download": allow_download,
        }
    return {
        "schema_version": 1,
        "report": "ncf_2330_checklist_external_cache",
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
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = refresh_checklist_external_cache(
        db_path=args.db_path,
        start=args.start,
        end=args.end,
        allow_download=args.allow_download,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {args.output}")
    for ticker, info in report["tickers"].items():
        print(f"{ticker}: {info['status']} rows={info['rows']} last={info['last_date']}")


if __name__ == "__main__":
    main()
