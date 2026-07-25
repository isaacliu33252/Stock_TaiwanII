from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_research_shadow_blocker_triage import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _research(path: Path, *, extra_blockers: list[str] | None = None) -> Path:
    blockers = [
        "finstressts_snapshot_blocked",
        "trigate_vol_memory_blocks_leverage_add",
        "rl_governance_readiness_blocked",
        "llm_state_reward_interface_readiness_blocked",
    ]
    blockers.extend(extra_blockers or [])
    return _write(
        path,
        {
            "status": "blocked",
            "blocking_reasons": blockers,
            "decision": {
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _manual(path: Path, *, ready: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_approval_review" if ready else "blocked",
            "training_queue_blocking_reasons": ["research_shadow_decision_snapshot_blocked"],
            "summary": {
                "alignment_remediation_resolves_return_red": True,
            },
            "decision": {
                "manual_approval_review_ready": ready,
                "manual_approval_to_queue_training_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_triage_classifies_research_shadow_blockers_for_manual_exception(tmp_path: Path) -> None:
    review = build_review(
        research_shadow_path=_research(tmp_path / "research.json"),
        manual_approval_path=_manual(tmp_path / "manual.json"),
        as_of="2026-07-22",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_research_shadow_blocker_triage"
    assert review["status"] == "available_for_manual_exception_review"
    assert review["summary"]["research_shadow_blocker_count"] == 4
    assert review["summary"]["live_allocation_blocker_count"] == 2
    assert review["summary"]["training_governance_blocker_count"] == 2
    assert review["summary"]["manual_exception_review_ready"] is True
    assert review["summary"]["human_exception_record_required"] is True
    assert review["classified_blockers"]["live_allocation_or_broker_action_blockers"] == [
        "finstressts_snapshot_blocked",
        "trigate_vol_memory_blocks_leverage_add",
    ]
    assert review["classified_blockers"]["training_governance_blockers"] == [
        "rl_governance_readiness_blocked",
        "llm_state_reward_interface_readiness_blocked",
    ]
    assert review["decision"]["manual_exception_to_queue_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_triage_warns_on_uncategorized_blocker(tmp_path: Path) -> None:
    review = build_review(
        research_shadow_path=_research(tmp_path / "research.json", extra_blockers=["new_unknown_blocker"]),
        manual_approval_path=_manual(tmp_path / "manual.json"),
        as_of="2026-07-22",
    )

    assert review["summary"]["uncategorized_blocker_count"] == 1
    assert "uncategorized_research_shadow_blocker:new_unknown_blocker" in review["warning_reasons"]
    assert review["decision"]["model_training_allowed"] is False


def test_triage_blocks_when_manual_review_not_ready(tmp_path: Path) -> None:
    review = build_review(
        research_shadow_path=_research(tmp_path / "research.json"),
        manual_approval_path=_manual(tmp_path / "manual.json", ready=False),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "manual_approval_review_not_ready" in review["blocking_reasons"]
    assert review["decision"]["manual_exception_review_ready"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "triage.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_research_shadow_blocker_triage",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_research_shadow_blocker_triage_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
