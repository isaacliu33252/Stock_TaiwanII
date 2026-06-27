#!/usr/bin/env python3
"""Regression checks for GroupA+ promotion eligibility gates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from group_a_plus.governance.compare import compare_candidates


class GroupAPlusGovernanceCompareTests(unittest.TestCase):
    def test_formal_ineligible_candidate_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(
                json.dumps(
                    {
                        "metrics": {
                            "final_value": 100.0,
                            "sharpe_ratio": 1.0,
                            "max_drawdown": -0.20,
                        }
                    }
                ),
                encoding="utf-8",
            )
            candidate.write_text(
                json.dumps(
                    {
                        "experiment": "coverage_gate",
                        "rows": [
                            {
                                "variant": "better_but_not_ready",
                                "final_value": 120.0,
                                "sharpe_ratio": 1.2,
                                "max_drawdown": -0.10,
                                "override_days": 2,
                                "formal_eligible": False,
                                "formal_ineligible_reason": "insufficient_sources",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = compare_candidates(baseline, [candidate])

        self.assertEqual(report["formal_upgrade_pass_count"], 0)
        self.assertFalse(report["rows"][0]["formal_upgrade_pass"])
        self.assertFalse(report["rows"][0]["formal_eligible"])
        self.assertEqual(report["rows"][0]["formal_ineligible_reason"], "insufficient_sources")


if __name__ == "__main__":
    unittest.main()
