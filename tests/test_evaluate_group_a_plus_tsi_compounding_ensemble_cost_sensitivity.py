from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_cost_sensitivity import _cost_summary, write_report


def test_cost_summary_extracts_best_and_temporal_oos_decision() -> None:
    sweep = {
        "best_by_final_value": {
            "threshold": 0.75,
            "tsi_trend_cap": 0.0,
            "ensemble_minus_compounding_final_value_sum": 100.0,
            "ensemble_minus_compounding_sharpe_sum": 0.1,
            "ensemble_minus_compounding_max_drawdown_sum": 0.0,
            "ensemble_positive_vs_compounding_windows": 2,
            "ensemble_non_worse_drawdown_vs_compounding_windows": 8,
        }
    }
    temporal_oos = {
        "decision": {"temporal_oos_passed": False},
        "blocking_reasons": ["research_only_no_live_weight_change", "temporal_oos_fold_failed:fixture"],
    }

    summary = _cost_summary(5.0, sweep, temporal_oos)

    assert summary["transaction_cost_bps"] == 5.0
    assert summary["best_threshold"] == 0.75
    assert summary["best_tsi_trend_cap"] == 0.0
    assert summary["best_delta_final_value_vs_compounding"] == 100.0
    assert summary["temporal_oos_passed"] is False
    assert "temporal_oos_fold_failed:fixture" in summary["temporal_oos_blocking_reasons"]


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_cost_sensitivity",
        "summaries": [
            {
                "transaction_cost_bps": 0.0,
                "best_threshold": 0.75,
                "best_tsi_trend_cap": 0.0,
                "best_delta_final_value_vs_compounding": 100.0,
                "best_delta_sharpe_vs_compounding": 0.1,
                "best_delta_max_drawdown_vs_compounding": 0.0,
                "best_positive_windows": 2,
                "best_non_worse_drawdown_windows": 8,
                "temporal_oos_passed": False,
            }
        ],
        "blocking_reasons": ["research_only_no_live_weight_change"],
        "decision": {"cost_sensitivity_passed": False, "promotion_allowed": False},
    }
    output = tmp_path / "latest" / "cost.json"
    output_md = tmp_path / "latest" / "cost.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_compounding_ensemble_cost_sensitivity"
    assert "TSI Compounding Ensemble Cost Sensitivity" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_compounding_ensemble_cost_sensitivity_*.json"))
