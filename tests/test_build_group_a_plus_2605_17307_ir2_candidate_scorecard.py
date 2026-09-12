from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_2605_17307_ir2_candidate_scorecard import (
    _candidate_weights,
    _metrics,
    build_scorecard,
    write_scorecard,
)


def test_metrics_ir2_penalizes_drawdown() -> None:
    smooth = pd.Series([0.01] * 20)
    drawdown = pd.Series([0.02] * 10 + [-0.15] + [0.01] * 9)

    smooth_metrics = _metrics(smooth)
    drawdown_metrics = _metrics(drawdown)

    assert smooth_metrics["max_drawdown"] == 0.0
    assert drawdown_metrics["max_drawdown"] < 0.0
    assert drawdown_metrics["ir2_like"] is not None


def test_candidate_weights_include_staged_ladder_and_current() -> None:
    ladder = {
        "stage_reviews": [
            {
                "stage_id": "00631l_to_4pct",
                "target_weights": {"0050.TW": 0.24, "00631L.TW": 0.04, "cash": 0.72},
            }
        ]
    }
    snapshot = {"portfolio_state": {"weights": {"0050.TW": 0.24}, "cash_weight": 0.76}}

    candidates = _candidate_weights(ladder, snapshot)

    assert "staged_ladder_00631l_to_4pct" in candidates
    assert candidates["current_authoritative_portfolio"] == {"0050.TW": 0.24, "cash": 0.76}


def test_write_scorecard_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2605_17307_ir2_candidate_scorecard",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_scorecard(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2605_17307_ir2_candidate_scorecard_20260825.json").exists()


def test_scorecard_marks_staged_candidate_blocked_when_not_extreme(tmp_path: Path) -> None:
    report = build_scorecard(db_path=tmp_path / "missing.duckdb")

    assert report["decision"]["target_weight_change_allowed"] is False
    assert "stock_database_missing" in report["blocking_reasons"]
