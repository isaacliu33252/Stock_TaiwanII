from __future__ import annotations

from scripts.evaluate.build_group_a_plus_profit_deployment_readiness import build_profit_deployment_readiness


def _clean_inputs() -> dict:
    return {
        "ops_health": {"status": "ok", "warnings": []},
        "broker_reconciliation": {
            "status": "ok",
            "blocking_reasons": [],
            "decision": {
                "can_generate_live_orders": True,
                "target_weight_change_allowed": True,
            },
        },
        "broker_holding_scope": {"status": "in_scope", "blockers": [], "out_of_universe_nonzero_holdings": {}},
        "deployment_summary": {
            "status": "ok",
            "broker_actionable": True,
            "blocking_reasons": [],
            "warning_reasons": [],
        },
        "daily_artifact_integrity": {"status": "ok", "errors": []},
        "execution_plan_promotion": {"status": "ready_for_human_promotion_review", "blockers": []},
        "staged_reentry": {"status": "inactive", "blockers": ["not_enough_signal"]},
        "a2120_small_00631l": {"status": "inactive", "blockers": ["regime_not_ready"]},
        "a2118_seed_averaging": {"status": "inactive", "production_blockers": []},
        "gjr_post_trigger": {"status": "inactive", "blockers": ["trigger_inactive"]},
        "tail_sensitive_scorecard_2607_16450": {},
        "turnover_cost_robustness_2607_16450": {},
        "candidate_tail_review_2607_16450": {},
        "staged_reentry_promotion_review": {},
        "regime_switching_volatility_gate_2607_16450": {},
        "tail_dependence_monitor_2607_16450": {},
        "geopolitical_cvar_overlay_2607_16450": {},
        "bootstrap_promotion_gate_2607_16450": {},
    }


def test_blocks_when_profit_candidate_exists_but_ops_and_broker_are_blocked() -> None:
    inputs = _clean_inputs()
    inputs["ops_health"] = {
        "status": "error",
        "errors": ["feature_table_sync"],
        "warnings": ["system_resources"],
    }
    inputs["broker_reconciliation"] = {
        "status": "blocked",
        "blocking_reasons": ["authoritative_broker_export_missing"],
        "decision": {
            "can_generate_live_orders": False,
            "target_weight_change_allowed": False,
        },
    }
    inputs["broker_holding_scope"] = {
        "status": "blocked_scope_decision_required",
        "blockers": ["nonzero_holding_outside_execution_universe"],
        "out_of_universe_nonzero_holdings": {"00751B.TWO": 100},
    }
    inputs["deployment_summary"] = {
        "status": "blocked",
        "broker_actionable": False,
        "blocking_reasons": ["execution_plan_date_mismatch"],
        "warning_reasons": ["daily_status_pre_trade_guard_not_ok"],
    }
    inputs["daily_artifact_integrity"] = {
        "status": "error",
        "errors": ["execution_plan actual_data_date does not match live_signal"],
    }
    inputs["execution_plan_promotion"] = {
        "status": "blocked",
        "blockers": ["broker_reconciliation_not_reconciled"],
    }
    inputs["staged_reentry"] = {"status": "active_shadow_candidate", "recommended_shadow_action": "increase_0050_first_stage"}

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "blocked_profit_candidates_exist"
    assert result["profit_impact"] == "actionable_shadow_candidates_exist_but_live_execution_blocked"
    assert result["active_shadow_candidates"] == ["staged_reentry"]
    assert "ops_health_error:feature_table_sync" in result["deployment_blockers"]
    assert "broker_reconciliation:authoritative_broker_export_missing" in result["deployment_blockers"]
    assert "broker_holding_scope:nonzero_holding_outside_execution_universe" in result["deployment_blockers"]
    assert "broker_holding_scope_out_of_universe:00751B.TWO" in result["deployment_blockers"]
    assert "artifact_integrity_error:execution_plan actual_data_date does not match live_signal" in result["deployment_blockers"]
    assert "execution_plan_promotion:broker_reconciliation_not_reconciled" in result["deployment_blockers"]
    assert result["decision"]["creates_orders"] is False
    assert result["decision"]["target_weight_change_allowed"] is False
    assert result["tail_sensitive_review"]["status"] == "missing"
    assert result["turnover_cost_robustness_review"]["status"] == "missing"
    assert result["candidate_tail_review"]["status"] == "missing"
    assert result["staged_reentry_promotion_review"]["status"] == "missing"
    assert result["regime_switching_volatility_gate"]["status"] == "missing"
    assert result["tail_dependence_monitor"]["status"] == "missing"
    assert result["geopolitical_cvar_overlay"]["status"] == "missing"
    assert result["bootstrap_promotion_gate"]["status"] == "missing"


def test_candidate_without_deployment_blockers_requires_human_review_not_orders() -> None:
    inputs = _clean_inputs()
    inputs["a2118_seed_averaging"] = {
        "decision": {
            "shadow_gate": "pass",
            "shadow_queue": "candidate_for_forward_shadow_monitoring",
            "production_blockers": ["inference_integration_not_implemented"],
        },
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "ready_for_promotion_review"
    assert result["active_shadow_candidates"] == ["a2118_seed_averaging"]
    assert result["live_ready_shadow_candidates"] == ["a2118_seed_averaging"]
    assert result["shadow_candidates"][2]["blockers"] == ["inference_integration_not_implemented"]
    assert result["deployment_blockers"] == []
    assert result["decision"]["creates_orders"] is False
    assert result["decision"]["target_weight_change_allowed"] == "human_review_required"


def test_no_candidate_and_no_blocker_stays_monitoring() -> None:
    result = build_profit_deployment_readiness(**_clean_inputs())

    assert result["status"] == "monitoring"
    assert result["active_shadow_candidates"] == []
    assert result["profit_impact"] == "no_current_shadow_candidate"


def test_tail_sensitive_scorecard_is_review_only_not_profit_candidate() -> None:
    inputs = _clean_inputs()
    inputs["tail_sensitive_scorecard_2607_16450"] = {
        "status": "available",
        "ranked_references": [
            {
                "strategy": "defensive_0050_70_cash30",
                "score": 83.9849,
            }
        ],
        "decision": {
            "use_for_promotion_review": True,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_scorecard": False,
        },
        "warning_reasons": ["defensive_0050_70_cash30_tail_score_above_golden1_proxy"],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "monitoring"
    assert result["active_shadow_candidates"] == []
    assert result["tail_sensitive_review"] == {
        "status": "available",
        "use_for_promotion_review": True,
        "target_weight_change_allowed": False,
        "allow_00631l_add_from_scorecard": False,
        "top_reference": "defensive_0050_70_cash30",
        "top_reference_score": 83.9849,
        "warning_reasons": ["defensive_0050_70_cash30_tail_score_above_golden1_proxy"],
    }
    assert (
        "tail_sensitive_scorecard_2607_16450:defensive_0050_70_cash30_tail_score_above_golden1_proxy"
        in result["warnings"]
    )
    assert result["decision"]["target_weight_change_allowed"] is False


def test_turnover_cost_robustness_is_review_only_not_deployment_blocker() -> None:
    inputs = _clean_inputs()
    inputs["turnover_cost_robustness_2607_16450"] = {
        "status": "blocked_for_live_promotion",
        "decision": {
            "promote_dynamic_cvar_optimizer": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_cost_sweep": False,
        },
        "blocking_reasons": [
            "dynamic_tangency_cvar_underperforms_defensive_reference_on_return",
            "dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95",
        ],
        "warning_reasons": ["dynamic_tangency_cvar_starr95_below_10_under_cost"],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "monitoring"
    assert result["active_shadow_candidates"] == []
    assert result["deployment_blockers"] == []
    assert result["turnover_cost_robustness_review"]["promote_dynamic_cvar_optimizer"] is False
    assert result["turnover_cost_robustness_review"]["allow_00631l_add_from_cost_sweep"] is False
    assert (
        "turnover_cost_robustness_2607_16450:dynamic_tangency_cvar_underperforms_defensive_reference_on_return"
        in result["warnings"]
    )


def test_regime_switching_volatility_gate_is_review_only_not_deployment_blocker() -> None:
    inputs = _clean_inputs()
    inputs["regime_switching_volatility_gate_2607_16450"] = {
        "status": "blocked_for_live_promotion",
        "decision": {
            "promote_regime_switching_volatility_gate": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_regime_gate": False,
        },
        "blocking_reasons": [
            "h5_underperforms_har_rv_on_qlike",
            "h10_win_rate_below_har_threshold",
        ],
        "warning_reasons": ["regime_switching_volatility_materially_worse_than_har_rv_all_horizons"],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "monitoring"
    assert result["deployment_blockers"] == []
    assert result["regime_switching_volatility_gate"]["promote_regime_switching_volatility_gate"] is False
    assert result["regime_switching_volatility_gate"]["allow_00631l_add_from_regime_gate"] is False
    assert "regime_switching_volatility_gate_2607_16450:h5_underperforms_har_rv_on_qlike" in result["warnings"]
    assert result["source_status"]["regime_switching_volatility_gate_2607_16450"] == "blocked_for_live_promotion"


def test_tail_dependence_monitor_is_review_only_and_blocks_00631l_add_permission() -> None:
    inputs = _clean_inputs()
    inputs["tail_dependence_monitor_2607_16450"] = {
        "status": "available_for_monitoring",
        "high_tail_dependence_pairs": [{"asset": "00631L.TW"}],
        "decision": {
            "promote_dynamic_copula_gate": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_tail_dependence": False,
        },
        "warning_reasons": [
            "high_lower_tail_dependence_pairs_present",
            "00631l_lower_tail_dependence_high_vs_0050",
        ],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "monitoring"
    assert result["deployment_blockers"] == []
    assert result["tail_dependence_monitor"]["high_tail_dependence_assets"] == ["00631L.TW"]
    assert result["tail_dependence_monitor"]["allow_00631l_add_from_tail_dependence"] is False
    assert "tail_dependence_monitor_2607_16450:00631l_lower_tail_dependence_high_vs_0050" in result["warnings"]


def test_geopolitical_cvar_overlay_is_review_only_risk_cap_advisory() -> None:
    inputs = _clean_inputs()
    inputs["geopolitical_cvar_overlay_2607_16450"] = {
        "status": "available_for_monitoring",
        "score": {"state": "elevated_geopolitical_stress"},
        "overlay": {"cvar_penalty_multiplier": 1.25, "advisory_max_00631l_weight": 0.05},
        "decision": {
            "promote_geopolitical_cvar_overlay": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_geopolitical_overlay": False,
        },
        "warning_reasons": ["geopolitical_risk_state:elevated_geopolitical_stress"],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "monitoring"
    assert result["deployment_blockers"] == []
    assert result["geopolitical_cvar_overlay"]["state"] == "elevated_geopolitical_stress"
    assert result["geopolitical_cvar_overlay"]["cvar_penalty_multiplier"] == 1.25
    assert result["geopolitical_cvar_overlay"]["advisory_max_00631l_weight"] == 0.05
    assert result["geopolitical_cvar_overlay"]["allow_00631l_add_from_geopolitical_overlay"] is False
    assert (
        "geopolitical_cvar_overlay_2607_16450:geopolitical_risk_state:elevated_geopolitical_stress"
        in result["warnings"]
    )


def test_bootstrap_promotion_gate_is_review_only_not_deployment_blocker() -> None:
    inputs = _clean_inputs()
    inputs["bootstrap_promotion_gate_2607_16450"] = {
        "status": "blocked_for_live_promotion",
        "live_ready_candidates": [],
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "allow_00631l_add_from_bootstrap_gate": False,
        },
        "blocking_reasons": [
            "staged_reentry:staged_reentry_edge_5d_bootstrap_rows_below_minimum",
            "a2118_seed_averaging:a2118_forward_rows_below_bootstrap_minimum",
        ],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "monitoring"
    assert result["deployment_blockers"] == []
    assert result["bootstrap_promotion_gate"]["status"] == "blocked_for_live_promotion"
    assert result["bootstrap_promotion_gate"]["allow_00631l_add_from_bootstrap_gate"] is False
    assert (
        "bootstrap_promotion_gate_2607_16450:a2118_seed_averaging:a2118_forward_rows_below_bootstrap_minimum"
        in result["warnings"]
    )


def test_candidate_tail_review_summarizes_candidate_tail_statuses_without_orders() -> None:
    inputs = _clean_inputs()
    inputs["staged_reentry"] = {"status": "active_shadow_candidate"}
    inputs["a2118_seed_averaging"] = {
        "decision": {"shadow_gate": "pass", "shadow_queue": "candidate_for_forward_shadow_monitoring"}
    }
    inputs["candidate_tail_review_2607_16450"] = {
        "status": "available",
        "live_ready_candidates": [],
        "decision": {"allow_00631l_add_from_candidate_tail_review": False},
        "candidate_reviews": [
            {"name": "staged_reentry", "tail_review_status": "tail_acceptable_shadow_only"},
            {"name": "a2118_seed_averaging", "tail_review_status": "blocked_for_live_promotion"},
        ],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "shadow_candidates_blocked_for_live_promotion"
    assert result["active_shadow_candidates"] == ["staged_reentry", "a2118_seed_averaging"]
    assert result["live_ready_shadow_candidates"] == []
    assert result["candidate_tail_review"] == {
        "status": "available",
        "live_ready_candidates": [],
        "allow_00631l_add_from_candidate_tail_review": False,
        "candidate_statuses": {
            "staged_reentry": "tail_acceptable_shadow_only",
            "a2118_seed_averaging": "blocked_for_live_promotion",
        },
    }
    assert result["decision"]["creates_orders"] is False


def test_staged_reentry_promotion_review_blocks_live_promotion_not_shadow_review() -> None:
    inputs = _clean_inputs()
    inputs["staged_reentry"] = {"status": "active_shadow_candidate"}
    inputs["staged_reentry_promotion_review"] = {
        "status": "blocked_for_live_promotion",
        "event_study": {"active_event_count": 1, "forward_edge_counts": {"edge_5d": 0}},
        "decision": {"target_weight_change_allowed": False},
        "blocking_reasons": [
            "staged_reentry_active_event_count_below_promotion_minimum",
            "staged_reentry_forward_edge_rows_below_promotion_minimum",
        ],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "ready_for_promotion_review"
    assert result["active_shadow_candidates"] == ["staged_reentry"]
    assert result["live_ready_shadow_candidates"] == ["staged_reentry"]
    assert result["deployment_blockers"] == []
    assert result["staged_reentry_promotion_review"]["status"] == "blocked_for_live_promotion"
    assert result["staged_reentry_promotion_review"]["target_weight_change_allowed"] is False
    assert (
        "staged_reentry_promotion_review:staged_reentry_active_event_count_below_promotion_minimum"
        in result["warnings"]
    )


def test_candidate_tail_review_available_with_no_live_ready_blocks_target_review() -> None:
    inputs = _clean_inputs()
    inputs["staged_reentry"] = {"status": "active_shadow_candidate"}
    inputs["candidate_tail_review_2607_16450"] = {
        "status": "available",
        "live_ready_candidates": [],
        "decision": {"allow_00631l_add_from_candidate_tail_review": False},
        "candidate_reviews": [
            {"name": "staged_reentry", "tail_review_status": "tail_acceptable_shadow_only"},
        ],
    }

    result = build_profit_deployment_readiness(**inputs)

    assert result["status"] == "shadow_candidates_blocked_for_live_promotion"
    assert result["active_shadow_candidates"] == ["staged_reentry"]
    assert result["live_ready_shadow_candidates"] == []
    assert result["decision"]["requires_human_promotion_review"] is False
    assert result["decision"]["target_weight_change_allowed"] is False
    assert result["recommended_next_actions"][0] == (
        "continue shadow monitoring; do not prepare target-weight changes until a candidate becomes live-ready"
    )
    assert "keep 00631L additions blocked unless candidate tail review produces a live-ready candidate" in result[
        "recommended_next_actions"
    ]
