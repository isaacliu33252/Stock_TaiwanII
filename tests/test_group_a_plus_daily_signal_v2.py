#!/usr/bin/env python3
"""Regression checks for the schema-v2 daily GroupA+ signal."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from group_a_plus.operations.daily_signal import (
    TAIWAN_MARKET_HOLIDAYS,
    _a2118_live_hard_overlay_reason,
    _a2118_live_hard_overlay_weights,
    _a2118_live_signal_is_current,
    _apply_bearish_high_risk_trim,
    _business_days_between,
    _previous_a2118_hold_active,
    _resolve_weights,
    _source_freshness,
    _tbrain_shadow_snapshot,
)


class DailySignalV2Tests(unittest.TestCase):
    def test_weekend_staleness_counts_weekdays_only(self) -> None:
        self.assertEqual(_business_days_between("2026-06-11", "2026-06-13"), 1)

    def test_taiwan_holiday_is_not_counted_as_stale_day(self) -> None:
        self.assertEqual(_business_days_between("2026-06-18", "2026-06-22"), 1)

    def test_taiwan_market_holidays_cover_more_than_one_date(self) -> None:
        """M5 (2026-07-02 Fable 5 audit): previously only 2026-06-19 was
        listed. Lock in that the calendar now spans both 2025 and 2026 and
        includes the major holiday clusters (Lunar New Year, National Day)."""
        self.assertGreater(len(TAIWAN_MARKET_HOLIDAYS), 1)
        assert pd.Timestamp("2025-01-01") in TAIWAN_MARKET_HOLIDAYS
        assert pd.Timestamp("2026-01-01") in TAIWAN_MARKET_HOLIDAYS
        assert pd.Timestamp("2026-02-17") in TAIWAN_MARKET_HOLIDAYS  # Lunar New Year 2026
        assert pd.Timestamp("2026-10-09") in TAIWAN_MARKET_HOLIDAYS  # National Day (observed)

    def test_national_day_2026_not_counted_as_stale_day(self) -> None:
        # 2026-10-09 (Fri, observed National Day) is excluded from the
        # weekday count; 2026-10-08 (Thu) and 2026-10-12 (Mon) still count.
        self.assertEqual(_business_days_between("2026-10-07", "2026-10-08"), 1)
        self.assertEqual(_business_days_between("2026-10-07", "2026-10-12"), 2)

    def test_resolve_weights_supports_three_regime_a213(self) -> None:
        report = {
            "weights": {
                "group_a_plus_recovery": {"0050.TW": 0.7, "cash": 0.3},
            }
        }

        weights = _resolve_weights(report, "group_a_plus_recovery")

        self.assertAlmostEqual(weights["0050.TW"], 0.7)
        self.assertAlmostEqual(weights["cash"], 0.3)

    def test_resolve_weights_supports_legacy_alias(self) -> None:
        report = {"weights": {"golden1_0531_1m": {"0050.TW": 0.6, "cash": 0.4}}}

        weights = _resolve_weights(report, "golden1")

        self.assertAlmostEqual(weights["0050.TW"], 0.6)
        self.assertAlmostEqual(weights["cash"], 0.4)

    def test_a2118_live_signal_current_guard_rejects_stale_signal(self) -> None:
        self.assertTrue(
            _a2118_live_signal_is_current(
                {"status": "ok", "signal_date": "2026-06-29"},
                pd.Timestamp("2026-06-29"),
            )
        )
        self.assertFalse(
            _a2118_live_signal_is_current(
                {"status": "stale", "signal_date": "2026-06-29"},
                pd.Timestamp("2026-06-29"),
            )
        )
        self.assertFalse(
            _a2118_live_signal_is_current(
                {"status": "ok", "signal_date": "2026-06-18"},
                pd.Timestamp("2026-06-29"),
            )
        )

    def test_previous_a2118_hold_active_requires_prior_date(self) -> None:
        previous = {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-06-28",
            "ncf_live_overlay": {"a2118_late_bull_hard_overlay_applied": True},
        }

        self.assertTrue(_previous_a2118_hold_active(previous, pd.Timestamp("2026-06-29")))
        self.assertFalse(_previous_a2118_hold_active(previous, pd.Timestamp("2026-06-28")))

    def test_previous_a2118_hold_active_rejects_payload_older_than_panel(self) -> None:
        previous = {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-06-28",
            "ncf_live_overlay": {"a2118_late_bull_hard_overlay_applied": True},
            "_payload_metadata": {"timestamp": "2026-06-30T15:19:17"},
        }

        self.assertFalse(
            _previous_a2118_hold_active(
                previous,
                pd.Timestamp("2026-06-29"),
                min_generated_at=datetime.fromisoformat("2026-06-30T16:56:59"),
            )
        )
        self.assertTrue(
            _previous_a2118_hold_active(
                previous,
                pd.Timestamp("2026-06-29"),
                min_generated_at=datetime.fromisoformat("2026-06-30T15:00:00"),
            )
        )

    def test_a2118_overlay_reason_rally_suppressed_does_not_trigger(self) -> None:
        """M4 (2026-07-02 Fable 5 audit): if rally_suppress_min is ever
        enabled, a rally-suppressed trigger day must not apply hard-hedge
        weights via the "trigger" reason (effective_hedge_active=False)."""
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {
                "status": "ok",
                "signal_date": "2026-06-29",
                "late_bull_triggered": True,
                "rally_suppressed": True,
                "effective_hedge_active": False,
                "h5_prob_up": 0.30,
            },
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="golden1",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=None,
        )

        self.assertIsNone(reason)

    def test_a2118_overlay_reason_trigger_takes_precedence(self) -> None:
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {
                "status": "ok",
                "signal_date": "2026-06-29",
                "late_bull_triggered": True,
                "h5_prob_up": 0.30,
            },
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="golden1",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=None,
        )

        self.assertEqual("trigger", reason)

    def test_a2118_overlay_reason_extends_hold_until_h5_reentry(self) -> None:
        previous = {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-06-28",
            "ncf_live_overlay": {"a2118_late_bull_hard_overlay_applied": True},
        }
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {
                "status": "ok",
                "signal_date": "2026-06-29",
                "late_bull_triggered": False,
                "h5_prob_up": 0.54,
            },
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="golden1",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=previous,
        )

        self.assertEqual("h5_hold", reason)

    def test_a2118_h5_hold_uses_hard_hedge_weights(self) -> None:
        report = {
            "base_weights": {
                "golden1": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
                "ncf_late_bull_hedge": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            },
            "ncf_live_signal": {
                "effective_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            },
        }

        weights = _a2118_live_hard_overlay_weights(report, "h5_hold")

        self.assertAlmostEqual(0.70, weights["0050.TW"])
        self.assertAlmostEqual(0.10, weights["00631L.TW"])
        self.assertAlmostEqual(0.20, weights["cash"])

    def test_a2118_overlay_reason_fails_closed_when_signal_stale_and_hold_was_active(self) -> None:
        """H5 (2026-07-02 Fable 5 audit): NCF stale + a hedge was active
        yesterday must preserve the hedge, not silently revert to golden1."""
        previous = {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-06-28",
            "ncf_live_overlay": {"a2118_late_bull_hard_overlay_applied": True},
        }
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {"status": "stale", "signal_date": "2026-06-29"},
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="golden1",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=previous,
        )

        self.assertEqual("stale_fail_closed", reason)

    def test_a2118_overlay_reason_stale_with_no_prior_hold_stays_none(self) -> None:
        """Fail-closed only kicks in when there's something to preserve --
        stale NCF with no prior hedge active must not fabricate one."""
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {"status": "stale", "signal_date": "2026-06-29"},
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="golden1",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=None,
        )

        self.assertIsNone(reason)

    def test_a2118_stale_fail_closed_uses_hard_hedge_weights(self) -> None:
        report = {
            "base_weights": {
                "golden1": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
                "ncf_late_bull_hedge": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            },
        }

        weights = _a2118_live_hard_overlay_weights(report, "stale_fail_closed")

        self.assertAlmostEqual(0.70, weights["0050.TW"])
        self.assertAlmostEqual(0.10, weights["00631L.TW"])
        self.assertAlmostEqual(0.20, weights["cash"])

    def test_a2118_overlay_reason_exits_when_h5_recovers(self) -> None:
        previous = {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-06-28",
            "ncf_live_overlay": {"a2118_late_bull_hard_overlay_applied": True},
        }
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {
                "status": "ok",
                "signal_date": "2026-06-29",
                "late_bull_triggered": False,
                "h5_prob_up": 0.56,
            },
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="golden1",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=previous,
        )

        self.assertIsNone(reason)

    def test_a2118_overlay_reason_not_used_when_regime_already_hedged(self) -> None:
        report = {
            "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "ncf_live_signal": {
                "status": "ok",
                "signal_date": "2026-06-29",
                "late_bull_triggered": True,
                "h5_prob_up": 0.35,
            },
            "rules": {"ncf_late_bull_h5_reentry_min": 0.55},
        }

        reason = _a2118_live_hard_overlay_reason(
            report=report,
            execution_regime="ncf_late_bull_hedge",
            actual_date=pd.Timestamp("2026-06-29"),
            previous_signal=None,
        )

        self.assertIsNone(reason)

    def test_bearish_high_risk_trim_reduces_00631l(self) -> None:
        weights, overlay = _apply_bearish_high_risk_trim(
            {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            {"total_risk_score": 10},
            {"alignment": "wide_divergence", "dominant_direction": "bearish"},
            {
                "current_regime": "golden1",
                "base_golden1_weights": {"00631L.TW": 0.10},
                "adjusted_golden1_weights": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            },
        )

        self.assertTrue(overlay["bearish_high_risk_trim_applied"])
        self.assertAlmostEqual(0.07, weights["00631L.TW"])
        self.assertAlmostEqual(0.23, weights["cash"])
        self.assertAlmostEqual(1.0, sum(weights.values()))

    def test_bearish_high_risk_trim_ignores_low_risk(self) -> None:
        weights, overlay = _apply_bearish_high_risk_trim(
            {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            {"total_risk_score": 5},
            {"alignment": "wide_divergence", "dominant_direction": "bearish"},
            {"current_regime": "golden1"},
        )

        self.assertAlmostEqual(0.10, weights["00631L.TW"])
        self.assertNotIn("bearish_high_risk_trim_applied", overlay)

    def test_optional_source_freshness_aligns_to_actual_price_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                for ticker in TICKERS:
                    con.execute("INSERT INTO ohlcv VALUES (?, ?, ?)", [ticker, "2026-06-26", 100.0])
                con.execute("CREATE TABLE dealer_futures_data (dt DATE, futures_id VARCHAR, is_after_hour INTEGER)")
                con.execute("CREATE TABLE dealer_options_data (dt DATE, option_id VARCHAR, is_after_hour INTEGER)")
                con.execute("INSERT INTO dealer_futures_data VALUES (?, ?, ?)", ["2026-06-24", "TX", 0])
                con.execute("INSERT INTO dealer_options_data VALUES (?, ?, ?)", ["2026-06-24", "TXO", 0])
            finally:
                con.close()

            freshness = _source_freshness(
                db_path,
                pd.Timestamp("2026-06-30"),
                pd.Timestamp("2026-06-26"),
            )

        self.assertEqual("2026-06-26", freshness["optional_sources"]["dealer_tx"]["freshness_as_of"])
        self.assertEqual(2, freshness["optional_sources"]["dealer_tx"]["business_stale_days"])
        self.assertEqual("ok", freshness["optional_sources"]["dealer_tx"]["status"])
        self.assertEqual("ok", freshness["optional_sources"]["dealer_txo"]["status"])

    def test_t_plus_one_chip_sources_are_allowed_but_t_plus_two_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                for ticker in TICKERS:
                    con.execute("INSERT INTO ohlcv VALUES (?, ?, ?)", [ticker, "2026-07-02", 100.0])
                con.execute("CREATE TABLE foreign_shareholding_data (ticker VARCHAR, dt DATE)")
                con.execute("INSERT INTO foreign_shareholding_data VALUES (?, ?)", ["0050.TW", "2026-07-01"])
            finally:
                con.close()

            freshness = _source_freshness(
                db_path,
                pd.Timestamp("2026-07-02"),
                pd.Timestamp("2026-07-02"),
            )

            self.assertEqual("ok", freshness["optional_sources"]["foreign_shareholding_0050"]["status"])
            self.assertEqual(1, freshness["optional_sources"]["foreign_shareholding_0050"]["business_stale_days"])

            con = duckdb.connect(str(db_path))
            try:
                con.execute("DELETE FROM foreign_shareholding_data")
                con.execute("INSERT INTO foreign_shareholding_data VALUES (?, ?)", ["0050.TW", "2026-06-30"])
            finally:
                con.close()

            stale_freshness = _source_freshness(
                db_path,
                pd.Timestamp("2026-07-02"),
                pd.Timestamp("2026-07-02"),
            )

        self.assertEqual("block", stale_freshness["optional_sources"]["foreign_shareholding_0050"]["status"])
        self.assertEqual(2, stale_freshness["optional_sources"]["foreign_shareholding_0050"]["business_stale_days"])

    def test_tbrain_shadow_snapshot_reads_latest_0050_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute(
                    "CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)"
                )
                for i, dt in enumerate(pd.bdate_range("2025-01-01", periods=150)):
                    close = 100.0 + i
                    con.execute(
                        "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ["0050.TW", str(dt.date()), close - 0.2, close + 1.0, close - 1.0, close, 1_000_000 + i],
                    )
            finally:
                con.close()

            snapshot = _tbrain_shadow_snapshot(db_path, pd.Timestamp("2025-07-29"))

        self.assertEqual("available", snapshot["status"])
        self.assertEqual("0050.TW", snapshot["ticker"])
        self.assertIn("tbrain_close_ma22_loc", snapshot["features"])


if __name__ == "__main__":
    unittest.main()
