from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_goal_horizon_reward_readiness_review import build_review, write_review


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_goal_horizon_review_blocks_when_goal_contract_missing(tmp_path: Path) -> None:
    signal = _write(
        tmp_path / "signal.json",
        {"data": {"target_weights": {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}}},
    )
    plan = _write(tmp_path / "plan.json", {"data": {"summary": {}}})

    review = build_review(live_signal_path=signal, execution_plan_path=plan, as_of="2026-08-08")

    assert review["report_type"] == "group_a_plus_goal_horizon_reward_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["goal_horizon_reward_layer_imported_as_review"] is True
    assert review["decision"]["live_rl_allocator_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True
    assert "missing_explicit_financial_goal_target_value" in review["blocking_reasons"]
    assert "missing_explicit_goal_target_date" in review["blocking_reasons"]
    assert "missing_periodic_contribution_plan" in review["blocking_reasons"]


def test_goal_horizon_review_research_ready_when_contract_present(tmp_path: Path) -> None:
    signal = _write(
        tmp_path / "signal.json",
        {
            "data": {
                "financial_goal_target_value": 1_200_000,
                "financial_goal_target_date": "2026-12-31",
                "planned_periodic_contribution": 10_000,
                "target_weights": {"0050.TW": 0.6, "00631L.TW": 0.1, "cash": 0.3},
            }
        },
    )
    plan = _write(tmp_path / "plan.json", {"data": {"summary": {"estimated_total_cost": 120.0}}})

    review = build_review(live_signal_path=signal, execution_plan_path=plan, as_of="2026-08-08")

    assert review["status"] == "research_ready"
    assert review["goal_path_readiness"]["has_goal_target"] is True
    assert review["goal_path_readiness"]["has_goal_horizon"] is True
    assert review["goal_path_readiness"]["has_contribution_plan"] is True
    assert review["decision"]["ready_for_reward_overlay_backtest"] is True
    assert review["decision"]["auto_rebalance_allowed"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "goal.json"
    history = tmp_path / "history"
    review = {"report_type": "group_a_plus_goal_horizon_reward_readiness_review", "as_of": "2026-08-08"}

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "goal_horizon_reward_readiness_20260808.json").read_text(encoding="utf-8")) == review
