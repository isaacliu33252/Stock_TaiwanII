from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_es_threshold_sensitivity import (
    build_sensitivity,
    write_sensitivity,
)
from tests.test_build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import _seed_db


def test_00631l_4pct_es_threshold_sensitivity_reviews_fixed_thresholds(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    report = build_sensitivity(
        db_path=db,
        start="2025-01-02",
        end="2026-05-20",
        horizon=20,
        lookback=126,
        min_events=5,
        es_thresholds=(-0.002, -0.003),
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_4pct_es_threshold_sensitivity"
    assert report["status"] == "available_for_shadow_review"
    assert [row["max_es_extra_loss"] for row in report["threshold_reviews"]] == [-0.002, -0.003]
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_micro_add_from_sensitivity"] is False


def test_00631l_4pct_es_threshold_sensitivity_blocks_missing_db(tmp_path: Path) -> None:
    report = build_sensitivity(db_path=tmp_path / "missing.db", end="2026-05-20")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_00631l_4pct_es_threshold_sensitivity_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_4pct_es_threshold_sensitivity",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_sensitivity(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_4pct_es_threshold_sensitivity_20260825.json").exists()
