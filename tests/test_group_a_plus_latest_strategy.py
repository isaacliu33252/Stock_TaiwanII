#!/usr/bin/env python3
"""Regression checks for the schema-v2 GroupA+ latest manifest."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest
from group_a_plus.runners.a213 import A213_ID, run_a213
from group_a_plus.runners.a214 import A214_ID, run_a214
from group_a_plus.runners.a2111 import A2111_ID
from group_a_plus.runners.a2112 import A2112_ID


class LatestStrategyTests(unittest.TestCase):
    def test_repository_manifest_activates_a2111(self) -> None:
        manifest = resolve_latest(DEFAULT_LATEST_STRATEGY)

        self.assertEqual(manifest["active_strategy"]["id"], "a2111_tight_entry_bond30c30")
        self.assertEqual(A2111_ID, manifest["active_strategy"]["id"])
        self.assertNotEqual(A2111_ID, A213_ID)
        self.assertNotEqual(A2111_ID, A2112_ID)
        self.assertTrue(manifest["compatibility"]["legacy_pointer_unchanged"])

    def test_unknown_strategy_is_rejected(self) -> None:
        manifest = {
            "schema_version": 2,
            "active_strategy": {"id": "unknown", "runner": "unknown.runner"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "strategy.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unsupported active strategy"):
                resolve_latest(path)

    @patch("group_a_plus.runners.a213._run_recovery_strategy")
    def test_a213_parameters_are_immutable(self, core) -> None:
        core.return_value = ({}, None)

        run_a213("2025-01-02", "2026-06-18", 1_000_000, Path("test.db"))

        kwargs = core.call_args.kwargs
        self.assertEqual(kwargs["strategy_id"], "a213_cash30_recovery_ramp")
        self.assertEqual(kwargs["basket_name"], "cash30")
        self.assertEqual(kwargs["ma_window"], 75)

    @patch("group_a_plus.runners.a214._run_recovery_strategy")
    def test_a214_parameters_are_isolated(self, core) -> None:
        core.return_value = ({}, None)

        run_a214("2025-01-02", "2026-06-18", 1_000_000, Path("test.db"))

        kwargs = core.call_args.kwargs
        self.assertEqual(kwargs["strategy_id"], "a214_bond30c30_mw60")
        self.assertEqual(kwargs["basket_name"], "bond30_cash30")
        self.assertEqual(kwargs["ma_window"], 60)


if __name__ == "__main__":
    unittest.main()
