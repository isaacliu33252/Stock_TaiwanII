from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_promotion_gate_freshness_retry import (
    build_retry_report,
    write_retry_report,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_promotion_gate_freshness_retry_blocks_stale_holdings(tmp_path: Path) -> None:
    live = _write_json(
        tmp_path / "live.json",
        {"data": {"actual_data_date": "2026-08-25", "requested_as_of_date": "2026-08-25"}},
    )
    holdings = _write_json(tmp_path / "holdings.json", {"as_of": "2026-08-24", "source_file": "old.xlsx"})

    report = build_retry_report(live_signal_path=live, holdings_snapshot_path=holdings)

    assert report["status"] == "blocked"
    assert report["freshness_check"]["required_as_of"] == "2026-08-25"
    assert report["freshness_check"]["holdings_snapshot_as_of"] == "2026-08-24"
    assert "holdings_snapshot_not_same_day" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_promotion_gate_freshness_retry_blocks_missing_inputs(tmp_path: Path) -> None:
    report = build_retry_report(
        live_signal_path=tmp_path / "missing_live.json",
        holdings_snapshot_path=tmp_path / "missing_holdings.json",
    )

    assert report["status"] == "blocked"
    assert "live_signal_missing" in report["blocking_reasons"]
    assert "holdings_snapshot_missing" in report["blocking_reasons"]


def test_write_promotion_gate_freshness_retry_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_promotion_gate_freshness_retry",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_retry_report(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_promotion_gate_freshness_retry_20260825.json").exists()
