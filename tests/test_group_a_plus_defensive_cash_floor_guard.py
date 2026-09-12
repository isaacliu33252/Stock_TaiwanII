from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.defensive_cash_floor_guard import (
    append_guarded_candidate_log,
    build_guarded_candidate,
    raise_cash_floor,
)


def test_raise_cash_floor_reduces_risky_weights_pro_rata() -> None:
    adjusted, changed = raise_cash_floor(
        {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3},
        cash_floor=0.55,
    )

    assert changed is True
    assert round(adjusted["cash"], 6) == 0.55
    assert round(adjusted["0050.TW"], 6) == round(0.4 * 0.45 / 0.7, 6)
    assert round(adjusted["00679B.TWO"], 6) == round(0.3 * 0.45 / 0.7, 6)


def test_guarded_candidate_triggers_but_stays_disabled_without_signature() -> None:
    signal = {
        "requested_as_of_date": "2026-08-10",
        "actual_data_date": "2026-08-07",
        "execution_regime": "group_a_plus_defensive",
        "base_regime": "golden1",
        "execution_allowed": True,
        "target_weights": {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3},
        "latest_features": {"total_risk_score": 7, "tail_risk_score": 0},
    }
    review = {"decision": {"signed_review_ready": True, "manual_signature_valid": False}}

    report = build_guarded_candidate(signal, signed_review=review, enabled=True)

    assert report["triggered"] is True
    assert report["changed"] is True
    assert report["candidate"]["target_weights"]["cash"] == 0.55
    assert report["decision"]["target_weight_change_allowed"] is False
    assert "manual_signature_not_valid" in report["reason_codes"]


def test_guarded_candidate_does_not_trigger_outside_defensive() -> None:
    signal = {
        "execution_regime": "golden1",
        "target_weights": {"0050.TW": 0.3, "00632R.TW": 0.27, "cash": 0.43},
        "latest_features": {"total_risk_score": 9, "tail_risk_score": 2},
    }

    report = build_guarded_candidate(signal, enabled=False)

    assert report["triggered"] is False
    assert report["changed"] is False
    assert report["candidate"]["target_weights"] == report["formal_reference"]["target_weights"]
    assert report["decision"]["auto_rebalance_allowed"] is False


def test_guarded_candidate_can_allow_formal_target_only_when_enabled_and_signed() -> None:
    signal = {
        "execution_regime": "group_a_plus_defensive",
        "target_weights": {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3},
        "latest_features": {"total_risk_score": 0, "tail_risk_score": 1},
    }
    review = {"decision": {"signed_review_ready": True, "manual_signature_valid": True}}

    report = build_guarded_candidate(signal, signed_review=review, enabled=True)

    assert report["triggered"] is True
    assert report["decision"]["target_weight_change_allowed"] is True
    assert report["decision"]["guarded_candidate_target_output_allowed"] is True
    assert report["decision"]["auto_rebalance_allowed"] is False


def test_guarded_candidate_signed_but_untriggered_does_not_allow_target_change() -> None:
    signal = {
        "execution_regime": "golden1",
        "target_weights": {"0050.TW": 0.3, "00632R.TW": 0.27, "cash": 0.43},
        "latest_features": {"total_risk_score": 2, "tail_risk_score": 0},
    }
    review = {"decision": {"signed_review_ready": True, "manual_signature_valid": True}}

    report = build_guarded_candidate(signal, signed_review=review, enabled=True)

    assert report["triggered"] is False
    assert report["decision"]["guarded_candidate_target_output_allowed"] is True
    assert report["decision"]["target_weight_change_allowed"] is False


def test_append_guarded_candidate_log_is_idempotent_by_date(tmp_path: Path) -> None:
    path = tmp_path / "guard.jsonl"
    report = build_guarded_candidate(
        {
            "actual_data_date": "2026-08-07",
            "execution_regime": "golden1",
            "target_weights": {"cash": 1.0},
            "latest_features": {},
        }
    )

    append_guarded_candidate_log(path, report, date="2026-08-07")
    append_guarded_candidate_log(path, report, date="2026-08-07")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
