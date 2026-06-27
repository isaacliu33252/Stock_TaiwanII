#!/usr/bin/env python3
"""Regression checks for the schema-v2 daily GroupA+ signal."""

from __future__ import annotations

import unittest

from group_a_plus.operations.daily_signal import _business_days_between, _resolve_weights


class DailySignalV2Tests(unittest.TestCase):
    def test_weekend_staleness_counts_weekdays_only(self) -> None:
        self.assertEqual(_business_days_between("2026-06-11", "2026-06-13"), 1)

    def test_taiwan_holiday_is_not_counted_as_stale_day(self) -> None:
        self.assertEqual(_business_days_between("2026-06-18", "2026-06-22"), 1)

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


if __name__ == "__main__":
    unittest.main()
