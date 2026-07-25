from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_readiness_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_review_blocks_llm_interface_when_inputs_are_not_promotable(tmp_path: Path) -> None:
    inputs = {
        "rl_governance": _write(
            tmp_path / "rl.json",
            {
                "status": "blocked",
                "decision": {
                    "rl_component_promotable": False,
                    "live_rl_allocator_allowed": False,
                    "allow_00631l_add": False,
                },
            },
        ),
        "market_impact": _write(
            tmp_path / "market.json",
            {"status": "blocked", "decision": {"market_impact_ready": False}},
        ),
        "synthetic_augmentation_validation": _write(
            tmp_path / "synthetic.json",
            {"status": "blocked", "decision": {"synthetic_validation_ready": False}},
        ),
        "dynamic_cvar_tail_cost": _write(
            tmp_path / "cvar.json",
            {"status": "blocked", "decision": {"tail_cost_readiness_ready": False}},
        ),
        "deployment_consistency": _write(
            tmp_path / "deployment.json",
            {"status": "manual_review_required", "decision": {"broker_actionable": False}},
        ),
        "research_shadow_decision_snapshot": _write(
            tmp_path / "research.json",
            {"status": "blocked", "decision": {"allow_00631l_add": False}},
        ),
    }

    review = build_review(inputs, as_of="2026-07-20")

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["feature_proposal_governance_imported"] is True
    assert review["decision"]["llm_state_reward_interface_ready"] is False
    assert review["decision"]["live_llm_trading_allowed"] is False
    assert review["decision"]["live_ppo_allocator_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["allowed_shadow_scope"]["llm_queries_allowed_at_test_time"] is False
    assert "rl_governance_blocked" in review["blocking_reasons"]
    assert "rl_component_not_promotable_for_llm_interface" in review["blocking_reasons"]
    assert "deployment_not_broker_actionable" in review["blocking_reasons"]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "llm_state_reward.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_readiness_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_readiness_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
