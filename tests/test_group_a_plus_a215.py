#!/usr/bin/env python3
"""Regression tests for A21.5 identity and train-only selection."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from evaluate_group_a_plus_a215 import _select_train_candidate
from group_a_plus.runners.a215 import run_a215


class A215Tests(unittest.TestCase):
    @patch("group_a_plus.runners.a215._run_recovery_strategy")
    def test_runner_parameters_are_frozen(self, core) -> None:
        core.return_value = ({}, None)
        run_a215("2025-01-02", "2026-06-18", 1_000_000, Path("test.db"))
        kwargs = core.call_args.kwargs
        self.assertEqual(kwargs["ma_window"], 80)
        self.assertEqual(kwargs["basket_name"], "cash40")

    def test_selection_uses_passing_train_rows(self) -> None:
        baseline = {"final_value": 100, "sharpe_ratio": 1, "max_drawdown": -0.2, "expected_tail_loss_5pct": -0.03}
        rows = [
            {"name": "fail", "final_value": 120, "sharpe_ratio": 2, "max_drawdown": -0.21, "expected_tail_loss_5pct": -0.02},
            {"name": "pass", "final_value": 105, "sharpe_ratio": 1.1, "max_drawdown": -0.19, "expected_tail_loss_5pct": -0.02},
        ]
        self.assertEqual(_select_train_candidate(rows, baseline)["name"], "pass")


if __name__ == "__main__":
    unittest.main()
