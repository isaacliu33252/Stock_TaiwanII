from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_promotion_gate import build_promotion_gate


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_promotion_gate_blocks_when_panel_drift_exceeds_limit(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                # h20_prob_up is trigger-critical (a2118 reads it directly). Its
                # limit was recalibrated from 0.05 to 0.15 on 2026-07-07 (see
                # DRIFT_LIMIT_TIERS comment -- 0.05 was unsatisfiable even by
                # the accepted, shipped panel-drift fix), so 0.20 must still fail.
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.20, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift)

    assert report["metrics_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["status"] == "fail"
    assert report["decision"] == "blocked_panel_drift"
    assert report["blocking_gates"] == ["panel_drift"]
    assert report["panel_drift_gate"]["checks"]["h20_prob_up"]["tier"] == "trigger_critical"


def test_promotion_gate_blocks_when_panel_drift_audit_is_missing(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    deployment = _write_json(
        tmp_path / "deployment.json",
        {
            "status": "blocked",
            "computed": {
                "gift_signed_approval_governance": {
                    "signed_approval_record_valid": False,
                    "human_exception_approved": False,
                    "training_queue_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                }
            },
            "blocking_reasons": ["source_freshness_not_ok"],
            "warning_reasons": ["gift_signed_approval_record_missing_or_invalid"],
            "decision": {"broker_actionable": False},
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=tmp_path / "missing_drift.json",
        deployment_consistency=deployment,
    )

    assert report["panel_drift_gate"]["status"] == "fail"
    assert report["panel_drift_gate"]["reason"] == "panel drift audit is required but the file is missing"
    assert report["decision"] == "blocked_deployment_consistency_and_model_gates"
    assert report["blocking_gates"] == ["panel_drift", "deployment_consistency"]
    assert "source_freshness_not_ok" in report["deployment_consistency_gate"]["blocking_reasons"]


def test_promotion_gate_allows_relaxed_diagnostic_drift_within_new_tier_limit(tmp_path: Path) -> None:
    """2026-07-07 Fable audit: under the old flat 0.05 limit, any NCF-panel
    candidate was permanently blocked because ensemble_prob_up (a diagnostic
    column a2118 never reads) has irreducible residual drift up to ~0.11-0.21
    even in the validated, promoted 2026-07-07 panel-drift fix. 0.15 must now
    pass -- it would have failed under the old flat limit."""
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.15, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift)

    assert report["panel_drift_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["checks"]["ensemble_prob_up"]["tier"] == "diagnostic"
    assert report["decision"] == "promotion_ready"


def test_promotion_gate_allows_formal_candidate_when_drift_passes(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift)

    assert report["metrics_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["status"] == "pass"
    assert report["multi_window_gate"]["status"] == "not_required"
    assert report["decision"] == "promotion_ready"


def test_promotion_gate_blocks_when_gift_governance_is_not_approved(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    deployment = _write_json(
        tmp_path / "deployment.json",
        {
            "status": "manual_review_required",
            "computed": {
                "gift_signed_approval_governance": {
                    "validation_status": "blocked",
                    "signed_approval_record_valid": False,
                    "human_exception_approved": False,
                    "non_ppo_shadow_queue_review_allowed": False,
                    "training_queue_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                    "training_queue_blocking_reasons": [
                        "signed_human_exception_approval_record_missing_or_invalid"
                    ],
                }
            },
            "blocking_reasons": [],
            "warning_reasons": [
                "gift_signed_approval_record_missing_or_invalid",
                "gift_human_exception_not_approved",
            ],
            "decision": {"broker_actionable": False},
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift, deployment_consistency=deployment)

    context = report["governance_context"]
    deployment_context = context["deployment_consistency"]
    assert report["decision"] == "blocked_deployment_consistency"
    assert report["deployment_consistency_gate"]["status"] == "fail"
    assert report["blocking_gates"] == ["deployment_consistency"]
    assert "deployment_consistency_not_broker_actionable" in report["deployment_consistency_gate"]["blocking_reasons"]
    assert (
        "gift_signed_approval_record_missing_or_invalid"
        in report["deployment_consistency_gate"]["manual_approval_pending_reasons"]
    )
    assert "gift_human_exception_not_approved" in report["deployment_consistency_gate"]["manual_approval_pending_reasons"]
    assert context["active_allocation_impact"] == "none"
    assert context["target_weight_change_allowed"] is False
    assert context["auto_rebalance_allowed"] is False
    assert context["model_training_allowed"] is False
    assert context["ppo_training_allowed"] is False
    assert context["promote_to_live"] is False
    assert context["allow_00631l_add"] is False
    assert context["allow_00632r_open"] is False
    assert context["keep_golden1_0531_unchanged"] is True
    assert deployment_context["status"] == "manual_review_required"
    assert deployment_context["broker_actionable"] is False
    assert deployment_context["gift_signed_approval_record_valid"] is False


def test_promotion_gate_separates_manual_approval_pending_from_hard_deployment_blockers(
    tmp_path: Path,
) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.20, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    multi_window = _write_json(
        tmp_path / "multi_window.json",
        {"decision": "research_only_no_multi_window_pass", "candidate_count": 1, "candidates": []},
    )
    deployment = _write_json(
        tmp_path / "deployment.json",
        {
            "status": "manual_review_required",
            "broker_actionable": True,
            "computed": {
                "gift_signed_approval_governance": {
                    "signed_approval_record_valid": False,
                    "human_exception_approved": False,
                    "training_queue_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                }
            },
            "blocking_reasons": [],
            "warning_reasons": [
                "gift_signed_approval_record_missing_or_invalid",
                "gift_human_exception_not_approved",
            ],
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=drift,
        multi_window_gate=multi_window,
        deployment_consistency=deployment,
    )
    deployment_context = report["governance_context"]["deployment_consistency"]

    assert report["decision"] == "blocked_model_gates_manual_approval_pending"
    assert report["blocking_gates"] == ["panel_drift", "multi_window"]
    assert report["deployment_consistency_gate"]["status"] == "pass"
    assert report["deployment_consistency_gate"]["blocking_reasons"] == []
    assert report["deployment_consistency_gate"]["hard_blocking_reasons"] == []
    assert report["deployment_consistency_gate"]["manual_approval_pending_reasons"] == [
        "gift_signed_approval_record_missing_or_invalid",
        "gift_human_exception_not_approved",
    ]
    assert deployment_context["gift_human_exception_approved"] is False
    assert deployment_context["gift_training_queue_allowed"] is False
    assert deployment_context["gift_model_training_allowed"] is False
    assert deployment_context["gift_ppo_training_allowed"] is False
    assert deployment_context["gift_promote_to_live"] is False
    assert "gift_signed_approval_record_missing_or_invalid" in deployment_context["warning_reasons"]


def test_promotion_gate_blocks_when_deployment_consistency_context_is_missing(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=drift,
        deployment_consistency=tmp_path / "missing_deployment.json",
    )

    deployment_context = report["governance_context"]["deployment_consistency"]
    assert report["decision"] == "blocked_deployment_consistency"
    assert report["deployment_consistency_gate"]["status"] == "fail"
    assert report["blocking_gates"] == ["deployment_consistency"]
    assert "deployment_consistency_review_missing" in report["deployment_consistency_gate"]["blocking_reasons"]
    assert deployment_context["status"] == "missing"
    assert deployment_context["blocking_reasons"] == ["deployment_consistency_review_missing"]
    assert report["governance_context"]["promote_to_live"] is False


def test_promotion_gate_allows_formal_candidate_when_deployment_consistency_passes(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    deployment = _write_json(
        tmp_path / "deployment.json",
        {
            "status": "pass",
            "computed": {
                "gift_signed_approval_governance": {
                    "validation_status": "approved",
                    "signed_approval_record_valid": True,
                    "human_exception_approved": True,
                    "non_ppo_shadow_queue_review_allowed": True,
                    "training_queue_allowed": False,
                    "model_training_allowed": False,
                    "ppo_training_allowed": False,
                    "promote_to_live": False,
                    "training_queue_blocking_reasons": [],
                }
            },
            "blocking_reasons": [],
            "warning_reasons": [],
            "decision": {"broker_actionable": True},
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift, deployment_consistency=deployment)

    assert report["deployment_consistency_gate"]["status"] == "pass"
    assert report["blocking_gates"] == []
    assert report["decision"] == "promotion_ready"


def test_promotion_gate_requires_deployment_summary_consistency(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    summary = _write_json(
        tmp_path / "deployment_summary.json",
        {
            "status": "manual_review_required",
            "broker_actionable": True,
            "blocking_reasons": [],
            "warning_reasons": [],
            "consistency_review": {"status": "ok", "errors": [], "warnings": []},
            "decision": {
                "summary_only": True,
                "creates_orders": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
                "keep_golden1_0531_unchanged": True,
            },
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift, deployment_summary=summary)

    assert report["deployment_summary_gate"]["status"] == "pass"
    assert report["governance_context"]["deployment_summary"]["consistency_review_status"] == "ok"
    assert report["blocking_gates"] == []
    assert report["decision"] == "promotion_ready"


def test_promotion_gate_blocks_when_deployment_summary_is_inconsistent(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    summary = _write_json(
        tmp_path / "deployment_summary.json",
        {
            "status": "manual_review_required",
            "broker_actionable": True,
            "blocking_reasons": [],
            "warning_reasons": [],
            "consistency_review": {
                "status": "error",
                "errors": ["deployment_decision_target_weight_change_allowed_mismatch"],
                "warnings": [],
            },
            "decision": {
                "summary_only": True,
                "creates_orders": False,
                "target_weight_change_allowed": True,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
                "keep_golden1_0531_unchanged": True,
            },
        },
    )

    report = build_promotion_gate(baseline, [candidate], drift_audit=drift, deployment_summary=summary)

    assert report["deployment_summary_gate"]["status"] == "fail"
    assert report["blocking_gates"] == ["deployment_summary"]
    assert report["decision"] == "blocked_deployment_summary"
    blockers = report["deployment_summary_gate"]["blocking_reasons"]
    assert "deployment_summary_consistency_review:error" in blockers
    assert "deployment_summary_target_weight_change_allowed_unexpected" in blockers
    assert "deployment_decision_target_weight_change_allowed_mismatch" in blockers


def test_promotion_gate_blocks_when_multi_window_gate_fails(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.01, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )
    multi_window = _write_json(
        tmp_path / "multi_window.json",
        {
            "decision": "research_only_no_multi_window_pass",
            "row_count": 2,
            "candidate_count": 1,
            "criteria": {"min_pass_ratio": 1.0},
            "candidates": [
                {
                    "candidate": "strong_candidate",
                    "decision": "research_only_multi_window_unstable",
                    "pass_count": 1,
                    "window_count": 2,
                    "pass_ratio": 0.5,
                }
            ],
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=drift,
        multi_window_gate=multi_window,
    )

    assert report["metrics_gate"]["status"] == "pass"
    assert report["panel_drift_gate"]["status"] == "pass"
    assert report["multi_window_gate"]["status"] == "fail"
    assert report["decision"] == "blocked_multi_window"
    assert report["blocking_gates"] == ["multi_window"]


def test_promotion_gate_reports_combined_blockers(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "candidate",
            "rows": [
                {
                    "name": "strong_candidate",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.3,
                    "max_drawdown": -0.10,
                    "trigger_days": 3,
                }
            ],
        },
    )
    drift = _write_json(
        tmp_path / "drift.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.02, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.20, "max_abs_delta_date": "2025-01-02"},
                "confidence": {"max_abs_delta": 0.03, "max_abs_delta_date": "2025-01-02"},
            }
        },
    )

    report = build_promotion_gate(
        baseline,
        [candidate],
        drift_audit=drift,
        require_multi_window_gate=True,
    )

    assert report["panel_drift_gate"]["status"] == "fail"
    assert report["multi_window_gate"]["status"] == "fail"
    assert report["decision"] == "blocked_panel_drift_and_multi_window"
    assert report["blocking_gates"] == ["panel_drift", "multi_window"]
