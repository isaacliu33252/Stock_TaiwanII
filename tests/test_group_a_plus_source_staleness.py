#!/usr/bin/env python3
"""Regression check for bounded source carry-forward in GroupA+ features."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from backtest_group_a_plus_policy_signal import TICKERS


class SourceStalenessTests(unittest.TestCase):
    def test_2022_tdcc_change_is_not_carried_into_2025(self) -> None:
        prices = _load_prices(Path(DB_PATH), list(TICKERS), "2020-01-02", "2025-06-19")
        features = _load_chip_features(Path(DB_PATH), prices.index, "2020-01-02", "2025-06-19")
        recent = features.loc["2025-01-02":"2025-06-19"]

        self.assertTrue((recent["tdcc_0050_minority_chg_1w"] == 0.0).all())
        self.assertTrue((recent["tdcc_0050_major_chg_1w"] == 0.0).all())


if __name__ == "__main__":
    unittest.main()
