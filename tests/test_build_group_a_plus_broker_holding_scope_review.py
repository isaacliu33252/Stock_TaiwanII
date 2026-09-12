from __future__ import annotations

from scripts.evaluate.build_group_a_plus_broker_holding_scope_review import build_broker_holding_scope_review


def test_nonzero_out_of_universe_holding_requires_scope_decision() -> None:
    review = build_broker_holding_scope_review(
        broker_sample={
            "authoritative_broker_export": True,
            "latest_positions": {
                "0050.TW": 4471,
                "00631L.TW": 580,
                "00679B.TWO": 100,
                "00751B.TWO": 100,
            },
        },
        execution_universe=("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"),
    )

    assert review["status"] == "blocked_scope_decision_required"
    assert review["out_of_universe_nonzero_holdings"] == {"00751B.TWO": 100}
    assert "nonzero_holding_outside_execution_universe" in review["blockers"]
    assert review["decision"]["creates_orders"] is False
    assert review["decision"]["scope_decision_required"] is True


def test_all_nonzero_holdings_in_universe_pass_scope_review() -> None:
    review = build_broker_holding_scope_review(
        broker_sample={
            "authoritative_broker_export": True,
            "latest_positions": {
                "0050.TW": 4471,
                "00631L.TW": 580,
                "00751B.TWO": 0,
            },
        },
        execution_universe=("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"),
    )

    assert review["status"] == "in_scope"
    assert review["out_of_universe_nonzero_holdings"] == {}
    assert review["decision"]["can_build_live_execution_plan_without_scope_exception"] is True
