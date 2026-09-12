from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_broker_holdings_reconciliation_review import (
    build_review,
    confirmed_from_authoritative_sample,
    write_review,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_review_blocks_when_confirmed_holdings_mismatch_sample(tmp_path: Path) -> None:
    sample = tmp_path / "sample.json"
    _write(
        sample,
        {
            "authoritative_broker_export": False,
            "coverage": {"last_transaction_date": "2026-07-17"},
            "latest_positions": {"0050.TW": -2304, "00631L.TW": 500},
            "negative_positions": {"0050.TW": -2304},
        },
    )

    review = build_review(sample_path=sample, confirmed_holdings={"0050.TW": 2794, "00631L.TW": 500})

    assert review["status"] == "blocked"
    assert review["summary"]["matched_confirmed_count"] == 1
    assert review["summary"]["mismatched_confirmed_count"] == 1
    assert "authoritative_broker_export_missing" in review["blocking_reasons"]
    assert "transaction_sample_has_negative_positions" in review["blocking_reasons"]
    assert "confirmed_holdings_mismatch_transaction_sample" in review["blocking_reasons"]
    rows = {row["ticker"]: row for row in review["comparison"]}
    assert rows["00631L.TW"]["matches_confirmed"] is True
    assert rows["0050.TW"]["sample_minus_confirmed"] == -5098
    assert review["decision"]["can_generate_live_orders"] is False
    assert review["decision"]["allow_00631l_add"] is False


def test_write_review_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_broker_holdings_reconciliation_review",
        "as_of": "2026-07-17",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "20260717.json").read_text(encoding="utf-8")) == review


def test_authoritative_sample_can_supply_confirmed_holdings_and_pass_gate(tmp_path: Path) -> None:
    sample = tmp_path / "authoritative.json"
    _write(
        sample,
        {
            "authoritative_broker_export": True,
            "coverage": {"last_transaction_date": "2026-08-24"},
            "latest_positions": {
                "0050.TW": 2794,
                "00631L.TW": 500,
                "00632R.TW": 0,
                "00679B.TWO": 0,
            },
            "negative_positions": {},
        },
    )

    confirmed = confirmed_from_authoritative_sample(sample)
    review = build_review(
        sample_path=sample,
        confirmed_holdings=confirmed,
        confirmed_holdings_source="authoritative_broker_export_latest_positions",
    )

    assert review["status"] == "reconciled_for_manual_review"
    assert review["blocking_reasons"] == []
    assert review["confirmed_holdings_source"] == "authoritative_broker_export_latest_positions"
    assert review["summary"]["matched_confirmed_count"] == 4
    assert review["decision"]["broker_holdings_reconciled"] is True
    assert review["decision"]["can_generate_live_orders"] is True
    assert review["decision"]["target_weight_change_allowed"] is True


def test_confirmed_from_authoritative_sample_rejects_non_authoritative_sample(tmp_path: Path) -> None:
    sample = tmp_path / "sample.json"
    _write(
        sample,
        {
            "authoritative_broker_export": False,
            "latest_positions": {
                "0050.TW": 2794,
                "00631L.TW": 500,
                "00632R.TW": 0,
                "00679B.TWO": 0,
            },
        },
    )

    try:
        confirmed_from_authoritative_sample(sample)
    except ValueError as exc:
        assert "authoritative_broker_export=true" in str(exc)
    else:
        raise AssertionError("expected non-authoritative sample to be rejected")
