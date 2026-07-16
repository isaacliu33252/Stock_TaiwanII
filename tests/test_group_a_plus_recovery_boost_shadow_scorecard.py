from __future__ import annotations

from scripts.evaluate.build_group_a_plus_recovery_boost_shadow_scorecard import build_scorecard


def test_recovery_boost_shadow_scorecard_prefers_a2129_and_blocks_production() -> None:
    clean_report = {
        "summary": {
            "recovery_boost_010": {
                "tuning_sum_delta_final_value": 2655.0,
                "oos_sum_delta_final_value": 3116.5,
                "tuning_sum_delta_sharpe_ratio": 0.002,
                "oos_sum_delta_sharpe_ratio": 0.0238,
                "changed_days": 32,
            },
            "recovery_boost_100_age20": {
                "tuning_sum_delta_final_value": 2655.0,
                "oos_sum_delta_final_value": 1733.2,
                "tuning_sum_delta_sharpe_ratio": 0.002,
                "oos_sum_delta_sharpe_ratio": 0.0141,
                "changed_days": 22,
            },
            "recovery_boost_150_age20": {
                "tuning_sum_delta_final_value": 3827.1,
                "oos_sum_delta_final_value": 2669.6,
                "tuning_sum_delta_sharpe_ratio": 0.0029,
                "oos_sum_delta_sharpe_ratio": 0.0213,
                "changed_days": 22,
            },
        }
    }
    crisis_report = {
        "summary": {
            "recovery_boost_010": {
                "rebased_sum_delta_final_value": -2071.2,
                "rebased_sum_delta_sharpe_ratio": -0.0082,
                "rebased_positive_final_value_folds": 2,
                "total_folds": 5,
                "total_boosted_recovery_days": 236,
            },
            "recovery_boost_010_age20": {
                "rebased_sum_delta_final_value": 9072.2,
                "rebased_sum_delta_sharpe_ratio": 0.0151,
                "rebased_positive_final_value_folds": 3,
                "total_folds": 5,
                "total_boosted_recovery_days": 114,
            },
            "recovery_boost_015_age20": {
                "rebased_sum_delta_final_value": 13843.2,
                "rebased_sum_delta_sharpe_ratio": 0.023,
                "rebased_positive_final_value_folds": 3,
                "total_folds": 5,
                "total_boosted_recovery_days": 114,
            },
        }
    }

    scorecard = build_scorecard(clean_report, crisis_report)

    assert scorecard["decision"]["production"] == "do_not_promote"
    assert scorecard["decision"]["preferred_shadow"] == "a2129_recovery_00631l_boost_age_guard_aggressive_shadow"
    assert scorecard["decision"]["conservative_shadow"] == "a2128_recovery_00631l_boost_age_guard_shadow"
    assert scorecard["ranked_candidates"][0]["production_upgrade_pass"] is False
    assert "research_only_shadow_candidate" in scorecard["ranked_candidates"][0]["production_blockers"]
