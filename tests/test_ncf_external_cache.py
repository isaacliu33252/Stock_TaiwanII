from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from ncf_external_cache import _read_cached_close, _write_cache, fetch_yf_close_cached


def _ohlcv(rows: list[tuple[str, float]], ticker: str = "QQQ") -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["dt", "close"])
    df["dt"] = pd.to_datetime(df["dt"])
    df["provider"] = "yfinance"
    df["ticker"] = ticker
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    df["volume"] = 100
    df["source"] = "yfinance"
    df["fetched_at"] = pd.Timestamp("2026-06-27")
    return df[["provider", "ticker", "dt", "open", "high", "low", "close", "volume", "source", "fetched_at"]]


class NCFExternalCacheTests(unittest.TestCase):
    def test_cache_hit_with_normal_weekend_gap_does_not_download(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cache.duckdb"
            _write_cache(
                db_path,
                "QQQ",
                _ohlcv([
                    ("2026-06-22", 100.0),
                    ("2026-06-23", 101.0),
                    ("2026-06-26", 102.0),
                ]),
                "test",
            )
            with patch("ncf_external_cache._download_yf") as download:
                result = fetch_yf_close_cached("QQQ", "2026-06-22", "2026-06-30", db_path)
            download.assert_not_called()
            self.assertEqual(len(result), 3)

    def test_large_middle_gap_triggers_refresh(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cache.duckdb"
            _write_cache(
                db_path,
                "QQQ",
                _ohlcv([
                    ("2026-06-01", 100.0),
                    ("2026-06-02", 101.0),
                    ("2026-06-26", 110.0),
                ]),
                "test",
            )
            refreshed = _ohlcv([
                ("2026-06-01", 100.0),
                ("2026-06-02", 101.0),
                ("2026-06-03", 102.0),
                ("2026-06-04", 103.0),
                ("2026-06-05", 104.0),
                ("2026-06-08", 105.0),
                ("2026-06-09", 106.0),
                ("2026-06-10", 107.0),
                ("2026-06-11", 108.0),
                ("2026-06-12", 109.0),
                ("2026-06-15", 110.0),
                ("2026-06-16", 111.0),
                ("2026-06-17", 112.0),
                ("2026-06-18", 113.0),
                ("2026-06-19", 114.0),
                ("2026-06-22", 115.0),
                ("2026-06-23", 116.0),
                ("2026-06-24", 117.0),
                ("2026-06-25", 118.0),
                ("2026-06-26", 119.0),
            ])

            with patch("ncf_external_cache._download_yf", return_value=refreshed) as download:
                result = fetch_yf_close_cached("QQQ", "2026-06-01", "2026-06-30", db_path)
            download.assert_called_once()
            self.assertEqual(len(result), len(refreshed))
            self.assertAlmostEqual(float(result.loc[pd.Timestamp("2026-06-26")]), 119.0)

    def test_cache_only_mode_returns_available_rows_without_download(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cache.duckdb"
            _write_cache(
                db_path,
                "QQQ",
                _ohlcv([
                    ("2026-06-01", 100.0),
                    ("2026-06-02", 101.0),
                    ("2026-06-26", 110.0),
                ]),
                "test",
            )

            with patch("ncf_external_cache._download_yf") as download:
                result = fetch_yf_close_cached(
                    "QQQ",
                    "2026-06-01",
                    "2026-06-30",
                    db_path,
                    allow_download=False,
                )
            download.assert_not_called()
            self.assertEqual(len(result), 3)
            self.assertAlmostEqual(float(result.loc[pd.Timestamp("2026-06-26")]), 110.0)


class NCFExternalCacheExDividendBoundaryTests(unittest.TestCase):
    """M8-4 (2026-07-02 Fable 5 audit): auto_adjust=True re-bases historical
    closes relative to every split/dividend known at download time. A
    re-fetch that only returns a narrower tail than originally requested
    (rate limit, transient yfinance gap, etc.) must not leave older,
    stale-basis rows sitting next to the freshly rebased tail -- that
    produces a spurious price jump at the boundary that corrupts
    pct_change()-based features."""

    def test_write_cache_purges_full_requested_window_not_just_downloaded_span(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cache.duckdb"
            _write_cache(
                db_path,
                "QQQ",
                _ohlcv([
                    ("2026-06-01", 100.0),
                    ("2026-06-02", 101.0),
                    ("2026-06-26", 102.0),
                ]),
                "test",
            )
            # Only a narrow tail actually downloaded, but the caller
            # originally requested the full 2026-06-01..2026-07-02 window.
            _write_cache(
                db_path,
                "QQQ",
                _ohlcv([("2026-06-29", 90.0), ("2026-06-30", 91.0)]),
                "test",
                requested_start="2026-06-01",
                requested_end="2026-07-02",
            )

            full_range = _read_cached_close(db_path, "QQQ", "2026-06-01", "2026-07-02")
            self.assertNotIn(pd.Timestamp("2026-06-01"), full_range.index)
            self.assertNotIn(pd.Timestamp("2026-06-02"), full_range.index)
            self.assertNotIn(pd.Timestamp("2026-06-26"), full_range.index)
            self.assertIn(pd.Timestamp("2026-06-29"), full_range.index)
            self.assertAlmostEqual(float(full_range.loc[pd.Timestamp("2026-06-29")]), 90.0)

    def test_fetch_yf_close_cached_partial_redownload_does_not_mix_adjustment_bases(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cache.duckdb"
            _write_cache(
                db_path,
                "QQQ",
                _ohlcv([
                    ("2026-06-01", 100.0),
                    ("2026-06-02", 101.0),
                    ("2026-06-26", 102.0),
                ]),
                "test",
            )
            narrow_new_basis = _ohlcv([("2026-06-29", 90.0), ("2026-06-30", 91.0)])

            with patch("ncf_external_cache._download_yf", return_value=narrow_new_basis) as download:
                fetch_yf_close_cached("QQQ", "2026-06-01", "2026-07-02", db_path)
            download.assert_called_once()

            full_range = _read_cached_close(db_path, "QQQ", "2026-06-01", "2026-07-02")
            self.assertNotIn(pd.Timestamp("2026-06-01"), full_range.index)
            self.assertNotIn(pd.Timestamp("2026-06-26"), full_range.index)
            self.assertIn(pd.Timestamp("2026-06-29"), full_range.index)
            self.assertAlmostEqual(float(full_range.loc[pd.Timestamp("2026-06-29")]), 90.0)


if __name__ == "__main__":
    unittest.main()
