from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_bavar_direction_filter import (
    build_filter,
    write_filter,
)
from tests.test_build_group_a_plus_2606_09104_har_bavar_prior_shadow import _seed_db


def test_00631l_4pct_bavar_direction_filter_remains_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    report = build_filter(
        db_path=db,
        start="2025-01-02",
        end="2026-05-20",
        horizon=20,
        lookback=126,
        train_window=126,
        step=5,
        min_filtered_events=1,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_4pct_bavar_direction_filter"
    assert report["status"] in {"available_for_shadow_review", "blocked"}
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_micro_add_from_filter"] is False
    assert "baseline_prediction_date_summary" in report


def test_00631l_4pct_bavar_direction_filter_blocks_missing_db(tmp_path: Path) -> None:
    report = build_filter(db_path=tmp_path / "missing.db", end="2026-05-20")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_00631l_4pct_bavar_direction_filter_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_4pct_bavar_direction_filter",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_filter(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_4pct_bavar_direction_filter_20260825.json").exists()
