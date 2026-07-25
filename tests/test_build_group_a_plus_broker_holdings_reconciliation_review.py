from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_broker_holdings_reconciliation_review import (
    build_review,
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
