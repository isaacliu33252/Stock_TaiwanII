#!/usr/bin/env python3
"""Regression checks for staged A20.7 defensive exposure."""

from __future__ import annotations

import unittest

import pandas as pd

from backtest_group_a_plus_dynamic_exposure import _blend_weights, _dynamic_exposure


class DynamicExposureTests(unittest.TestCase):
    def test_blend_weights_interpolates_and_normalizes(self) -> None:
        weights = _blend_weights({"0050.TW": 1.0}, {"00679B.TWO": 0.8, "cash": 0.2}, 0.5)

        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["0050.TW"], 0.5)
        self.assertAlmostEqual(weights["00679B.TWO"], 0.4)
        self.assertAlmostEqual(weights["cash"], 0.1)

    def test_full_defense_has_priority_then_recovers_in_steps(self) -> None:
        frame = pd.DataFrame(
            {
                "regime": ["golden1", "group_a_plus_defensive", "golden1", "golden1"],
                "ma_gap": [-0.02, -0.03, 0.03, 0.03],
                "drawdown": [-0.07, -0.12, -0.01, -0.01],
                "exit_momentum": [-0.01, -0.02, 0.02, 0.02],
                "total_risk_score": [4, 7, 2, 2],
                "realized_vol_ratio_20_60": [1.0, 1.3, 1.0, 1.0],
            },
            index=pd.date_range("2026-01-01", periods=4),
        )

        result, _events = _dynamic_exposure(frame, 4, -0.01, -0.06, 0.25, 0.5)

        self.assertEqual(result["defensive_share"].tolist(), [0.25, 1.0, 0.5, 0.0])

    def test_warning_can_require_tail_confirmation_and_persistence(self) -> None:
        frame = pd.DataFrame(
            {
                "regime": ["golden1"] * 3,
                "ma_gap": [-0.02] * 3,
                "drawdown": [-0.07] * 3,
                "exit_momentum": [-0.01] * 3,
                "total_risk_score": [5] * 3,
                "tail_risk_score": [0, 1, 1],
                "realized_vol_ratio_20_60": [1.0] * 3,
            },
            index=pd.date_range("2026-01-01", periods=3),
        )

        result, _events = _dynamic_exposure(
            frame, 4, -0.01, -0.06, 0.25, 0.5, min_tail_score=1, warning_confirm_days=2
        )

        self.assertEqual(result["defensive_share"].tolist(), [0.0, 0.0, 0.5])
        self.assertEqual(result["exposure_reason"].tolist(), ["normal", "normal", "strong_warning"])


if __name__ == "__main__":
    unittest.main()
