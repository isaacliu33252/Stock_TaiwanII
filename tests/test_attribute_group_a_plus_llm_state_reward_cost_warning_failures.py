from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import attribute_group_a_plus_llm_state_reward_cost_warning_failures as attribution


def test_metric_failures_classifies_fold_deltas() -> None:
    assert attribution._metric_failures(
        {"final_value": 0.01, "sharpe_ratio": -0.1, "max_drawdown": 0.0}
    ) == ["sharpe_delta_not_positive"]
    assert attribution._metric_failures(
        {"final_value": 0.0, "sharpe_ratio": 0.0, "max_drawdown": -0.001}
    ) == [
        "final_value_delta_not_positive",
        "sharpe_delta_not_positive",
        "max_drawdown_delta_worse",
    ]


def test_fold_row_with_window_adds_failure_details() -> None:
    row = {
        "fold": 2,
        "status": "available_for_manual_offline_review",
        "delta_vs_equal_weight": {
            "final_value": 0.01,
            "sharpe_ratio": -0.2,
            "max_drawdown": 0.001,
        },
    }
    fold = {
        "fold": 2,
        "train_start": "2020-01-01",
        "train_end": "2021-01-01",
        "test_start": "2021-01-02",
        "test_end": "2021-12-31",
    }

    result = attribution._fold_row_with_window(row, fold)

    assert result["test_start"] == "2021-01-02"
    assert result["failed_metrics"] == ["sharpe_delta_not_positive"]
    assert result["passed_all_delta_checks"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "attribution.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_cost_warning_failure_attribution",
        "as_of": "2026-07-21",
    }

    attribution.write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_cost_warning_failure_attribution_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
