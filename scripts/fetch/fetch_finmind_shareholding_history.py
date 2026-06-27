#!/usr/bin/env python3
"""Fetch FinMind TaiwanStockHoldingSharesPer history into the local DuckDB."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import parse_shareholding_distribution_rows, upsert_shareholding_distribution


API_URL = "https://api.finmindtrade.com/api/v4/data"
DEFAULT_TICKERS = "0050,00631L,00632R"


def fetch_finmind_history(tickers: list[str], start_date: str, end_date: str, token: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    headers = {"Authorization": f"Bearer {token}"}
    for ticker in tickers:
        response = requests.get(
            API_URL,
            headers=headers,
            params={
                "dataset": "TaiwanStockHoldingSharesPer",
                "data_id": ticker,
                "start_date": start_date,
                "end_date": end_date,
            },
            timeout=60,
        )
        payload = response.json()
        if response.status_code != 200:
            raise RuntimeError(f"FinMind {ticker}: HTTP {response.status_code}: {payload.get('msg', payload)}")
        frame = parse_shareholding_distribution_rows(payload, source="finmind_v4")
        if frame.empty:
            print(f"[FinMind] WARN {ticker}: no rows")
        else:
            frames.append(frame)
            print(f"[FinMind] {ticker}: {len(frame)} rows, {frame['dt'].min()} ~ {frame['dt'].max()}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=DEFAULT_TICKERS, help="Comma-separated stock IDs")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    token = os.environ.get("FINMIND_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set FINMIND_API_TOKEN to a FinMind backer/sponsor API token")
    tickers = [item.strip().upper() for item in args.tickers.split(",") if item.strip()]
    rows = fetch_finmind_history(tickers, args.start, args.end, token)
    if rows.empty:
        raise SystemExit("No FinMind rows fetched")
    written = upsert_shareholding_distribution(rows)
    print(
        f"[FinMind] rows_written={written}, stocks={rows['stock_id'].nunique()}, "
        f"dates={rows['dt'].nunique()}, range={rows['dt'].min()} ~ {rows['dt'].max()}"
    )


if __name__ == "__main__":
    main()
