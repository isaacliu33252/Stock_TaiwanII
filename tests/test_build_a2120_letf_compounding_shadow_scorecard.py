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
    failed = [check["name"] for check in scorecard["checks"] if not check["passed"]]
    assert failed == ["cost20_positive"]


def test_a2120_scorecard_fails_when_rolling_stability_fails() -> None:
    inputs = _base_inputs()
    inputs["rolling_report"]["summary"]["pass"] = False
    inputs["rolling_report"]["summary"]["preferred_delta_final_value"]["min"] = -3000.0

    scorecard = build_scorecard(**inputs)

    assert scorecard["decision"]["shadow_gate"] == "fail"
    failed = [check["name"] for check in scorecard["checks"] if not check["passed"]]
    assert failed == ["rolling_cost20_stability"]
