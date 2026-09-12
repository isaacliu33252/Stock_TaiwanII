from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_defensive_cash_floor_guarded_candidate import (
    build_report,
    write_report,
)


def test_build_guarded_candidate_report_from_wrapped_signal(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    review = tmp_path / "review.json"
    live.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    "actual_data_date": "2026-08-07",
                    "execution_regime": "group_a_plus_defensive",
                    "target_weights": {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3},
                    "latest_features": {"total_risk_score": 7, "tail_risk_score": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    review.write_text(
        json.dumps({"status": "manual_signature_pending", "decision": {"manual_signature_valid": False}}),
        encoding="utf-8",
    )

    report = build_report(live_signal_path=live, signed_review_path=review, enabled=True)

    assert report["as_of"] == "2026-08-07"
    assert report["triggered"] is True
    assert report["changed"] is True
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_guarded_candidate_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "guard.json"
    history = tmp_path / "history"
    log = tmp_path / "guard.jsonl"
    report = {
        "as_of": "2026-08-07",
        "variant": "cash55_risk7_tail1",
        "enabled": False,
        "triggered": False,
        "changed": False,
        "can_apply_to_formal_target": False,
        "inputs": {},
        "formal_reference": {},
        "candidate": {},
        "decision": {"target_weight_change_allowed": False},
        "reason_codes": [],
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "defensive_cash_floor_guarded_candidate_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
