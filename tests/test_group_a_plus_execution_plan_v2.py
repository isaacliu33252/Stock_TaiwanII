#!/usr/bin/env python3
"""Regression checks for Group A++ workbook execution planning."""

from __future__ import annotations

import unittest

import pandas as pd

from group_a_plus.operations.execution_plan import (
    _apply_execution_controls,
    _build_trades,
    _parse_group_a_plus_holdings,
)


class ExecutionPlanV2Tests(unittest.TestCase):
    def test_parser_stops_before_group_b(self) -> None:
        frame = pd.DataFrame(
            [
                [None, "Group A++", None, "Group B", None],
                [None, "ETF 0050", "Bond 00679B", "ETF 0056", "ETF 00878"],
                ["即時庫存", 100, 200, 300, 400],
            ]
        )

        holdings = _parse_group_a_plus_holdings(frame)

        self.assertEqual(holdings, {"0050.TW": 100, "00679B.TWO": 200})

    def test_bond_etf_sale_has_no_tax(self) -> None:
        trades, totals = _build_trades(
            {"00751B.TWO": 10},
            {"00751B.TWO": 0},
            {"00751B.TWO": 30.0},
            commission_rate=0.0,
            slippage_rate=0.0,
            equity_etf_sell_tax=0.001,
        )

        self.assertEqual(trades[0]["sell_tax"], 0.0)
        self.assertEqual(totals["sell_tax"], 0.0)

    def test_small_trade_inside_band_is_suppressed(self) -> None:
        targets, suppressed = _apply_execution_controls(
            {"0050.TW": 100},
            {"0050.TW": 102},
            {"0050.TW": 100.0},
            total_assets=100_000.0,
            min_trade_notional=500.0,
            min_weight_deviation=0.01,
            share_lot_size=1,
        )

        self.assertEqual(targets["0050.TW"], 100)
        self.assertEqual(suppressed[0]["ticker"], "0050.TW")

    def test_liquidation_bypasses_execution_bands(self) -> None:
        targets, suppressed = _apply_execution_controls(
            {"00679B.TWO": 1},
            {"00679B.TWO": 0},
            {"00679B.TWO": 27.0},
            total_assets=100_000.0,
            min_trade_notional=5000.0,
            min_weight_deviation=0.1,
            share_lot_size=1,
        )

        self.assertEqual(targets["00679B.TWO"], 0)
        self.assertEqual(suppressed, [])


if __name__ == "__main__":
    unittest.main()
