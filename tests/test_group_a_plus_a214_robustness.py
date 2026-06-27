#!/usr/bin/env python3
"""Unit tests for matched A21.4 robustness comparisons."""

from __future__ import annotations

import unittest

from validate_group_a_plus_a214_robustness import _comparison_row, _summary


class A214RobustnessTests(unittest.TestCase):
    def test_joint_pass_requires_all_three_metrics(self) -> None:
        base = {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.2}
        candidate = {"final_value": 110.0, "sharpe_ratio": 1.1, "max_drawdown": -0.19}

        row = _comparison_row("test", "pass", base, candidate)

        self.assertTrue(row["joint_pass"])
        candidate["max_drawdown"] = -0.21
        self.assertFalse(_comparison_row("test", "fail", base, candidate)["joint_pass"])

    def test_summary_counts_each_gate(self) -> None:
        rows = [
            {"joint_pass": True, "final_pass": True, "sharpe_pass": True, "mdd_pass": True, "delta_final": 10.0},
            {"joint_pass": False, "final_pass": False, "sharpe_pass": True, "mdd_pass": True, "delta_final": -2.0},
        ]

        summary = _summary(rows)

        self.assertEqual(summary["joint_pass_count"], 1)
        self.assertEqual(summary["final_pass_count"], 1)
        self.assertEqual(summary["worst_delta_final"], -2.0)


if __name__ == "__main__":
    unittest.main()
