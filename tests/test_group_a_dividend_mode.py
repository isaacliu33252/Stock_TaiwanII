#!/usr/bin/env python3
"""Regression checks for Group A dividend reinvestment mode."""

from __future__ import annotations

import unittest

import pandas as pd

from train_dual_group_2024_2026 import FEATURE_COLUMNS, PortfolioEnv


GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _make_panel() -> pd.DataFrame:
    dates = pd.date_range("2026-05-18", periods=3, freq="B")
    rows: list[dict[str, float | str]] = []
    for idx, date in enumerate(dates):
        row: dict[str, float | str] = {"date": date}
        for ticker in GROUP_A_TICKERS:
            row[f"{ticker}_open"] = 10.0
            row[f"{ticker}_close"] = 10.0
            row[f"{ticker}_dividends"] = 1.0 if ticker == "0050.TW" and idx == 1 else 0.0
            for feature in FEATURE_COLUMNS:
                row[f"{ticker}_{feature}"] = 0.0
        rows.append(row)
    return pd.DataFrame(rows)


class GroupADividendModeTests(unittest.TestCase):
    def test_group_a_defaults_to_reinvest_weights(self) -> None:
        env = PortfolioEnv(
            _make_panel(),
            GROUP_A_TICKERS,
            initial_cash=1000.0,
            commission_rate=0.0,
        )

        self.assertEqual(env.dividend_mode, "reinvest_weights")

        env.step(0)

        self.assertAlmostEqual(float(env.total_dividend_credited), 50.0, places=6)
        self.assertAlmostEqual(float(env.cash), 0.0, places=6)
        self.assertAlmostEqual(float(env.shares[0]), 52.5, places=6)
        self.assertAlmostEqual(float(env.shares[1]), 52.5, places=6)
        self.assertAlmostEqual(float(env.shares[2]), 0.0, places=6)
        self.assertEqual(len(env.dividend_reinvestment_history), 1)
        self.assertEqual(env.dividend_reinvestment_history[0]["mode"], "reinvest_weights")

    def test_reinvest_0050_and_cash_modes_remain_selectable(self) -> None:
        panel = _make_panel()
        reinvest_0050_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            initial_cash=1000.0,
            commission_rate=0.0,
            dividend_mode="reinvest_0050",
        )
        cash_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            initial_cash=1000.0,
            commission_rate=0.0,
            dividend_mode="cash",
        )

        reinvest_0050_env.step(0)
        cash_env.step(0)

        self.assertAlmostEqual(float(reinvest_0050_env.cash), 0.0, places=6)
        self.assertAlmostEqual(float(reinvest_0050_env.shares[0]), 55.0, places=6)
        self.assertAlmostEqual(float(reinvest_0050_env.shares[1]), 50.0, places=6)
        self.assertEqual(reinvest_0050_env.dividend_reinvestment_history[0]["mode"], "reinvest_0050")

        self.assertAlmostEqual(float(cash_env.cash), 50.0, places=6)
        self.assertAlmostEqual(float(cash_env.shares[0]), 50.0, places=6)
        self.assertAlmostEqual(float(cash_env.shares[1]), 50.0, places=6)
        self.assertEqual(len(cash_env.dividend_reinvestment_history), 0)


if __name__ == "__main__":
    unittest.main()
