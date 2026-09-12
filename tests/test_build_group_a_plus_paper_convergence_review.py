from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_paper_convergence_review import build_report, write_report


def test_build_paper_convergence_report_from_files(tmp_path: Path) -> None:
    signed = tmp_path / "signed.json"
    validation = tmp_path / "validation.json"
    guarded = tmp_path / "guarded.json"
    liquidity = tmp_path / "liquidity.json"
    cvar_cost_window_split = tmp_path / "cvar_cost_window_split.json"
    re_evaluation_gate = tmp_path / "re_evaluation_gate.json"
    auxiliary_task_readiness = tmp_path / "auxiliary_task_readiness.json"
    adoption_2609_08106 = tmp_path / "adoption_2609_08106.json"
    signed.write_text(
        json.dumps({"signed_review_ready": True, "decision": {"manual_signature_valid": False}}),
        encoding="utf-8",
    )
    guarded.write_text(json.dumps({"enabled": False}), encoding="utf-8")
    validation.write_text(
        json.dumps({"status": "valid_for_guarded_candidate_target_output", "decision": {"manual_signature_valid": True}}),
        encoding="utf-8",
    )
    liquidity.write_text(
        json.dumps({"summary": {"ready_for_manual_review": True}, "input_coverage": {"trigger_count": 313}}),
        encoding="utf-8",
    )
    cvar_cost_window_split.write_text(
        json.dumps(
            {
                "status": "blocked_for_live_promotion",
                "summary": {"tail_cost_window_split_passed": False},
            }
        ),
        encoding="utf-8",
    )
    re_evaluation_gate.write_text(
        json.dumps(
            {
                "decision": {
                    "promotion_allowed": False,
                    "decision": "keep_shadow_do_not_promote",
                    "blockers": ["tail_bank_promotion_allowed"],
                }
            }
        ),
        encoding="utf-8",
    )
    auxiliary_task_readiness.write_text(
        json.dumps(
            {
                "decision": {
                    "promotion_allowed": False,
                    "decision": "shadow_readiness_only",
                    "blockers": ["downstream_policy_lift_validated"],
                }
            }
        ),
        encoding="utf-8",
    )
    adoption_2609_08106.write_text(
        json.dumps(
            {
                "decision": {
                    "adopt_into_latest_strategy_now": False,
                    "advisory_import_allowed": True,
                    "live_weight_change_allowed": False,
                },
                "forward_evidence_gate": {"passed": False, "sample_count": 2, "triggered_count": 0, "realized_count": 0},
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        as_of="2026-08-07",
        signed_review_path=signed,
        signed_approval_validation_path=validation,
        guarded_candidate_path=guarded,
        liquidity_feedback_path=liquidity,
        tracking_review_path=None,
        market_impact_path=None,
        moira_validation_path=None,
        moira_backtest_path=None,
        event_quality_path=None,
        cvar_review_path=None,
        cvar_cost_window_split_path=cvar_cost_window_split,
        tail_review_path=None,
        re_evaluation_gate_path=re_evaluation_gate,
        auxiliary_task_readiness_path=auxiliary_task_readiness,
        adoption_2609_08106_path=adoption_2609_08106,
    )

    assert report["report_type"] == "group_a_plus_paper_convergence_review"
    assert report["top_candidate_id"] == "defensive_cash_floor_high_risk_state"
    assert report["sources"]["signed_review"] == str(signed)
    assert report["sources"]["signed_approval_validation"] == str(validation)
    assert report["sources"]["cvar_cost_window_split"] == str(cvar_cost_window_split)
    assert report["sources"]["re_evaluation_gate"] == str(re_evaluation_gate)
    assert report["sources"]["auxiliary_task_readiness"] == str(auxiliary_task_readiness)
    assert report["sources"]["adoption_2609_08106"] == str(adoption_2609_08106)
    assert any(
        candidate["candidate_id"] == "nystrom_attention_complementarity_2609_08106"
        for candidate in report["candidates"]
    )


def test_write_paper_convergence_report_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "paper.json"
    history = tmp_path / "history"
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_paper_convergence_review",
        "policy": "review_only_no_target_weight_change",
        "as_of": "2026-08-07",
        "top_candidate_id": "defensive_cash_floor_high_risk_state",
        "top_candidate_decision": "best_candidate_but_signed_review_blocked",
        "candidates": [],
        "decision": {"target_weight_change_allowed": False},
        "summary": {},
    }

    write_report(report, output_path=output, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8"))["top_candidate_id"] == "defensive_cash_floor_high_risk_state"
    assert (history / "paper_convergence_review_20260807.json").exists()
