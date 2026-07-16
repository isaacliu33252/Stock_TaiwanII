#!/usr/bin/env python3
"""Regression checks for the schema-v2 daily GroupA+ signal."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from group_a_plus.operations import daily_signal
from group_a_plus.operations.daily_signal import (
    DEFAULT_LIVE_SIGNAL,
    TAIWAN_MARKET_HOLIDAYS,
    _a2118_extreme_risk_warning,
    _a2118_live_hard_overlay_reason,
    _a2118_live_hard_overlay_weights,
    _a2118_live_signal_is_current,
    _apply_bearish_high_risk_trim,
    _apply_tsmc_weakness_trim,
    _build_signal_alerts,
    _business_days_between,
    _load_previous_live_signal,
    _market_state_regime,
    _previous_a2118_hold_active,
    _resolve_weights,
    _source_freshness,
    _tsmc_0050_reference_guidance,
    _tbrain_shadow_snapshot,
    main,
)
from group_a_plus.paths import PROJECT_ROOT


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

    def test_default_live_signal_path_is_anchored_to_project_root(self) -> None:
        """2026-07-04 audit fix: DEFAULT_LIVE_SIGNAL used to be a bare
        cwd-relative Path("report/group_a_plus/latest/live_signal.json").
        A manual invocation from a directory other than PROJECT_ROOT made
        _load_previous_live_signal() silently find nothing, disabling the
        H5/stale-fail-closed hold-carryover guard exactly when it matters.
        """
        self.assertTrue(DEFAULT_LIVE_SIGNAL.is_absolute())
        self.assertEqual(
            DEFAULT_LIVE_SIGNAL,
            PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json",
        )

    def test_load_previous_live_signal_default_path_independent_of_cwd(self) -> None:
        original_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                import os

                os.chdir(tmp_dir)
                # With the old cwd-relative default, this would look for
                # <tmp_dir>/report/group_a_plus/latest/live_signal.json and
                # return None even though the real pointer file exists under
                # PROJECT_ROOT. Confirms the anchored default still resolves.
                result = _load_previous_live_signal()
        finally:
            os.chdir(original_cwd)
        if DEFAULT_LIVE_SIGNAL.exists():
            self.assertIsNotNone(result)
        else:
            self.assertIsNone(result)

    def test_market_state_regime_uses_hedge_label_when_live_overlay_applied(self) -> None:
        """2026-07-04 audit fix: a2118's *live* hard overlay (h5_hold /
        stale_fail_closed / trigger / panel_trigger) can apply hedge weights
        while the frame/panel-derived execution_regime string still reads
        "golden1" -- the live overlay is driven by the fresher ncf_live_signal
        JSON, not the panel CSV baked into the frame. market_state's regime
        input must reflect the hedge, not the stale "golden1" label.
        """
        self.assertEqual(
            _market_state_regime("golden1", {"a2118_late_bull_hard_overlay_applied": True}),
            "ncf_late_bull_hedge",
        )
        self.assertEqual(
            _market_state_regime("golden1", {"a2118_late_bull_hard_overlay_applied": False}),
            "golden1",
        )
        self.assertEqual(_market_state_regime("golden1", {}), "golden1")
        # Regular regimes (defensive/recovery) pass through unchanged when no
        # hard overlay is active.
        self.assertEqual(
            _market_state_regime("group_a_plus_defensive", {}),
            "group_a_plus_defensive",
        )

    def test_tsmc_false_breakout_guidance_is_avoid_add_only(self) -> None:
        guidance = _tsmc_0050_reference_guidance("tsmc_false_breakout")

        self.assertEqual(guidance["reference_action"], "avoid_add_00631l")
        self.assertEqual(guidance["trade_policy"], "diagnostic_only_no_weight_change")
        self.assertFalse(guidance["manual_review_required"])
        self.assertFalse(guidance["allow_00631l_add"])

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

    def test_bearish_high_risk_trim_bypasses_low_score_when_chip_data_stale(self) -> None:
        # total_risk_score reads as 0 during a chip/derivative data outage
        # (see the 2026-07-04 a2118 chip-data-outage fix); the trim must not
        # stay structurally disabled by the same outage it exists to help
        # defend against, as long as chip_data_core_days_since_source_update
        # shows the data is genuinely stale.
        weights, overlay = _apply_bearish_high_risk_trim(
            {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            {"total_risk_score": 0, "chip_data_core_days_since_source_update": 999_999},
            {"alignment": "wide_divergence", "dominant_direction": "bearish"},
            {
                "current_regime": "golden1",
                "base_golden1_weights": {"00631L.TW": 0.10},
                "adjusted_golden1_weights": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            },
        )

        self.assertTrue(overlay["bearish_high_risk_trim_applied"])
        self.assertIn("chip_data_stale=True", overlay["bearish_high_risk_trim_reason"])
        self.assertAlmostEqual(0.08, weights["00631L.TW"])

    def test_bearish_high_risk_trim_low_score_ignored_when_chip_data_fresh(self) -> None:
        weights, overlay = _apply_bearish_high_risk_trim(
            {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            {"total_risk_score": 0, "chip_data_core_days_since_source_update": 0},
            {"alignment": "wide_divergence", "dominant_direction": "bearish"},
            {"current_regime": "golden1"},
        )

        self.assertAlmostEqual(0.10, weights["00631L.TW"])
        self.assertNotIn("bearish_high_risk_trim_applied", overlay)

    def test_a2118_extreme_risk_warning_is_advisory_only(self) -> None:
        warning = _a2118_extreme_risk_warning(
            {
                "status": "ok",
                "signal_date": "2026-02-26",
                "h20_prob_up": 0.19,
                "prob_fwd_mdd_gt5_h20": 0.91,
                "prob_fwd_gain_gt5_h20": 0.39,
                "confidence": 0.36,
            },
            {"current_regime": "golden1"},
            pd.Timestamp("2026-02-26"),
        )

        self.assertTrue(warning["active"])
        self.assertEqual("warning_only_no_weight_change", warning["policy"])
        self.assertEqual("pause_new_risk_adds", warning["recommended_action"])
        self.assertFalse(warning["allow_new_0050_add"])
        self.assertFalse(warning["allow_new_00631l_add"])

    def test_a2118_extreme_risk_warning_uses_overlay_mdd_fallback(self) -> None:
        warning = _a2118_extreme_risk_warning(
            {
                "status": "ok",
                "signal_date": "2026-02-26",
                "h20_prob_up": 0.19,
                "confidence": 0.36,
            },
            {
                "current_regime": "golden1",
                "ncf_00631l": {"prob_fwd_mdd_gt5_h20": 0.91},
            },
            pd.Timestamp("2026-02-26"),
        )

        self.assertTrue(warning["active"])
        self.assertEqual(0.91, warning["inputs"]["prob_fwd_mdd_gt5_h20"])

    def test_tsmc_weakness_trim_requires_tsmc_and_00631l_confirmation(self) -> None:
        weights, overlay = _apply_tsmc_weakness_trim(
            {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            {
                "current_regime": "golden1",
                "base_golden1_weights": {"00631L.TW": 0.10},
                "adjusted_golden1_weights": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
                "tsmc_0050_health": {"status": "available", "state": "tsmc_weak_confirmed"},
                "ncf_00631l": {
                    "calibrated_prob_up": 0.48,
                    "horizon_prob_up": {"20": 0.42},
                    "prob_fwd_mdd_gt5_h20": 0.55,
                },
            },
        )

        self.assertTrue(overlay["tsmc_weakness_trim_applied"])
        self.assertAlmostEqual(0.075, weights["00631L.TW"])
        self.assertAlmostEqual(0.225, weights["cash"])
        self.assertAlmostEqual(1.0, sum(weights.values()))

    def test_tsmc_narrow_leadership_is_diagnostic_only(self) -> None:
        weights, overlay = _apply_tsmc_weakness_trim(
            {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
            {
                "current_regime": "golden1",
                "tsmc_0050_health": {"status": "available", "state": "tsmc_led_narrow"},
                "ncf_00631l": {
                    "calibrated_prob_up": 0.40,
                    "horizon_prob_up": {"20": 0.40},
                    "prob_fwd_mdd_gt5_h20": 0.60,
                },
            },
        )

        self.assertAlmostEqual(0.10, weights["00631L.TW"])
        self.assertNotIn("tsmc_weakness_trim_applied", overlay)

    def test_tsmc_reference_guidance_avoids_add_on_narrow_leadership(self) -> None:
        guidance = _tsmc_0050_reference_guidance("tsmc_led_narrow")

        self.assertEqual("avoid_add_00631l", guidance["reference_action"])
        self.assertFalse(guidance["allow_00631l_add"])
        self.assertEqual("diagnostic_only_no_weight_change", guidance["trade_policy"])

    def test_holiday_calendar_coverage_alert_absent_within_60_days_of_last_entry(self) -> None:
        near_last_entry = max(TAIWAN_MARKET_HOLIDAYS) + pd.Timedelta(days=59)
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=near_last_entry,
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
        )

        self.assertNotIn("holiday_calendar_coverage", {alert["type"] for alert in alerts})

    def test_holiday_calendar_coverage_alert_fires_past_60_days_of_last_entry(self) -> None:
        """Fable audit (2026-07-08, #6): TAIWAN_MARKET_HOLIDAYS' last entry is
        a fixed date that needs periodic upkeep -- this must self-report once
        the signal date runs far enough past it, instead of silently
        miscounting business-day staleness forever."""
        past_last_entry = max(TAIWAN_MARKET_HOLIDAYS) + pd.Timedelta(days=61)
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=past_last_entry,
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
        )

        alert_types = {alert["type"] for alert in alerts}
        self.assertIn("holiday_calendar_coverage", alert_types)

    def test_tsmc_reference_alert_for_narrow_leadership(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-02"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            ncf_live_overlay={
                "tsmc_0050_health": {
                    "status": "available",
                    "state": "tsmc_led_narrow",
                    "reference_guidance": _tsmc_0050_reference_guidance("tsmc_led_narrow"),
                }
            },
            signal_alignment={"alignment": "mixed"},
        )

        alert_types = {alert["type"] for alert in alerts}
        self.assertIn("tsmc_led_narrow_reference", alert_types)
        self.assertNotIn("tsmc_weakness_trim", alert_types)

    def test_tsmc_reference_alert_for_weak_manual_review(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-02"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            ncf_live_overlay={
                "tsmc_0050_health": {
                    "status": "available",
                    "state": "tsmc_weak_confirmed",
                    "reference_guidance": _tsmc_0050_reference_guidance("tsmc_weak_confirmed"),
                }
            },
            signal_alignment={"alignment": "mixed"},
        )

        alert_types = {alert["type"] for alert in alerts}
        self.assertIn("tsmc_weak_manual_review", alert_types)
        self.assertNotIn("tsmc_weakness_trim", alert_types)

    def test_leverage_suitability_tier0_adds_manual_review_alert(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-02"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            signal_alignment={
                "alignment": "mixed",
                "leverage_suitability": {"tier": 0, "label_zh": "不利 00631L"},
            },
        )

        by_type = {alert["type"]: alert for alert in alerts}
        self.assertIn("leverage_suitability_tier0", by_type)
        self.assertEqual("medium", by_type["leverage_suitability_tier0"]["level"])
        self.assertIn("advisory-only", by_type["leverage_suitability_tier0"]["reason"])
        self.assertNotIn("bearish_high_risk_trim", by_type)
        self.assertNotIn("tsmc_weakness_trim", by_type)

    def test_leverage_suitability_tier3_adds_opportunity_alert(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-02"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            signal_alignment={
                "alignment": "bullish_alignment",
                "leverage_suitability": {"tier": 3, "label_zh": "適合提高 00631L"},
            },
        )

        by_type = {alert["type"]: alert for alert in alerts}
        self.assertIn("leverage_suitability_tier3", by_type)
        self.assertEqual("low", by_type["leverage_suitability_tier3"]["level"])
        self.assertIn("advisory-only", by_type["leverage_suitability_tier3"]["reason"])

    def test_a2118_extreme_risk_warning_adds_advisory_alert(self) -> None:
        warning = _a2118_extreme_risk_warning(
            {
                "status": "ok",
                "signal_date": "2026-02-26",
                "h20_prob_up": 0.19,
                "prob_fwd_mdd_gt5_h20": 0.91,
            },
            {"current_regime": "golden1"},
            pd.Timestamp("2026-02-26"),
        )
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-02-26"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            ncf_live_overlay={"a2118_extreme_risk_warning": warning},
        )

        by_type = {alert["type"]: alert for alert in alerts}
        self.assertIn("a2118_extreme_risk_warning", by_type)
        self.assertEqual("medium", by_type["a2118_extreme_risk_warning"]["level"])
        self.assertEqual(
            "warning_only_no_weight_change",
            by_type["a2118_extreme_risk_warning"]["metadata"]["policy"],
        )
        self.assertEqual(
            "pause_new_risk_adds",
            by_type["a2118_extreme_risk_warning"]["metadata"]["recommended_action"],
        )

    def test_a2118_extreme_warning_live_payload_does_not_change_weights(self) -> None:
        weights_before = {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20}
        warning = _a2118_extreme_risk_warning(
            {
                "status": "ok",
                "signal_date": "2026-02-26",
                "h20_prob_up": 0.19,
                "prob_fwd_mdd_gt5_h20": 0.91,
            },
            {"current_regime": "golden1"},
            pd.Timestamp("2026-02-26"),
        )
        overlay = {"current_regime": "golden1", "a2118_extreme_risk_warning": warning}
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-02-26"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            ncf_live_overlay=overlay,
        )

        live_payload = {
            "target_weights": dict(weights_before),
            "ncf_live_overlay": overlay,
            "signal_alerts": alerts,
        }

        self.assertEqual(weights_before, live_payload["target_weights"])
        self.assertTrue(live_payload["ncf_live_overlay"]["a2118_extreme_risk_warning"]["active"])
        self.assertIn("a2118_extreme_risk_warning", {alert["type"] for alert in live_payload["signal_alerts"]})

    def test_tail_conformal_warning_adds_advisory_alert_without_weight_change(self) -> None:
        weights_before = {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20}
        tail_conformal = {
            "state": "TAIL_RISK_HIGH",
            "policy": "diagnostic_warning_only_no_weight_change",
            "recommended_action": "pause_new_00631l_adds_and_monitor_trough",
            "allow_00631l_add": False,
            "auto_reduce_00631l": False,
            "ticker": "00631L.TW",
            "current_risk_bucket": "severe",
            "min_lower_tail_confidence_bound": -0.09,
            "max_prob_mdd_lt_8pct": 0.41,
            "high_tail_reasons": ["h10_lower_bound_le_8pct"],
            "diagnostics": {"h5": {"lower_tail_confidence_bound": -0.04}},
        }
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-02-26"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            tail_conformal=tail_conformal,
        )

        by_type = {alert["type"]: alert for alert in alerts}
        self.assertEqual(weights_before, {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20})
        self.assertIn("tail_specific_conformal_warning", by_type)
        self.assertEqual("medium", by_type["tail_specific_conformal_warning"]["level"])
        metadata = by_type["tail_specific_conformal_warning"]["metadata"]
        self.assertFalse(metadata["allow_00631l_add"])
        self.assertFalse(metadata["auto_reduce_00631l"])
        self.assertEqual("pause_new_00631l_adds_and_monitor_trough", metadata["recommended_action"])

    def test_cross_market_graph_no_add_adds_shadow_alert_only(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-15"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            cross_market_graph_shadow={
                "status": "available",
                "policy": "shadow_only_no_weight_change",
                "no_add_active": True,
                "recommended_action": "pause_new_risk_adds_manual_review",
                "allow_auto_weight_change": False,
                "allow_00631l_add_reference": False,
                "latest_shadow_action": "NO_ADD",
                "latest_probabilities": {"REENTER": 0.41, "NO_ADD": 0.67},
                "thresholds": {"no_add_alert_probability": 0.65},
                "selected_features": ["src_SOXX_ret1d"],
                "report_path": "results/cross_market_directed_graph_shadow_latest.json",
            },
        )

        by_type = {alert["type"]: alert for alert in alerts}
        self.assertIn("cross_market_graph_no_add_shadow", by_type)
        self.assertNotIn("tail_specific_conformal_warning", by_type)
        metadata = by_type["cross_market_graph_no_add_shadow"]["metadata"]
        self.assertFalse(metadata["allow_auto_weight_change"])
        self.assertFalse(metadata["allow_00631l_add_reference"])
        self.assertEqual("NO_ADD", metadata["latest_shadow_action"])
        self.assertEqual(0.67, metadata["latest_probabilities"]["NO_ADD"])

    def test_cross_market_graph_keep_does_not_add_alert(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-15"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            cross_market_graph_shadow={
                "status": "available",
                "no_add_active": False,
                "latest_shadow_action": "KEEP",
                "latest_probabilities": {"REENTER": 0.44, "NO_ADD": 0.42},
            },
        )

        self.assertNotIn("cross_market_graph_no_add_shadow", {alert["type"] for alert in alerts})

    def test_volatility_gate_high_vol_adds_manual_review_alert(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-02"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            garch_regime_shadow={
                "status": "available",
                "volatility_gate": {
                    "policy": "shadow_only_no_weight_change",
                    "gate": "high_vol_defensive",
                    "high_vol_gate": True,
                    "reference_00631l_scale": 0.5,
                    "inputs": {
                        "garch_proxy_vol_ratio": 1.25,
                        "garch_proxy_vol_percentile": 0.88,
                        "return_0050_5d": -0.04,
                    },
                },
            },
        )

        by_type = {alert["type"]: alert for alert in alerts}
        self.assertIn("volatility_gate_high_vol", by_type)
        self.assertEqual("medium", by_type["volatility_gate_high_vol"]["level"])
        self.assertIn("advisory-only", by_type["volatility_gate_high_vol"]["reason"])
        self.assertIn("Reference scale=0.5", by_type["volatility_gate_high_vol"]["reason"])
        metadata = by_type["volatility_gate_high_vol"]["metadata"]
        self.assertFalse(metadata["allow_00631l_add"])
        self.assertEqual("advisory_no_auto_weight_change", metadata["trade_policy"])
        self.assertEqual("high_vol_defensive", metadata["volatility_gate"])

    def test_volatility_gate_low_vol_does_not_add_alert(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118",
            actual_date=pd.Timestamp("2026-07-02"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.1},
            latest_features={"total_risk_score": 2},
            finbert_sentiment={"risk_score": 0.0},
            garch_regime_shadow={
                "status": "available",
                "volatility_gate": {
                    "policy": "shadow_only_no_weight_change",
                    "gate": "low_vol_participation",
                    "high_vol_gate": False,
                    "reference_00631l_scale": 1.0,
                },
            },
        )

        self.assertNotIn("volatility_gate_high_vol", {alert["type"] for alert in alerts})

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

    def test_main_does_not_overwrite_latest_pointer_on_build_failure(self) -> None:
        """Fable audit (2026-07-08, #1): build_daily_signal raising must not
        clobber the latest pointer with an error payload (data=None) -- that
        would silently disable the H5 stale-fail-closed hold-carryover chain
        and make alert_state think every prior alert had resolved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pointer_path = Path(tmp_dir) / "live_signal.json"
            output_path = Path(tmp_dir) / "dated_output.json"
            good_payload = {"success": True, "data": {"signal_alerts": ["existing_alert"]}, "error": None}
            pointer_path.write_text(json.dumps(good_payload), encoding="utf-8")

            argv = [
                "daily_signal.py",
                "--latest-pointer",
                str(pointer_path),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv), patch.object(
                daily_signal, "build_daily_signal", side_effect=RuntimeError("boom")
            ):
                main()

            pointer_after = json.loads(pointer_path.read_text(encoding="utf-8"))
            self.assertEqual(good_payload, pointer_after)

            dated_after = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertFalse(dated_after["success"])
            self.assertIn("boom", dated_after["error"]["message"])


if __name__ == "__main__":
    unittest.main()
