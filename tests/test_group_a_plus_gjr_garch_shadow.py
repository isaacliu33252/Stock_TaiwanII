from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from group_a_plus.integrations.gjr_garch_shadow import (
    append_gjr_garch_shadow_log,
    compute_gjr_garch_shadow,
)


def _write_ohlcv(db_path: Path, closes: pd.Series, ticker: str = "00631L.TW") -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = [(ticker, str(dt.date()), float(price)) for dt, price in closes.items()]
        con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)
    finally:
        con.close()


def _synthetic_closes(n: int = 360, as_of: str = "2026-07-31") -> pd.Series:
    rng = np.random.default_rng(260716450)
    dates = pd.bdate_range(end=pd.Timestamp(as_of), periods=n)
    returns = rng.normal(loc=0.0003, scale=0.012, size=n)
    returns[-1] = -0.035
    prices = 30.0 * np.cumprod(1.0 + returns)
    return pd.Series(prices, index=dates)


class TestGjrGarchShadow(unittest.TestCase):
    def test_compute_available_shadow_preserves_no_weight_change_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            _write_ohlcv(db_path, _synthetic_closes())

            shadow = compute_gjr_garch_shadow(
                db_path,
                "2026-07-31",
                lookback_calendar_days=700,
                train_obs=300,
            )

        self.assertEqual("available", shadow["status"])
        self.assertEqual("shadow_only_no_weight_change", shadow["policy"])
        self.assertEqual("none", shadow["active_allocation_impact"])
        self.assertEqual("00631L.TW", shadow["ticker"])
        self.assertIn(shadow["evidence_level"], {"none", "watch", "weak"})
        self.assertIn("forecast_variance_ratio_gjr_over_symmetric", shadow)
        self.assertFalse(shadow["decision_boundary"]["target_weight_change_allowed"])
        self.assertFalse(shadow["decision_boundary"]["risk_mechanism_trigger_allowed"])

    def test_insufficient_history_reports_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            _write_ohlcv(db_path, _synthetic_closes(n=40))

            shadow = compute_gjr_garch_shadow(db_path, "2026-07-31")

        self.assertEqual("unavailable", shadow["status"])
        self.assertEqual("insufficient_return_history", shadow["reason"])

    def test_shadow_log_is_idempotent_per_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "gjr_garch_shadow_log.jsonl"
            first = {
                "status": "available",
                "date": "2026-07-31",
                "ticker": "00631L.TW",
                "evidence_level": "none",
                "policy": "shadow_only_no_weight_change",
            }
            second = {**first, "evidence_level": "weak"}

            append_gjr_garch_shadow_log(log_path, first)
            append_gjr_garch_shadow_log(log_path, second)

            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(1, len(rows))
        self.assertEqual("weak", rows[0]["evidence_level"])

    def test_unavailable_shadow_is_not_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "gjr_garch_shadow_log.jsonl"
            append_gjr_garch_shadow_log(log_path, {"status": "unavailable", "reason": "missing"})

            self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
