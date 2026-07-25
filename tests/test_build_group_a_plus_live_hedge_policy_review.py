from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_live_hedge_policy_review import build_review, write_review


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manual(path: Path, allowed: bool) -> Path:
    return _write(path, {"decision": {"manual_hedge_discussion_allowed": allowed}})


def _tail(path: Path, passed: bool) -> Path:
    return _write(path, {"decision": {"manual_discussion_tail_gate_passed": passed}})


def _fee(path: Path, passed: bool) -> Path:
    return _write(path, {"decision": {"effective_fee_proxy_validated_for_manual_review": passed}})


def test_policy_defined_but_blocked_when_evidence_gates_fail(tmp_path: Path) -> None:
    review = build_review(
        manual_hedge_path=_manual(tmp_path / "manual.json", False),
        tail_gate_path=_tail(tmp_path / "tail.json", True),
        effective_fee_path=_fee(tmp_path / "fee.json", False),
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_live_hedge_policy_review"
    assert review["status"] == "blocked"
    assert review["summary"]["policy_defined"] is True
    assert review["summary"]["live_hedge_policy_validated"] is False
    assert review["summary"]["manual_hedge_discussion_allowed"] is False
    assert "manual_hedge_eligibility_blocks_discussion" in review["blocking_reasons"]
    assert "effective_fee_proxy_not_validated_for_manual_review" in review["blocking_reasons"]
    assert review["decision"]["live_hedge_policy_validated"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_policy_still_does_not_open_00632r_when_inputs_pass(tmp_path: Path) -> None:
    review = build_review(
        manual_hedge_path=_manual(tmp_path / "manual.json", True),
        tail_gate_path=_tail(tmp_path / "tail.json", True),
        effective_fee_path=_fee(tmp_path / "fee.json", True),
        as_of="2026-07-20",
    )

    assert review["summary"]["policy_validated_for_manual_discussion"] is True
    assert review["blocking_reasons"] == ["live_hedge_policy_not_validated_for_live_action"]
    assert review["decision"]["live_hedge_policy_validated"] is False
    assert review["decision"]["manual_hedge_discussion_allowed"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "policy.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_live_hedge_policy_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "live_hedge_policy_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
