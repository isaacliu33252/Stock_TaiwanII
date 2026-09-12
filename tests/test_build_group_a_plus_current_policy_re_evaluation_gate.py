from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_current_policy_re_evaluation_gate as module


def _shadow_payload() -> dict:
    return {
        "status": "ok",
        "policy": "research_only_no_weight_change",
        "as_of": "2026-09-03",
        "risk_state": {"cap_only_annualized_volatility_reduction": 0.01},
        "adjoint_policy_iteration_shadow": {
            "policy": "research_only_no_weight_change",
            "stable_within_grid_step": True,
            "cap_delta_second_minus_first": {"00631L.TW": 0.0},
            "first_pass": {"cap_only_weights": {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}},
            "second_pass": {"cap_only_weights": {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}},
        },
        "active_set_stability": {
            "verdict": "stable_active_set",
            "stability_ratio": 1.0,
        },
        "matched_budget_re_evaluation_comparator": {
            "agrees_with_frozen_budget": True,
            "verdict": "current_policy_re_evaluation_supported",
            "frozen_policy_vote_fraction": {"00631L.TW": 1.0},
        },
        "error_decomposition": {
            "verdict": "diagnostic_supported_but_not_actionable",
            "blockers": ["stability_tuned_gate_inactive"],
        },
        "stability_tuned_re_evaluation_gate": {
            "gate_active": True,
        },
    }


def _tail_bank_payload(*, promotion_allowed: bool) -> dict:
    return {
        "policy": "research_only_no_weight_change",
        "decision": {
            "promotion_allowed": promotion_allowed,
            "decision": "eligible_for_manual_review_not_auto_promote"
            if promotion_allowed
            else "do_not_promote_keep_shadow",
            "best_stability_candidate": "stable",
            "no_further_auto_tuning_recommended": not promotion_allowed,
        },
    }


def test_build_report_blocks_when_tail_bank_rejects() -> None:
    report = module.build_report(
        _shadow_payload(),
        shadow_path=Path("shadow.json"),
        tail_bank=_tail_bank_payload(promotion_allowed=False),
        tail_bank_path=Path("tail.json"),
    )

    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["decision"] == "keep_shadow_do_not_promote"
    assert "tail_bank_promotion_allowed" in report["decision"]["blockers"]
    assert report["changes_latest_strategy"] is False
    assert report["changes_golden1_0531"] is False
    assert report["changes_golden2_0830"] is False


def test_build_report_allows_manual_review_only_when_all_checks_pass() -> None:
    report = module.build_report(
        _shadow_payload(),
        shadow_path=Path("shadow.json"),
        tail_bank=_tail_bank_payload(promotion_allowed=True),
        tail_bank_path=Path("tail.json"),
    )

    assert report["decision"]["promotion_allowed"] is True
    assert report["decision"]["decision"] == "eligible_for_manual_review_not_auto_promote"
    assert report["decision"]["blockers"] == []
    assert report["policy"] == "research_only_no_weight_change"


def test_write_outputs_renders_decision_and_checks(tmp_path: Path) -> None:
    report = module.build_report(
        _shadow_payload(),
        shadow_path=tmp_path / "shadow.json",
        tail_bank=_tail_bank_payload(promotion_allowed=False),
        tail_bank_path=tmp_path / "tail.json",
    )
    output = tmp_path / "gate.json"
    markdown = tmp_path / "gate.md"

    module.write_outputs(report, output, markdown)

    payload = json.loads(output.read_text(encoding="utf-8"))
    text = markdown.read_text(encoding="utf-8")
    assert payload["report_type"] == "group_a_plus_current_policy_re_evaluation_gate"
    assert "Current-Policy Re-Evaluation Gate" in text
    assert "keep_shadow_do_not_promote" in text
    assert "tail_bank_promotion_allowed" in text
