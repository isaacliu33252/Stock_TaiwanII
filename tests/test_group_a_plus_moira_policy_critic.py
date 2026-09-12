from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.moira_policy_critic import (
    append_moira_policy_critic_log,
    build_moira_policy_critic,
)


def test_policy_critic_proposes_review_only_rules_from_shadow_failures() -> None:
    report = build_moira_policy_critic(
        hierarchical_credit_review={
            "as_of": "2026-08-07",
            "primary_attribution": "data_freshness_error",
            "evidence": ["execution_guard_not_satisfied", "stale_data_forecast=2_actual=2"],
        },
        event_execution_quality={
            "as_of": "2026-08-07",
            "status": "blocked_review_only",
            "quality_score": 0.48,
            "blockers": ["execution_guard_satisfied", "source_fresh_enough"],
            "warnings": [
                "no_large_00632r_chase_without_staging",
                "0050_reduction_not_aggressive_in_low_risk_bullish_state",
            ],
        },
        relative_exposure_thesis={
            "as_of": "2026-08-07",
            "thesis_class": "short_term_inverse_hedge_review_only",
            "blocking_evidence": ["execution_guard_not_satisfied"],
        },
    )

    proposal_ids = [row["proposal_id"] for row in report["proposals"]]
    assert report["status"] == "blocked_review_only"
    assert report["proposal_count"] == 5
    assert proposal_ids[:2] == ["freshness_first_review_gate", "execution_guard_hard_stop_for_new_risk"]
    assert "large_inverse_hedge_staging_review" in proposal_ids
    assert "execution_quality_below_0_50" in report["blocking_reasons"]
    assert all(row["allowed_to_apply"] is False for row in report["proposals"])
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["code_change_allowed"] is False
    assert report["decision"]["guarded_candidate_allowed"] is False
    assert report["immutable_policy_contract"]["requires_signed_approval"] is True


def test_policy_critic_handles_no_proposals_without_unlocking_decisions() -> None:
    report = build_moira_policy_critic(
        hierarchical_credit_review={"primary_attribution": "market_noise", "evidence": []},
        event_execution_quality={"quality_score": 0.9, "blockers": [], "warnings": []},
        relative_exposure_thesis={"thesis_class": "maintain_unlevered_beta_preferred"},
        as_of="2026-08-07",
    )

    assert report["status"] == "research_proposals_available"
    assert report["proposal_count"] == 0
    assert "no_policy_change_proposal_from_current_shadow_inputs" in report["warning_reasons"]
    assert report["decision"]["promote_to_live"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False


def test_policy_critic_log_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "critic.jsonl"
    report = build_moira_policy_critic(
        hierarchical_credit_review={"primary_attribution": "data_freshness_error"},
        event_execution_quality={"quality_score": 1.0, "blockers": ["source_fresh_enough"], "warnings": []},
        relative_exposure_thesis={},
        as_of="2026-08-07",
    )

    append_moira_policy_critic_log(log, report, date="2026-08-07")
    append_moira_policy_critic_log(log, report | {"proposal_count": 99}, date="2026-08-07")

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["proposal_count"] == 99
