"""Date resolution helpers for the 2330.TW NCF workflow."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def resolve_end_date(db_path: Path, ticker: str, requested_end: str) -> str:
    """Resolve 'latest' to the newest valid OHLCV date for 2330.TW.

    2330.TW OHLCV lives in `external_market_ohlcv` with provider `yfinance`.
    The volume guard avoids phantom zero-volume rows becoming "latest".
    """
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute(
            "SELECT MAX(dt) FROM external_market_ohlcv WHERE provider='yfinance' AND ticker = ? AND volume > 0",
            [ticker],
        ).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")
