#!/usr/bin/env python3
"""Archive 30-minute intraday OHLCV bars for the RF_0050/RF_00631L/RF_00713
morning-to-last-hour research line (2026-09-09, arXiv:2608.29025-inspired).

yfinance's free intraday API only serves ~60 calendar days of 30-minute
history -- a hard external limit, not something this script can extend.
This script exists so history can start accumulating in the DB from today
forward instead of being re-fetched (and silently losing everything older
than 60 days) on every ad-hoc research run. Safe to run daily: upserts on
(ticker, dt, bar_start), so re-running never duplicates rows.

Table: ohlcv_intraday_30m (ticker, dt, bar_start [Asia/Taipei local time of
the bar], open, high, low, close, volume, source_file, updated_at).

Read-only w.r.t. production: this table is not read by any existing
production pipeline. It only feeds the RF_* research scripts.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_TICKERS = ["0050.TW", "00631L.TW", "00713.TW"]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ohlcv_intraday_30m (
    ticker VARCHAR NOT NULL,
    dt DATE NOT NULL,
    bar_start TIMESTAMP NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume BIGINT NOT NULL,
    source_file VARCHAR NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt, bar_start)
)
"""


def fetch_ticker(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="60d", interval="30m", progress=False)
    if df.empty:
        return df
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = df.index.tz_convert("Asia/Taipei")
    df = df.reset_index().rename(
        columns={"Datetime": "bar_start", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )
    df["bar_start"] = df["bar_start"].dt.tz_localize(None)
    df["dt"] = df["bar_start"].dt.date
    df["ticker"] = ticker
    df["source_file"] = f"yfinance_30m_{date.today().isoformat()}"
    return df[["ticker", "dt", "bar_start", "open", "high", "low", "close", "volume", "source_file"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    con = duckdb.connect(args.db)
    con.execute(CREATE_TABLE_SQL)

    total_upserted = 0
    for ticker in args.tickers:
        print(f"Fetching {ticker} 30-minute bars...")
        df = fetch_ticker(ticker)
        if df.empty:
            print(f"  no data returned for {ticker}")
            continue
        con.register("new_rows", df)
        min_bar, max_bar = df["bar_start"].min(), df["bar_start"].max()
        con.execute(
            "DELETE FROM ohlcv_intraday_30m WHERE ticker = ? AND bar_start BETWEEN ? AND ?",
            [ticker, min_bar, max_bar],
        )
        con.execute(
            """
            INSERT INTO ohlcv_intraday_30m (ticker, dt, bar_start, open, high, low, close, volume, source_file)
            SELECT ticker, dt, bar_start, open, high, low, close, volume, source_file FROM new_rows
            """
        )
        con.unregister("new_rows")
        count = con.execute(
            "SELECT COUNT(*) FROM ohlcv_intraday_30m WHERE ticker = ?", [ticker]
        ).fetchone()[0]
        date_range = con.execute(
            "SELECT MIN(dt), MAX(dt) FROM ohlcv_intraday_30m WHERE ticker = ?", [ticker]
        ).fetchone()
        print(f"  {ticker}: {len(df)} bars fetched, {count} total rows stored, range {date_range[0]}..{date_range[1]}")
        total_upserted += len(df)

    con.close()
    print(f"\nDone. {total_upserted} bars processed across {len(args.tickers)} ticker(s).")


if __name__ == "__main__":
    main()
