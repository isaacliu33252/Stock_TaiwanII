from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_rl_governance_readiness_review import build_review, write_review


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_review_blocks_rl_promotion_when_governance_inputs_are_blocked(tmp_path: Path) -> None:
    inputs = {
        "deployment_consistency": _write(
            tmp_path / "deployment.json",
            {"status": "manual_review_required", "decision": {"broker_actionable": False}},
        ),
        "market_impact_readiness": _write(
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
        "intervention_fatigue_risk_budget": _write(
            tmp_path / "intervention.json",
            {"status": "blocked", "decision": {"risk_budget_pacing_ready": False}},
        ),
        "research_shadow_decision_snapshot": _write(
            tmp_path / "research.json",
            {"status": "blocked", "decision": {"allow_00631l_add": False}},
        ),
        "adversarial_market_integrity": _write(
            tmp_path / "adversarial.json",
            {"status": "blocked", "decision": {"market_integrity_ready": False}},
        ),
        "finstressts_decision_snapshot": _write(
            tmp_path / "fin.json",
            {"status": "blocked", "decision": {"allow_00631l_add": False}},
        ),
    }

    review = build_review(inputs, as_of="2026-07-20")

    assert review["report_type"] == "group_a_plus_rl_governance_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["rl_component_promotable"] is False
    assert review["decision"]["live_rl_allocator_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "market_impact_readiness_blocked" in review["blocking_reasons"]
    assert "deployment_not_broker_actionable" in review["blocking_reasons"]
    assert "research_shadow_snapshot_blocked" in review["blocking_reasons"]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "rl_governance.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_rl_governance_readiness_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "rl_governance_readiness_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
