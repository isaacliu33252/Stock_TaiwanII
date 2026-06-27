#!/usr/bin/env python3
"""Regression checks for A21 total-return and execution mechanics."""

from __future__ import annotations

import unittest

import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    _asymmetric_delayed_regime,
    _delayed_regime,
    _dominates,
    _recovery_ramp_regime,
    _simulate_costed_curve,
    _stress_episodes,
    _trade_cost,
)


class DefensiveBasketTests(unittest.TestCase):
    def test_bond_etf_sell_is_tax_exempt(self) -> None:
        current = {"0050.TW": 100.0, "00679B.TWO": 100.0}
        target = {"0050.TW": 0.0, "00679B.TWO": 0.0}
        cost, turnover = _trade_cost(current, target, 0.0, 0.0, 0.001)

        self.assertAlmostEqual(turnover, 200.0)
        self.assertAlmostEqual(cost, 0.1)

    def test_costed_curve_deducts_initial_buy_cost(self) -> None:
        index = pd.date_range("2026-01-01", periods=2)
        prices = pd.DataFrame({ticker: [10.0, 10.0] for ticker in ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")}, index=index)
        regimes = pd.Series(["golden1", "golden1"], index=index)
        weights = {"golden1": {"0050.TW": 1.0}}

        curve, execution = _simulate_costed_curve(prices, regimes, weights, 1_000.0, 0.001, 0.0, 0.001)

        self.assertLess(curve.iloc[0], 1_000.0)
        self.assertAlmostEqual(curve.iloc[0], curve.iloc[1])
        self.assertEqual(execution["rebalance_count"], 1)

    def test_signal_delay_uses_prior_regime(self) -> None:
        regime = pd.Series(["golden1", "group_a_plus_defensive", "group_a_plus_defensive"])
        self.assertEqual(_delayed_regime(regime, 1).tolist(), ["golden1", "golden1", "group_a_plus_defensive"])

    def test_asymmetric_delay_can_defer_only_entry(self) -> None:
        regime = pd.Series(
            ["golden1", "group_a_plus_defensive", "group_a_plus_defensive", "golden1", "golden1"]
        )

        delayed = _asymmetric_delayed_regime(regime, enter_delay=1, exit_delay=0)

        self.assertEqual(
            delayed.tolist(),
            ["golden1", "golden1", "group_a_plus_defensive", "golden1", "golden1"],
        )

    def test_recovery_ramp_is_one_shot_until_formal_exit(self) -> None:
        index = pd.date_range("2026-01-01", periods=5)
        regime = pd.Series(
            ["group_a_plus_defensive"] * 4 + ["golden1"],
            index=index,
        )
        features = pd.DataFrame(
            {
                "ma_gap": [-0.02, 0.01, -0.03, -0.02, 0.03],
                "exit_momentum": [-0.01, 0.01, -0.02, -0.02, 0.02],
            },
            index=index,
        )

        result = _recovery_ramp_regime(regime, features)

        self.assertEqual(
            result.tolist(),
            [
                "group_a_plus_defensive",
                "group_a_plus_recovery",
                "group_a_plus_recovery",
                "group_a_plus_recovery",
                "golden1",
            ],
        )

    def test_metric_comparison_tolerates_floating_noise(self) -> None:
        reference = {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.2}
        candidate = {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20000000000000012}

        self.assertTrue(_dominates(candidate, reference))

    def test_stress_episode_uses_price_entry_and_recovery(self) -> None:
        index = pd.date_range("2026-01-01", periods=7)
        frame = pd.DataFrame(
            {
                "ma_gap": [0.0, -0.02, -0.03, -0.01, 0.0, 0.021, 0.03],
                "drawdown": [0.0] * 7,
                "exit_momentum": [0.0, -0.01, -0.01, -0.01, 0.0, 0.01, 0.02],
            },
            index=index,
        )

        episodes = _stress_episodes(frame, min_trading_days=5)

        self.assertEqual(episodes, [(index[1], index[5])])


if __name__ == "__main__":
    unittest.main()
