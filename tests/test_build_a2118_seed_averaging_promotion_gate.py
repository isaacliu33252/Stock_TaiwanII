from __future__ import annotations

from scripts.evaluate.build_a2118_seed_averaging_promotion_gate import build_promotion_gate


def _row(as_of: str, *, parity: bool = True, action: str = "hold_or_align_to_target") -> dict:
    return {
        "as_of": as_of,
        "status": "forward_shadow_row_available_parity_pending",
        "ensemble_inference": {"as_of": as_of, "action": action},
        "latest_live_action_parity": {
            "validated": parity,
            "live_action": "hold_or_align_to_target",
            "ensemble_action": action,
        },
    }


def test_gate_blocks_with_insufficient_history_and_latest_parity_failure() -> None:
    latest = _row("2026-08-24", parity=False, action="rebalance_to_0050_70_00631L_30")

    result = build_promotion_gate(latest_monitor=latest, history_rows=[latest])

    assert result["status"] == "blocked"
    assert "forward_shadow_monitoring_history_insufficient" in result["blockers"]
    assert "latest_live_action_parity_not_validated" in result["blockers"]
    assert "latest_live_action_parity_pass_rate_below_threshold" in result["blockers"]
    assert result["decision"]["can_promote_to_production"] is False
    assert result["decision"]["creates_orders"] is False


def test_gate_blocks_when_a_history_row_lacks_date_matched_inference() -> None:
    rows = [_row(f"2026-08-{day:02d}") for day in range(1, 21)]
    rows[3]["ensemble_inference"]["as_of"] = "2026-07-31"

    result = build_promotion_gate(latest_monitor=rows[-1], history_rows=rows)

    assert result["status"] == "blocked"
    assert "forward_shadow_inference_snapshot_missing_or_stale" in result["blockers"]


def test_gate_ready_when_forward_history_and_parity_meet_thresholds() -> None:
    rows = [_row(f"2026-08-{day:02d}") for day in range(1, 21)]

    result = build_promotion_gate(latest_monitor=rows[-1], history_rows=rows)

    assert result["status"] == "ready_for_human_promotion_review"
    assert result["blockers"] == []
    assert result["summary"]["forward_rows"] == 20
    assert result["summary"]["parity_pass_rate"] == 1.0
    assert result["decision"]["can_promote_to_production"] is True
    assert result["decision"]["target_weight_change_allowed"] is False
