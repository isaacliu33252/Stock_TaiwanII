#!/usr/bin/env python3
"""Regression checks for the A20.9 warmup-consistency runner."""

from __future__ import annotations

import unittest

import pandas as pd

from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start


class WarmupConsistencyTests(unittest.TestCase):
    def test_warmup_start_uses_calendar_days(self) -> None:
        self.assertEqual(_warmup_start("2025-01-02", 365), "2024-01-03")

    def test_trim_window_preserves_precomputed_state(self) -> None:
        index = pd.date_range("2024-12-30", periods=6, freq="D")
        prices = pd.DataFrame({"close": range(6)}, index=index)
        frame = pd.DataFrame(
            {"regime": ["golden1", "group_a_plus_defensive", "group_a_plus_defensive", "golden1", "golden1", "golden1"]},
            index=index,
        )
        events = [
            {"date": "2024-12-31", "action": "enter"},
            {"date": "2025-01-02", "action": "exit"},
        ]

        trimmed_prices, trimmed_frame, trimmed_events = _trim_window(
            prices, frame, events, "2025-01-01", "2025-01-03"
        )

        self.assertEqual(len(trimmed_prices), 3)
        self.assertEqual(trimmed_frame["regime"].iloc[0], "group_a_plus_defensive")
        self.assertEqual([event["date"] for event in trimmed_events], ["2025-01-02"])


if __name__ == "__main__":
    unittest.main()
