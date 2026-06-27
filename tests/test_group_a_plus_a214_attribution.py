#!/usr/bin/env python3
"""Unit tests for the A21.4 matched attribution calculations."""

from __future__ import annotations

import unittest

from backtest_group_a_plus_a214_attribution import ATTRIBUTION_METRICS, WINDOWS, _attribution


class A214AttributionTests(unittest.TestCase):
    def test_factor_effects_reconstruct_combined_delta(self) -> None:
        rows = []
        values = {
            "ma75_cash30": 100.0,
            "ma60_cash30": 110.0,
            "ma75_bond30_cash30": 120.0,
            "ma60_bond30_cash30": 135.0,
        }
        for window in WINDOWS:
            for variant, value in values.items():
                rows.append({"window": window, "variant": variant, **{metric: value for metric in ATTRIBUTION_METRICS}})

        effects = _attribution(rows)

        self.assertEqual(len(effects), len(WINDOWS) * len(ATTRIBUTION_METRICS))
        for row in effects:
            reconstructed = (
                row["ma60_effect_at_cash30"]
                + row["bond_basket_effect_at_ma75"]
                + row["interaction_effect"]
            )
            self.assertAlmostEqual(reconstructed, row["a214_combined_effect"])
            self.assertEqual(row["interaction_effect"], 5.0)


if __name__ == "__main__":
    unittest.main()
