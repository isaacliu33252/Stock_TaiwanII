from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_candidate_tail_review import (
    build_candidate_tail_review,
    write_review,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_candidate_tail_review_blocks_00631l_candidates_but_keeps_staged_shadow(tmp_path: Path) -> None:
    scorecard = tmp_path / "scorecard.json"
    cost = tmp_path / "cost.json"
    staged = tmp_path / "staged.json"
    a2118 = tmp_path / "a2118.json"
    monitor = tmp_path / "monitor.json"
    risk_down = tmp_path / "risk_down.json"
    a2120 = tmp_path / "a2120.json"
    gjr = tmp_path / "gjr.json"

    _write(
        scorecard,
        {
            "latest_strategy_context": {"actual_data_date": "2026-08-24"},
            "ranked_references": [{"strategy": "defensive_0050_70_cash30", "score": 84.0}],
        },
    )
    _write(
        cost,
        {
            "status": "blocked_for_live_promotion",
            "as_of": "2026-08-24",
            "decision": {"promote_dynamic_cvar_optimizer": False},
            "blocking_reasons": ["dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95"],
        },
    )
    _write(
        staged,
        {
            "status": "active_shadow_candidate",
            "actual_data_date": "2026-08-24",
            "proposed_shadow_target_weights": {"0050.TW": 0.45, "00631L.TW": 0.0, "cash": 0.55},
            "blockers": [],
            "warnings": ["dominant_direction_bearish_blocks_00631l_stage"],
        },
    )
    _write(
        a2118,
        {
            "preferred_ensemble": "42+43+44",
            "decision": {
                "shadow_gate": "pass",
                "production_blockers": ["forward_shadow_monitoring_history_insufficient"],
            },
            "summary": {"preferred_full": {"annual_return": 0.76, "sharpe": 1.96, "max_drawdown": -0.288}},
        },
    )
    _write(
        monitor,
        {
            "ensemble_inference": {
                "action": "rebalance_to_0050_70_00631L_30",
                "target_weights_for_action": {"0050.TW": 0.7, "00631L.TW": 0.3},
            }
        },
    )
    _write(
        risk_down,
        {
            "status": "mapped_shadow_available_blocked_for_live_promotion",
            "mapped_variants": [
                {
                    "name": "map_to_0050_only",
                    "status": "tail_compatible_shadow_candidate",
                    "weights": {"0050.TW": 1.0, "00631L.TW": 0.0, "cash": 0.0},
                    "allow_00631l_add": False,
                }
            ],
            "blocking_reasons": ["raw_a2118_action_adds_00631l_but_tail_review_disallows"],
        },
    )
    _write(
        a2120,
        {
            "status": "inactive",
            "candidate_target_weights_if_blockers_clear": {"0050.TW": 0.3, "00631L.TW": 0.05, "cash": 0.65},
            "blockers": ["dominant_direction_bearish"],
        },
    )
    _write(gjr, {"status": "inactive", "blockers": ["a2126_tail_risk_condition_inactive"], "warnings": []})

    review = build_candidate_tail_review(
        scorecard_path=scorecard,
        cost_robustness_path=cost,
        staged_reentry_path=staged,
        a2118_path=a2118,
        a2118_monitor_path=monitor,
        a2118_risk_down_path=risk_down,
        a2120_path=a2120,
        gjr_path=gjr,
    )

    assert review["report_type"] == "group_a_plus_2607_16450_candidate_tail_review"
    assert review["status"] == "available"
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add_from_candidate_tail_review"] is False
    assert review["live_ready_candidates"] == []

    by_name = {row["name"]: row for row in review["candidate_reviews"]}
    assert by_name["staged_reentry"]["tail_review_status"] == "tail_acceptable_shadow_only"
    assert by_name["staged_reentry"]["decision"]["allow_00631l_add"] is False
    assert by_name["a2118_seed_averaging"]["tail_review_status"] == "blocked_for_live_promotion"
    assert by_name["a2118_seed_averaging"]["risk_down_mapping"]["status"] == (
        "mapped_shadow_available_blocked_for_live_promotion"
    )
    assert by_name["a2118_seed_averaging"]["risk_down_mapping"]["variants"][0]["name"] == "map_to_0050_only"
    assert "a2118_shadow_action_adds_00631l_against_current_tail_review" in by_name["a2118_seed_averaging"]["tail_blockers"]
    assert (
        "turnover_cost_robustness:dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95"
        in by_name["a2118_seed_averaging"]["tail_blockers"]
    )
    assert by_name["a2120_small_00631l"]["decision"]["allow_00631l_add"] is False


def test_write_candidate_tail_review_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2607_16450_candidate_tail_review",
        "as_of": "2026-08-24",
        "decision": {"allow_00631l_add_from_candidate_tail_review": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert (history / "2607_16450_candidate_tail_review_20260824.json").exists()
