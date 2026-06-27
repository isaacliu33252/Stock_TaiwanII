#!/usr/bin/env python3
"""Smoke test for the Group A FinRL-X adapter and backtest bridge."""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from FinRL.backtesting import GroupABridgeConfig, run_group_a_finrlx_backtest


PROJECT_ROOT = Path(__file__).resolve().parent
PAYLOAD_PATH = PROJECT_ROOT / "results" / "group_a_runtime_payload_primary_20260524.json"
SMOKE_START = "2024-01-02"
SMOKE_END = "2024-03-29"
EXPECTED_TICKERS = {"0050.TW", "00631L.TW", "00632R.TW"}


def _payload_model_exists() -> bool:
    if not PAYLOAD_PATH.exists():
        return False

    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    group_a = payload.get("group_a", {}) or {}

    model_name = group_a.get("model_name")
    if model_name:
        candidate = PROJECT_ROOT / "models" / "portfolio" / str(model_name)
        if candidate.exists() or (candidate.suffix != ".zip" and candidate.with_suffix(".zip").exists()):
            return True

    resume_model = payload.get("group_a_resume_model") or group_a.get("resume_model")
    if resume_model:
        candidate = Path(str(resume_model))
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        if candidate.exists():
            return True

    return False


class GroupAFinRLXBridgeSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PAYLOAD_PATH.exists():
            raise unittest.SkipTest(f"Missing Group A payload: {PAYLOAD_PATH}")
        if not _payload_model_exists():
            raise unittest.SkipTest(f"Missing Group A model artifact referenced by {PAYLOAD_PATH.name}")

        cls.bridge_result = run_group_a_finrlx_backtest(
            GroupABridgeConfig(
                payload_path=str(PAYLOAD_PATH),
                name="group_a_finrlx_smoke_test",
                start_date=SMOKE_START,
                end_date=SMOKE_END,
                target_date=SMOKE_END,
                download_end=SMOKE_END,
            )
        )

    def test_adapter_emits_strategy_result_with_required_metadata(self) -> None:
        strategy_result = self.bridge_result.strategy_result
        metadata = strategy_result.metadata or {}

        self.assertEqual(strategy_result.strategy_name, "group_a_finrlx_smoke_test")
        self.assertFalse(strategy_result.weights.empty)
        self.assertEqual(set(strategy_result.weights.columns), EXPECTED_TICKERS)
        self.assertIn("weights_full", metadata)
        self.assertIn("weights_rebalance", metadata)
        self.assertIn("prices", metadata)
        self.assertIn("decision_history", metadata)
        self.assertIn("initial_cash", metadata)
        self.assertFalse(metadata["weights_full"].empty)
        self.assertFalse(metadata["prices"].empty)
        self.assertEqual(set(metadata["prices"].columns), EXPECTED_TICKERS)
        self.assertEqual(metadata["target_date"], SMOKE_END)

    def test_finrlx_backtest_runs_on_short_window(self) -> None:
        backtest_result = self.bridge_result.backtest_result
        summary = self.bridge_result.summary

        self.assertFalse(backtest_result.portfolio_values.empty)
        self.assertFalse(backtest_result.weights_history.empty)
        self.assertIn("sharpe", backtest_result.metrics)
        self.assertIn("max_drawdown", backtest_result.metrics)
        self.assertTrue(math.isfinite(float(summary["comparison"]["final_value_diff"])))
        self.assertIn("DCA", summary["comparison"]["note"])
        self.assertEqual(summary["window"]["start_date"], SMOKE_START)
        self.assertEqual(summary["window"]["end_date"], SMOKE_END)


if __name__ == "__main__":
    unittest.main()
