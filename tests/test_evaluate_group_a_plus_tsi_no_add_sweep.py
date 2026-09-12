from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_sweep import _combo_summary, write_sweep


def test_combo_summary_extracts_totals_and_governance() -> None:
    report = {
        "tsi_threshold": 0.85,
        "alert_mode": "tsi_and_existing_any",
        "guard_add_fraction": 0.25,
        "totals": {
            "tsi_alert_days": 10,
            "blocked_days": 3,
            "delta_final_value_sum": 100.0,
            "delta_sharpe_sum": 0.1,
            "delta_max_drawdown_sum": 0.01,
            "positive_final_value_windows": 2,
            "non_worse_drawdown_windows": 3,
        },
        "blocking_reasons": ["research_only"],
    }

    summary = _combo_summary(report)

    assert summary["threshold"] == 0.85
    assert summary["alert_mode"] == "tsi_and_existing_any"
    assert summary["guard_add_fraction"] == 0.25
    assert summary["blocked_days"] == 3
    assert summary["blocking_reasons"] == ["research_only"]


def test_write_sweep_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_no_add_sweep",
        "production_effect": "none",
        "summaries": [
            {
                "threshold": 0.9,
                "alert_mode": "tsi_only",
                "guard_add_fraction": 0.0,
                "tsi_alert_days": 4,
                "blocked_days": 2,
                "delta_final_value_sum": -10.0,
                "delta_sharpe_sum": 0.0,
                "delta_max_drawdown_sum": 0.0,
            }
        ],
        "best_by_final_value": {"threshold": 0.9, "alert_mode": "tsi_only"},
        "best_by_drawdown": {"threshold": 0.9, "alert_mode": "tsi_only"},
        "decision": {"promotion_allowed": False},
    }
    output = tmp_path / "latest" / "sweep.json"
    output_md = tmp_path / "latest" / "sweep.md"
    history = tmp_path / "history"

    write_sweep(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_no_add_sweep"
    assert "TSI No-Add Sweep" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_no_add_sweep_*.json"))
