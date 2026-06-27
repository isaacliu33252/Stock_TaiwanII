#!/usr/bin/env python3
"""Tests for A21.6 severity escalation and hysteresis."""

from __future__ import annotations

import unittest

import pandas as pd

from group_a_plus.runners.a216 import _severity_regime


class A216Tests(unittest.TestCase):
    def test_severity_latches_until_recovery(self) -> None:
        index = pd.date_range("2026-01-01", periods=5)
        regimes = pd.Series(
            ["group_a_plus_defensive", "group_a_plus_defensive", "group_a_plus_defensive", "group_a_plus_recovery", "golden1"],
            index=index,
        )
        features = pd.DataFrame(
            {
                "total_risk_score": [6, 8, 6, 6, 2],
                "drawdown": [-0.11] * 5,
                "tail_risk_score": [0] * 5,
            },
            index=index,
        )

        result = _severity_regime(regimes, features)

        self.assertEqual(
            result.tolist(),
            ["group_a_plus_defensive", "group_a_plus_severe", "group_a_plus_severe", "group_a_plus_recovery", "golden1"],
        )


if __name__ == "__main__":
    unittest.main()
