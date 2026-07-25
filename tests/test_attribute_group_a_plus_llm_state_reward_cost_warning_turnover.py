from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import attribute_group_a_plus_llm_state_reward_cost_warning_turnover as turnover


def _row(final_value: float, sharpe_ratio: float, max_drawdown: float) -> dict:
    return {
        "delta_vs_equal_weight": {
            "final_value": final_value,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
        }
    }


def test_metric_cost_classification_distinguishes_cost_from_raw_signal() -> None:
    classifications = turnover._metric_cost_classification(
        _row(0.01, 0.02, 0.001),
        _row(0.005, -0.001, -0.0001),
    )

    assert classifications["final_value"] == "positive_after_cost"
    assert classifications["sharpe_ratio"] == "cost_caused_sharpe_failure"
    assert classifications["max_drawdown"] == "cost_caused_drawdown_failure"

    classifications = turnover._metric_cost_classification(
        _row(-0.01, -0.02, -0.001),
        _row(-0.02, -0.03, -0.002),
    )

    assert classifications["final_value"] == "raw_signal_final_failure"
    assert classifications["sharpe_ratio"] == "raw_signal_sharpe_failure"
    assert classifications["max_drawdown"] == "raw_signal_drawdown_failure"


def test_fold_turnover_summary_adds_cost_drag_and_failure_flags() -> None:
    fold = {
        "fold": 1,
        "train_start": "2020-01-01",
        "train_end": "2021-01-01",
        "test_start": "2021-01-02",
        "test_end": "2021-12-31",
    }
    no_cost = _row(0.01, 0.02, 0.001)
    with_cost = {
        "candidate": {"mean_daily_turnover": 0.02, "total_turnover": 4.0},
        "delta_vs_equal_weight": {
            "final_value": 0.005,
            "sharpe_ratio": -0.001,
            "max_drawdown": 0.0005,
        },
    }

    result = turnover._fold_turnover_summary(fold, no_cost=no_cost, with_cost=with_cost, warning_cost_bps=5.0)

    assert result["test_start"] == "2021-01-02"
    assert result["estimated_cost_drag_return"] == 0.002
    assert result["cost_drag_delta_vs_equal_weight"]["sharpe_ratio"] == -0.021
    assert result["metric_cost_classification"]["sharpe_ratio"] == "cost_caused_sharpe_failure"
    assert result["cost_caused_any_failure"] is True
    assert result["raw_signal_any_failure"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "turnover.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_cost_warning_turnover_attribution",
        "as_of": "2026-07-21",
    }

    turnover.write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_cost_warning_turnover_attribution_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
