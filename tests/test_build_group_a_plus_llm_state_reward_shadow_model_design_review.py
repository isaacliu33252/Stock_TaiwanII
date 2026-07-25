from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_model_design_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _promotion_gate(path: Path, *, passed: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review" if passed else "blocked",
            "decision": {
                "promotion_gate_passed": passed,
                "next_shadow_model_design_allowed": passed,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _manifest(path: Path) -> Path:
    return _write(
        path,
        {
            "status": "frozen_for_manual_offline_review",
            "freeze": {
                "freeze_id": "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721",
                "frozen_manifest_sha256": "a" * 64,
                "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                "selected_label": "v2_tuned_downside_tail_decay",
                "state_columns": ["downside_deviation", "realized_volatility"],
                "reward_columns": ["drawdown_penalty", "reward_proxy"],
                "reward_params": {"drawdown_weight": 0.3},
            },
            "decision": {
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _micro_tilt(path: Path, *, passed: bool = True, eligible_tickers: list[str] | None = None) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review" if passed else "blocked",
            "inputs": {
                "eligible_tickers": eligible_tickers or ["0050.TW", "0056.TW", "00713.TW"],
                "excluded_tickers": ["00631L.TW", "00632R.TW"],
                "required_cost_bps": [0.0, 2.0],
                "warning_cost_bps": [5.0],
            },
            "summary": {
                "micro_tilt_guard_passed": passed,
                "required_cost_scenarios_passed": 2 if passed else 0,
                "warning_cost_scenarios_passed": 0,
                "required_results": [],
                "warning_results": [],
            },
            "warning_reasons": ["warning_cost_scenario_failed:5bps"] if passed else [],
            "decision": {
                "cost_aware_micro_tilt_guard_passed_shadow_gate": passed,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_build_review_allows_shadow_design_but_not_training_or_live(tmp_path: Path) -> None:
    review = build_review(
        promotion_gate_path=_promotion_gate(tmp_path / "gate.json"),
        frozen_manifest_path=_manifest(tmp_path / "manifest.json"),
        micro_tilt_guard_path=_micro_tilt(tmp_path / "micro.json"),
        as_of="2026-07-21",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_shadow_model_design_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["design"]["freeze_id"] == "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721"
    assert review["design"]["proposal_id"] == "gift_research_downside_vol_letf_tail_decay_v1"
    assert review["design"]["eligible_tickers"] == ["0050.TW", "0056.TW", "00713.TW"]
    assert review["decision"]["shadow_model_design_allowed"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "warning_cost_scenario_failed:5bps" in review["warning_reasons"]


def test_build_review_blocks_when_gate_not_passed(tmp_path: Path) -> None:
    review = build_review(
        promotion_gate_path=_promotion_gate(tmp_path / "gate.json", passed=False),
        frozen_manifest_path=_manifest(tmp_path / "manifest.json"),
        micro_tilt_guard_path=_micro_tilt(tmp_path / "micro.json"),
        as_of="2026-07-21",
    )

    assert review["status"] == "blocked"
    assert "promotion_gate_not_available:blocked" in review["blocking_reasons"]
    assert review["decision"]["shadow_model_design_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_build_review_blocks_if_excluded_ticker_present(tmp_path: Path) -> None:
    review = build_review(
        promotion_gate_path=_promotion_gate(tmp_path / "gate.json"),
        frozen_manifest_path=_manifest(tmp_path / "manifest.json"),
        micro_tilt_guard_path=_micro_tilt(tmp_path / "micro.json", eligible_tickers=["0050.TW", "00631L.TW"]),
        as_of="2026-07-21",
    )

    assert review["status"] == "blocked"
    assert "excluded_ticker_present_in_shadow_design_universe" in review["blocking_reasons"]
    assert review["design"]["blocked_live_tickers_present"] == ["00631L.TW"]
    assert review["decision"]["allow_00631l_add"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "design.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_shadow_model_design_review",
        "as_of": "2026-07-21",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_shadow_model_design_review_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
