from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plusplus_2609_04917_alpha_translation_readiness as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_inputs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "profit_readiness_path": tmp_path / "profit.json",
        "shadow_registry_path": tmp_path / "registry.json",
        "daily_artifact_integrity_path": tmp_path / "integrity.json",
        "ops_health_path": tmp_path / "ops.json",
        "execution_plan_promotion_path": tmp_path / "exec_promo.json",
        "market_impact_path": tmp_path / "impact.json",
        "capacity_crowding_path": tmp_path / "capacity.json",
        "selection_ledger_path": tmp_path / "selection.json",
        "live_signal_path": tmp_path / "live.json",
        "execution_plan_path": tmp_path / "plan.json",
    }
    _write_json(
        paths["profit_readiness_path"],
        {
            "status": "shadow_candidates_blocked_for_live_promotion",
            "active_shadow_candidates": ["staged_reentry"],
            "live_ready_shadow_candidates": [],
            "deployment_blockers": [],
            "decision": {
                "creates_orders": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
            },
            "tail_sensitive_review": {"status": "available"},
            "candidate_tail_review": {"status": "available"},
            "bootstrap_promotion_gate": {"status": "blocked_for_live_promotion"},
            "turnover_cost_robustness_review": {"status": "blocked_for_live_promotion"},
            "staged_reentry_promotion_review": {"status": "blocked_for_live_promotion"},
            "source_status": {"ops_health": "ok"},
        },
    )
    _write_json(paths["shadow_registry_path"], {"artifacts": [{"path": "a"}, {"path": "b"}]})
    _write_json(paths["daily_artifact_integrity_path"], {"status": "ok"})
    _write_json(paths["ops_health_path"], {"status": "ok"})
    _write_json(paths["execution_plan_promotion_path"], {"status": "available_for_manual_review"})
    _write_json(paths["market_impact_path"], {"status": "available_for_manual_review"})
    _write_json(paths["capacity_crowding_path"], {"status": "blocked"})
    _write_json(
        paths["selection_ledger_path"],
        {
            "status": "blocked",
            "blocking_reasons": ["frozen_confirmatory_specification_missing"],
            "decision": {"selection_ledger_available": True, "confirmatory_specification_frozen": False},
        },
    )
    _write_json(
        paths["live_signal_path"],
        {"actual_data_date": "2026-09-09", "target_weights": {"0050.TW": 0.4, "cash": 0.6}},
    )
    _write_json(paths["execution_plan_path"], {"planning_status": "manual_review_required"})
    return paths


def test_alpha_translation_gate_is_shadow_only_and_blocks_incomplete_evidence(tmp_path: Path) -> None:
    paths = _base_inputs(tmp_path)

    report = module.build_report(**paths, as_of="2026-09-09")

    assert report["status"] == "blocked_for_live_promotion"
    assert report["policy"] == "shadow_only_alpha_translation_governance_no_weight_change"
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["latest_strategy_change_allowed"] is False
    assert "selection_control" in report["blocked_dimensions"]
    assert "confirmatory_specification_not_frozen_for_2609_04917_gate" in report["dimensions"]["selection_control"]["blockers"]
    assert "selection_ledger:frozen_confirmatory_specification_missing" in report["dimensions"]["selection_control"]["blockers"]
    assert "risk_benchmark" in report["blocked_dimensions"]
    assert "implementation_realism" in report["blocked_dimensions"]
    assert report["live_ready_shadow_candidates_after_2609_04917_gate"] == []


def test_alpha_translation_gate_can_clear_mocked_complete_evidence_except_selection(tmp_path: Path) -> None:
    paths = _base_inputs(tmp_path)
    _write_json(
        paths["profit_readiness_path"],
        {
            "active_shadow_candidates": ["staged_reentry"],
            "live_ready_shadow_candidates": ["staged_reentry"],
            "deployment_blockers": [],
            "decision": {
                "creates_orders": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
            },
            "tail_sensitive_review": {"status": "available"},
            "candidate_tail_review": {"status": "available"},
            "bootstrap_promotion_gate": {"status": "available"},
            "turnover_cost_robustness_review": {"status": "available"},
            "staged_reentry_promotion_review": {"status": "available"},
            "source_status": {"ops_health": "ok"},
        },
    )
    _write_json(paths["capacity_crowding_path"], {"status": "available"})
    _write_json(
        paths["selection_ledger_path"],
        {
            "status": "available_for_confirmatory_review",
            "blocking_reasons": [],
            "decision": {"selection_ledger_available": True, "confirmatory_specification_frozen": True},
        },
    )

    report = module.build_report(**paths, as_of="2026-09-09")

    assert report["dimensions"]["temporality"]["status"] == "pass"
    assert report["dimensions"]["portfolio_mapping"]["status"] == "pass"
    assert report["dimensions"]["implementation_realism"]["status"] == "pass"
    assert report["dimensions"]["risk_benchmark"]["status"] == "pass"
    assert report["dimensions"]["operational_provenance"]["status"] == "pass"
    assert report["dimensions"]["selection_control"]["status"] == "pass"
    assert report["dimensions"]["external_validity"]["status"] == "blocked"
    assert report["decision"]["human_promotion_review_allowed"] is False


def test_markdown_lists_all_seven_dimensions(tmp_path: Path) -> None:
    paths = _base_inputs(tmp_path)
    report = module.build_report(**paths, as_of="2026-09-09")
    markdown = module._markdown(report)

    for dimension in module.DIMENSIONS:
        assert f"| {dimension} |" in markdown
    assert "## Recommended Next Actions" in markdown
