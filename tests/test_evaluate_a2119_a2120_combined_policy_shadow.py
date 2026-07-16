from __future__ import annotations

from scripts.evaluate.evaluate_a2119_a2120_combined_policy_shadow import combine_policy, latest_a2119_decision


def test_combined_policy_hard_guard_has_highest_precedence() -> None:
    out = combine_policy(
        a2119_action="REENTER",
        a2120_regime="TREND_PERSISTENT",
        a2120_raw_action="FAST_REENTER_CANDIDATE",
        hard_blockers=["turnover cap"],
        shadow_target_00631l=942,
        turnover50_target_00631l=942,
    )

    assert out["combined_action"] == "BLOCKED_BY_HARD_GUARD"
    assert out["production_effect"] == "none"


def test_combined_policy_a2119_no_add_blocks_a2120_fast_reentry() -> None:
    out = combine_policy(
        a2119_action="NO_ADD",
        a2120_regime="TREND_PERSISTENT",
        a2120_raw_action="FAST_REENTER_CANDIDATE",
        hard_blockers=[],
    )

    assert out["combined_action"] == "NO_ADD"
    assert "A21.19 NO_ADD has precedence" in out["reason"]


def test_combined_policy_keep_allows_a2120_fast_reentry_candidate() -> None:
    out = combine_policy(
        a2119_action="KEEP",
        a2120_regime="TREND_PERSISTENT",
        a2120_raw_action="FAST_REENTER_CANDIDATE",
        hard_blockers=[],
    )

    assert out["combined_action"] == "FAST_REENTER_CANDIDATE"


def test_latest_a2119_decision_uses_latest_recent_decision() -> None:
    out = latest_a2119_decision(
        {
            "windows": [
                {"label": "old", "recent_decisions": [{"date": "2026-01-02", "action": "NO_ADD"}]},
                {"label": "new", "recent_decisions": [{"date": "2026-01-03", "action": "KEEP"}]},
            ]
        }
    )

    assert out["date"] == "2026-01-03"
    assert out["action"] == "KEEP"
    assert out["window_label"] == "new"
