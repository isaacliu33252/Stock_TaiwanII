from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_0050_00631l_combo_sweep import build_sweep, write_sweep
from tests.test_build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import _seed_db


def test_0050_00631l_combo_sweep_reviews_fixed_grid(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    report = build_sweep(
        db_path=db,
        start="2025-01-02",
        end="2026-05-20",
        horizon=20,
        lookback=126,
        weights_0050=(0.25, 0.30),
        weights_00631l=(0.025, 0.04),
        min_events=5,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_0050_00631l_combo_sweep"
    assert report["status"] == "available_for_shadow_monitoring"
    assert len(report["combo_reviews"]) == 4
    assert report["combo_reviews"][0]["weights"] == {"0050.TW": 0.25, "00631L.TW": 0.025, "cash": 0.725}
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_combo_from_this_sweep"] is False


def test_0050_00631l_combo_sweep_blocks_missing_db(tmp_path: Path) -> None:
    report = build_sweep(db_path=tmp_path / "missing.db", end="2026-05-20")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_0050_00631l_combo_sweep_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_0050_00631l_combo_sweep",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_sweep(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_0050_00631l_combo_sweep_20260825.json").exists()
