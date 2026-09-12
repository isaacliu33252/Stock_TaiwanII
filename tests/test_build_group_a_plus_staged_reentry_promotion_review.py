from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_staged_reentry_promotion_review import (
    build_promotion_review,
    write_review,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_staged_reentry_promotion_blocks_sparse_event_study(tmp_path: Path) -> None:
    staged = tmp_path / "staged.json"
    event = tmp_path / "event.json"
    tail = tmp_path / "tail.json"
    _write(
        staged,
        {
            "status": "active_shadow_candidate",
            "actual_data_date": "2026-08-24",
            "candidate_policy": "bull_pullback_cash_to_0050_first_stage_no_00631l_when_bearish",
            "warnings": ["dominant_direction_bearish_blocks_00631l_stage"],
        },
    )
    _write(
        event,
        {
            "unique_signal_dates": 30,
            "active_event_count": 1,
            "summary": {
                "edge_5d": {"count": 0},
                "edge_10d": {"count": 0},
                "edge_20d": {"count": 0},
            },
        },
    )
    _write(
        tail,
        {
            "candidate_reviews": [
                {"name": "staged_reentry", "tail_review_status": "tail_acceptable_shadow_only"}
            ]
        },
    )

    review = build_promotion_review(
        staged_path=staged,
        event_study_path=event,
        candidate_tail_path=tail,
    )

    assert review["report_type"] == "group_a_plus_staged_reentry_promotion_review"
    assert review["status"] == "blocked_for_live_promotion"
    assert review["decision"]["shadow_monitoring_allowed"] is True
    assert review["decision"]["target_weight_change_allowed"] is False
    assert "staged_reentry_active_event_count_below_promotion_minimum" in review["blocking_reasons"]
    assert "staged_reentry_forward_edge_rows_below_promotion_minimum" in review["blocking_reasons"]
    assert "staged_reentry_tail_review_shadow_only" in review["warning_reasons"]


def test_write_staged_reentry_promotion_review_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_staged_reentry_promotion_review",
        "actual_data_date": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert (history / "staged_reentry_promotion_review_20260824.json").exists()
