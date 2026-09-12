from __future__ import annotations

from scripts.evaluate.build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint import build_report


def test_candidate_auxiliary_bank_blueprint_blocks_when_readiness_has_blockers() -> None:
    report = build_report(
        {
            "decision": {
                "blockers": [
                    "downstream_policy_lift_validated",
                    "multi_window_cost_turnover_passed",
                ]
            }
        }
    )

    assert report["training_allowed"] is False
    assert report["promotion_allowed"] is False
    assert report["decision"]["decision"] == "blocked_until_readiness_gates_pass"
    assert [item["gvf_question_count"] for item in report["candidate_grid"]] == [16, 32, 32, 64]
    assert "standalone_auc_only_without_portfolio_lift" in report["hard_rejections"]


def test_candidate_auxiliary_bank_blueprint_allows_offline_research_spec_when_readiness_clear() -> None:
    report = build_report({"decision": {"blockers": []}})

    assert report["training_allowed"] is True
    assert report["promotion_allowed"] is False
    assert report["decision"]["decision"] == "research_spec_ready_for_offline_experiment"
    assert "purged_walk_forward_policy_impact_passed" in report["admission_tests"]
