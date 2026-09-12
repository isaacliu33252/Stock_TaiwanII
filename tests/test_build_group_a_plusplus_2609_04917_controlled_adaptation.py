from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plusplus_2609_04917_controlled_adaptation as module


def _write(path: Path, payload: dict | str) -> None:
    path.write_text(json.dumps(payload) if isinstance(payload, dict) else payload, encoding="utf-8")


def test_controlled_adaptation_blocks_missing_approval_and_rollback(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha.json"
    selection = tmp_path / "selection.json"
    bom = tmp_path / "bom.json"
    joint = tmp_path / "joint.json"
    registry = tmp_path / "registry.json"
    _write(alpha, {"status": "blocked", "blocked_dimensions": ["external_validity"], "generated_at": "x"})
    _write(selection, {"status": "blocked", "frozen_confirmatory_specification_available": False, "generated_at": "x"})
    _write(bom, {"status": "warning"})
    _write(joint, {"status": "blocked"})
    _write(registry, {"artifacts": [{"path": "a"}]})

    report = module.build_report(
        alpha_gate_path=alpha,
        selection_ledger_path=selection,
        information_bom_path=bom,
        joint_execution_path=joint,
        shadow_registry_path=registry,
    )

    assert report["status"] == "blocked"
    assert "predeclared_trigger_available" in report["blocking_reasons"]
    assert "human_approval_record_available" in report["blocking_reasons"]
    assert "rollback_plan_available" in report["blocking_reasons"]
    assert report["decision"]["creates_orders"] is False


def test_controlled_adaptation_can_reach_limited_review_when_all_controls_exist(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha.json"
    selection = tmp_path / "selection.json"
    bom = tmp_path / "bom.json"
    joint = tmp_path / "joint.json"
    registry = tmp_path / "registry.json"
    approval = tmp_path / "approval.json"
    rollback = tmp_path / "rollback.md"
    _write(alpha, {"status": "available_for_human_review", "blocked_dimensions": [], "generated_at": "x"})
    _write(selection, {"status": "available", "frozen_confirmatory_specification_available": True, "generated_at": "x"})
    _write(bom, {"status": "available"})
    _write(joint, {"status": "available_for_manual_review"})
    _write(registry, {"artifacts": [{"path": "a"}]})
    _write(approval, {"approved": True})
    _write(rollback, "rollback")

    report = module.build_report(
        alpha_gate_path=alpha,
        selection_ledger_path=selection,
        information_bom_path=bom,
        joint_execution_path=joint,
        shadow_registry_path=registry,
        rollback_plan_path=rollback,
        approval_record_path=approval,
    )

    assert report["status"] == "ready_for_limited_human_adaptation_review"
    assert report["blocking_reasons"] == []
    assert report["decision"]["promotion_allowed"] is False
