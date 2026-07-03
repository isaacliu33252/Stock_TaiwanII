#!/usr/bin/env python3
"""Check raw OHLCV cache quality against DuckDB usable OHLCV dates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH


CACHE_DIR = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache"
DEFAULT_TICKERS = (
    "0050.TW",
    "0056.TW",
    "00631L.TW",
    "00632R.TW",
    "00646.TW",
    "00679B.TWO",
    "00713.TW",
    "00751B.TWO",
    "00878.TW",
)


def _safe_ticker(ticker: str) -> str:
    return ticker.replace(".", "_")


def _auto_target_date(today: date | None = None) -> date:
    current = today or date.today()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _parse_cache_range(path: Path, safe_ticker: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    match = re.match(rf"^{re.escape(safe_ticker)}_(\d{{8}})_(\d{{8}})_1d_raw_v1\.parquet$", path.name)
    if not match:
        return None
    return pd.Timestamp(match.group(1)), pd.Timestamp(match.group(2))


def find_raw_cache(cache_dir: Path, ticker: str, target_date: str) -> Path | None:
    safe = _safe_ticker(ticker)
    target = pd.Timestamp(target_date).normalize()
    candidates: list[tuple[int, int, Path]] = []
    for path in cache_dir.glob(f"{safe}_*_1d_raw_v1.parquet"):
        parsed = _parse_cache_range(path, safe)
        if parsed is None:
            continue
        start, end = parsed
        if start <= target <= end:
            span = int((end - start).days)
            candidates.append((span, -int(end.strftime("%Y%m%d")), path))
    if not candidates:
        return None
    return sorted(candidates)[0][2]


def _read_raw_cache_status(path: Path | None, target_date: str) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": None,
            "exists": False,
            "min_date": None,
            "max_date": None,
            "rows": 0,
            "has_target_date": False,
            "target_close_valid": False,
            "target_adj_close_valid": False,
            "target_ohlv_valid": False,
        }

    df = pd.read_parquet(path)
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    if "date" not in df.columns:
        raise RuntimeError(f"{path} missing date column")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    target = pd.Timestamp(target_date).normalize()
    target_rows = df[df["date"] == target]
    close = pd.to_numeric(target_rows.get("close", pd.Series(dtype=float)), errors="coerce")
    adj_close = pd.to_numeric(target_rows.get("adj_close", pd.Series(dtype=float)), errors="coerce")
    ohlv_cols = ["open", "high", "low", "volume"]
    ohlv_valid = False
    if not target_rows.empty and all(col in target_rows.columns for col in ohlv_cols):
        ohlv_valid = bool(
            pd.to_numeric(target_rows["open"], errors="coerce").notna().any()
            and pd.to_numeric(target_rows["high"], errors="coerce").notna().any()
            and pd.to_numeric(target_rows["low"], errors="coerce").notna().any()
            and pd.to_numeric(target_rows["volume"], errors="coerce").notna().any()
        )
    return {
        "path": str(path),
        "exists": True,
        "min_date": df["date"].min().date().isoformat() if not df.empty else None,
        "max_date": df["date"].max().date().isoformat() if not df.empty else None,
        "rows": int(len(df)),
        "has_target_date": bool(not target_rows.empty),
        "target_close_valid": bool(close.notna().any()),
        "target_adj_close_valid": bool(adj_close.notna().any()),
        "target_ohlv_valid": ohlv_valid,
    }


def _db_max_date(db_path: Path, ticker: str) -> str | None:
    with duckdb.connect(str(db_path), read_only=True) as con:
        value = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker=?", [ticker]).fetchone()[0]
    if value is None:
        return None
    return pd.Timestamp(value).date().isoformat()


def check_ticker(
    ticker: str,
    target_date: str,
    *,
    db_path: Path = DB_PATH,
    cache_dir: Path = CACHE_DIR,
    max_db_lag_days: int = 3,
) -> dict[str, Any]:
    raw_path = find_raw_cache(cache_dir, ticker, target_date)
    raw = _read_raw_cache_status(raw_path, target_date)
    db_max = _db_max_date(db_path, ticker)
    lag_days = None if db_max is None else (pd.Timestamp(target_date) - pd.Timestamp(db_max)).days

    warnings: list[str] = []
    errors: list[str] = []
    if not raw["exists"]:
        warnings.append("raw_cache_missing")
    elif not raw["has_target_date"]:
        warnings.append("raw_target_date_missing")
    elif raw["target_ohlv_valid"] and not raw["target_close_valid"]:
        warnings.append("raw_target_close_invalid")
    elif not raw["target_ohlv_valid"]:
        warnings.append("raw_target_ohlv_invalid")

    if db_max is None:
        errors.append("db_ohlcv_missing")
    elif lag_days is not None and lag_days > max_db_lag_days:
        errors.append("db_ohlcv_stale")

    status = "error" if errors else ("warning" if warnings else "ok")
    return {
        "ticker": ticker,
        "target_date": target_date,
        "db_max_date": db_max,
        "db_lag_days": lag_days,
        "raw_cache": raw,
        "status": status,
        "warnings": warnings,
        "errors": errors,
    }


def build_report(
    tickers: list[str],
    target_date: str,
    *,
    db_path: Path = DB_PATH,
    cache_dir: Path = CACHE_DIR,
    max_db_lag_days: int = 3,
) -> dict[str, Any]:
    rows = [
        check_ticker(
            ticker,
            target_date,
            db_path=db_path,
            cache_dir=cache_dir,
            max_db_lag_days=max_db_lag_days,
        )
        for ticker in tickers
    ]
    errors = [row["ticker"] for row in rows if row["status"] == "error"]
    warnings = [row["ticker"] for row in rows if row["status"] == "warning"]
    overall = "error" if errors else ("warning" if warnings else "ok")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date,
        "max_db_lag_days": max_db_lag_days,
        "overall_status": overall,
        "error_tickers": errors,
        "warning_tickers": warnings,
        "tickers": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--target-date", default="auto")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--cache-dir", default=str(CACHE_DIR))
    parser.add_argument("--max-db-lag-days", type=int, default=3)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = _auto_target_date().isoformat() if args.target_date == "auto" else args.target_date
    tickers = [ticker.strip() for ticker in args.tickers.split(",") if ticker.strip()]
    report = build_report(
        tickers,
        target,
        db_path=Path(args.db),
        cache_dir=Path(args.cache_dir),
        max_db_lag_days=args.max_db_lag_days,
    )
    if args.output:
        out = Path(args.output)
        if not out.is_absolute():
            out = PROJECT_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved: {out}")

    print(f"OHLCV freshness: {report['overall_status']} target={target}")
    for row in report["tickers"]:
        print(
            f"  {row['ticker']}: {row['status']} "
            f"db={row['db_max_date']} lag={row['db_lag_days']} "
            f"raw_target={row['raw_cache']['has_target_date']} "
            f"close_valid={row['raw_cache']['target_close_valid']} "
            f"warnings={','.join(row['warnings']) or '-'}"
        )

    if report["overall_status"] == "error" or (args.fail_on_warning and report["overall_status"] == "warning"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
