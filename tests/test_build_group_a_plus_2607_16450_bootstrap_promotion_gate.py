from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_bootstrap_promotion_gate import build_bootstrap_gate, write_gate


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_bootstrap_gate_blocks_when_forward_rows_are_insufficient(tmp_path: Path) -> None:
    staged = tmp_path / "staged.json"
    a2118 = tmp_path / "a2118.json"
    candidate_tail = tmp_path / "candidate_tail.json"
    _write(
        staged,
        {
            "status": "event_study_complete",
            "active_event_count": 1,
            "events": [{"actual_data_date": "2026-08-24", "forward": {"edge_5d": None}}],
        },
    )
    _write(
        a2118,
        {
            "status": "forward_shadow_row_available_parity_pending",
            "as_of": "2026-08-24",
            "monitoring_requirements": {"current_forward_rows_counted_by_log": 1},
            "latest_live_action_parity": {"validated": False},
        },
    )
    _write(
        candidate_tail,
        {
            "as_of": "2026-08-24",
            "candidate_reviews": [
                {"name": "staged_reentry", "tail_review_status": "tail_acceptable_shadow_only"},
                {"name": "a2118_seed_averaging", "tail_review_status": "blocked_for_live_promotion"},
            ],
        },
    )

    gate = build_bootstrap_gate(
        staged_event_study_path=staged,
        a2118_monitor_path=a2118,
        candidate_tail_path=candidate_tail,
        min_rows=20,
        bootstrap_samples=200,
    )

    assert gate["report_type"] == "group_a_plus_2607_16450_bootstrap_promotion_gate"
    assert gate["status"] == "blocked_for_live_promotion"
    assert gate["decision"]["target_weight_change_allowed"] is False
    assert gate["decision"]["allow_00631l_add_from_bootstrap_gate"] is False
    assert "staged_reentry:staged_reentry_edge_5d_bootstrap_rows_below_minimum" in gate["blocking_reasons"]
    assert "a2118_seed_averaging:a2118_forward_rows_below_bootstrap_minimum" in gate["blocking_reasons"]


def test_bootstrap_gate_can_pass_shadow_statistical_gate_without_live_permission(tmp_path: Path) -> None:
    staged = tmp_path / "staged.json"
    a2118 = tmp_path / "a2118.json"
    candidate_tail = tmp_path / "candidate_tail.json"
    events = [
        {
            "actual_data_date": f"2026-08-{day:02d}",
            "forward": {"edge_5d": 0.01 + day / 10000, "edge_10d": 0.012, "edge_20d": 0.015},
        }
        for day in range(1, 31)
    ]
    _write(staged, {"status": "event_study_complete", "active_event_count": 30, "events": events})
    _write(
        a2118,
        {
            "status": "ready",
            "as_of": "2026-08-30",
            "monitoring_requirements": {"current_forward_rows_counted_by_log": 30},
            "latest_live_action_parity": {"validated": True},
        },
    )
    _write(
        candidate_tail,
        {
            "as_of": "2026-08-30",
            "candidate_reviews": [
                {"name": "staged_reentry", "tail_review_status": "tail_acceptable_shadow_only"},
                {"name": "a2118_seed_averaging", "tail_review_status": "tail_acceptable_shadow_only"},
            ],
        },
    )

    gate = build_bootstrap_gate(
        staged_event_study_path=staged,
        a2118_monitor_path=a2118,
        candidate_tail_path=candidate_tail,
        min_rows=20,
        bootstrap_samples=300,
    )

    assert gate["status"] == "passed_shadow_statistical_gate"
    assert gate["live_ready_candidates"] == ["staged_reentry"]
    assert gate["decision"]["promotion_allowed"] is False
    assert gate["decision"]["target_weight_change_allowed"] is False
    staged_review = gate["candidate_reviews"][0]
    assert staged_review["statistical_status"] == "passed"
    assert staged_review["horizon_reviews"]["edge_5d"]["ci_lower"] > 0


def test_write_bootstrap_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    gate = {
        "report_type": "group_a_plus_2607_16450_bootstrap_promotion_gate",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(gate, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == gate
    assert (history / "2607_16450_bootstrap_promotion_gate_20260824.json").exists()
