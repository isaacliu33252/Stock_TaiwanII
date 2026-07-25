from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_promotion_gate_snapshot import (
    build_snapshot,
    write_snapshot,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _inputs(tmp_path: Path, *, passing: bool = False) -> dict[str, Path]:
    baseline_summary = {
        "positive_final_value_folds": 4,
        "positive_sharpe_folds": 4,
        "non_worse_drawdown_folds": 3 if passing else 1,
    }
    return {
        "proposal_comparison": _write(
            tmp_path / "proposal.json",
            {"status": "available_for_manual_offline_review", "summary": {"best_candidate": "v2_tuned"}},
        ),
        "frozen_manifest": _write(
            tmp_path / "manifest.json",
            {
                "status": "available_for_manual_offline_review",
                "freeze_id": "unit_freeze",
                "frozen_manifest_sha256": "a" * 64,
            },
        ),
        "frozen_panel_review": _write(
            tmp_path / "panel.json",
            {"status": "available_for_manual_offline_review", "summary": {"rows": 100, "ticker_count": 6}},
        ),
        "walk_forward_audit": _write(
            tmp_path / "audit.json",
            {"status": "available_for_manual_offline_review", "summary": {"fold_count": 6, "warning_count": 0}},
        ),
        "baseline_shadow": _write(
            tmp_path / "baseline.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": baseline_summary,
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "baseline_param_sweep": _write(
            tmp_path / "baseline_sweep.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"has_recommended_candidate": passing, "recommended_count": 1 if passing else 0},
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "drawdown_attribution": _write(
            tmp_path / "attribution.json",
            {"status": "available_for_manual_offline_review", "summary": {"failing_drawdown_folds": 0 if passing else 5}},
        ),
        "risk_control_overlay": _write(
            tmp_path / "overlay.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"pass_risk_control_overlay_gate": passing},
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "cost_aware_micro_tilt_guard": _write(
            tmp_path / "micro_tilt.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {
                    "micro_tilt_guard_passed": passing,
                    "required_cost_scenarios": 2,
                    "required_cost_scenarios_passed": 2 if passing else 0,
                },
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "stress_regime_gate": _write(
            tmp_path / "stress.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"pass_stress_regime_gate": False},
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "bucket_guard": _write(
            tmp_path / "bucket.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"pass_bucket_guard_gate": False},
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "relative_drawdown_circuit": _write(
            tmp_path / "circuit.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"pass_relative_drawdown_circuit_gate": False},
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "relative_drawdown_circuit_sweep": _write(
            tmp_path / "circuit_sweep.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"has_recommended_candidate": False, "passed_count": 0},
                "decision": {"model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "v3_high_dividend_active_pain_dgr": _write(
            tmp_path / "v3_dgr.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"alignment_grade": "green", "pass_high_dividend_active_pain_dgr": passing},
                "decision": {"high_dividend_active_pain_dgr_passed": passing, "model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "v3_high_dividend_active_pain_smoke": _write(
            tmp_path / "v3_smoke.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {
                    "high_dividend_active_pain_offline_smoke": {
                        "positive_final_value_folds": 4 if passing else 0,
                        "positive_sharpe_folds": 4 if passing else 0,
                        "non_worse_drawdown_folds": 3 if passing else 0,
                    },
                    "pass_high_dividend_active_pain_offline_smoke": passing,
                },
                "decision": {"high_dividend_active_pain_offline_smoke_passed": passing, "model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "v3_high_dividend_active_pain_panel_audit": _write(
            tmp_path / "v3_audit.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"fold_count": 6, "duplicate_fold_date_ticker_rows": 0},
                "decision": {"v3_walk_forward_panel_audit_passed": passing, "model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
        "v3_high_dividend_active_pain_param_sweep": _write(
            tmp_path / "v3_param_sweep.json",
            {
                "status": "available_for_manual_offline_review",
                "summary": {"evaluated_count": 45, "passed_count": 16 if passing else 0, "robustness_passed": passing},
                "decision": {"v3_active_pain_param_robustness_passed": passing, "model_training_allowed": False, "ppo_training_allowed": False, "promote_to_live": False},
            },
        ),
    }


def test_build_snapshot_blocks_failed_promotion_gate(tmp_path: Path) -> None:
    snapshot = build_snapshot(_inputs(tmp_path, passing=False), as_of="2026-07-20")

    assert snapshot["report_type"] == "group_a_plus_llm_state_reward_interface_promotion_gate_snapshot"
    assert snapshot["status"] == "blocked"
    assert snapshot["decision"]["promotion_gate_passed"] is False
    assert snapshot["decision"]["next_shadow_model_design_allowed"] is False
    assert snapshot["decision"]["model_training_allowed"] is False
    assert snapshot["decision"]["ppo_training_allowed"] is False
    assert snapshot["decision"]["promote_to_live"] is False
    assert snapshot["decision"]["outputs_target_weights"] is False
    assert snapshot["decision"]["allow_00631l_add"] is False
    assert snapshot["decision"]["allow_00632r_open"] is False
    assert "baseline_non_worse_drawdown_folds_below_threshold:1<3" in snapshot["blocking_reasons"]
    assert "no_shadow_risk_control_passed_promotion_gate" in snapshot["blocking_reasons"]
    assert "baseline_param_sweep_has_no_recommended_candidate" in snapshot["blocking_reasons"]


def test_build_snapshot_can_allow_only_next_shadow_design_when_gate_passes(tmp_path: Path) -> None:
    snapshot = build_snapshot(_inputs(tmp_path, passing=True), as_of="2026-07-20")

    assert snapshot["status"] == "available_for_manual_offline_review"
    assert snapshot["decision"]["promotion_gate_passed"] is True
    assert snapshot["decision"]["next_shadow_model_design_allowed"] is True
    assert snapshot["decision"]["model_training_allowed"] is False
    assert snapshot["decision"]["ppo_training_allowed"] is False
    assert snapshot["decision"]["promote_to_live"] is False
    assert snapshot["decision"]["outputs_target_weights"] is False
    assert snapshot["decision"]["allow_00631l_add"] is False
    assert snapshot["decision"]["allow_00632r_open"] is False
    assert snapshot["summary"]["risk_control_gate_passes"]["v3_high_dividend_active_pain"] is True
    assert snapshot["summary"]["risk_control_gate_passes"]["cost_aware_micro_tilt_guard"] is True
    assert snapshot["summary"]["v3_high_dividend_active_pain"]["non_worse_drawdown_folds"] == 3
    assert snapshot["summary"]["v3_high_dividend_active_pain"]["param_robustness_passed"] is True


def test_build_snapshot_uses_recommended_baseline_sweep_gate_metrics(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, passing=False)
    baseline_sweep = {
        "status": "available_for_manual_offline_review",
        "summary": {
            "recommended_count": 1,
            "best_recommended_aggregate": {
                "positive_final_value_folds": 4,
                "positive_sharpe_folds": 4,
                "non_worse_drawdown_folds": 4,
            },
        },
        "decision": {
            "recommended_baseline_variant_available": True,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
        },
    }
    inputs["baseline_param_sweep"] = _write(tmp_path / "baseline_sweep_decision_only.json", baseline_sweep)

    snapshot = build_snapshot(inputs, as_of="2026-07-20")

    assert snapshot["status"] == "blocked"
    assert snapshot["summary"]["baseline_gate_metrics"] == {
        "source": "baseline_param_sweep_best_recommended",
        "positive_final_value_folds": 4,
        "positive_sharpe_folds": 4,
        "non_worse_drawdown_folds": 4,
    }
    assert "baseline_non_worse_drawdown_folds_below_threshold:1<3" not in snapshot["blocking_reasons"]
    assert "baseline_param_sweep_has_no_recommended_candidate" not in snapshot["blocking_reasons"]
    assert "no_shadow_risk_control_passed_promotion_gate" in snapshot["blocking_reasons"]


def test_build_snapshot_accepts_cost_aware_micro_tilt_as_shadow_risk_control(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, passing=False)
    baseline_sweep = {
        "status": "available_for_manual_offline_review",
        "summary": {
            "recommended_count": 1,
            "best_recommended_aggregate": {
                "positive_final_value_folds": 4,
                "positive_sharpe_folds": 4,
                "non_worse_drawdown_folds": 4,
            },
        },
        "decision": {
            "recommended_baseline_variant_available": True,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
        },
    }
    micro_tilt = {
        "status": "available_for_manual_offline_review",
        "summary": {
            "micro_tilt_guard_passed": True,
            "required_cost_scenarios": 2,
            "required_cost_scenarios_passed": 2,
        },
        "decision": {
            "cost_aware_micro_tilt_guard_passed_shadow_gate": True,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
        },
    }
    inputs["baseline_param_sweep"] = _write(tmp_path / "baseline_sweep_decision_only.json", baseline_sweep)
    inputs["cost_aware_micro_tilt_guard"] = _write(tmp_path / "micro_tilt_pass.json", micro_tilt)

    snapshot = build_snapshot(inputs, as_of="2026-07-20")

    assert snapshot["status"] == "available_for_manual_offline_review"
    assert snapshot["decision"]["promotion_gate_passed"] is True
    assert snapshot["decision"]["next_shadow_model_design_allowed"] is True
    assert snapshot["summary"]["risk_control_gate_passes"]["cost_aware_micro_tilt_guard"] is True
    assert snapshot["summary"]["risk_control_gate_passes"]["v3_high_dividend_active_pain"] is False
    assert snapshot["decision"]["model_training_allowed"] is False
    assert snapshot["decision"]["promote_to_live"] is False
    assert snapshot["decision"]["allow_00631l_add"] is False
    assert snapshot["decision"]["allow_00632r_open"] is False


def test_build_snapshot_treats_blocked_v3_branch_as_optional_when_micro_tilt_passes(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, passing=False)
    inputs["baseline_param_sweep"] = _write(
        tmp_path / "baseline_sweep_pass.json",
        {
            "status": "available_for_manual_offline_review",
            "summary": {
                "recommended_count": 1,
                "best_recommended_aggregate": {
                    "positive_final_value_folds": 4,
                    "positive_sharpe_folds": 4,
                    "non_worse_drawdown_folds": 4,
                },
            },
            "decision": {
                "recommended_baseline_variant_available": True,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )
    inputs["cost_aware_micro_tilt_guard"] = _write(
        tmp_path / "micro_tilt_pass.json",
        {
            "status": "available_for_manual_offline_review",
            "summary": {"micro_tilt_guard_passed": True},
            "decision": {
                "cost_aware_micro_tilt_guard_passed_shadow_gate": True,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )
    inputs["v3_high_dividend_active_pain_smoke"] = _write(
        tmp_path / "v3_smoke_blocked.json",
        {
            "status": "blocked",
            "summary": {"high_dividend_active_pain_offline_smoke": {}},
            "decision": {
                "high_dividend_active_pain_offline_smoke_passed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )
    inputs["v3_high_dividend_active_pain_panel_audit"] = _write(
        tmp_path / "v3_audit_blocked.json",
        {
            "status": "blocked",
            "summary": {"fold_count": 0},
            "decision": {
                "v3_walk_forward_panel_audit_passed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
            },
        },
    )

    snapshot = build_snapshot(inputs, as_of="2026-07-20")

    assert snapshot["status"] == "available_for_manual_offline_review"
    assert snapshot["decision"]["promotion_gate_passed"] is True
    assert snapshot["decision"]["next_shadow_model_design_allowed"] is True
    assert "v3_high_dividend_active_pain_smoke_blocked" in snapshot["warning_reasons"]
    assert "v3_high_dividend_active_pain_smoke_blocked" not in snapshot["blocking_reasons"]
    assert snapshot["decision"]["model_training_allowed"] is False
    assert snapshot["decision"]["promote_to_live"] is False


def test_write_snapshot_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "snapshot.json"
    history = tmp_path / "history"
    snapshot = {
        "report_type": "group_a_plus_llm_state_reward_interface_promotion_gate_snapshot",
        "as_of": "2026-07-20",
    }

    write_snapshot(snapshot, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == snapshot
    history_file = history / "llm_state_reward_interface_promotion_gate_snapshot_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == snapshot
