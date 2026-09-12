from __future__ import annotations

from scripts.evaluate.build_group_a_plus_broker_export_request import build_broker_export_request


def test_request_required_when_reconciliation_has_blockers() -> None:
    result = build_broker_export_request(
        {
            "status": "blocked",
            "as_of": "2026-07-17",
            "blocking_reasons": [
                "authoritative_broker_export_missing",
                "confirmed_holdings_mismatch_transaction_sample",
            ],
            "comparison": [
                {
                    "ticker": "0050.TW",
                    "confirmed_shares": 2794,
                    "sample_shares": -2304,
                    "matches_confirmed": False,
                },
                {
                    "ticker": "00631L.TW",
                    "confirmed_shares": 500,
                    "sample_shares": 500,
                    "matches_confirmed": True,
                },
            ],
        }
    )

    assert result["status"] == "required"
    assert result["decision"]["creates_orders"] is False
    assert result["decision"]["target_weight_change_allowed"] is False
    assert result["decision"]["broker_export_required"] is True
    assert result["current_mismatches"][0]["ticker"] == "0050.TW"
    assert "cash_balance" in result["required_export_fields"]


def test_request_not_required_when_reconciliation_has_no_blockers() -> None:
    result = build_broker_export_request({"status": "reconciled_for_manual_review", "blocking_reasons": []})

    assert result["status"] == "not_required"
    assert result["why_required"] == []
    assert result["decision"]["broker_export_required"] is False
