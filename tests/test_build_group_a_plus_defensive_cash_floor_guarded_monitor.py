from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_defensive_cash_floor_guarded_monitor import write_report


def test_write_guarded_monitor_report_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "monitor.json"
    history = tmp_path / "history"
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_defensive_cash_floor_guarded_monitor",
        "policy": "monitor_only_no_target_weight_change_no_orders",
        "as_of": "2026-08-07",
        "candidate_id": "defensive_cash_floor_high_risk_state",
        "variant": "cash55_risk7_tail1",
        "input_counts": {"trigger_rows": 0},
        "first_trigger_window": {},
        "evaluated_events": [],
        "pending_events": [],
        "rollback": {"disable_candidate": False, "reasons": []},
        "decision": {"target_weight_change_allowed": False},
        "summary": {"no_trigger_yet": True},
    }

    write_report(report, output_path=output, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["no_trigger_yet"] is True
    assert (history / "defensive_cash_floor_guarded_monitor_20260807.json").exists()
