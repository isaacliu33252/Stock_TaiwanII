from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_training_readiness_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _design(path: Path, *, status: str = "available_for_manual_offline_review", warnings: list[str] | None = None) -> Path:
    return _write(
        path,
        {
            "status": status,
            "design": {
                "design_id": "unit_shadow_model_design",
                "freeze_id": "group_a_plus_gift_downside_tail_decay_v2_tuned_20260721",
                "frozen_manifest_sha256": "a" * 64,
                "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                "selected_label": "v2_tuned_downside_tail_decay",
                "eligible_tickers": ["0050.TW", "0056.TW", "00713.TW"],
                "excluded_tickers": ["00631L.TW", "00632R.TW"],
                "blocked_live_tickers_present": [],
                "state_columns": ["downside_deviation", "realized_volatility"],
                "reward_columns": ["drawdown_penalty", "reward_proxy"],
                "allowed_shadow_model_family": "tabular_or_sequence_shadow_model_design_only",
                "allowed_training_label": "future_return_or_downside_proxy_for_offline_design",
                "validation_plan": {"walk_forward_required": True, "purge_required": True},
                "hard_constraints": {
                    "no_model_training_in_this_step": True,
                    "no_ppo_training": True,
                    "no_live_signal_output": True,
                    "no_target_weight_output": True,
                    "no_auto_rebalance": True,
                    "no_00631l_add": True,
                    "no_00632r_open": True,
                },
            },
            "warning_reasons": warnings or [],
            "decision": {
                "shadow_model_design_allowed": status == "available_for_manual_offline_review",
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_build_review_blocks_training_readiness_on_cost_warning(tmp_path: Path) -> None:
    review = build_review(
        design_review_path=_design(tmp_path / "design.json", warnings=["warning_cost_scenario_failed:5bps"]),
        as_of="2026-07-21",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_shadow_training_readiness_review"
    assert review["status"] == "blocked"
    assert review["summary"]["shadow_training_ready"] is False
    assert "unresolved_cost_warning:5bps" in review["blocking_reasons"]
    assert review["decision"]["shadow_training_request_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_uses_cost_warning_remediation_source(tmp_path: Path) -> None:
    remediation = _write(
        tmp_path / "remediation.json",
        {
            "status": "blocked",
            "summary": {
                "cost_warning_resolved": False,
                "evaluated_count": 3,
            },
        },
    )
    attribution = _write(
        tmp_path / "attribution.json",
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "best_high_score": 1.02,
                "dominant_failure_metric_for_best": "sharpe_delta_not_positive",
            },
            "decision": {
                "cost_warning_failure_explained": True,
                "model_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )
    turnover_attribution = _write(
        tmp_path / "turnover_attribution.json",
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "best_failure_cause": "turnover_cost_and_raw_signal",
                "best_cost_caused_failure_fold_count": 1,
                "best_raw_signal_failure_fold_count": 3,
            },
            "decision": {
                "turnover_cost_attribution_ready": True,
                "model_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )

    review = build_review(
        design_review_path=_design(tmp_path / "design.json", warnings=["warning_cost_scenario_failed:5bps"]),
        cost_warning_remediation_path=remediation,
        cost_warning_attribution_path=attribution,
        cost_warning_turnover_attribution_path=turnover_attribution,
        as_of="2026-07-21",
    )

    assert review["status"] == "blocked"
    assert "cost_warning_remediation_failed_to_resolve_warning_cost" in review["blocking_reasons"]
    assert review["summary"]["cost_warning_remediation_status"] == "blocked"
    assert review["summary"]["cost_warning_resolved"] is False
    assert review["summary"]["cost_warning_remediation_evaluated_count"] == 3
    assert review["summary"]["cost_warning_failure_explained"] is True
    assert review["summary"]["cost_warning_dominant_failure_metric"] == "sharpe_delta_not_positive"
    assert review["summary"]["cost_warning_best_high_score"] == 1.02
    assert review["summary"]["cost_warning_turnover_failure_cause"] == "turnover_cost_and_raw_signal"
    assert review["summary"]["cost_warning_turnover_cost_caused_failure_fold_count"] == 1
    assert review["summary"]["cost_warning_raw_signal_failure_fold_count"] == 3
    assert review["inputs"]["cost_warning_remediation"] == str(remediation)
    assert review["inputs"]["cost_warning_remediation_sha256"] is not None
    assert review["inputs"]["cost_warning_attribution"] == str(attribution)
    assert review["inputs"]["cost_warning_attribution_sha256"] is not None
    assert review["inputs"]["cost_warning_turnover_attribution"] == str(turnover_attribution)
    assert review["inputs"]["cost_warning_turnover_attribution_sha256"] is not None
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_build_review_accepts_regime_filter_cost_warning_resolution(tmp_path: Path) -> None:
    remediation = _write(
        tmp_path / "remediation.json",
        {
            "status": "blocked",
            "summary": {"cost_warning_resolved": False, "evaluated_count": 3},
        },
    )
    regime_filter = _write(
        tmp_path / "regime_filter.json",
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "recommended_candidate": {
                    "regime_rule": "trend_above_train_median",
                    "high_score": 1.03,
                    "aggregate": {
                        "positive_final_value_folds": 5,
                        "positive_sharpe_folds": 4,
                        "non_worse_drawdown_folds": 4,
                    },
                }
            },
            "decision": {
                "regime_filter_resolves_5bps_warning": True,
                "model_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )

    review = build_review(
        design_review_path=_design(tmp_path / "design.json", warnings=["warning_cost_scenario_failed:5bps"]),
        cost_warning_remediation_path=remediation,
        regime_filtered_micro_tilt_path=regime_filter,
        as_of="2026-07-21",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["shadow_training_ready"] is True
    assert review["summary"]["training_readiness_blocked_by_cost_warning"] is False
    assert review["summary"]["regime_filter_resolves_5bps_warning"] is True
    assert review["summary"]["regime_filter_recommended_candidate"]["regime_rule"] == "trend_above_train_median"
    assert "cost_warning_resolved_by_regime_filtered_micro_tilt" in review["warning_reasons"]
    assert review["decision"]["shadow_training_request_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_can_mark_ready_when_warning_cost_is_not_required(tmp_path: Path) -> None:
    review = build_review(
        design_review_path=_design(tmp_path / "design.json", warnings=["warning_cost_scenario_failed:5bps"]),
        require_warning_cost_pass=False,
        as_of="2026-07-21",
    )

    assert review["status"] == "available_for_manual_offline_review"
    assert review["decision"]["shadow_training_ready"] is True
    assert "warning_cost_scenario_failed:5bps" in review["warning_reasons"]
    assert review["decision"]["shadow_training_request_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["promote_to_live"] is False


def test_build_review_blocks_missing_hard_constraints(tmp_path: Path) -> None:
    design_path = _design(tmp_path / "design.json")
    payload = json.loads(design_path.read_text(encoding="utf-8"))
    payload["design"]["hard_constraints"].pop("no_target_weight_output")
    design_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    review = build_review(design_review_path=design_path, as_of="2026-07-21")

    assert review["status"] == "blocked"
    assert "missing_hard_constraint:no_target_weight_output" in review["blocking_reasons"]
    assert review["decision"]["outputs_target_weights"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "readiness.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_shadow_training_readiness_review",
        "as_of": "2026-07-21",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_shadow_training_readiness_review_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
