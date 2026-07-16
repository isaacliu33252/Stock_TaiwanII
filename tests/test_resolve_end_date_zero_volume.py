from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResolveEndDateZeroVolumeTests(unittest.TestCase):
    """2026-07-12 fix: resolve_end_date(db, ticker, "latest") used to pick
    up a phantom zero-volume ohlcv row (market holiday / ticker-specific
    halt carried forward instead of skipped) as "the latest date," which is
    how ncf_00631l_latest_20260711.json ended up dated 2026-07-10 (a real
    holiday). See GROUP_A_PLUS_A2118_CHIP_DATA_CORE_CLOCK_AUDIT_HANDOFF_20260712.md.
    """

    def _fixture_db_with_ohlcv(self, tmp: str, ticker: str) -> Path:
        db_path = Path(tmp) / "fixture.db"
        con = duckdb.connect(str(db_path))
        try:
            con.execute(
                "CREATE TABLE ohlcv (ticker TEXT, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, "
                "close DOUBLE, volume BIGINT, source_file TEXT)"
            )
            rows = [
                (ticker, "2026-07-08", 100.0, 101.0, 99.0, 100.0, 1000),
                (ticker, "2026-07-09", 101.0, 102.0, 100.0, 101.0, 1200),
                (ticker, "2026-07-10", 101.0, 101.0, 101.0, 101.0, 0),
            ]
            for tick, dt, o, h, l, c, v in rows:
                con.execute("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, 'fixture')", [tick, dt, o, h, l, c, v])
        finally:
            con.close()
        return db_path

    def _fixture_db_with_external_market_ohlcv(self, tmp: str, ticker: str) -> Path:
        db_path = Path(tmp) / "fixture.db"
        con = duckdb.connect(str(db_path))
        try:
            con.execute(
                "CREATE TABLE external_market_ohlcv (provider TEXT, ticker TEXT, dt DATE, close DOUBLE, volume BIGINT)"
            )
            rows = [
                ("yfinance", ticker, "2026-07-08", 100.0, 1000),
                ("yfinance", ticker, "2026-07-09", 101.0, 1200),
                ("yfinance", ticker, "2026-07-10", 101.0, 0),
            ]
            for provider, tick, dt, c, v in rows:
                con.execute("INSERT INTO external_market_ohlcv VALUES (?, ?, ?, ?, ?)", [provider, tick, dt, c, v])
        finally:
            con.close()
        return db_path

    def test_ncf_00631l_resolve_end_date_skips_phantom_row(self) -> None:
        mod = _load_module(PROJECT_ROOT / "scripts" / "misc" / "ncf_00631l.py", "_test_ncf_00631l")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fixture_db_with_ohlcv(tmp, "00631L.TW")
            resolved = mod.resolve_end_date(db_path, "00631L.TW", "latest")

        self.assertEqual(resolved, "2026-07-09")

    def test_ncf_00632r_resolve_end_date_skips_phantom_row(self) -> None:
        mod = _load_module(PROJECT_ROOT / "ncf_00632r.py", "_test_ncf_00632r")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fixture_db_with_ohlcv(tmp, "00632R.TW")
            resolved = mod.resolve_end_date(db_path, "00632R.TW", "latest")

        self.assertEqual(resolved, "2026-07-09")

    def test_ncf_2330_resolve_end_date_skips_phantom_row(self) -> None:
        mod = _load_module(PROJECT_ROOT / "ncf_2330.py", "_test_ncf_2330")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fixture_db_with_external_market_ohlcv(tmp, "2330.TW")
            resolved = mod.resolve_end_date(db_path, "2330.TW", "latest")

        self.assertEqual(resolved, "2026-07-09")

    def test_explicit_end_date_bypasses_lookup_entirely(self) -> None:
        # Non-"latest" requests must not touch the DB at all -- backtest/
        # evaluation callers pass explicit dates and must see zero behavior
        # change from this fix.
        mod = _load_module(PROJECT_ROOT / "scripts" / "misc" / "ncf_00631l.py", "_test_ncf_00631l_explicit")
        resolved = mod.resolve_end_date(Path("/nonexistent/db.duckdb"), "00631L.TW", "2020-01-01")
        self.assertEqual(resolved, "2020-01-01")


if __name__ == "__main__":
    unittest.main()
