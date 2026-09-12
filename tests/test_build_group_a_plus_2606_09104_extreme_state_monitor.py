from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_2606_09104_extreme_state_monitor import (
    _last_extreme_review,
    build_monitor,
    write_monitor,
)


def test_last_extreme_review_reports_distance_and_run() -> None:
    states = pd.DataFrame(
        [
            {"risk_aversion_score": 20, "risk_aversion_state": "LOW", "reasons": []},
            {"risk_aversion_score": 90, "risk_aversion_state": "EXTREME", "reasons": ["a"]},
            {"risk_aversion_score": 95, "risk_aversion_state": "EXTREME", "reasons": ["b"]},
            {"risk_aversion_score": 70, "risk_aversion_state": "HIGH", "reasons": ["c"]},
        ],
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]),
    )

    review = _last_extreme_review(states)

    assert review["last_extreme"]["date"] == "2026-01-05"
    assert review["calendar_days_since_last_extreme"] == 1
    assert review["trading_days_since_last_extreme"] == 1
    assert review["last_extreme_run"] == {
        "start_date": "2026-01-02",
        "end_date": "2026-01-05",
        "trading_days": 2,
    }


def test_build_monitor_blocks_when_database_missing(tmp_path: Path) -> None:
    ladder = tmp_path / "ladder.json"
    ladder.write_text(
        json.dumps(
            {
                "status": "blocked",
                "decision": {"any_stage_ready_if_extreme": True, "best_stage_cap_if_extreme": 0.04},
                "blocking_reasons": ["latest_state_not_extreme"],
            }
        ),
        encoding="utf-8",
    )

    report = build_monitor(db_path=tmp_path / "missing.duckdb", ladder_path=ladder)

    assert report["report_type"] == "group_a_plus_2606_09104_extreme_state_monitor"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["staged_ladder_status"]["best_stage_cap_if_extreme"] == 0.04


def test_write_monitor_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_extreme_state_monitor",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_monitor(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_extreme_state_monitor_20260825.json").exists()
