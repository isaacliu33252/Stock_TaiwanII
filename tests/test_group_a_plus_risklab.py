#!/usr/bin/env python3
"""Tests for the isolated RiskLabAI integration."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from group_a_plus.integrations.risklab import load_risklab_components


RISKLAB_ROOT = Path("/mnt/c/Users/isaac/Downloads/RiskLabAI.py-main/RiskLabAI.py-main")


class RiskLabIntegrationTests(unittest.TestCase):
    def test_selected_components_load_without_package_init(self) -> None:
        components = load_risklab_components(RISKLAB_ROOT)
        probability = components["psr"].probabilistic_sharpe_ratio(1.0, 0.5, 252)
        self.assertGreater(probability, 0.5)

    def test_microstructure_estimators_return_aligned_series(self) -> None:
        components = load_risklab_components(RISKLAB_ROOT)
        index = pd.date_range("2025-01-01", periods=30)
        high = pd.Series(np.linspace(101.0, 111.0, 30), index=index)
        low = high - 1.0
        spread = components["corwin"].corwin_schultz_estimator(high, low, 20)
        volatility = components["bekker"].bekker_parkinson_volatility_estimates(high, low, 20)
        self.assertTrue(spread.index.equals(index))
        self.assertTrue(volatility.index.equals(index))


if __name__ == "__main__":
    unittest.main()
