from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_human_exception_record_draft import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _triage(path: Path, *, ready: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_exception_review" if ready else "blocked",
            "summary": {
                "research_shadow_blocker_count": 14,
                "live_allocation_blocker_count": 12,
                "training_governance_blocker_count": 2,
            },
            "classified_blockers": {
                "live_allocation_or_broker_action_blockers": ["finstressts_snapshot_blocked"],
                "training_governance_blockers": ["rl_governance_readiness_blocked"],
                "uncategorized_blockers": [],
            },
            "decision": {
                "manual_exception_review_ready": ready,
                "manual_exception_to_queue_training_allowed": False,
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "outputs_actions": False,
                "outputs_target_weights": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
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
            "decision": {
                "manual_approval_review_ready": ready,
                "manual_approval_to_queue_training_allowed": False,
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "outputs_actions": False,
                "outputs_target_weights": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _package(path: Path, *, excluded_tickers: list[str] | None = None) -> Path:
    if excluded_tickers is None:
        excluded_tickers = ["00631L.TW", "00632R.TW"]
    return _write(
        path,
        {
            "status": "available_for_manual_review",
            "summary": {
                "package_ready_for_manual_review": True,
                "recommended_regime_rule": "trend_above_train_median",
            },
            "request_boundary": {
                "freeze_id": "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721",
                "frozen_manifest_sha256": "abc123",
                "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                "eligible_tickers": ["0050.TW", "0056.TW"],
                "excluded_tickers": excluded_tickers,
                "state_columns": ["downside_deviation", "realized_volatility"],
                "reward_columns": ["drawdown_penalty", "reward_proxy"],
                "recommended_regime_filter": {"regime_rule": "trend_above_train_median"},
                "hard_constraints": {
                    "no_00631l_add": "00631L.TW" in excluded_tickers,
                    "no_00632r_open": "00632R.TW" in excluded_tickers,
                },
            },
            "decision": {
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "outputs_actions": False,
                "outputs_target_weights": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_human_exception_record_draft_ready_but_all_permissions_false(tmp_path: Path) -> None:
    review = build_review(
        triage_path=_triage(tmp_path / "triage.json"),
        manual_approval_path=_manual(tmp_path / "manual.json"),
        request_package_path=_package(tmp_path / "package.json"),
        as_of="2026-07-22",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_human_exception_record_draft"
    assert review["status"] == "draft_ready_for_human_review"
    assert review["summary"]["human_exception_record_draft_ready"] is True
    assert review["summary"]["human_exception_approved"] is False
    assert review["summary"]["training_queue_allowed"] is False
    assert review["decision"]["training_queue_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True
    assert review["exception_record_draft"]["approval_state"] == "draft_not_approved"
    assert review["exception_record_draft"]["scope"] == "non_ppo_offline_shadow_training_queue_review_only"
    assert review["exception_record_draft"]["excluded_tickers"] == ["00631L.TW", "00632R.TW"]
    assert review["exception_record_draft"]["hard_constraints"]["no_auto_rebalance"] is True
    assert review["exception_record_draft"]["hard_constraints"]["no_target_weight_output"] is True


def test_human_exception_record_draft_blocks_when_triage_not_ready(tmp_path: Path) -> None:
    review = build_review(
        triage_path=_triage(tmp_path / "triage.json", ready=False),
        manual_approval_path=_manual(tmp_path / "manual.json"),
        request_package_path=_package(tmp_path / "package.json"),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "manual_exception_review_not_ready" in review["blocking_reasons"]
    assert review["decision"]["human_exception_record_draft_ready"] is False
    assert review["decision"]["model_training_allowed"] is False


def test_human_exception_record_draft_blocks_when_required_exclusion_missing(tmp_path: Path) -> None:
    review = build_review(
        triage_path=_triage(tmp_path / "triage.json"),
        manual_approval_path=_manual(tmp_path / "manual.json"),
        request_package_path=_package(tmp_path / "package.json", excluded_tickers=["00631L.TW"]),
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "request_boundary_missing_excluded_ticker:00632R.TW" in review["blocking_reasons"]
    assert "request_boundary_missing_hard_constraint:no_00632r_open:00632R.TW" in review["blocking_reasons"]
    assert review["decision"]["allow_00632r_open"] is False


def test_human_exception_record_draft_detects_unexpected_permission(tmp_path: Path) -> None:
    package = _package(tmp_path / "package.json")
    payload = json.loads(package.read_text(encoding="utf-8"))
    payload["decision"]["model_training_allowed"] = True
    package.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    review = build_review(
        triage_path=_triage(tmp_path / "triage.json"),
        manual_approval_path=_manual(tmp_path / "manual.json"),
        request_package_path=package,
        as_of="2026-07-22",
    )

    assert review["status"] == "blocked"
    assert "request_package_unexpected_permission:model_training_allowed" in review["blocking_reasons"]
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "draft.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_human_exception_record_draft",
        "as_of": "2026-07-22",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_human_exception_record_draft_20260722.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
