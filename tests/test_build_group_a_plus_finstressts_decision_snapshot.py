from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_finstressts_decision_snapshot import (
    build_snapshot,
    write_snapshot,
)


def test_build_snapshot_blocks_when_upstream_reports_block(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    counterfactual = tmp_path / "counterfactual.json"
    baseline = tmp_path / "baseline.json"
    readiness.write_text(
        json.dumps({"status": "blocked", "summary": {"blocked_mechanisms": ["heavy_tailed_shocks"]}}),
        encoding="utf-8",
    )
    counterfactual.write_text(
        json.dumps({"decision": {"reference_loses_to_no_00631l_scenarios": 5, "reference_tail_failure_scenarios": 4}}),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps({"best_shadow_candidate": "combined_vol_trend_gate", "wins_vs_no_00631l": {"x": 0}}),
        encoding="utf-8",
    )

    snapshot = build_snapshot(readiness_path=readiness, counterfactual_path=counterfactual, baseline_path=baseline)

    assert snapshot["status"] == "blocked"
    assert snapshot["decision"]["allow_00631l_add"] is False
    assert "readiness_review_blocked" in snapshot["blocking_reasons"]
    assert "no_baseline_beats_no_00631l" in snapshot["blocking_reasons"]


def test_write_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"
    snapshot = {"report_type": "group_a_plus_finstressts_decision_snapshot"}

    write_snapshot(snapshot, output)

    assert json.loads(output.read_text(encoding="utf-8")) == snapshot
