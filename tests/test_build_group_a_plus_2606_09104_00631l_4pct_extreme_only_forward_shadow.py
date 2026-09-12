from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow import (
    build_shadow,
    write_shadow,
)
from tests.test_build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import _seed_db


def test_extreme_only_forward_shadow_remains_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    report = build_shadow(
        db_path=db,
        start="2025-01-02",
        end="2026-05-20",
        horizon=20,
        lookback=126,
        min_extreme_events=1,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow"
    assert report["status"] in {"available_for_shadow_review", "blocked"}
    assert report["parameters"]["activation_rule"] == "decision_date_risk_aversion_state == EXTREME"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_micro_add_from_extreme_only_shadow"] is False


def test_extreme_only_forward_shadow_blocks_missing_db(tmp_path: Path) -> None:
    report = build_shadow(db_path=tmp_path / "missing.db", end="2026-05-20")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_extreme_only_forward_shadow_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_shadow(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_4pct_extreme_only_forward_shadow_20260825.json").exists()
