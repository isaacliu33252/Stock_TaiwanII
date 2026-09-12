from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_regime_split import build_split, write_split
from tests.test_build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import _seed_db


def test_00631l_4pct_regime_split_builds_state_summaries(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)
    forward = tmp_path / "forward.json"
    forward.write_text(
        json.dumps(
            {
                "live_signal": {
                    "strategy_id": "a2118",
                    "execution_regime": "golden1",
                    "market_state": {"state": "bull_pullback_deep"},
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_split(
        db_path=db,
        forward_monitor_path=forward,
        start="2025-01-02",
        end="2026-05-20",
        horizon=20,
        lookback=126,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_4pct_regime_split"
    assert report["status"] == "available_for_shadow_review"
    assert set(report["state_split_summary"]) == {"LOW", "MEDIUM", "HIGH", "EXTREME"}
    assert report["latest_a2118_context"]["execution_regime"] == "golden1"
    assert report["decision"]["target_weight_change_allowed"] is False


def test_00631l_4pct_regime_split_blocks_missing_db(tmp_path: Path) -> None:
    report = build_split(db_path=tmp_path / "missing.db", end="2026-05-20")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_00631l_4pct_regime_split_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_4pct_regime_split",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_split(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_4pct_regime_split_20260825.json").exists()
