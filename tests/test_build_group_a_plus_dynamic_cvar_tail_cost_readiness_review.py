from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_dynamic_cvar_tail_cost_readiness_review import build_review, write_review


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_review_blocks_when_inputs_are_research_only(tmp_path: Path) -> None:
    cvar = tmp_path / "cvar.json"
    density = tmp_path / "density.json"
    market = tmp_path / "market.json"
    rebalance = tmp_path / "rebalance.json"
    systemic = tmp_path / "systemic.json"
    hmm = tmp_path / "hmm.json"
    cvar_cost_window_split = tmp_path / "cvar_cost_window_split.json"
    rolling_tail_no_add = tmp_path / "rolling_tail_no_add.json"
    _write(
        cvar,
        {
            "status": "research_only",
            "promotion_decision": "research_only",
            "00631l_only_tail_diagnostics": {
                "expected_shortfall_loss_95": 0.07,
                "hill_95": {"hill_xi": 0.3},
                "pot_gpd_95": {"shape_xi": 0.2},
            },
        },
    )
    _write(
        density,
        {
            "status": "available",
            "best_heads": {
                "recommended_research_baseline": "gaussian_residual_head",
                "gmm_status": "unstable_across_windows_research_only",
            },
        },
    )
    _write(
        market,
        {
            "status": "blocked",
            "computed": {"turnover": 0.6},
            "decision": {"auto_rebalance_allowed": False, "allow_00631l_add": False},
        },
    )
    _write(
        rebalance,
        {
            "dates": {"requested_as_of_date": "2026-07-20"},
            "decision": {
                "auto_rebalance_allowed": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
            },
        },
    )
    _write(
        systemic,
        {
            "states": {"overall_state": "blocked_for_leverage_add", "systemic_score": 2},
            "decision": {"allow_00631l_add": False},
        },
    )
    _write(
        hmm,
        {
            "status": "blocked",
            "data_readiness": {"all_required_tickers_ready": True},
            "decision": {"can_generate_scenarios_for_decision": False},
        },
    )
    _write(
        cvar_cost_window_split,
        {
            "status": "blocked_for_live_promotion",
            "summary": {
                "valid_windows": 5,
                "tail_cost_window_split_passed": False,
                "latest_loses_to_no_00631l_windows": 5,
                "latest_loses_to_no_letf_windows": 4,
            },
        },
    )
    _write(
        rolling_tail_no_add,
        {
            "status": "available_for_shadow_monitoring",
            "summary": {
                "window_count": 3,
                "block_00631l_add_windows": 3,
                "block_00632r_open_windows": 0,
                "allow_00631l_add": False,
                "allow_00632r_open": True,
            },
            "decision": {"target_weight_change_allowed": False},
        },
    )

    review = build_review(
        cvar_path=cvar,
        density_path=density,
        market_impact_path=market,
        rebalance_path=rebalance,
        systemic_bubble_path=systemic,
        hmm_wj_path=hmm,
        cvar_cost_window_split_path=cvar_cost_window_split,
        rolling_tail_no_add_path=rolling_tail_no_add,
    )

    assert review["report_type"] == "group_a_plus_dynamic_cvar_tail_cost_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["dynamic_optimizer_ready"] is False
    assert review["decision"]["tail_cost_readiness_ready"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert "dynamic_cvar_optimizer_not_implemented" in review["blocking_reasons"]
    assert "cvar_cost_window_split_2606_26625_failed" in review["blocking_reasons"]
    assert "rolling_tail_no_add_gate_2606_26625_blocks_00631l_add" in review["blocking_reasons"]
    assert "taiwan_etf_walkforward_validation_missing" not in review["blocking_reasons"]
    assert review["component_readiness"]["cvar_cost_window_split_2606_26625"][
        "latest_loses_to_no_00631l_windows"
    ] == 5
    assert review["component_readiness"]["rolling_tail_no_add_gate_2606_26625"][
        "block_00631l_add_windows"
    ] == 3


def test_write_review_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_dynamic_cvar_tail_cost_readiness_review",
        "as_of": "2026-07-20",
        "decision": {"allow_00631l_add": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "20260720.json").read_text(encoding="utf-8")) == review
