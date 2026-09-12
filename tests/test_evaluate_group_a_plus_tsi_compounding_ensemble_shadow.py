from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_shadow import _thresholds, write_report


def test_thresholds_match_compounding_staged_candidate() -> None:
    thresholds = _thresholds()

    assert thresholds.ar1_revert_max == -0.15
    assert thresholds.mean_reversion_score_min == 5


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_shadow",
        "policy": "compounding_staged_with_tsi_trend_persistent_add_cap_shadow",
        "tsi_threshold": 0.8,
        "tsi_trend_cap": 0.5,
        "production_effect": "none",
        "windows": [
            {
                "label": "fixture",
                "kind": "test",
                "tsi_alert_days": 3,
                "trend_persistent_tsi_alert_days": 1,
                "ensemble_delta_vs_compounding": {
                    "final_value": 100.0,
                    "sharpe_ratio": 0.1,
                    "max_drawdown": 0.0,
                },
            }
        ],
        "totals": {"ensemble_minus_compounding_final_value_sum": 100.0},
        "decision": {"promotion_allowed": False},
    }
    output = tmp_path / "latest" / "tsi_compounding_ensemble_shadow.json"
    output_md = tmp_path / "latest" / "tsi_compounding_ensemble_shadow.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_compounding_ensemble_shadow"
    assert "TSI Compounding Ensemble Shadow" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_compounding_ensemble_shadow_*.json"))
