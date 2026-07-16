"""Tests for the GARCH-proxy volatility-regime shadow diagnostic (2026-07-05).

See group_a_plus/integrations/garch_regime_shadow.py's module docstring for
the walk-forward research this is based on. This module is shadow/diagnostic
only -- these tests check the computation and logging behave correctly, not
that the underlying regime signal is profitable (that question is tracked in
results/garch_specialist_routing_walkforward_20260705.json and
results/garch_specialist_routing_2008_fold_20260705.json, both n=1-crisis
research, not settled).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from group_a_plus.integrations.garch_regime_shadow import (
    append_garch_regime_shadow_log,
    compute_garch_regime_shadow,
    volatility_gate_reference,
)


def _write_ohlcv(db_path: Path, closes: pd.Series, ticker: str = "0050.TW") -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = [(ticker, str(dt.date()), float(price)) for dt, price in closes.items()]
        con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)
        # _load_chip_features' smart-money-cost proxy now guards these with
        # _table_exists (2026-07-06 fix; see
        # test_missing_institutional_and_margin_tables_reports_unavailable_without_raising
        # below for the case where they're absent entirely) -- included here
        # anyway so these tests exercise the common with-both-tables path.
        con.execute(
            "CREATE TABLE institutional_data ("
            "ticker VARCHAR, dt DATE, institutional_total_net_buy DOUBLE, foreign_net_buy DOUBLE)"
        )
        con.execute(
            "CREATE TABLE margin_data (ticker VARCHAR, dt DATE, margin_balance DOUBLE, margin_buy DOUBLE, margin_sell DOUBLE)"
        )
    finally:
        con.close()


def _calm_uptrend_closes(n: int = 1000, as_of: str = "2026-07-03") -> pd.Series:
    rng = np.random.default_rng(7)
    end = pd.Timestamp(as_of)
    dates = pd.bdate_range(end=end, periods=n)
    daily_returns = rng.normal(loc=0.0004, scale=0.006, size=n)
    prices = 100.0 * np.cumprod(1.0 + daily_returns)
    return pd.Series(prices, index=dates)


def _closes_with_late_crash(n: int = 1000, as_of: str = "2026-07-03") -> pd.Series:
    closes = _calm_uptrend_closes(n=n, as_of=as_of)
    # copy=True: pandas 3.x's copy-on-write returns a read-only view from
    # to_numpy() when no copy is otherwise needed, since the dtype already
    # matches -- this array is mutated in place below, so it must be a real
    # copy, not a view.
    values = closes.to_numpy(dtype=float, copy=True)
    # Force a sharp, sustained sell-off into the last week so the GARCH-proxy
    # vol ratio/percentile and the 5d return both cross the frozen shadow
    # thresholds (ratio>=1.05 or percentile>=0.70, AND return_5d<0).
    crash_returns = [-0.06, -0.05, -0.05, -0.04, -0.03]
    for i, ret in enumerate(crash_returns):
        idx = len(values) - len(crash_returns) + i
        values[idx] = values[idx - 1] * (1.0 + ret)
    return pd.Series(values, index=closes.index)


class TestComputeGarchRegimeShadow(unittest.TestCase):
    def test_calm_market_does_not_flag_high_vol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            closes = _calm_uptrend_closes()
            _write_ohlcv(db_path, closes)

            shadow = compute_garch_regime_shadow(db_path, pd.Timestamp("2026-07-03"))

        self.assertEqual("available", shadow["status"])
        self.assertEqual("shadow_only_no_weight_change", shadow["policy"])
        self.assertFalse(shadow["high_vol_flag"])
        self.assertEqual("a207", shadow["selected_rule"])
        self.assertEqual(shadow["a207_regime"], shadow["shadow_selected_regime"])
        self.assertEqual("shadow_only_no_weight_change", shadow["volatility_gate"]["policy"])
        self.assertIn(shadow["volatility_gate"]["gate"], {"low_vol_participation", "neutral_vol"})

    def test_late_crash_flags_high_vol_and_selects_ma20(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            closes = _closes_with_late_crash()
            _write_ohlcv(db_path, closes)

            shadow = compute_garch_regime_shadow(db_path, pd.Timestamp("2026-07-03"))

        self.assertEqual("available", shadow["status"])
        self.assertTrue(shadow["high_vol_flag"])
        self.assertLess(shadow["return_0050_5d"], 0.0)
        self.assertEqual("ma20", shadow["selected_rule"])
        self.assertEqual(shadow["ma20_regime"], shadow["shadow_selected_regime"])
        self.assertEqual("high_vol_defensive", shadow["volatility_gate"]["gate"])
        self.assertTrue(shadow["volatility_gate"]["high_vol_gate"])
        self.assertFalse(shadow["volatility_gate"]["low_vol_gate"])
        self.assertEqual(0.5, shadow["volatility_gate"]["reference_00631l_scale"])

    def test_no_rows_in_lookback_window_reports_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            # Price history exists but entirely predates the lookback window
            # for the requested as_of date -- _load_prices finds zero rows.
            closes = _calm_uptrend_closes(n=20, as_of="2018-01-10")
            _write_ohlcv(db_path, closes)

            shadow = compute_garch_regime_shadow(db_path, pd.Timestamp("2026-07-03"))

        self.assertEqual("unavailable", shadow["status"])

    def test_missing_db_reports_unavailable_without_raising(self) -> None:
        shadow = compute_garch_regime_shadow(Path("/nonexistent/db.duckdb"), pd.Timestamp("2026-07-03"))
        self.assertEqual("unavailable", shadow["status"])

    def test_missing_institutional_and_margin_tables_reports_unavailable_without_raising(self) -> None:
        # 2026-07-06 fix: _attach_smart_money_cost_proxy used to unconditionally
        # LEFT JOIN institutional_data/margin_data with no _table_exists guard
        # (unlike every other chip source), so a db file missing those tables
        # entirely raised a duckdb CatalogException instead of degrading --
        # which, per this module's own docstring contract, must never
        # propagate out and break the day's real live signal.
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                closes = _calm_uptrend_closes()
                rows = [("0050.TW", str(dt.date()), float(price)) for dt, price in closes.items()]
                con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)
            finally:
                con.close()

            shadow = compute_garch_regime_shadow(db_path, pd.Timestamp("2026-07-03"))

        self.assertEqual("available", shadow["status"])


class TestVolatilityGateReference(unittest.TestCase):
    def test_low_vol_gate_allows_participation_reference(self) -> None:
        gate = volatility_gate_reference(
            high_vol=False,
            ratio=0.92,
            percentile=0.25,
            return_5d=0.01,
        )

        self.assertEqual("shadow_only_no_weight_change", gate["policy"])
        self.assertEqual("low_vol_participation", gate["gate"])
        self.assertTrue(gate["low_vol_gate"])
        self.assertFalse(gate["high_vol_gate"])
        self.assertEqual(1.0, gate["reference_00631l_scale"])

    def test_neutral_vol_requires_calibration_reference(self) -> None:
        gate = volatility_gate_reference(
            high_vol=False,
            ratio=1.02,
            percentile=0.55,
            return_5d=0.02,
        )

        self.assertEqual("neutral_vol", gate["gate"])
        self.assertFalse(gate["low_vol_gate"])
        self.assertFalse(gate["high_vol_gate"])
        self.assertEqual("calibrate_thresholds", gate["signal_reliability"])
        self.assertEqual(0.75, gate["reference_00631l_scale"])

    def test_high_vol_gate_suppresses_return_prediction_reference(self) -> None:
        gate = volatility_gate_reference(
            high_vol=True,
            ratio=1.3,
            percentile=0.9,
            return_5d=-0.04,
        )

        self.assertEqual("high_vol_defensive", gate["gate"])
        self.assertFalse(gate["low_vol_gate"])
        self.assertTrue(gate["high_vol_gate"])
        self.assertEqual("suppress_return_prediction", gate["signal_reliability"])
        self.assertEqual(0.5, gate["reference_00631l_scale"])


class TestAppendGarchRegimeShadowLog(unittest.TestCase):
    def test_appends_and_is_idempotent_per_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "garch_regime_shadow_log.jsonl"
            day1 = {"status": "available", "date": "2026-07-01", "selected_rule": "a207"}
            day2 = {"status": "available", "date": "2026-07-02", "selected_rule": "ma20"}
            day1_rerun = {"status": "available", "date": "2026-07-01", "selected_rule": "ma20"}

            append_garch_regime_shadow_log(log_path, day1, execution_regime="golden1")
            append_garch_regime_shadow_log(log_path, day2, execution_regime="golden1")
            append_garch_regime_shadow_log(log_path, day1_rerun, execution_regime="golden1")

            lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(2, len(lines))
        by_date = {row["date"]: row for row in lines}
        self.assertEqual("ma20", by_date["2026-07-01"]["selected_rule"])
        self.assertEqual("ma20", by_date["2026-07-02"]["selected_rule"])
        self.assertEqual("golden1", by_date["2026-07-01"]["logged_execution_regime"])

    def test_unavailable_shadow_is_not_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "garch_regime_shadow_log.jsonl"
            append_garch_regime_shadow_log(log_path, {"status": "unavailable", "reason": "x"})
            self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
