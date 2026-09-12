from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_2608_08405_capacity_grid_shadow as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_capacity_grid_shadow_reports_grid_without_capacity_point(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    market = tmp_path / "market.json"
    assigned = tmp_path / "assigned.json"
    _write_json(
        live,
        {
            "actual_data_date": "2026-09-04",
            "target_weights": {"0050.TW": 0.53, "00631L.TW": 0.17, "cash": 0.30},
        },
    )
    _write_json(
        market,
        {
            "status": "blocked",
            "computed": {"max_participation_of_volume": 0.001},
            "decision": {"target_weight_change_allowed": False},
        },
    )
    _write_json(assigned, {"status": "blocked"})

    report = module.build_report(
        live_signal_path=live,
        market_impact_path=market,
        assigned_realized_path=assigned,
        capital=1_000_000.0,
        arms=[0.0, 0.5, 1.0, 1.5, 2.0],
    )

    assert report["status"] == "not_identified_shadow_only"
    assert report["grid_specification"]["capacity_interval_identified"] is False
    assert report["grid_specification"]["point_estimate_allowed"] is False
    assert report["decision"]["capacity_point_estimate_reported"] is False
    assert report["decision"]["capacity_scaling_allowed"] is False
    assert len(report["grid_rows"]) == 5
    assert report["grid_rows"][2]["deployment_arm_beta"] == 1.0
    assert report["grid_rows"][2]["scaled_risky_notional"] == 700000.0
    assert "simultaneous_band_not_estimable" in report["blocking_reasons"]


def test_capacity_grid_shadow_still_blocks_even_when_upstreams_ready(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    market = tmp_path / "market.json"
    assigned = tmp_path / "assigned.json"
    _write_json(live, {"actual_data_date": "2026-09-04", "target_weights": {"0050.TW": 0.7, "cash": 0.3}})
    _write_json(
        market,
        {
            "status": "available_for_manual_review",
            "computed": {"max_participation_of_volume": 0.002},
            "decision": {"target_weight_change_allowed": True},
        },
    )
    _write_json(assigned, {"status": "ready_for_capacity_shadow_review"})

    report = module.build_report(
        live_signal_path=live,
        market_impact_path=market,
        assigned_realized_path=assigned,
        capital=1_000_000.0,
        arms=[0.5, 1.0, 1.5],
    )
    markdown = module._markdown(report)

    assert report["blocking_reasons"] == [
        "randomized_parallel_sleeve_observations_missing",
        "edge_erosion_by_deployment_arm_missing",
        "simultaneous_band_not_estimable",
    ]
    assert report["decision"]["capacity_claim_allowed"] is False
    assert "## Grid Rows" in markdown
