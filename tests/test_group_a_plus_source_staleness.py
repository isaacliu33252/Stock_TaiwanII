#!/usr/bin/env python3
"""Regression check for bounded source carry-forward in GroupA+ features."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb
import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from backtest_group_a_plus_policy_signal import TICKERS


class SourceStalenessTests(unittest.TestCase):
    def test_2022_tdcc_change_is_not_carried_into_2025(self) -> None:
        prices = _load_prices(Path(DB_PATH), list(TICKERS), "2020-01-02", "2025-06-19")
        features = _load_chip_features(Path(DB_PATH), prices.index, "2020-01-02", "2025-06-19")
        recent = features.loc["2025-01-02":"2025-06-19"]

        self.assertTrue((recent["tdcc_0050_minority_chg_1w"] == 0.0).all())
        self.assertTrue((recent["tdcc_0050_major_chg_1w"] == 0.0).all())


class ExcludeZeroVolumeRowsTests(unittest.TestCase):
    """2026-07-12 fix: a market holiday (or a real multi-day source outage)
    can leave a spurious `ohlcv` row behind -- open=high=low=close=prior
    close, volume=0 -- instead of the date being skipped entirely. Live
    signal generation treats the last loaded price row as "today's real
    trading day," so a phantom row like this makes every chip/derivative
    freshness check look one day more stale than reality and can incorrectly
    block execution. See
    GROUP_A_PLUS_A2118_CHIP_DATA_CORE_CLOCK_AUDIT_HANDOFF_20260712.md."""

    def _fixture_db(self, tmp: str) -> Path:
        db_path = Path(tmp) / "fixture.db"
        con = duckdb.connect(str(db_path))
        try:
            con.execute(
                "CREATE TABLE ohlcv (ticker TEXT, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, "
                "close DOUBLE, volume BIGINT, source_file TEXT)"
            )
            rows = [
                ("0050.TW", "2026-07-08", 100.0, 101.0, 99.0, 100.0, 1000),
                ("0050.TW", "2026-07-09", 101.0, 102.0, 100.0, 101.0, 1200),
                # Phantom holiday row: flat OHLC at prior close, zero volume.
                ("0050.TW", "2026-07-10", 101.0, 101.0, 101.0, 101.0, 0),
            ]
            for ticker, dt, o, h, l, c, v in rows:
                con.execute(
                    "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, 'fixture')",
                    [ticker, dt, o, h, l, c, v],
                )
        finally:
            con.close()
        return db_path

    def test_default_behavior_includes_phantom_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fixture_db(tmp)
            prices = _load_prices(db_path, ["0050.TW"], "2026-07-08", "2026-07-12")

        self.assertEqual(str(prices.index.max().date()), "2026-07-10")

    def test_exclude_zero_volume_drops_phantom_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fixture_db(tmp)
            prices = _load_prices(
                db_path, ["0050.TW"], "2026-07-08", "2026-07-12", exclude_zero_volume=True
            )

        self.assertEqual(str(prices.index.max().date()), "2026-07-09")
        self.assertEqual(len(prices), 2)


if __name__ == "__main__":
    unittest.main()
