from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_parameter_robustness import (
    _parse_variants,
    _variant_summary,
    write_report,
)


def test_parse_variants_returns_tsi_parameter_sets() -> None:
    variants = _parse_variants("default,20,12,0.6,0.08;slow,30,18,0.4,0.04")

    assert variants == [
        {"label": "default", "window_days": 20, "min_observations": 12, "alpha_up": 0.6, "alpha_down": 0.08},
        {"label": "slow", "window_days": 30, "min_observations": 18, "alpha_up": 0.4, "alpha_down": 0.04},
    ]


def test_variant_summary_extracts_best_and_temporal_oos_decision() -> None:
    variant = {"label": "default", "window_days": 20, "min_observations": 12, "alpha_up": 0.6, "alpha_down": 0.08}
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
    temporal_oos = {"decision": {"temporal_oos_passed": False}, "blocking_reasons": ["temporal_oos_fold_failed:fixture"]}

    summary = _variant_summary(variant, sweep, temporal_oos)

    assert summary["variant"] == "default"
    assert summary["window_days"] == 20
    assert summary["best_threshold"] == 0.75
    assert summary["temporal_oos_passed"] is False


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_parameter_robustness",
        "summaries": [
            {
                "variant": "default",
                "window_days": 20,
                "alpha_up": 0.6,
                "alpha_down": 0.08,
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
        "decision": {"parameter_robustness_passed": False, "promotion_allowed": False},
    }
    output = tmp_path / "latest" / "robustness.json"
    output_md = tmp_path / "latest" / "robustness.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_compounding_ensemble_parameter_robustness"
    assert "TSI Compounding Ensemble Parameter Robustness" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_compounding_ensemble_parameter_robustness_*.json"))
