from __future__ import annotations

import importlib.metadata
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf


CREATE_EXTERNAL_MARKET_OHLCV_SQL = """
CREATE TABLE IF NOT EXISTS external_market_ohlcv (
    provider    TEXT NOT NULL DEFAULT 'yfinance',
    ticker      TEXT NOT NULL,
    dt          DATE NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    source      TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, ticker, dt)
);
"""

CREATE_EXTERNAL_DATA_VERSION_SQL = """
CREATE TABLE IF NOT EXISTS external_data_version (
    run_id            TEXT NOT NULL,
    provider          TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    start_dt          DATE,
    end_dt            DATE,
    row_count         BIGINT NOT NULL DEFAULT 0,
    yfinance_version  TEXT,
    fetched_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    purpose           TEXT NOT NULL DEFAULT 'ncf_external_features'
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_ext_market_ticker_dt ON external_market_ohlcv(provider, ticker, dt)",
    "CREATE INDEX IF NOT EXISTS idx_ext_market_dt ON external_market_ohlcv(dt)",
    "CREATE INDEX IF NOT EXISTS idx_ext_data_version_ticker ON external_data_version(provider, ticker, fetched_at)",
]


def ensure_external_cache_schema(db_path: Path) -> None:
    with duckdb.connect(str(db_path)) as con:
        con.execute(CREATE_EXTERNAL_MARKET_OHLCV_SQL)
        con.execute(CREATE_EXTERNAL_DATA_VERSION_SQL)
        for sql in INDEX_SQL:
            con.execute(sql)


def _read_cached_close(db_path: Path, ticker: str, start: str, end: str) -> pd.Series:
    ensure_external_cache_schema(db_path)
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute(
            """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider='yfinance'
              AND ticker=?
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    if df.empty:
        return pd.Series(dtype=float, name=ticker)
    out = df.set_index("dt")["close"]
    out.index = pd.to_datetime(out.index).normalize()
    return out[~out.index.duplicated()].rename(ticker)


def _has_large_cache_gap(series: pd.Series, max_gap_days: int = 7) -> bool:
    """Return True when cached rows have an implausibly large calendar gap."""
    if len(series) < 2:
        return False
    idx = pd.DatetimeIndex(series.index).sort_values()
    gaps = idx.to_series().diff().dropna()
    if gaps.empty:
        return False
    return bool(gaps.max() > pd.Timedelta(days=max_gap_days))


def _download_yf(ticker: str, start: str, end: str) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    out = pd.DataFrame(index=pd.to_datetime(raw.index).normalize())
    for src, dst in [
        ("Open", "open"),
        ("High", "high"),
        ("Low", "low"),
        ("Close", "close"),
        ("Volume", "volume"),
    ]:
        out[dst] = raw[src] if src in raw.columns else pd.NA
    out = out.reset_index(names="dt")
    out["provider"] = "yfinance"
    out["ticker"] = ticker
    out["source"] = "yfinance"
    out["fetched_at"] = datetime.now()
    out = out[["provider", "ticker", "dt", "open", "high", "low", "close", "volume", "source", "fetched_at"]]
    return out.dropna(subset=["close"])


def _write_cache(db_path: Path, ticker: str, df: pd.DataFrame, purpose: str) -> None:
    if df.empty:
        return
    ensure_external_cache_schema(db_path)
    start_dt = pd.to_datetime(df["dt"]).min().date()
    end_dt = pd.to_datetime(df["dt"]).max().date()
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    try:
        yf_version = importlib.metadata.version("yfinance")
    except importlib.metadata.PackageNotFoundError:
        yf_version = None
    with duckdb.connect(str(db_path)) as con:
        con.register("_ncf_ext_df", df)
        con.execute(
            """
            DELETE FROM external_market_ohlcv
            WHERE provider='yfinance'
              AND ticker=?
              AND dt BETWEEN ? AND ?
            """,
            [ticker, start_dt, end_dt],
        )
        con.execute("INSERT INTO external_market_ohlcv SELECT * FROM _ncf_ext_df")
        con.execute(
            """
            INSERT INTO external_data_version
                (run_id, provider, ticker, start_dt, end_dt, row_count, yfinance_version, purpose)
            VALUES (?, 'yfinance', ?, ?, ?, ?, ?, ?)
            """,
            [run_id, ticker, start_dt, end_dt, int(len(df)), yf_version, purpose],
        )


def fetch_yf_close_cached(
    ticker: str,
    start: str,
    end: str,
    db_path: Path,
    purpose: str = "ncf_external_features",
) -> pd.Series:
    """Return yfinance adjusted close, caching downloaded rows in DuckDB.

    yfinance treats `end` as exclusive. The cache query uses inclusive date
    filters, so callers can pass the same start/end they previously used.
    """
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    cached = _read_cached_close(db_path, ticker, start_ts.strftime("%Y-%m-%d"), end_ts.strftime("%Y-%m-%d"))
    if (
        not cached.empty
        and cached.index.min() <= start_ts
        and cached.index.max() >= end_ts - timedelta(days=4)
        and not _has_large_cache_gap(cached)
    ):
        return cached.rename(ticker)

    downloaded = _download_yf(ticker, start_ts.strftime("%Y-%m-%d"), end_ts.strftime("%Y-%m-%d"))
    if not downloaded.empty:
        _write_cache(db_path, ticker, downloaded, purpose)
        cached = _read_cached_close(db_path, ticker, start_ts.strftime("%Y-%m-%d"), end_ts.strftime("%Y-%m-%d"))
    return cached.rename(ticker)
