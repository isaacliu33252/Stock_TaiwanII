from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_llm_state_reward_cost_warning_remediation_review as remediation


def _micro_review(*, high_score: float, passed: bool, required_passed: int) -> dict:
    return {
        "status": "available_for_manual_offline_review" if passed else "blocked",
        "summary": {
            "micro_tilt_guard_passed": passed,
            "required_cost_scenarios_passed": required_passed,
        },
        "scenario_results": [
            {
                "cost_bps": 5.0,
                "passed": passed,
                "positive_final_folds": 4,
                "positive_sharpe_folds": 4 if passed else 3,
                "non_worse_drawdown_folds": 3,
                "high_score": high_score,
            }
        ],
        "blocking_reasons": [] if passed else ["required_cost_scenario_failed:5bps"],
    }


def test_build_review_blocks_when_no_candidate_resolves_cost_warning(monkeypatch) -> None:
    def fake_micro_review(**kwargs):
        high_score = kwargs["high_score"]
        return _micro_review(high_score=high_score, passed=False, required_passed=2)

    monkeypatch.setattr(remediation, "build_micro_tilt_review", fake_micro_review)

    review = remediation.build_review(
        panel_path=Path("panel.parquet"),
        walk_forward_audit_path=Path("audit.json"),
        high_scores=[1.01, 1.02, 1.03],
        required_cost_bps=[0.0, 2.0, 5.0],
        as_of="2026-07-21",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_cost_warning_remediation_review"
    assert review["status"] == "blocked"
    assert review["summary"]["passed_count"] == 0
    assert review["summary"]["cost_warning_resolved"] is False
    assert review["summary"]["best_high_score"] == 1.01
    assert "no_micro_tilt_candidate_passes_required_cost_scenarios" in review["blocking_reasons"]
    assert review["decision"]["shadow_training_ready"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False


def test_build_review_marks_cost_warning_resolved_when_candidate_passes(monkeypatch) -> None:
    def fake_micro_review(**kwargs):
        high_score = kwargs["high_score"]
        passed = high_score == 1.02
        return _micro_review(high_score=high_score, passed=passed, required_passed=3 if passed else 2)

    monkeypatch.setattr(remediation, "build_micro_tilt_review", fake_micro_review)

    review = remediation.build_review(
        panel_path=Path("panel.parquet"),
        walk_forward_audit_path=Path("audit.json"),
        high_scores=[1.01, 1.02],
        required_cost_bps=[0.0, 2.0, 5.0],
        as_of="2026-07-21",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["passed_count"] == 1
    assert review["summary"]["cost_warning_resolved"] is True
    assert review["summary"]["recommended_candidate"]["high_score"] == 1.02
    assert review["blocking_reasons"] == []
    assert review["decision"]["shadow_training_ready"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "remediation.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_cost_warning_remediation_review",
        "as_of": "2026-07-21",
    }

    remediation.write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_cost_warning_remediation_review_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
