#!/usr/bin/env python3
"""Refresh Group A / Group B market data caches and DuckDB in one step."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.data_utils import read_parquet_safe, write_parquet_safe
from FinRL.data.stock_db import CREATE_TABLE_SQL, DB_PATH, _ensure_indexes, _ensure_schema_compat

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
CACHE_DIR = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache"
GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
GROUP_B_TICKERS = ["0056.TW", "00646.TW", "00679B.TWO", "00713.TW", "00751B.TWO", "00878.TW"]
DEFAULT_GROUP_A_START = "2020-01-01"
DEFAULT_GROUP_B_START = "2020-01-01"
EXTRA_MARKET_STARTS = ["2024-01-01"]


@dataclass
class CacheStatus:
    path: str
    exists: bool
    min_date: str | None
    max_date: str | None
    has_target_date: bool
    rows: int


def _today_in_taipei(cutoff_hour: int) -> pd.Timestamp:
    now = datetime.now(TAIPEI_TZ)
    current = now.date()
    if now.hour < cutoff_hour:
        current = current - timedelta(days=1)
    while current.weekday() >= 5:
        current = current - timedelta(days=1)
    return pd.Timestamp(current).normalize()


def _parse_target_date(raw_value: str | None, cutoff_hour: int) -> pd.Timestamp:
    if raw_value in (None, "", "auto"):
        return _today_in_taipei(cutoff_hour)
    return pd.Timestamp(raw_value).normalize()


def _selected_tickers(group: str) -> list[str]:
    if group == "a":
        return list(GROUP_A_TICKERS)
    if group == "b":
        return list(GROUP_B_TICKERS)
    return list(GROUP_A_TICKERS) + list(GROUP_B_TICKERS)


def _stock_windows(group: str, group_a_start: str, group_b_start: str) -> list[tuple[str, list[str]]]:
    windows: list[tuple[str, list[str]]] = []
    if group in {"a", "both"}:
        windows.append((group_a_start, list(GROUP_A_TICKERS)))
    if group in {"b", "both"}:
        windows.append((group_b_start, list(GROUP_B_TICKERS)))
    return windows


def _market_starts(
    group: str,
    group_a_start: str,
    group_b_start: str,
    extra_starts: list[str] | None = None,
    target_date: pd.Timestamp | None = None,
) -> list[str]:
    starts = set(EXTRA_MARKET_STARTS)
    if extra_starts:
        starts.update(extra_starts)
    for start, _ in _stock_windows(group, group_a_start, group_b_start):
        starts.add(start)
    if target_date is not None:
        target_ts = pd.Timestamp(target_date).normalize()
        starts = {start for start in starts if pd.Timestamp(start).normalize() <= target_ts}
    return sorted(starts)


def _safe_ticker(ticker: str) -> str:
    return ticker.replace(".", "_")


def _raw_cache_name(ticker: str, start_date: str, end_date: str) -> str:
    return f"{_safe_ticker(ticker)}_{start_date.replace('-', '')}_{end_date.replace('-', '')}_1d_raw_v1.parquet"


def _market_cache_name(start_date: str, end_date: str) -> str:
    return f"TWII_DJI_{start_date.replace('-', '')}_{end_date.replace('-', '')}_1d_market_v3.parquet"


def _cache_status(path: Path, target_date: pd.Timestamp) -> CacheStatus:
    if not path.exists():
        return CacheStatus(
            path=str(path),
            exists=False,
            min_date=None,
            max_date=None,
            has_target_date=False,
            rows=0,
        )
    q = """
        SELECT
            MIN(date) AS min_date,
            MAX(date) AS max_date,
            SUM(CASE WHEN date = ? THEN 1 ELSE 0 END) AS hits,
            COUNT(*) AS rows
        FROM read_parquet(?)
    """
    min_date, max_date, hits, rows = duckdb.connect().execute(q, [target_date.date(), str(path)]).fetchone()
    return CacheStatus(
        path=str(path),
        exists=True,
        min_date=str(min_date) if min_date is not None else None,
        max_date=str(max_date) if max_date is not None else None,
        has_target_date=bool(hits),
        rows=int(rows or 0),
    )


def _db_status(tickers: Iterable[str], target_date: pd.Timestamp) -> list[dict[str, object]]:
    ticker_list = list(tickers)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        sql = """
            SELECT
                ticker,
                MIN(dt) AS min_date,
                MAX(dt) AS max_date,
                SUM(CASE WHEN dt = ? THEN 1 ELSE 0 END) AS hits,
                COUNT(*) AS rows
            FROM ohlcv
            WHERE ticker IN ({tickers})
            GROUP BY ticker
            ORDER BY ticker
        """.format(tickers=", ".join(["?"] * len(ticker_list)))
        params = [target_date.date(), *ticker_list]
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    out: list[dict[str, object]] = []
    for ticker, min_date, max_date, hits, row_count in rows:
        out.append(
            {
                "ticker": ticker,
                "min_date": str(min_date) if min_date is not None else None,
                "max_date": str(max_date) if max_date is not None else None,
                "has_target_date": bool(hits),
                "rows": int(row_count or 0),
            }
        )
    return out


def _all_current(
    tickers: list[str],
    target_date: pd.Timestamp,
    stock_windows: list[tuple[str, list[str]]],
    market_starts: list[str],
) -> tuple[bool, list[CacheStatus], list[CacheStatus], list[dict[str, object]]]:
    stock_statuses: list[CacheStatus] = []
    for start_date, window_tickers in stock_windows:
        for ticker in window_tickers:
            stock_statuses.append(_cache_status(CACHE_DIR / _raw_cache_name(ticker, start_date, str(target_date.date())), target_date))
    market_statuses = [
        _cache_status(CACHE_DIR / _market_cache_name(start_date, str(target_date.date())), target_date)
        for start_date in market_starts
    ]
    db_statuses = _db_status(tickers, target_date)
    all_ok = (
        all(status.has_target_date for status in stock_statuses)
        and all(status.has_target_date for status in market_statuses)
        and len(db_statuses) == len(tickers)
        and all(bool(row["has_target_date"]) for row in db_statuses)
    )
    return all_ok, stock_statuses, market_statuses, db_statuses


def _copy_market_slices(master_market_path: Path, market_starts: list[str], target_date: pd.Timestamp, temp_dir: Path) -> list[Path]:
    market_df = read_parquet_safe(master_market_path)
    if market_df is None or market_df.empty:
        raise RuntimeError(f"Missing market data: {master_market_path}")
    market_df = market_df.copy()
    market_df["date"] = pd.to_datetime(market_df["date"]).dt.tz_localize(None)

    created_paths: list[Path] = []
    for start_date in market_starts:
        out_path = temp_dir / _market_cache_name(start_date, str(target_date.date()))
        start_ts = pd.Timestamp(start_date).normalize()
        sliced = market_df[(market_df["date"] >= start_ts) & (market_df["date"] <= target_date)].copy()
        if sliced.empty:
            raise RuntimeError(f"Empty market slice for start={start_date}")
        if not write_parquet_safe(sliced, out_path):
            raise RuntimeError(f"Failed to write market cache: {out_path}")
        created_paths.append(out_path)
    return created_paths


def _upsert_raw_parquet_to_db(ticker: str, path: Path) -> int:
    df = duckdb.connect().execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchdf()
    df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
    if "date" not in df.columns:
        raise RuntimeError(f"{path.name} missing date column")
    if "dividends" not in df.columns:
        df["dividends"] = 0.0
    if "stock_splits" not in df.columns:
        df["stock_splits"] = 0.0

    batch_df = pd.DataFrame(
        {
            "ticker": ticker,
            "dt": pd.to_datetime(df["date"]).dt.tz_localize(None).dt.date,
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64"),
            "dividends": pd.to_numeric(df["dividends"], errors="coerce").fillna(0.0),
            "stock_splits": pd.to_numeric(df["stock_splits"], errors="coerce").fillna(0.0),
            "source_file": path.name,
        }
    ).dropna(subset=["dt", "open", "high", "low", "close"])

    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_TABLE_SQL)
        _ensure_schema_compat(con)
        _ensure_indexes(con)
        con.register("batch_df", batch_df)
        con.execute(
            """
            INSERT OR REPLACE INTO ohlcv
            (ticker, dt, open, high, low, close, volume, dividends, stock_splits, source_file)
            SELECT ticker, dt, open, high, low, close, volume, dividends, stock_splits, source_file
            FROM batch_df
            """
        )
        con.unregister("batch_df")
    finally:
        con.close()
    return int(len(batch_df))


def _refresh(
    group: str,
    target_date: pd.Timestamp,
    strict: bool,
    group_a_start: str,
    group_b_start: str,
    extra_market_starts: list[str] | None = None,
) -> dict[str, object]:
    from FinRL.portfolio_data_loader import download_all_stocks, download_market_features

    tickers = _selected_tickers(group)
    stock_windows = _stock_windows(group, group_a_start, group_b_start)
    market_starts = _market_starts(group, group_a_start, group_b_start, extra_market_starts, target_date)
    earliest_market_start = min(market_starts)

    with TemporaryDirectory(prefix="group_data_refresh_") as tmp:
        temp_dir = Path(tmp)
        raw_paths: dict[str, Path] = {}

        for start_date, window_tickers in stock_windows:
            download_all_stocks(window_tickers, start_date, str(target_date.date()), cache_dir=str(temp_dir))
            for ticker in window_tickers:
                raw_path = temp_dir / _raw_cache_name(ticker, start_date, str(target_date.date()))
                if not raw_path.exists():
                    raise FileNotFoundError(f"Missing raw cache after download: {raw_path}")
                raw_paths[ticker] = raw_path

        market_df = download_market_features(earliest_market_start, str(target_date.date()), cache_dir=str(temp_dir))
        if market_df is None or market_df.empty:
            raise RuntimeError("Market download returned no rows")
        master_market_path = temp_dir / _market_cache_name(earliest_market_start, str(target_date.date()))
        if not master_market_path.exists():
            raise FileNotFoundError(f"Missing market cache after download: {master_market_path}")
        market_paths = _copy_market_slices(master_market_path, market_starts, target_date, temp_dir)

        raw_statuses = {ticker: _cache_status(path, target_date) for ticker, path in raw_paths.items()}
        market_statuses = [_cache_status(path, target_date) for path in market_paths]
        if strict:
            missing = [ticker for ticker, status in raw_statuses.items() if not status.has_target_date]
            if missing:
                raise RuntimeError(f"Provider does not cover target date {target_date.date()} for tickers: {missing}")
            bad_market = [status.path for status in market_statuses if not status.has_target_date]
            if bad_market:
                raise RuntimeError(f"Provider does not cover target date {target_date.date()} for market caches: {bad_market}")

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        copied_paths: list[str] = []
        for path in list(raw_paths.values()) + market_paths:
            dst = CACHE_DIR / path.name
            shutil.copy2(path, dst)
            copied_paths.append(str(dst))

        db_rows_written = {}
        for ticker, path in raw_paths.items():
            db_rows_written[ticker] = _upsert_raw_parquet_to_db(ticker, path)

    db_after = _db_status(tickers, target_date)
    return {
        "group": group,
        "target_date": str(target_date.date()),
        "group_a_start": group_a_start,
        "group_b_start": group_b_start,
        "market_starts": market_starts,
        "strict": strict,
        "copied_paths": copied_paths,
        "raw_cache_status": {ticker: asdict(status) for ticker, status in raw_statuses.items()},
        "market_cache_status": [asdict(status) for status in market_statuses],
        "db_rows_written": db_rows_written,
        "db_status": db_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Group A / Group B data caches and DuckDB.")
    parser.add_argument("--group", choices=["a", "b", "both"], default="both", help="Which group to refresh.")
    parser.add_argument(
        "--target-date",
        default="auto",
        help="Target trading date in YYYY-MM-DD. Default: auto (Asia/Taipei, before 18:00 uses previous weekday).",
    )
    parser.add_argument(
        "--cutoff-hour",
        type=int,
        default=18,
        help="Only used by --target-date auto. Before this Taipei hour, use previous weekday.",
    )
    parser.add_argument("--group-a-start", default=DEFAULT_GROUP_A_START, help="Raw cache start for Group A.")
    parser.add_argument("--group-b-start", default=DEFAULT_GROUP_B_START, help="Raw cache start for Group B.")
    parser.add_argument(
        "--extra-market-start",
        action="append",
        default=[],
        help="Additional market cache start dates. Can be specified multiple times.",
    )
    parser.add_argument("--strict", action="store_true", help="Fail if provider does not return target_date exactly.")
    parser.add_argument("--force", action="store_true", help="Refresh even if cache and DuckDB already cover target_date.")
    parser.add_argument("--summary-path", help="Optional JSON file to write the refresh summary.")
    args = parser.parse_args()

    target_date = _parse_target_date(args.target_date, args.cutoff_hour)
    tickers = _selected_tickers(args.group)
    stock_windows = _stock_windows(args.group, args.group_a_start, args.group_b_start)
    market_starts = _market_starts(
        args.group,
        args.group_a_start,
        args.group_b_start,
        args.extra_market_start,
        target_date,
    )

    current_ok, stock_statuses, market_statuses, db_statuses = _all_current(
        tickers,
        target_date,
        stock_windows,
        market_starts,
    )

    if current_ok and not args.force:
        summary = {
            "status": "already_current",
            "group": args.group,
            "target_date": str(target_date.date()),
            "group_a_start": args.group_a_start,
            "group_b_start": args.group_b_start,
            "market_starts": market_starts,
            "stock_cache_status": [asdict(status) for status in stock_statuses],
            "market_cache_status": [asdict(status) for status in market_statuses],
            "db_status": db_statuses,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    summary = {
        "status": "refreshed",
        "precheck": {
            "group": args.group,
            "target_date": str(target_date.date()),
            "group_a_start": args.group_a_start,
            "group_b_start": args.group_b_start,
            "market_starts": market_starts,
            "stock_cache_status": [asdict(status) for status in stock_statuses],
            "market_cache_status": [asdict(status) for status in market_statuses],
            "db_status": db_statuses,
        },
        "refresh": _refresh(
            args.group,
            target_date,
            args.strict,
            args.group_a_start,
            args.group_b_start,
            args.extra_market_start,
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.summary_path:
        summary_path = Path(args.summary_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
