"""Data freshness helpers for NCF daily JSON outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


def _max_date(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> str | None:
    try:
        value = con.execute(sql, params or []).fetchone()[0]
    except Exception:
        return None
    if value is None:
        return None
    return str(pd.Timestamp(value).date())


def _days_lag(reference_date: str | None, source_date: str | None) -> int | None:
    if not reference_date or not source_date:
        return None
    return int((pd.Timestamp(reference_date) - pd.Timestamp(source_date)).days)


def _external_market_ticker_dates(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    try:
        rows = con.execute(
            """
            SELECT ticker, MAX(dt) AS max_dt
            FROM external_market_ohlcv
            WHERE provider='yfinance'
            GROUP BY ticker
            ORDER BY ticker
            """
        ).fetchall()
    except Exception:
        return {}
    return {str(ticker): str(pd.Timestamp(max_dt).date()) for ticker, max_dt in rows if max_dt is not None}


def ncf_data_freshness(db_path: Path, ticker: str, last_close_date: str) -> dict[str, Any]:
    """Return source freshness metadata for an NCF signal.

    Dates are compared against the OHLCV close date actually used by the model,
    not wall-clock today. This avoids marking a signal stale when Yahoo has a
    partial latest row with NaN close that is intentionally ignored by DuckDB.
    """
    ticker_id = ticker.split(".")[0]
    with duckdb.connect(str(db_path), read_only=True) as con:
        external_market_dates = _external_market_ticker_dates(con)
        sources = {
            "ohlcv": _max_date(con, "SELECT MAX(dt) FROM ohlcv WHERE ticker=?", [ticker]),
            "institutional": _max_date(con, "SELECT MAX(dt) FROM institutional_data WHERE ticker=?", [ticker]),
            "margin": _max_date(con, "SELECT MAX(dt) FROM margin_data WHERE ticker=?", [ticker]),
            "market_margin": _max_date(con, "SELECT MAX(dt) FROM market_margin_data"),
            "taifex_futures": _max_date(
                con,
                "SELECT MAX(dt) FROM taifex_futures_daily WHERE contract='TX'",
            ),
            "taifex_institutional": _max_date(
                con,
                "SELECT MAX(dt) FROM taifex_futures_institutional WHERE contract_code IN ('臺股期貨', '台股期貨', 'TX')",
            ),
            "tdcc_shareholding": _max_date(
                con,
                "SELECT MAX(dt) FROM shareholding_distribution WHERE stock_id=?",
                [ticker_id],
            ),
            # Worst-case (earliest) "latest date" across all tracked external
            # tickers (^VIX, ^TWII, ^GSPC, ^IRX, ^TNX, GC=F, etc.) -- catches
            # any single straggling ticker rather than averaging it away.
            # Previously this table wasn't monitored at all: the daily
            # pipeline could silently run on stale VIX/US-market data with
            # `status: "ok"` (see [[project_group_a_plus_fable5_audit_20260702]] H1).
            "external_market_ohlcv": _max_date(
                con,
                """
                SELECT MIN(max_dt) FROM (
                    SELECT ticker, MAX(dt) AS max_dt
                    FROM external_market_ohlcv
                    WHERE provider='yfinance'
                    GROUP BY ticker
                )
                """,
            ),
        }

    lag_days = {name: _days_lag(last_close_date, date) for name, date in sources.items()}
    source_details = {
        "external_market_ohlcv": {
            "ticker_dates": external_market_dates,
            "ticker_lag_days_vs_reference": {
                ext_ticker: _days_lag(last_close_date, ext_date)
                for ext_ticker, ext_date in external_market_dates.items()
            },
        }
    }
    missing = [name for name, date in sources.items() if date is None]
    stale = [
        name
        for name, lag in lag_days.items()
        if lag is not None and lag > (14 if name == "tdcc_shareholding" else 3)
    ]
    ahead = [name for name, lag in lag_days.items() if lag is not None and lag < 0]
    status = "ok"
    if missing:
        status = "degraded_missing"
    elif stale:
        status = "degraded_stale"

    return {
        "reference_last_close_date": str(pd.Timestamp(last_close_date).date()),
        "sources": sources,
        "source_details": source_details,
        "lag_days_vs_reference": lag_days,
        "missing_sources": missing,
        "stale_sources": stale,
        "sources_ahead_of_ohlcv": ahead,
        "status": status,
    }
