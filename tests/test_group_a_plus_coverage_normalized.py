#!/usr/bin/env python3
"""Regression checks for A20.8 coverage-normalized risk."""

from __future__ import annotations

import unittest

import pandas as pd

from backtest_group_a_plus_coverage_normalized import (
    _availability_from_dates,
    _coverage_normalized_regime,
)


class CoverageNormalizedTests(unittest.TestCase):
    def test_availability_requires_maturity_and_expires(self) -> None:
        index = pd.date_range("2026-01-01", periods=8, freq="D")
        result = _availability_from_dates(index, [index[0], index[1]], 2, 2)

        self.assertEqual(result.tolist(), [0, 1, 1, 1, 0, 0, 0, 0])

    def test_normalized_entry_and_low_coverage_fallback(self) -> None:
        index = pd.date_range("2026-01-01", periods=2, freq="D")
        features = pd.DataFrame(
            {
                "chip_inst_risk": [1, 1],
                "chip_margin_risk": [0, 0],
                "total_risk_score": [1, 6],
                "ma_gap": [-0.03, -0.03],
                "drawdown": [-0.05, -0.05],
                "exit_momentum": [-0.01, -0.01],
            },
            index=index,
        )
        availability = pd.DataFrame(
            {"chip_inst_risk": [1, 0], "chip_margin_risk": [1, 0]},
            index=index,
        )

        normalized, events = _coverage_normalized_regime(features.iloc[:1], availability.iloc[:1], 0.5, 2)
        fallback, fallback_events = _coverage_normalized_regime(features.iloc[1:], availability.iloc[1:], 0.5, 2)

        self.assertEqual(normalized["regime"].iloc[0], "group_a_plus_defensive")
        self.assertEqual(events[0]["entry_mode"], "normalized")
        self.assertEqual(fallback["regime"].iloc[0], "group_a_plus_defensive")
        self.assertEqual(fallback_events[0]["entry_mode"], "a207_fallback")


if __name__ == "__main__":
    unittest.main()
