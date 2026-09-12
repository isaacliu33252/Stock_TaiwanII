from __future__ import annotations

from scripts.evaluate.build_a2120_letf_compounding_shadow_scorecard import build_scorecard


def _base_inputs() -> dict:
    return {
        "seven_window_report": {
            "totals": {
                "positive_final_value_windows": 7,
                "delta_final_value_sum": 27_000.0,
            }
        },
        "cost20_report": {
            "transaction_cost_bps": 20.0,
            "totals": {
                "positive_final_value_windows": 7,
                "delta_final_value_sum": 25_000.0,
            },
        },
        "turnover_report": {
            "result": {
                "shadow_plan": {
                    "turnover_ratio": 0.499,
                    "target_shares": {"00631L.TW": 942},
                }
            }
        },
        "overlap_report": {
            "overlap_events": 9,
            "overlap_no_add_help": 0,
            "overlap_no_add_hurt": 9,
        },
        "replay_report": {
            "replay": {
                "raw_action": "FAST_REENTER_CANDIDATE",
                "recommended_action": "BLOCKED_BY_HARD_GUARD",
                "production_effect": "none",
                "shadow_target_shares_before_hard_guards": 942,
                "hard_blockers": ["turnover cap"],
            }
        },
        "rolling_report": {
            "transaction_cost_bps": 20.0,
            "summary": {
                "windows": 11,
                "pass": True,
                "preferred_delta_final_value": {
                    "positive_rate": 1.0,
                    "median": 3045.0,
                    "min": 63.0,
                },
                "incremental_delta_final_value": {
                    "positive_rate": 1.0,
                    "min": 34.0,
                },
            },
        },
        "t_plus_1_delay_report": {
            "totals": {
                "delayed_still_positive_overall": True,
                "delayed_positive_windows": 7,
                "window_count": 7,
                "same_day_delta_final_value_sum": 15_275.0,
                "delayed_delta_final_value_sum": 10_687.0,
            }
        },
        "execution_plan_is_fresh_shadow_snapshot": True,
    }


def test_a2120_scorecard_passes_shadow_gate_but_blocks_production() -> None:
    scorecard = build_scorecard(**_base_inputs())

    assert scorecard["decision"]["shadow_gate"] == "pass"
    assert scorecard["decision"]["daily_advisory"] == "enable_daily_advisory_shadow_only"
    assert scorecard["decision"]["production"] == "do_not_promote"
    assert scorecard["decision"]["production_upgrade_pass"] is False
    assert all(check["passed"] for check in scorecard["checks"])


def test_a2120_scorecard_fails_when_cost_stress_is_not_positive() -> None:
    inputs = _base_inputs()
    inputs["cost20_report"]["totals"]["positive_final_value_windows"] = 6
    inputs["cost20_report"]["totals"]["delta_final_value_sum"] = -1.0

    scorecard = build_scorecard(**inputs)

    assert scorecard["decision"]["shadow_gate"] == "fail"
    failed = [check["name"] for check in scorecard["checks"] if not check["passed"] and check["severity"] == "fail"]
    assert failed == ["cost20_positive"]


def test_a2120_scorecard_fails_when_rolling_stability_fails() -> None:
    inputs = _base_inputs()
    inputs["rolling_report"]["summary"]["pass"] = False
    inputs["rolling_report"]["summary"]["preferred_delta_final_value"]["min"] = -3000.0

    scorecard = build_scorecard(**inputs)

    assert scorecard["decision"]["shadow_gate"] == "fail"
    failed = [check["name"] for check in scorecard["checks"] if not check["passed"] and check["severity"] == "fail"]
    assert failed == ["rolling_cost20_stability"]


def test_a2120_scorecard_production_blockers_shrink_when_ops_and_delay_audit_resolved() -> None:
    """2026-08-22 (Fable 00631L direction #2, items a/b): production_blockers
    used to be a hardcoded, unconditional list of three items regardless of
    what evidence was actually supplied. Now two of the three are evaluated
    from real inputs -- confirm they drop out when resolved and reappear
    when not, so this can never silently go stale again.
    """
    resolved = build_scorecard(**_base_inputs())
    assert resolved["decision"]["production_blockers"] == [
        "research_only_shadow_candidate",
        "hard_guards_must_remain_precedence",
        "requires_rolling_window_shadow_monitoring_before_production",
    ]

    unresolved_inputs = _base_inputs()
    unresolved_inputs["t_plus_1_delay_report"] = None
    unresolved_inputs["execution_plan_is_fresh_shadow_snapshot"] = False
    unresolved = build_scorecard(**unresolved_inputs)
    assert unresolved["decision"]["production_blockers"] == [
        "research_only_shadow_candidate",
        "hard_guards_must_remain_precedence",
        "requires_rolling_window_shadow_monitoring_before_production",
        "requires_daily_ops_integration",
        "requires_t_plus_1_execution_alignment_audit",
    ]
    # requires_rolling_window_shadow_monitoring_before_production has no
    # programmatic shortcut -- it must always be present regardless of the
    # other two, since it depends on accumulating real forward-day history.
    assert "requires_rolling_window_shadow_monitoring_before_production" in resolved["decision"]["production_blockers"]


def test_a2120_scorecard_t_plus_1_check_fails_when_a_window_turns_negative() -> None:
    inputs = _base_inputs()
    inputs["t_plus_1_delay_report"]["totals"]["delayed_still_positive_overall"] = False
    inputs["t_plus_1_delay_report"]["totals"]["delayed_positive_windows"] = 6

    scorecard = build_scorecard(**inputs)

    t_plus_1_check = next(c for c in scorecard["checks"] if c["name"] == "t_plus_1_execution_delay_positive")
    assert t_plus_1_check["passed"] is False
    assert t_plus_1_check["severity"] == "advisory"
    # Advisory severity: does not flip the shadow gate to fail on its own.
    assert scorecard["decision"]["shadow_gate"] == "pass"
    assert "requires_t_plus_1_execution_alignment_audit" in scorecard["decision"]["production_blockers"]
