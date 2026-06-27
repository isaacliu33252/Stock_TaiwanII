#!/usr/bin/env python3
"""Unit tests for A21.12 — MA80 tight-entry + bond30_cash30 + low-risk exit."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backtest_group_a_plus_switch_policy import SwitchRule
from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2112 import A2112_ID, _build_switch_rule, run_a2112


class A2112SwitchRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = _build_switch_rule()

    def test_returns_switch_rule_instance(self) -> None:
        self.assertIsInstance(self.rule, SwitchRule)

    def test_ma_window_is_80(self) -> None:
        self.assertEqual(self.rule.ma_window, 80)

    def test_drawdown_window_matches_ma_window(self) -> None:
        self.assertEqual(self.rule.drawdown_window, self.rule.ma_window)

    def test_entry_gap_is_tight(self) -> None:
        self.assertAlmostEqual(self.rule.enter_ma_gap, 0.003, places=4)

    def test_exit_gap_is_standard(self) -> None:
        self.assertAlmostEqual(self.rule.exit_ma_gap, 0.010, places=4)

    def test_drawdown_threshold(self) -> None:
        self.assertAlmostEqual(self.rule.enter_drawdown, -0.11, places=3)

    def test_total_risk_score_gate_is_6(self) -> None:
        self.assertEqual(self.rule.require_total_risk_score, 6)

    def test_exit_max_total_risk_score_is_6(self) -> None:
        self.assertEqual(self.rule.exit_max_total_risk_score, 6)

    def test_low_risk_exit_ma_gap_enabled(self) -> None:
        """low_risk_exit_ma_gap must be set — the key improvement over A21.11."""
        self.assertIsNotNone(self.rule.low_risk_exit_ma_gap)
        self.assertAlmostEqual(self.rule.low_risk_exit_ma_gap, 0.003, places=4)

    def test_low_risk_exit_score_threshold(self) -> None:
        """Fast exit triggers when total_risk_score ≤ 1 (risk has dissipated)."""
        self.assertEqual(self.rule.low_risk_exit_score_threshold, 1)

    def test_low_risk_exit_is_tighter_than_standard_exit(self) -> None:
        """The fast-exit gap must be strictly less than the standard exit gap."""
        self.assertLess(self.rule.low_risk_exit_ma_gap, self.rule.exit_ma_gap)

    def test_hold_days_is_5(self) -> None:
        self.assertEqual(self.rule.min_hold_days, 5)

    def test_chip_score_not_used(self) -> None:
        self.assertEqual(self.rule.require_chip_score, 0)

    def test_derivative_score_not_used(self) -> None:
        self.assertEqual(self.rule.require_derivative_score, 0)

    def test_name_encodes_key_params(self) -> None:
        """Rule name should reference ma80, dd11, eg3, xg10, lrx3."""
        self.assertIn("ma80", self.rule.name)
        self.assertIn("dd11", self.rule.name)
        self.assertIn("eg3", self.rule.name)
        self.assertIn("xg10", self.rule.name)
        self.assertIn("lrx3", self.rule.name)

    def test_a2112_differs_from_a2111_by_ma_window(self) -> None:
        from group_a_plus.runners.a2111 import _build_switch_rule as _build_a2111
        rule_a2111 = _build_a2111()
        self.assertNotEqual(self.rule.ma_window, rule_a2111.ma_window)
        self.assertEqual(self.rule.enter_ma_gap, rule_a2111.enter_ma_gap)
        self.assertEqual(self.rule.exit_ma_gap, rule_a2111.exit_ma_gap)

    def test_a2112_adds_low_risk_exit_vs_a2111(self) -> None:
        from group_a_plus.runners.a2111 import _build_switch_rule as _build_a2111
        rule_a2111 = _build_a2111()
        self.assertIsNone(rule_a2111.low_risk_exit_ma_gap, "A21.11 must not have low_risk_exit")
        self.assertIsNotNone(self.rule.low_risk_exit_ma_gap, "A21.12 must have low_risk_exit")


class A2112GovernanceTests(unittest.TestCase):
    def test_strategy_id_registered_in_governance(self) -> None:
        self.assertIn(A2112_ID, SUPPORTED_STRATEGIES)

    def test_strategy_id_points_to_correct_runner(self) -> None:
        self.assertEqual(SUPPORTED_STRATEGIES[A2112_ID], "group_a_plus.runners.a2112")

    def test_strategy_id_constant(self) -> None:
        self.assertEqual(A2112_ID, "a2112_ma80_tight_entry_bond30c30_lrx")


class A2112RunnerParametersTests(unittest.TestCase):
    @patch("group_a_plus.runners.a2112._build_switch_rule")
    @patch("group_a_plus.runners.a2112._load_policy_signal")
    @patch("group_a_plus.runners.a2112._load")
    @patch("group_a_plus.runners.a2112._resolve")
    @patch("group_a_plus.runners.a2112._load_prices")
    @patch("group_a_plus.runners.a2112._load_chip_features")
    @patch("group_a_plus.runners.a2112._switch_returns")
    @patch("group_a_plus.runners.a2112._trim_window")
    @patch("group_a_plus.runners.a2112._load_total_return_prices")
    @patch("group_a_plus.runners.a2112._recovery_ramp_regime")
    @patch("group_a_plus.runners.a2112._simulate_costed_curve")
    @patch("group_a_plus.runners.a2112._warmup_start")
    @patch("group_a_plus.runners.a2112._normalize")
    @patch("group_a_plus.runners.a2112._weights_from_group_a_plus")
    @patch("group_a_plus.runners.a2112._weights_from_group_a")
    @patch("group_a_plus.runners.a2112._metrics")
    def test_report_contains_strategy_id(
        self, mock_metrics, mock_wga, mock_wgap, mock_norm, mock_warmup,
        mock_sim, mock_recovery, mock_tr_prices, mock_trim, mock_switch,
        mock_chip, mock_prices, mock_resolve, mock_load, mock_policy, mock_rule,
    ) -> None:
        import pandas as pd

        from group_a_plus.paths import PROJECT_ROOT
        mock_rule.return_value = _build_switch_rule()
        signal_path = PROJECT_ROOT / "report" / "signal.json"
        mock_policy.return_value = ({"weights": {}}, signal_path)
        mock_load.return_value = {"weights": {}}
        mock_resolve.side_effect = lambda x: PROJECT_ROOT / "report" / "golden.json"
        mock_norm.return_value = {}
        mock_wga.return_value = {}
        mock_wgap.return_value = {}
        mock_warmup.return_value = "2024-01-01"
        idx = pd.date_range("2025-01-02", periods=5, freq="B")
        mock_prices.return_value = pd.DataFrame({"0050.TW": [100.0] * 5}, index=idx)
        mock_chip.return_value = pd.DataFrame(index=idx)
        mock_switch.return_value = ([], pd.DataFrame({"regime": ["golden1"] * 5}, index=idx))
        close_df = pd.DataFrame({"0050.TW": [100.0] * 5}, index=idx)
        frame_df = pd.DataFrame({"regime": ["golden1"] * 5}, index=idx)
        mock_trim.return_value = (close_df, frame_df, [])
        mock_tr_prices.return_value = (close_df, {})
        mock_recovery.return_value = pd.Series(["golden1"] * 5, index=idx)
        mock_sim.return_value = (pd.Series([1_000_000.0] * 5, index=idx), {})
        mock_metrics.return_value = {"sharpe": 0.0}

        report, _ = run_a2112("2025-01-02", "2025-01-08", 1_000_000.0, Path("test.db"))

        self.assertEqual(report["strategy"], A2112_ID)
        self.assertEqual(report["status"], "research_candidate")
        self.assertEqual(report["rules"]["ma_window"], 80)
        self.assertAlmostEqual(report["rules"]["entry_gap"], 0.003, places=4)
        self.assertAlmostEqual(report["rules"]["low_risk_exit_ma_gap"], 0.003, places=4)
        self.assertEqual(report["rules"]["low_risk_exit_score_threshold"], 1)
        self.assertEqual(report["rules"]["basket_name"], "bond30_cash30")


if __name__ == "__main__":
    unittest.main()
