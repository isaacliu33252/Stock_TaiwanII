from __future__ import annotations

from scripts.run.run_a2120_daily_shadow_pipeline import build_latest_summary


def test_build_latest_summary_exposes_shadow_state_and_artifacts() -> None:
    out = build_latest_summary(
        date_stamp="20260715",
        diagnostic={"latest": {"date": "2026-07-15", "compounding_regime": "TREND_PERSISTENT"}},
        replay={
            "replay": {
                "raw_action": "FAST_REENTER_CANDIDATE",
                "recommended_action": "BLOCKED_BY_HARD_GUARD",
                "hard_blockers": ["turnover cap"],
                "shadow_target_shares_before_hard_guards": 942,
            }
        },
        turnover={"result": {"shadow_plan": {"target_shares": {"00631L.TW": 942}, "turnover_ratio": 0.499}}},
        scorecard={
            "candidate": {"name": "score3_ar0_persist50_rev50__base40_mr0_trend100"},
            "decision": {"shadow_gate": "pass", "production": "do_not_promote"},
        },
        combined={"combined": {"combined_action": "BLOCKED_BY_HARD_GUARD"}},
        risk_sensitive_replay={
            "replay": {
                "raw_action": "FAST_REENTER_CANDIDATE",
                "recommended_action": "BLOCKED_BY_HARD_GUARD",
                "weak_trend_edge_gate": "ce20_negative",
                "weak_trend_edge_active": True,
                "allowed_fraction_for_regime": 0.9,
                "shadow_target_shares_before_hard_guards": 900,
            }
        },
        risk_sensitive_turnover={
            "result": {"shadow_plan": {"target_shares": {"00631L.TW": 900}, "turnover_ratio": 0.47}}
        },
        artifacts={"scorecard": "report/group_a_plus/shadow/a2120.json"},
    )

    assert out["production_effect"] == "none"
    assert out["daily_state"]["compounding_regime"] == "TREND_PERSISTENT"
    assert out["daily_state"]["recommended_action"] == "BLOCKED_BY_HARD_GUARD"
    assert out["daily_state"]["combined_action"] == "BLOCKED_BY_HARD_GUARD"
    assert out["daily_state"]["turnover50_target_00631l"] == 942
    assert out["risk_sensitive_variant"]["name"] == "ce20_negative_to_trend90"
    assert out["risk_sensitive_variant"]["weak_trend_edge_active"] is True
    assert out["risk_sensitive_variant"]["turnover50_target_00631l"] == 900
    assert out["scorecard_decision"]["shadow_gate"] == "pass"
    assert out["artifacts"]["scorecard"] == "report/group_a_plus/shadow/a2120.json"
