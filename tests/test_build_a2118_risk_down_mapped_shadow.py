from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_a2118_risk_down_mapped_shadow import build_risk_down_mapping, write_report


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_risk_down_mapping_blocks_00631l_when_tail_review_disallows(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    live = tmp_path / "live.json"
    scorecard = tmp_path / "scorecard.json"
    cost = tmp_path / "cost.json"
    _write(
        inference,
        {
            "as_of": "2026-08-24",
            "action": "rebalance_to_0050_70_00631L_30",
            "action_index": 2,
            "target_weights_for_action": {"0050.TW": 0.7, "00631L.TW": 0.3},
            "average_probabilities": [0.36, 0.17, 0.41, 0.03, 0.03],
        },
    )
    _write(
        live,
        {
            "data": {
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "actual_data_date": "2026-08-24",
                "execution_regime": "golden1",
                "action": "hold_or_align_to_target",
                "target_weights": {"0050.TW": 0.3, "00631L.TW": 0.0, "cash": 0.7},
            }
        },
    )
    _write(scorecard, {"status": "available", "decision": {"allow_00631l_add_from_scorecard": False}})
    _write(
        cost,
        {
            "status": "blocked_for_live_promotion",
            "decision": {"allow_00631l_add_from_cost_sweep": False},
        },
    )

    report = build_risk_down_mapping(
        inference_path=inference,
        live_signal_path=live,
        tail_scorecard_path=scorecard,
        cost_robustness_path=cost,
    )

    assert report["report_type"] == "a2118_risk_down_mapped_shadow"
    assert report["status"] == "mapped_shadow_available_blocked_for_live_promotion"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_add"] is False
    assert "raw_a2118_action_adds_00631l_but_tail_review_disallows" in report["blocking_reasons"]

    variants = {row["name"]: row for row in report["mapped_variants"]}
    assert variants["map_to_0050_only"]["weights"]["00631L.TW"] == 0.0
    assert variants["map_to_0050_only"]["weights"]["0050.TW"] == 1.0
    assert variants["map_to_0050_only"]["allow_00631l_add"] is False
    assert variants["map_to_00631l_cap_5pct"]["status"] == "blocked_by_tail_review"
    assert variants["map_to_00631l_cap_5pct"]["weights"]["00631L.TW"] == 0.05


def test_write_risk_down_mapping_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "a2118_risk_down_mapped_shadow",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "a2118_risk_down_mapped_shadow_20260824.json").exists()
