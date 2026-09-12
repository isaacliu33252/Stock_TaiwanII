from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2605_17307_hierarchical_cash_equity_shadow import (
    _base_sleeves,
    _split_hierarchy,
    _weights_from_hierarchy,
    build_shadow,
    write_shadow,
)


def test_split_and_rebuild_hierarchy() -> None:
    split = _split_hierarchy({"0050.TW": 0.24, "00631L.TW": 0.06, "cash": 0.70})

    assert split["equity_budget"] == 0.3
    assert round(split["equity_sleeve"]["0050.TW"], 6) == 0.8
    rebuilt = _weights_from_hierarchy(split["equity_sleeve"], 0.25)
    assert round(rebuilt["0050.TW"], 6) == 0.2
    assert round(rebuilt["00631L.TW"], 6) == 0.05
    assert rebuilt["cash"] == 0.75


def test_base_sleeves_include_current_and_staged() -> None:
    ladder = {
        "best_ready_stage_if_extreme": {
            "target_weights": {"0050.TW": 0.24, "00631L.TW": 0.04, "cash": 0.72}
        }
    }
    snapshot = {"portfolio_state": {"weights": {"0050.TW": 0.24}, "cash_weight": 0.76}}

    sleeves = _base_sleeves(ladder, snapshot)

    assert "current_authoritative_sleeve" in sleeves
    assert "staged_4pct_sleeve" in sleeves


def test_shadow_blocks_when_database_missing(tmp_path: Path) -> None:
    report = build_shadow(db_path=tmp_path / "missing.duckdb")

    assert report["decision"]["target_weight_change_allowed"] is False
    assert "stock_database_missing" in report["blocking_reasons"]


def test_write_shadow_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2605_17307_hierarchical_cash_equity_shadow",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_shadow(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2605_17307_hierarchical_cash_equity_shadow_20260825.json").exists()
