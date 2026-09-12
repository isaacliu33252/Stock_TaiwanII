from __future__ import annotations

from group_a_plus.integrations.paper_convergence_review import build_paper_convergence_review


def test_convergence_review_ranks_defensive_cash_floor_when_package_exists() -> None:
    report = build_paper_convergence_review(
        as_of="2026-08-07",
        signed_review={"signed_review_ready": True, "decision": {"manual_signature_valid": False}},
        signed_approval_validation={"status": "valid_for_guarded_candidate_target_output", "decision": {"manual_signature_valid": True}},
        guarded_candidate={"enabled": False, "decision": {"target_weight_change_allowed": False}},
        liquidity_feedback={
            "summary": {"ready_for_manual_review": True},
            "input_coverage": {"trigger_count": 313},
        },
        tracking_review={"status": "blocked"},
        market_impact={"status": "blocked"},
        moira_backtest={"input_coverage": {"strict_actionable_trigger_count": 4}},
        event_quality={"status": "blocked_review_only"},
        cvar_review={"status": "blocked"},
        cvar_cost_window_split={
            "status": "blocked_for_live_promotion",
            "summary": {
                "tail_cost_window_split_passed": False,
                "latest_loses_to_no_00631l_windows": 5,
                "latest_loses_to_no_letf_windows": 4,
            },
        },
        tail_review={"status": "blocked"},
    )

    assert report["policy"] == "review_only_no_target_weight_change"
    assert report["top_candidate_id"] == "defensive_cash_floor_high_risk_state"
    assert report["top_candidate_decision"] == "candidate_ready_for_guarded_monitoring"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["summary"]["correct_use_found"] is True
    tail_cvar = next(candidate for candidate in report["candidates"] if candidate["candidate_id"] == "tail_risk_governance_not_optimizer")
    assert "cvar_cost_window_split_2606_26625_blocked_for_live_promotion" in tail_cvar["blockers"]
    assert tail_cvar["evidence"]["cvar_cost_window_split_2606_26625_passed"] is False


def test_convergence_review_keeps_letf_liquidity_review_only_when_inputs_blocked() -> None:
    report = build_paper_convergence_review(
        as_of="2026-08-07",
        liquidity_feedback={
            "summary": {"ready_for_manual_review": True},
            "input_coverage": {"trigger_count": 313},
        },
        tracking_review={"status": "blocked"},
        market_impact={"status": "blocked"},
    )

    letf = next(candidate for candidate in report["candidates"] if candidate["candidate_id"] == "letf_large_trade_staging_review")

    assert letf["decision"] == "research_candidate_needs_validation"
    assert "review_only_no_weight_change" in letf["blockers"]
    assert "tracking_error_review_blocked" in letf["blockers"]
    assert "market_impact_review_blocked" in letf["blockers"]


def test_convergence_review_includes_2608_17808_gate_as_shadow_only_context() -> None:
    report = build_paper_convergence_review(
        as_of="2026-09-03",
        re_evaluation_gate={
            "decision": {
                "promotion_allowed": False,
                "decision": "keep_shadow_do_not_promote",
                "blockers": ["tail_bank_promotion_allowed"],
            },
            "checks": {
                "shadow_report_ok": True,
                "tail_bank_promotion_allowed": False,
            },
            "evidence": {
                "two_pass_l1_delta_second_minus_first": 0.0,
                "active_set_verdict": "stable_active_set",
                "matched_budget_verdict": "current_policy_re_evaluation_supported",
                "error_decomposition_verdict": "diagnostic_blocked",
                "tail_bank": {"decision": "do_not_promote_keep_shadow"},
            },
        },
    )

    candidate = next(
        item for item in report["candidates"] if item["candidate_id"] == "current_policy_re_evaluation_gate_2608_17808"
    )
    assert candidate["decision"] == "review_context_only"
    assert "research_only_no_weight_change" in candidate["blockers"]
    assert "tail_bank_promotion_allowed" in candidate["blockers"]
    assert candidate["evidence"]["tail_bank_decision"] == "do_not_promote_keep_shadow"
    assert report["decision"]["target_weight_change_allowed"] is False


def test_convergence_review_includes_2608_15841_auxiliary_readiness_context() -> None:
    report = build_paper_convergence_review(
        as_of="2026-09-04",
        auxiliary_task_readiness={
            "decision": {
                "promotion_allowed": False,
                "decision": "shadow_readiness_only",
                "blockers": ["downstream_policy_lift_validated"],
            },
            "checks": {
                "existing_aux_heads_available": True,
                "aux_head_standalone_quality_passed": True,
                "live_feature_freshness_ok": False,
            },
            "panels": [
                {"ticker": "00631L.TW", "rows": 406, "date_start": "2025-01-02", "date_end": "2026-09-03"}
            ],
        },
    )

    candidate = next(
        item
        for item in report["candidates"]
        if item["candidate_id"] == "auxiliary_task_discovery_readiness_2608_15841"
    )
    assert candidate["decision"] == "research_candidate_needs_validation"
    assert "research_only_no_weight_change" in candidate["blockers"]
    assert "downstream_policy_lift_validated" in candidate["blockers"]
    assert candidate["evidence"]["aux_head_standalone_quality_passed"] is True
    assert report["decision"]["promote_to_live"] is False


def test_convergence_review_includes_2609_08106_complementarity_as_advisory_only() -> None:
    report = build_paper_convergence_review(
        as_of="2026-09-11",
        adoption_2609_08106={
            "decision": {
                "adopt_into_latest_strategy_now": False,
                "advisory_import_allowed": True,
                "live_weight_change_allowed": False,
            },
            "forward_evidence_gate": {
                "passed": False,
                "sample_count": 2,
                "triggered_count": 0,
                "realized_count": 0,
            },
            "candidates": [
                {"candidate": "cross_asset_complementarity_score", "verdict": "advisory_ready"},
                {"candidate": "mom5_gated_bond_sleeve", "verdict": "continue_forward_shadow"},
            ],
        },
    )

    candidate = next(
        item
        for item in report["candidates"]
        if item["candidate_id"] == "nystrom_attention_complementarity_2609_08106"
    )
    assert candidate["decision"] == "research_candidate_needs_validation"
    assert "forward_shadow_only_no_weight_change" in candidate["blockers"]
    assert "forward_evidence_gate_not_passed" in candidate["blockers"]
    assert candidate["evidence"]["advisory_import_allowed"] is True
    assert candidate["evidence"]["live_weight_change_allowed"] is False
    assert candidate["evidence"]["complementarity_verdict"] == "advisory_ready"
