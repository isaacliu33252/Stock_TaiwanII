from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_alignment_remediation_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _diagnostic(path: Path) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "mean_reward_future_return_alignment": -0.0142,
                "ppo_training_queue_allowed_by_alignment": False,
            },
            "decision": {
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _sweep(path: Path, *, return_alignment: float = -0.031) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "top_candidates": [
                {
                    "params": {"drawdown_weight": 0.3, "volatility_weight": 0.5},
                    "mean_return_alignment": return_alignment,
                    "mean_downside_alignment": -0.061,
                    "downside_grade": "green",
                    "rank_score": 1.0,
                }
            ],
            "decision": {
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_alignment_remediation_finds_manual_review_candidate(tmp_path: Path) -> None:
    review = build_review(
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        downside_tail_decay_sweep_path=_sweep(tmp_path / "sweep.json"),
        as_of="2026-07-22",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["current_return_alignment_grade"] == "red"
    assert review["summary"]["acceptable_candidate_count"] == 1
    assert review["summary"]["best_acceptable_return_alignment_grade"] == "yellow"
    assert review["decision"]["candidate_resolves_return_alignment_red_for_manual_review"] is True
    assert review["decision"]["candidate_allows_ppo_queue_by_alignment"] is False
    assert "candidate_requires_manual_review_yellow_alignment" in review["warning_reasons"]
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_alignment_remediation_keeps_blocker_when_no_candidate(tmp_path: Path) -> None:
    review = build_review(
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        downside_tail_decay_sweep_path=_sweep(tmp_path / "sweep.json", return_alignment=-0.01),
        as_of="2026-07-22",
    )

    assert review["summary"]["acceptable_candidate_count"] == 0
    assert review["decision"]["candidate_resolves_return_alignment_red_for_manual_review"] is False
    assert "no_candidate_moves_return_alignment_out_of_red" in review["warning_reasons"]
    assert review["decision"]["model_training_allowed"] is False


def test_alignment_remediation_blocks_unexpected_permissions(tmp_path: Path) -> None:
    sweep = _sweep(tmp_path / "sweep.json")
    payload = json.loads(sweep.read_text(encoding="utf-8"))
    payload["decision"]["ppo_training_allowed"] = True
    sweep.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    review = build_review(
        diagnostic_refinement_path=_diagnostic(tmp_path / "diagnostic.json"),
        downside_tail_decay_sweep_path=sweep,
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "downside_tail_decay_sweep_unexpected_permission:ppo_training_allowed" in review["blocking_reasons"]
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "remediation.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_alignment_remediation_review",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_alignment_remediation_review_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
