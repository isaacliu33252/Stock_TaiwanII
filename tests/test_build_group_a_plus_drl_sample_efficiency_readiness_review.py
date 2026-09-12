from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_drl_sample_efficiency_readiness_review import build_review


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_drl_sample_efficiency_review_blocks_live_allocator(tmp_path: Path) -> None:
    market = _write_json(
        tmp_path / "market.json",
        {
            "status": "blocked",
            "computed": {"turnover": 0.2, "max_participation_of_volume": 0.001},
            "decision": {"auto_rebalance_allowed": False},
        },
    )
    governance = _write_json(
        tmp_path / "governance.json",
        {
            "status": "blocked",
            "governance_checklist": {"live_exploration_forbidden": True},
            "decision": {"live_rl_allocator_allowed": False},
        },
    )
    execution_plan = tmp_path / "execution_plan.py"
    execution_plan.write_text(
        "def _apply_buy_staging(): pass\n"
        "max_initial_buy_fraction = 0.4\n"
        "total_execution_cost = 0.0\n",
        encoding="utf-8",
    )

    review = build_review(
        as_of="2026-08-14",
        market_impact_path=market,
        rl_governance_path=governance,
        execution_plan_py=execution_plan,
    )

    assert review["status"] == "blocked"
    assert review["decision"]["drl_allocator_promotable"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["local_capability_check"]["execution_plan_primitives"] == {
        "path": str(execution_plan),
        "staged_buys_present": True,
        "buy_fraction_control_present": True,
        "transaction_cost_logging_present": True,
    }
    assert "paper_sample_efficiency_requirement_not_satisfied_by_real_market_history" in review["blocking_reasons"]
    assert "market_impact_readiness_blocked" in review["blocking_reasons"]
    assert "rl_governance_readiness_blocked" in review["blocking_reasons"]
