"""Local price loaders for broker-neutral portfolio valuation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _clean_price(value: Any, *, ticker: str) -> float:
    price = float(value)
    if price <= 0:
        raise ValueError(f"price must be positive for {ticker}: {price}")
    return price


def load_prices_json(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "latest_prices" in payload and isinstance(payload["latest_prices"], dict):
        payload = payload["latest_prices"]
    if not isinstance(payload, dict):
        raise ValueError(f"price JSON must be an object: {path}")
    return {str(ticker): _clean_price(price, ticker=str(ticker)) for ticker, price in payload.items()}


def load_prices_from_ohlcv_freshness(path: Path, *, price_column: str = "close") -> dict[str, float]:
    """Load target-date prices from a local ohlcv freshness report.

    The freshness report records raw cache parquet paths and target dates. This
    loader only reads local cache files; it does not download or refresh data.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    tickers = payload.get("tickers")
    if not isinstance(tickers, list):
        raise ValueError(f"ohlcv freshness JSON has no tickers list: {path}")

    prices: dict[str, float] = {}
    for item in tickers:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "")
        target_date = str(item.get("target_date") or payload.get("target_date") or "")
        raw_cache = item.get("raw_cache") or {}
        raw_path = Path(str(raw_cache.get("path") or ""))
        if not ticker or not target_date or not raw_path.exists():
            continue

        df = pd.read_parquet(raw_path)
        if "date" in df.columns:
            dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            matched = df.loc[dates == target_date]
        else:
            matched = df.loc[pd.to_datetime(df.index).strftime("%Y-%m-%d") == target_date]
        if matched.empty:
            continue

        column = price_column if price_column in matched.columns else "adj close"
        if column not in matched.columns:
            column = "close"
        if column not in matched.columns:
            continue
        prices[ticker] = _clean_price(matched.iloc[-1][column], ticker=ticker)
    return prices
