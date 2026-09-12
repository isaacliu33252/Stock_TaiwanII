from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.backtest_group_a_plus_moira_execution_guard_hard_stop_shadow import build_report, write_report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_execution_guard_backtest_report_from_glob(tmp_path: Path) -> None:
    _write(
        tmp_path / "results/group_a_plus_live_signal_v2_20260801.json",
        {
            "data": {
                "actual_data_date": "2026-08-01",
                "execution_allowed": True,
                "latest_prices": {"0050.TW": 100, "00631L.TW": 30, "00632R.TW": 10},
                "target_weights": {"0050.TW": 0.5, "cash": 0.5},
            }
        },
    )
    _write(
        tmp_path / "results/group_a_plus_live_signal_v2_20260802.json",
        {
            "data": {
                "actual_data_date": "2026-08-02",
                "execution_allowed": False,
                "latest_prices": {"0050.TW": 101, "00631L.TW": 31, "00632R.TW": 9.9},
                "target_weights": {"0050.TW": 0.3, "00631L.TW": 0.2, "00632R.TW": 0.2, "cash": 0.3},
            }
        },
    )
    _write(
        tmp_path / "results/group_a_plus_live_signal_v2_20260803.json",
        {
            "data": {
                "actual_data_date": "2026-08-03",
                "execution_allowed": True,
                "latest_prices": {"0050.TW": 100, "00631L.TW": 29, "00632R.TW": 10.2},
                "target_weights": {"0050.TW": 0.3, "cash": 0.7},
            }
        },
    )

    report = build_report(
        signal_glob=str(tmp_path / "results/group_a_plus_live_signal_v2_*.json"),
        as_of="2026-08-03",
        min_trigger_count=1,
    )

    assert report["as_of"] == "2026-08-03"
    assert report["input_coverage"]["trigger_count"] == 1
    assert report["sources"]["signal_glob"].endswith("group_a_plus_live_signal_v2_*.json")
    assert report["decision"]["creates_orders"] is False


def test_write_execution_guard_backtest_report_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest/backtest.json"
    history = tmp_path / "history"
    report = {"as_of": "2026-08-07", "decision": {"target_weight_change_allowed": False}}

    write_report(report, output_path=output, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "moira_execution_guard_hard_stop_backtest_shadow_20260807.json").exists()
