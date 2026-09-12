from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_a2118_seed_averaging_forward_shadow_monitor import (
    append_monitor_log,
    build_monitor,
)


def _shadow() -> dict:
    return {
        "preferred_ensemble": "42+43+44",
        "decision": {
            "shadow_gate": "pass",
            "shadow_queue": "candidate_for_forward_shadow_monitoring",
            "production_blockers": [
                "inference_integration_not_implemented",
                "latest_live_action_parity_not_validated",
                "forward_shadow_monitoring_missing",
                "no_production_promotion_gate",
            ],
        },
    }


def _live_signal() -> dict:
    return {
        "success": True,
        "data": {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "requested_as_of_date": "2026-08-25",
            "actual_data_date": "2026-08-24",
            "action": "hold_or_align_to_target",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.3, "cash": 0.7},
            "market_state": {
                "state": "bull_pullback_deep",
                "bucket": "bull_pullback",
                "risk_level": "medium_high",
                "inputs": {"dominant_direction": "bearish"},
            },
            "execution_allowed": True,
        },
    }


def test_build_monitor_records_scaffold_when_inference_is_missing() -> None:
    result = build_monitor(shadow=_shadow(), live_signal=_live_signal())

    assert result["status"] == "monitoring_scaffold_ready_inference_missing"
    assert result["as_of"] == "2026-08-24"
    assert result["preferred_ensemble"] == "42+43+44"
    assert result["latest_live_action_parity"]["validated"] is False
    assert "forward_shadow_inference_snapshot_missing" in result["production_blockers"]
    assert "forward_shadow_monitoring_missing" not in result["production_blockers"]
    assert result["live_execution_effect"] == "none"


def test_build_monitor_compares_inference_snapshot_when_supplied() -> None:
    result = build_monitor(
        shadow=_shadow(),
        live_signal=_live_signal(),
        inference_snapshot={"as_of": "2026-08-24", "action": "hold_or_align_to_target", "probabilities": {"hold": 0.7}},
    )

    assert result["status"] == "forward_shadow_row_available_parity_pending"
    assert result["latest_live_action_parity"]["validated"] is True
    assert result["ensemble_inference"]["probabilities"]["hold"] == 0.7


def test_build_monitor_rejects_stale_inference_snapshot() -> None:
    result = build_monitor(
        shadow=_shadow(),
        live_signal=_live_signal(),
        inference_snapshot={"as_of": "2026-08-21", "action": "hold_or_align_to_target"},
    )

    assert result["status"] == "monitoring_scaffold_ready_inference_stale"
    assert result["latest_live_action_parity"]["reason"] == "inference_snapshot_as_of_mismatch"
    assert "forward_shadow_inference_snapshot_stale_or_mismatched" in result["production_blockers"]


def test_append_monitor_log_replaces_same_as_of_and_counts_rows(tmp_path: Path) -> None:
    log = tmp_path / "monitor.jsonl"
    append_monitor_log({"as_of": "2026-08-23", "monitoring_requirements": {}}, log)
    count = append_monitor_log({"as_of": "2026-08-24", "monitoring_requirements": {}}, log)
    count = append_monitor_log({"as_of": "2026-08-24", "status": "updated", "monitoring_requirements": {}}, log)

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    assert count == 2
    assert [row["as_of"] for row in rows] == ["2026-08-23", "2026-08-24"]
    assert rows[-1]["status"] == "updated"
    assert rows[-1]["monitoring_requirements"]["current_forward_rows_counted_by_log"] == 2
