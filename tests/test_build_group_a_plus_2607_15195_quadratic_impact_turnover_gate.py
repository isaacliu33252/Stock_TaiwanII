from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_15195_quadratic_impact_turnover_gate import build_gate, write_gate


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _cost_shadow() -> dict:
    return {
        "status": "available_for_shadow_monitoring",
        "as_of": "2026-08-24",
        "scenarios": [
            {
                "scenario": "guarded_live_target",
                "turnover": 0.02,
                "total_estimated_cost_bps_of_assets": 0.1,
                "linear_cost": 10.0,
                "quadratic_impact_cost": 0.1,
                "execution_cost_state": "EXECUTION_LOW_COST",
            },
            {
                "scenario": "raw_a2118_seed_ensemble_target",
                "turnover": 0.65,
                "total_estimated_cost_bps_of_assets": 3.0,
                "linear_cost": 500.0,
                "quadratic_impact_cost": 1.0,
                "execution_cost_state": "EXECUTION_WEAK",
            },
        ],
    }


def test_quadratic_impact_turnover_gate_blocks_upstream_signal_and_market_impact(tmp_path: Path) -> None:
    cost = tmp_path / "cost.json"
    signal = tmp_path / "signal.json"
    market = tmp_path / "market.json"
    _write(cost, _cost_shadow())
    _write(signal, {"status": "blocked", "decision": {"real_signal_quality_sufficient_for_sciphyrl_optimizer_research": False}})
    _write(market, {"status": "blocked", "decision": {"auto_rebalance_allowed": False}})

    gate = build_gate(cost_shadow_path=cost, signal_gate_path=signal, market_impact_path=market)

    assert gate["status"] == "blocked"
    guarded = next(row for row in gate["scenario_cost_reviews"] if row["scenario"] == "guarded_live_target")
    raw = next(row for row in gate["scenario_cost_reviews"] if row["scenario"] == "raw_a2118_seed_ensemble_target")
    assert guarded["scenario_passes_cost_gate"] is True
    assert raw["scenario_passes_cost_gate"] is False
    assert "real_signal_quality_gate_not_passed" in gate["blocking_reasons"]
    assert "market_impact_readiness_blocked" in gate["blocking_reasons"]
    assert gate["decision"]["target_weight_change_allowed"] is False


def test_quadratic_impact_turnover_gate_passes_when_all_inputs_pass(tmp_path: Path) -> None:
    cost = tmp_path / "cost.json"
    signal = tmp_path / "signal.json"
    market = tmp_path / "market.json"
    _write(cost, _cost_shadow())
    _write(signal, {"status": "pass", "decision": {"real_signal_quality_sufficient_for_sciphyrl_optimizer_research": True}})
    _write(market, {"status": "available_for_manual_review", "decision": {"auto_rebalance_allowed": True}})

    gate = build_gate(cost_shadow_path=cost, signal_gate_path=signal, market_impact_path=market)

    assert gate["status"] == "pass"
    assert gate["decision"]["allow_sciphyrl_optimizer_research"] is True
    assert gate["decision"]["target_weight_change_allowed"] is False


def test_write_quadratic_impact_turnover_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    gate = {
        "report_type": "group_a_plus_2607_15195_quadratic_impact_turnover_gate",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(gate, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == gate
    assert (history / "2607_15195_quadratic_impact_turnover_gate_20260824.json").exists()
