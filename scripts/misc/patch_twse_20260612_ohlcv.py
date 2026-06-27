#!/usr/bin/env python3
"""Patch 2026-06-12 TWSE ETF OHLCV rows from TWSE monthly API."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from refresh_group_data import _raw_cache_name, _upsert_raw_parquet_to_db


PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache"
TARGET_DATE = pd.Timestamp("2026-06-12")
TWSE_TICKERS = [
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "0056.TW",
    "00646.TW",
    "00713.TW",
    "00878.TW",
]


def _code(ticker: str) -> str:
    return ticker.split(".")[0]


def _parse_number(value: str) -> float:
    value = str(value).replace(",", "").replace("--", "").strip()
    return float(value) if value else 0.0


def _fetch_twse_row(ticker: str) -> dict[str, float]:
    response = requests.get(
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
        params={"response": "json", "date": TARGET_DATE.strftime("%Y%m%d"), "stockNo": _code(ticker)},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("stat") != "OK":
        raise RuntimeError(f"TWSE returned {payload.get('stat')} for {ticker}")
    target_roc = "115/06/12"
    for row in payload.get("data", []):
        if str(row[0]).strip() == target_roc:
            return {
                "open": _parse_number(row[3]),
                "high": _parse_number(row[4]),
                "low": _parse_number(row[5]),
                "close": _parse_number(row[6]),
                "volume": int(_parse_number(row[1])),
            }
    raise RuntimeError(f"No {target_roc} TWSE row for {ticker}")


def _patch_cache(ticker: str, values: dict[str, float]) -> Path:
    path = CACHE_DIR / _raw_cache_name(ticker, "2020-01-01", TARGET_DATE.strftime("%Y-%m-%d"))
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    mask = df["date"].dt.normalize() == TARGET_DATE
    if not mask.any():
        new_row = {column: 0.0 for column in df.columns}
        new_row["date"] = TARGET_DATE
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        mask = df["date"].dt.normalize() == TARGET_DATE
    for column in ("open", "high", "low", "close", "volume"):
        df.loc[mask, column] = values[column]
    if "adj close" in df.columns:
        df.loc[mask, "adj close"] = values["close"]
    if "dividends" in df.columns:
        df.loc[mask, "dividends"] = df.loc[mask, "dividends"].fillna(0.0)
    if "stock splits" in df.columns:
        df.loc[mask, "stock splits"] = df.loc[mask, "stock splits"].fillna(0.0)
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(path, index=False)
    return path


def main() -> None:
    for ticker in TWSE_TICKERS:
        values = _fetch_twse_row(ticker)
        path = _patch_cache(ticker, values)
        rows = _upsert_raw_parquet_to_db(ticker, path)
        print(
            f"{ticker}: close={values['close']:.2f}, volume={values['volume']}, "
            f"cache={path.name}, db_rows={rows}"
        )


if __name__ == "__main__":
    main()
