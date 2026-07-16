from __future__ import annotations

from pathlib import Path

import pandas as pd

import scripts.fetch.fetch_cross_market_ohlcv as fetch_cross_market_ohlcv


def test_refresh_cross_market_ohlcv_always_allows_download(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_fetch_yf_close_cached(ticker, start, end, db_path, purpose, allow_download):
        calls.append({"ticker": ticker, "allow_download": allow_download, "purpose": purpose})
        return pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-07-08", "2026-07-09"]), name=ticker)

    monkeypatch.setattr(fetch_cross_market_ohlcv, "fetch_yf_close_cached", _fake_fetch_yf_close_cached)

    report = fetch_cross_market_ohlcv.refresh_cross_market_ohlcv(
        db_path=Path("/nonexistent/stock_data.db"),
        start="2026-01-01",
        end="2026-07-10",
    )

    assert {c["ticker"] for c in calls} == set(fetch_cross_market_ohlcv.DEFAULT_TICKERS)
    assert all(c["allow_download"] is True for c in calls)
    assert report["tickers"]["^VIX"]["status"] == "available"
    assert report["tickers"]["^VIX"]["last_date"] == "2026-07-09"


def test_refresh_cross_market_ohlcv_reports_missing_ticker(monkeypatch) -> None:
    def _empty_fetch(ticker, start, end, db_path, purpose, allow_download):
        return pd.Series(dtype=float, name=ticker)

    monkeypatch.setattr(fetch_cross_market_ohlcv, "fetch_yf_close_cached", _empty_fetch)

    report = fetch_cross_market_ohlcv.refresh_cross_market_ohlcv(
        db_path=Path("/nonexistent/stock_data.db"),
        start="2026-01-01",
        end="2026-07-10",
    )

    assert all(entry["status"] == "missing" for entry in report["tickers"].values())
