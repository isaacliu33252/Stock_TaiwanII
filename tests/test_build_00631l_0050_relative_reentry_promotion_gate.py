from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_00631l_0050_relative_reentry_promotion_gate import build_gate


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _advisory(trust_level: str = "TRUST", action: str = "SHIFT_00631L_5") -> dict:
    return {
        "gates": {
            "checks": {
                "risk_mechanism_pass": True,
                "exact_live_date_decision_available": True,
                "model_internal_gates_pass": True,
            },
            "latest_strategy_trust": {"trust_level": trust_level, "reasons": []},
        },
        "model_snapshot": {
            "selected_decision": {
                "date": "2026-08-03",
                "action": action,
                "predicted_regret": 0.001,
                "action_allowed": True,
                "reliability_gate_pass": True,
                "block_reason": None,
            }
        },
    }


def _review() -> dict:
    return {
        "summary": {
            "edge_20d": {"positive_rate": 0.9, "p10": 0.001},
            "min_path_edge_20d": {"p10": -0.002, "worst": -0.004},
            "max_cluster_length": 9,
        }
    }


def test_gate_promotes_when_hard_checks_pass(tmp_path: Path) -> None:
    advisory = tmp_path / "advisory.json"
    review = tmp_path / "review.json"
    _write(advisory, _advisory())
    _write(review, _review())

    gate = build_gate(advisory_path=advisory, review_path=review)

    assert gate["promote_to_advisory"] is True
    assert gate["recommendation"] == "promote_to_advisory_candidate"
    assert gate["blocked_by"] == []
    assert gate["warnings"] == []


def test_gate_blocks_abstain_and_keep_action(tmp_path: Path) -> None:
    advisory = tmp_path / "advisory.json"
    review = tmp_path / "review.json"
    _write(advisory, _advisory(trust_level="ABSTAIN", action="KEEP"))
    _write(review, _review())

    gate = build_gate(advisory_path=advisory, review_path=review)

    assert gate["promote_to_advisory"] is False
    assert gate["manual_review_candidate"] is False
    assert "strategy_trust_not_abstain" in gate["blocked_by"]
    assert "model_action_shift_00631l_5" in gate["blocked_by"]


def test_gate_allows_shadow_only_manual_review_candidate(tmp_path: Path) -> None:
    advisory = tmp_path / "advisory.json"
    review = tmp_path / "review.json"
    _write(advisory, _advisory(trust_level="SHADOW_ONLY"))
    _write(review, _review())

    gate = build_gate(advisory_path=advisory, review_path=review)

    assert gate["promote_to_advisory"] is False
    assert gate["manual_review_candidate"] is True
    assert gate["recommendation"] == "manual_review_candidate_only"
    assert "strategy_trust_shadow_only_manual_review" in gate["warnings"]


def test_gate_warns_on_path_tail_without_blocking(tmp_path: Path) -> None:
    advisory = tmp_path / "advisory.json"
    review = tmp_path / "review.json"
    weak_review = _review()
    weak_review["summary"]["min_path_edge_20d"] = {"p10": -0.004, "worst": -0.007}
    weak_review["summary"]["max_cluster_length"] = 12
    _write(advisory, _advisory())
    _write(review, weak_review)

    gate = build_gate(advisory_path=advisory, review_path=review)

    assert gate["promote_to_advisory"] is True
    assert set(gate["warnings"]) == {
        "min_path_edge_20d_p10_warning",
        "min_path_edge_20d_worst_warning",
        "candidate_cluster_length_warning",
    }
