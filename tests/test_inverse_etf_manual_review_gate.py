from __future__ import annotations

from group_a_plus.operations.execution_guard import apply_inverse_etf_manual_review_gate


def test_inverse_etf_gate_blocks_00632r_open_without_manual_review() -> None:
    guarded, guard = apply_inverse_etf_manual_review_gate(
        {"00632R.TW": 0},
        {"00632R.TW": 1000},
    )

    assert guarded["00632R.TW"] == 0
    assert guard["status"] == "blocked"
    assert guard["side"] == "buy"
    assert guard["allow_00632r_open"] is False
    assert guard["allow_00632r_auto_trade"] is False
    assert guard["auto_rebalance_allowed"] is False
    assert "realized_pnl_review_available" in guard["missing_checks"]


def test_inverse_etf_gate_blocks_00632r_close_until_realized_pnl_reviewed() -> None:
    guarded, guard = apply_inverse_etf_manual_review_gate(
        {"00632R.TW": 800},
        {"00632R.TW": 0},
        artifact_freshness_verified=True,
        hedge_rationale_available=True,
    )

    assert guarded["00632R.TW"] == 800
    assert guard["status"] == "blocked"
    assert guard["side"] == "sell"
    assert guard["blocked_trades"][0]["blocked_delta_shares"] == -800
    assert "cost_basis_available" in guard["missing_checks"]
    assert "realized_pnl_review_available" in guard["missing_checks"]


def test_inverse_etf_gate_is_inactive_when_00632r_unchanged() -> None:
    guarded, guard = apply_inverse_etf_manual_review_gate(
        {"00632R.TW": 100},
        {"00632R.TW": 100},
    )

    assert guarded["00632R.TW"] == 100
    assert guard["status"] == "inactive"
    assert guard["blocked_trades"] == []
