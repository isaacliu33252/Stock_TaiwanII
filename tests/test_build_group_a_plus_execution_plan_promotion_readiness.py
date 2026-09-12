from __future__ import annotations

from scripts.evaluate.build_group_a_plus_execution_plan_promotion_readiness import (
    build_execution_plan_promotion_readiness,
)


def _plan(**overrides) -> dict:
    base = {
        "actual_data_date": "2026-08-24",
        "current_cash_input": 100000.0,
        "cash_assumption": "workbook has no cash field; using explicit --cash-balance input",
        "holdings_source": "broker_authoritative_export.csv",
        "current_holdings": {"0050.TW": 2794, "00631L.TW": 500, "00632R.TW": 0, "00679B.TWO": 0},
        "trades": [{"ticker": "0050.TW", "delta_shares": 10}],
    }
    base.update(overrides)
    return base


def _integrity(**overrides) -> dict:
    base = {
        "status": "warning",
        "dates": {"execution_plan_actual_data_date": "2026-08-24"},
        "errors": [],
        "warnings": ["NCF decision calibration artifact missing"],
    }
    base.update(overrides)
    return base


def _broker(**overrides) -> dict:
    base = {
        "status": "reconciled_for_manual_review",
        "decision": {
            "can_generate_live_orders": True,
            "target_weight_change_allowed": True,
        },
        "comparison": [
            {"ticker": "0050.TW", "confirmed_shares": 2794},
            {"ticker": "00631L.TW", "confirmed_shares": 500},
            {"ticker": "00632R.TW", "confirmed_shares": 0},
            {"ticker": "00679B.TWO", "confirmed_shares": 0},
        ],
    }
    base.update(overrides)
    return base


def test_blocks_when_shadow_plan_uses_workbook_and_broker_reconciliation_is_blocked() -> None:
    result = build_execution_plan_promotion_readiness(
        shadow_plan=_plan(current_cash_input=0.0, holdings_source="taiwan_stock_20260619.xlsx"),
        shadow_integrity=_integrity(),
        broker_reconciliation=_broker(
            status="blocked",
            decision={"can_generate_live_orders": False, "target_weight_change_allowed": False},
        ),
    )

    assert result["status"] == "blocked"
    assert "broker_reconciliation_not_reconciled" in result["blockers"]
    assert "broker_gate_disallows_live_orders" in result["blockers"]
    assert "shadow_plan_zero_cash_with_nonzero_trades" in result["blockers"]
    assert "shadow_plan_uses_workbook_holdings_not_authoritative_broker_export" in result["blockers"]
    assert result["decision"]["can_replace_live_execution_plan"] is False
    assert result["decision"]["creates_orders"] is False


def test_ready_only_when_shadow_integrity_and_broker_gate_are_clean() -> None:
    result = build_execution_plan_promotion_readiness(
        shadow_plan=_plan(),
        shadow_integrity=_integrity(),
        broker_reconciliation=_broker(),
    )

    assert result["status"] == "ready_for_human_promotion_review"
    assert result["blockers"] == []
    assert result["decision"]["can_replace_live_execution_plan"] is True
    assert result["decision"]["target_weight_change_allowed"] is False


def test_shadow_integrity_error_blocks_promotion() -> None:
    result = build_execution_plan_promotion_readiness(
        shadow_plan=_plan(),
        shadow_integrity=_integrity(status="error", errors=["execution_plan actual_data_date does not match live_signal"]),
        broker_reconciliation=_broker(),
    )

    assert result["status"] == "blocked"
    assert "shadow_artifact_integrity_has_errors" in result["blockers"]


def test_nonzero_broker_holding_missing_from_plan_blocks_promotion() -> None:
    result = build_execution_plan_promotion_readiness(
        shadow_plan=_plan(),
        shadow_integrity=_integrity(),
        broker_reconciliation=_broker(
            comparison=[
                {"ticker": "0050.TW", "confirmed_shares": 2794},
                {"ticker": "00751B.TWO", "confirmed_shares": 100},
            ]
        ),
    )

    assert result["status"] == "blocked"
    assert "broker_nonzero_holding_missing_from_execution_plan" in result["blockers"]
    assert result["summary"]["broker_nonzero_holdings_missing_from_plan"] == ["00751B.TWO"]
