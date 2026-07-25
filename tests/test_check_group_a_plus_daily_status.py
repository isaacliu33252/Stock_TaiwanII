#!/usr/bin/env python3
"""Tests for GroupA+ daily status payload assembly."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from scripts.misc.check_group_a_plus_daily_status import _live_status_report, _markdown_text


def _write_standard(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps({"success": True, "data": data, "metadata": {}, "error": None}, ensure_ascii=False),
        encoding="utf-8",
    )


def _args(live_signal: Path, execution_plan: Path) -> Namespace:
    return Namespace(
        live_signal=str(live_signal),
        execution_plan=str(execution_plan),
        compounding_regime=str(live_signal.parent / "missing_compounding_regime.json"),
        dfl_advisory=str(live_signal.parent / "missing_dfl_advisory.json"),
        dfl_shadow_ensemble=str(live_signal.parent / "missing_dfl_shadow_ensemble.json"),
        dfl_active_date_audit=str(live_signal.parent / "missing_dfl_active_date_audit.json"),
        finstressts_decision_snapshot=str(live_signal.parent / "missing_finstressts_decision_snapshot.json"),
        trigate_vol_memory_shadow=str(live_signal.parent / "missing_trigate_vol_memory_shadow.json"),
        systemic_bubble_time_at_risk_review=str(
            live_signal.parent / "missing_systemic_bubble_time_at_risk_review.json"
        ),
        illiquidity_network_readiness_review=str(
            live_signal.parent / "missing_illiquidity_network_readiness_review.json"
        ),
        speculative_influence_network_readiness_review=str(
            live_signal.parent / "missing_speculative_influence_network_readiness_review.json"
        ),
        sin_lite_proxy=str(live_signal.parent / "missing_sin_lite_proxy.json"),
        hmm_wj_synthetic_scenario_readiness_review=str(
            live_signal.parent / "missing_hmm_wj_synthetic_scenario_readiness_review.json"
        ),
        dynamic_cvar_tail_cost_readiness_review=str(
            live_signal.parent / "missing_dynamic_cvar_tail_cost_readiness_review.json"
        ),
        synthetic_augmentation_validation_readiness_review=str(
            live_signal.parent / "missing_synthetic_augmentation_validation_readiness_review.json"
        ),
        intervention_fatigue_risk_budget_readiness_review=str(
            live_signal.parent / "missing_intervention_fatigue_risk_budget_readiness_review.json"
        ),
        letf_tracking_error_effective_fee_readiness_review=str(
            live_signal.parent / "missing_letf_tracking_error_effective_fee_readiness_review.json"
        ),
        asian_etf_tail_analytics_readiness_review=str(
            live_signal.parent / "missing_asian_etf_tail_analytics_readiness_review.json"
        ),
        research_shadow_decision_snapshot=str(live_signal.parent / "missing_research_shadow_decision_snapshot.json"),
        gift_signed_approval_checklist_review=str(
            live_signal.parent / "missing_gift_signed_approval_checklist_review.json"
        ),
        gift_signed_approval_validator_smoke=str(
            live_signal.parent / "missing_gift_signed_approval_validator_smoke.json"
        ),
        promotion_gate=str(live_signal.parent / "missing_promotion_gate.json"),
        check_date="2026-07-09",
        status_stage="pre_promotion",
        max_business_stale_days=3,
    )


def _live_signal_data() -> dict:
    return {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "strategy_status": "active",
        "requested_as_of_date": "2026-07-09",
        "actual_data_date": "2026-07-09",
        "execution_allowed": True,
        "execution_guard_reasons": [],
        "execution_warning_reasons": [],
        "action": "rebalance_to_target",
        "regime_reason": "active strategy regime",
        "execution_regime": "golden1",
        "target_weights": {"0050.TW": 0.8, "00631L.TW": 0.2},
        "reference_target_shares_before_cost": {"0050.TW": 100, "00631L.TW": 150},
        "estimated_cash_after_rounding_before_cost": 1000.0,
        "data_freshness": {"optional_sources": {}},
    }


def test_live_status_includes_aligned_execution_plan_pre_trade_guard(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
            "pre_trade_guard": {
                "status": "blocked",
                "ticker": "00631L.TW",
                "allow_00631l_add": False,
                "policy": "advisory_no_auto_weight_change",
                "blocked_trades": [
                    {
                        "ticker": "00631L.TW",
                        "side": "buy",
                        "current_shares": 100,
                        "requested_target_shares": 150,
                        "guarded_target_shares": 100,
                    }
                ],
            },
            "compounding_regime_pre_trade_guard": {
                "status": "blocked",
                "ticker": "00631L.TW",
                "allow_00631l_add": False,
                "compounding_regime": "MEAN_REVERTING",
                "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
            },
            "pre_trade_guards": [
                {"name": "volatility_gate_no_00631l_add", "status": "blocked"},
                {"name": "compounding_regime_no_00631l_add", "status": "blocked"},
            ],
            "current_cash_input": 1_000_000.0,
            "cash_assumption": "workbook has no cash field; using explicit --cash-balance input",
            "trades": [
                {"ticker": "0050.TW", "delta_shares": 10},
                {"ticker": "00679B.TWO", "delta_shares": -5},
            ],
        },
    )

    report = _live_status_report(_args(live_signal, execution_plan))
    guard = report["group_a_plus"]["pre_trade_guard"]
    cash = report["group_a_plus"]["execution_plan_cash"]

    assert guard["status"] == "blocked"
    assert guard["allow_00631l_add"] is False
    assert cash["available"] is True
    assert cash["current_cash_input"] == 1_000_000.0
    assert cash["cash_assumption"] == "workbook has no cash field; using explicit --cash-balance input"
    assert cash["nonzero_trade_count"] == 2
    assert report["status_stage"] == "pre_promotion"
    assert [check for check in report["checks"] if check["name"] == "execution_plan_pre_trade_guard"][0]["status"] == "ok"
    markdown = _markdown_text(report)
    assert "Status stage: `pre_promotion`" in markdown
    assert "## Pre-Trade Guard" in markdown
    assert "## 00631L Compounding Guard" in markdown
    assert "00631L add: `blocked`" in markdown
    assert "Execution plan cash input: `1000000.0`" in markdown
    assert "Execution plan nonzero trades: `2`" in markdown


def test_live_status_ignores_stale_execution_plan_guard(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-08",
            "pre_trade_guard": {"status": "blocked", "allow_00631l_add": False},
        },
    )

    report = _live_status_report(_args(live_signal, execution_plan))
    guard_check = [check for check in report["checks"] if check["name"] == "execution_plan_pre_trade_guard"][0]

    assert report["group_a_plus"]["pre_trade_guard"] == {}
    assert report["group_a_plus"]["execution_plan_cash"]["available"] is False
    assert guard_check["status"] == "warn"
    assert report["overall_status"] == "warn"


def test_live_status_includes_promotion_gate_deployment_summary_status(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    promotion_gate = tmp_path / "promotion_gate.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    promotion_gate.write_text(
        json.dumps(
            {
                "decision": "blocked_deployment_consistency_and_model_gates",
                "blocking_gates": ["panel_drift", "deployment_consistency"],
                "deployment_summary_gate": {
                    "status": "pass",
                    "reason": "deployment summary governance passed",
                    "blocking_reasons": [],
                },
                "governance_context": {
                    "deployment_summary": {
                        "consistency_review_status": "ok",
                        "consistency_review_errors": [],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.promotion_gate = str(promotion_gate)

    report = _live_status_report(args)
    promotion = report["group_a_plus"]["promotion_gate"]
    check = [row for row in report["checks"] if row["name"] == "promotion_gate_deployment_summary"][0]

    assert promotion["deployment_summary_gate_status"] == "pass"
    assert promotion["deployment_summary_consistency_status"] == "ok"
    assert check["status"] == "ok"
    markdown = _markdown_text(report)
    assert "## Promotion Gate" in markdown
    assert "Deployment summary gate: `pass`" in markdown
    assert "Deployment summary consistency: `ok`" in markdown


def test_live_status_includes_compounding_regime_diagnostic(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    compounding = tmp_path / "compounding.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    compounding.write_text(
        json.dumps(
            {
                "report_type": "00631l_leveraged_compounding_regime",
                "generated_at": "2026-07-09T18:00:00",
                "active_allocation_impact": "none",
                "latest": {
                    "date": "2026-07-09",
                    "compounding_regime": "MEAN_REVERTING",
                    "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
                    "trend_score": 3,
                    "mean_reversion_score": 4,
                    "rolling_AR1_5d": -0.12,
                    "rolling_AR1_20d": -0.08,
                    "variance_ratio": 0.91,
                    "trend_persistence": 0.50,
                    "reversal_speed": 0.65,
                    "positive_return_streak": 0.0,
                    "negative_return_streak": 2.0,
                    "drawdown_recovery_ratio": 0.70,
                    "00631L_vs_0050_relative_momentum": -0.02,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.compounding_regime = str(compounding)

    report = _live_status_report(args)
    diagnostic = report["group_a_plus"]["compounding_regime_diagnostic"]

    assert diagnostic["status"] == "ok"
    assert diagnostic["compounding_regime"] == "MEAN_REVERTING"
    assert diagnostic["active_allocation_impact"] == "none"
    markdown = _markdown_text(report)
    assert "## 00631L Compounding Regime" in markdown
    assert "MEAN_REVERTING" in markdown


def test_live_status_includes_dfl_advisory(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dfl = tmp_path / "dfl.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    dfl.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_type": "a2118_dfl_advisory",
                "status": "available",
                "policy": "advisory_only_no_auto_weight_change",
                "action": "CAP10",
                "advisory_active": True,
                "selected_decision": {"predicted_regret": 0.0012},
                "selective_variants": {
                    "p50": {
                        "status": "available",
                        "action": "KEEP",
                        "advisory_active": False,
                        "selected_decision": None,
                    },
                    "p70": {
                        "status": "available",
                        "action": "CAP10",
                        "advisory_active": True,
                        "selected_decision": {"reliability_error_percentile": 0.42},
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_advisory = str(dfl)

    report = _live_status_report(args)
    advisory = report["group_a_plus"]["dfl_advisory"]

    assert advisory["status"] == "available"
    assert advisory["action"] == "CAP10"
    markdown = _markdown_text(report)
    assert "## A21.18 DFL Advisory" in markdown
    assert "Predicted regret: `0.0012`" in markdown
    assert "### Selective Variants" in markdown
    assert "`p70` action `CAP10` active `True` reliability `0.42`" in markdown


def test_live_status_includes_dfl_active_date_audit(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    audit = tmp_path / "dfl_audit.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    audit.write_text(
        json.dumps(
            {
                "report_type": "a2118_dfl_active_date_audit",
                "status": "research_only",
                "conclusion": "passes_replay_audit_with_warnings_shadow_only",
                "summary": {
                    "active_days": 7,
                    "all_checks_pass": True,
                    "warning_days": 3,
                    "existing_guard_overlap_days": 0,
                    "total_estimated_cost_bps": 8.0749,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_active_date_audit = str(audit)

    report = _live_status_report(args)
    active_date_audit = report["group_a_plus"]["dfl_active_date_audit"]

    assert active_date_audit["status"] == "research_only"
    assert active_date_audit["summary"]["active_days"] == 7
    markdown = _markdown_text(report)
    assert "## A21.18 DFL Active-Date Audit" in markdown
    assert "passes_replay_audit_with_warnings_shadow_only" in markdown
    assert "Total estimated cost bps / 1M: `8.0749`" in markdown


def _write_frozen_dfl_source(path: Path, *, live_max_date: str, oos_max_date: str = "2019-12-31") -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "a2118_decision_focused_action_shadow",
                "status": "available",
                "generated_at": f"{live_max_date}T14:45:49",
                "results": [
                    {
                        "label": "live_2024_2026",
                        "bucket": "tuning_window",
                        "recent_decisions": [{"date": live_max_date, "action": "KEEP"}],
                        "non_keep_decisions": [],
                    },
                    {
                        "label": "2019_recovery",
                        "bucket": "out_of_sample",
                        "recent_decisions": [{"date": oos_max_date, "action": "KEEP"}],
                        "non_keep_decisions": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_live_status_dfl_frozen_input_staleness_ok_within_threshold(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dfl = tmp_path / "dfl.json"
    frozen_source = tmp_path / "frozen_source.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {"strategy_id": "a2118_a2111_ncf_late_bull_deleverage", "actual_data_date": "2026-07-09"},
    )
    _write_frozen_dfl_source(frozen_source, live_max_date="2026-07-05")
    dfl.write_text(
        json.dumps(
            {
                "status": "available",
                "action": "KEEP",
                "advisory_active": False,
                "input": str(frozen_source),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_advisory = str(dfl)

    report = _live_status_report(args)
    staleness = report["group_a_plus"]["dfl_frozen_input_staleness"]
    check = [c for c in report["checks"] if c["name"] == "dfl_advisory_frozen_input_staleness"][0]

    assert staleness["status"] == "ok"
    assert staleness["max_live_window_decision_date"] == "2026-07-05"
    assert staleness["calendar_gap_days"] == 4
    assert check["status"] == "ok"
    assert report["overall_status"] == "ok"


def test_live_status_dfl_frozen_input_staleness_warns_past_threshold(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dfl = tmp_path / "dfl.json"
    frozen_source = tmp_path / "frozen_source.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {"strategy_id": "a2118_a2111_ncf_late_bull_deleverage", "actual_data_date": "2026-07-09"},
    )
    # Frozen backtest was generated 2026-06-14 and never re-run -- 25 calendar
    # days behind check_date, well past the default 14-day threshold.
    _write_frozen_dfl_source(frozen_source, live_max_date="2026-06-14")
    dfl.write_text(
        json.dumps(
            {
                "status": "available",
                "action": "KEEP",
                "advisory_active": False,
                "input": str(frozen_source),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_advisory = str(dfl)

    report = _live_status_report(args)
    staleness = report["group_a_plus"]["dfl_frozen_input_staleness"]
    check = [c for c in report["checks"] if c["name"] == "dfl_advisory_frozen_input_staleness"][0]

    assert staleness["calendar_gap_days"] == 25
    assert check["status"] == "warn"
    assert report["overall_status"] == "warn"


def test_live_status_dfl_frozen_input_staleness_not_applicable_when_dfl_unavailable(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {"strategy_id": "a2118_a2111_ncf_late_bull_deleverage", "actual_data_date": "2026-07-09"},
    )

    report = _live_status_report(_args(live_signal, execution_plan))
    check = [c for c in report["checks"] if c["name"] == "dfl_advisory_frozen_input_staleness"][0]

    assert check["status"] == "ok"
    assert report["overall_status"] == "ok"


def test_live_status_includes_dfl_shadow_ensemble(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    ensemble = tmp_path / "ensemble.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    ensemble.write_text(
        json.dumps(
            {
                "report_type": "a2118_dfl_shadow_ensemble",
                "status": "available",
                "policy": "shadow_only_no_auto_weight_change",
                "ensemble_level": "watch",
                "manual_review_required": True,
                "signals": {
                    "base": {"action": "KEEP", "active": False, "reliability_error_percentile": None},
                    "p50": {"action": "KEEP", "active": False, "reliability_error_percentile": None},
                    "p70": {"action": "CAP10", "active": True, "reliability_error_percentile": 0.42},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dfl_shadow_ensemble = str(ensemble)

    report = _live_status_report(args)
    shadow = report["group_a_plus"]["dfl_shadow_ensemble"]

    assert shadow["ensemble_level"] == "watch"
    markdown = _markdown_text(report)
    assert "## A21.18 DFL Shadow Ensemble" in markdown
    assert "Level: `watch`" in markdown
    assert "`p70` action `CAP10` active `True` reliability `0.42`" in markdown


def test_live_status_includes_finstressts_decision_snapshot(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    snapshot = tmp_path / "finstressts_snapshot.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    snapshot.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_finstressts_decision_snapshot",
                "status": "blocked",
                "policy": "research_only_summary_no_weight_change",
                "summary": {
                    "blocked_mechanisms": ["heavy_tailed_shocks"],
                    "reference_loses_to_no_00631l_scenarios": 5,
                    "reference_tail_failure_scenarios": 4,
                    "baseline_best_shadow_candidate": "combined_vol_trend_gate",
                },
                "decision": {
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.finstressts_decision_snapshot = str(snapshot)

    report = _live_status_report(args)
    finstressts = report["group_a_plus"]["finstressts_decision_snapshot"]

    assert finstressts["status"] == "blocked"
    assert finstressts["decision"]["allow_00631l_add"] is False
    markdown = _markdown_text(report)
    assert "## FinStressTS Shadow Snapshot" in markdown
    assert "00631L add: `blocked`" in markdown
    assert "combined_vol_trend_gate" in markdown


def test_live_status_includes_trigate_vol_memory_shadow(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    trigate = tmp_path / "trigate.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    trigate.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_trigate_vol_memory_shadow",
                "policy": "research_only_vol_memory_decomposition_no_weight_change",
                "latest": {
                    "vol_level_percentile_252d": 0.93,
                    "memory_shape_percentile_252d": 0.97,
                    "tempo_percentile_252d": 1.0,
                },
                "tri_gate_state": {
                    "state": "blocked_for_leverage_add",
                    "stress_gate_count": 3,
                    "level_gate_active": True,
                    "shape_gate_active": True,
                    "tempo_gate_active": True,
                },
                "decision": {
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.trigate_vol_memory_shadow = str(trigate)

    report = _live_status_report(args)
    shadow = report["group_a_plus"]["trigate_vol_memory_shadow"]

    assert shadow["tri_gate_state"]["state"] == "blocked_for_leverage_add"
    assert shadow["decision"]["allow_00631l_add"] is False
    markdown = _markdown_text(report)
    assert "## Tri-Gate Volatility Memory Shadow" in markdown
    assert "Stress gate count: `3`" in markdown
    assert "00631L add: `blocked`" in markdown


def test_live_status_includes_research_shadow_decision_snapshot(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    snapshot = tmp_path / "research_shadow.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    snapshot.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_research_shadow_decision_snapshot",
                "status": "blocked",
                "policy": "research_shadow_summary_no_weight_change",
                "summary": {
                    "finstressts_status": "blocked",
                    "trigate_state": "blocked_for_leverage_add",
                    "trigate_stress_gate_count": 3,
                    "dynamic_cvar_status": "blocked",
                    "dynamic_cvar_tail_cost_ready": False,
                    "dynamic_cvar_optimizer_ready": False,
                    "speculative_influence_network_status": "blocked",
                    "speculative_influence_network_ready": False,
                    "sin_lite_proxy_state": "normal",
                    "sin_lite_proxy_score": 0.38,
                    "synthetic_augmentation_status": "blocked",
                    "synthetic_validation_ready": False,
                    "directional_synthetic_alpha_allowed": False,
                    "intervention_fatigue_status": "blocked",
                    "risk_budget_pacing_ready": False,
                    "letf_tracking_status": "blocked",
                    "letf_hedge_neutrality_ready": False,
                    "asian_etf_tail_analytics_status": "blocked",
                    "asian_etf_tail_analytics_ready": False,
                    "llm_state_reward_signed_approval_validation_status": "blocked",
                    "llm_state_reward_signed_approval_record_valid": False,
                    "llm_state_reward_signed_approval_human_exception_approved": False,
                    "llm_state_reward_signed_approval_non_ppo_shadow_queue_review_allowed": False,
                    "llm_state_reward_signed_approval_training_queue_allowed": False,
                    "llm_state_reward_signed_approval_model_training_allowed": False,
                    "llm_state_reward_signed_approval_ppo_training_allowed": False,
                    "llm_state_reward_signed_approval_promote_to_live": False,
                    "llm_state_reward_manual_approval_to_queue_training_allowed": False,
                    "llm_state_reward_manual_approval_queue_blocking_reasons": [
                        "signed_human_exception_approval_record_missing_or_invalid"
                    ],
                },
                "warning_reasons": [
                    "llm_state_reward_signed_approval_validation_blocked",
                    "llm_state_reward_signed_approval_validation_status:blocked",
                    "llm_state_reward_signed_approval_validation:missing_signed_human_exception_approval_record",
                ],
                "decision": {
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.research_shadow_decision_snapshot = str(snapshot)
    checklist = tmp_path / "gift_checklist.json"
    checklist.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_gift_signed_approval_checklist_review",
                "status": "manual_completion_pending",
                "summary": {
                    "manual_completion_ready": True,
                    "manual_completion_pending": True,
                    "signed_record_exists": False,
                },
                "decision": {"checklist_available_for_manual_completion": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    smoke = tmp_path / "gift_smoke.json"
    smoke.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_gift_signed_approval_validator_smoke",
                "status": "passed",
                "summary": {
                    "valid_non_ppo_shadow_record_accepted": True,
                    "invalid_allow_00631l_add_blocked": True,
                    "invalid_allow_model_training_command_blocked": True,
                    "formal_signed_record_written": False,
                },
                "decision": {"validator_smoke_passed": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args.gift_signed_approval_checklist_review = str(checklist)
    args.gift_signed_approval_validator_smoke = str(smoke)

    report = _live_status_report(args)
    research_shadow = report["group_a_plus"]["research_shadow_decision_snapshot"]
    gift_governance = report["group_a_plus"]["gift_signed_approval_governance"]

    assert research_shadow["status"] == "blocked"
    assert research_shadow["decision"]["allow_00631l_add"] is False
    assert gift_governance["validation_status"] == "blocked"
    assert gift_governance["signed_approval_record_valid"] is False
    assert gift_governance["human_exception_approved"] is False
    assert gift_governance["non_ppo_shadow_queue_review_allowed"] is False
    assert gift_governance["manual_approval_to_queue_training_allowed"] is False
    assert gift_governance["training_queue_allowed"] is False
    assert gift_governance["model_training_allowed"] is False
    assert gift_governance["ppo_training_allowed"] is False
    assert gift_governance["promote_to_live"] is False
    assert gift_governance["training_queue_blocking_reasons"] == [
        "signed_human_exception_approval_record_missing_or_invalid"
    ]
    assert gift_governance["checklist_status"] == "manual_completion_pending"
    assert gift_governance["checklist_manual_completion_ready"] is True
    assert gift_governance["checklist_manual_completion_pending"] is True
    assert gift_governance["checklist_signed_record_exists"] is False
    assert gift_governance["validator_smoke_status"] == "passed"
    assert gift_governance["validator_smoke_passed"] is True
    assert gift_governance["validator_smoke_blocks_00631l_add"] is True
    assert gift_governance["validator_smoke_blocks_model_training"] is True
    assert gift_governance["formal_signed_record_written_by_smoke"] is False
    assert gift_governance["signed_approval_warnings"] == [
        "llm_state_reward_signed_approval_validation_blocked",
        "llm_state_reward_signed_approval_validation_status:blocked",
        "llm_state_reward_signed_approval_validation:missing_signed_human_exception_approval_record",
    ]
    markdown = _markdown_text(report)
    assert "## Research Shadow Decision Snapshot" in markdown
    assert "Tri-gate state: `blocked_for_leverage_add`" in markdown
    assert "Dynamic CVaR status: `blocked`" in markdown
    assert "Dynamic CVaR tail/cost ready: `False`" in markdown
    assert "Dynamic CVaR optimizer ready: `False`" in markdown
    assert "Speculative influence status: `blocked`" in markdown
    assert "Speculative influence ready: `False`" in markdown
    assert "SIN-lite state: `normal`" in markdown
    assert "SIN-lite score: `0.38`" in markdown
    assert "Synthetic augmentation status: `blocked`" in markdown
    assert "Synthetic validation ready: `False`" in markdown
    assert "Directional synthetic alpha: `False`" in markdown
    assert "Intervention fatigue status: `blocked`" in markdown
    assert "Risk-budget pacing ready: `False`" in markdown
    assert "LETF tracking status: `blocked`" in markdown
    assert "Asian ETF tail analytics status: `blocked`" in markdown
    assert "Asian ETF tail analytics ready: `False`" in markdown
    assert "LETF hedge neutrality ready: `False`" in markdown
    assert "GIFT signed approval validation: `blocked`" in markdown
    assert "GIFT signed approval record valid: `False`" in markdown
    assert "GIFT human exception approved: `False`" in markdown
    assert "GIFT non-PPO shadow queue review allowed: `False`" in markdown
    assert "GIFT manual approval queue allowed: `False`" in markdown
    assert "GIFT training queue blockers: `['signed_human_exception_approval_record_missing_or_invalid']`" in markdown
    assert "GIFT checklist status: `manual_completion_pending`" in markdown
    assert "GIFT validator smoke status: `passed`" in markdown
    assert "## GIFT Signed Approval Governance" in markdown
    assert "Validation status: `blocked`" in markdown
    assert "Signed approval record valid: `False`" in markdown
    assert "Queue blockers: `['signed_human_exception_approval_record_missing_or_invalid']`" in markdown
    assert "Checklist manual completion ready: `True`" in markdown
    assert "Checklist signed record exists: `False`" in markdown
    assert "Validator smoke passed: `True`" in markdown
    assert "Validator blocks 00631L add: `True`" in markdown
    assert "Validator blocks model training: `True`" in markdown
    assert "Smoke wrote formal signed record: `False`" in markdown
    assert "missing_signed_human_exception_approval_record" in markdown
    assert "00631L add: `blocked`" in markdown


def test_live_status_includes_systemic_bubble_time_at_risk_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    systemic = tmp_path / "systemic_bubble.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    systemic.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_systemic_bubble_time_at_risk_review",
                "policy": "research_only_systemic_bubble_time_at_risk_no_weight_change",
                "latest": {
                    "2330_0050_corr_60d": 0.8733,
                    "etf_coupling_score": 0.944,
                },
                "states": {
                    "overall_state": "blocked_for_leverage_add",
                    "systemic_score": 2,
                    "time_at_risk_state": "elevated",
                    "etf_coupling_state": "watch",
                    "reflexivity_proxy_state": "elevated",
                },
                "decision": {
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.systemic_bubble_time_at_risk_review = str(systemic)

    report = _live_status_report(args)
    review = report["group_a_plus"]["systemic_bubble_time_at_risk_review"]

    assert review["states"]["overall_state"] == "blocked_for_leverage_add"
    assert review["decision"]["allow_00631l_add"] is False
    assert report["source_paths"]["systemic_bubble_time_at_risk_review"] == str(systemic)
    markdown = _markdown_text(report)
    assert "## Systemic Bubble Time-At-Risk Review" in markdown
    assert "Systemic score: `2`" in markdown
    assert "2330/0050 corr 60d: `0.8733`" in markdown


def test_live_status_includes_illiquidity_network_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    illiquidity = tmp_path / "illiquidity.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(execution_plan, {})
    illiquidity.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_illiquidity_network_readiness_review",
                "policy": "research_only_illiquidity_network_readiness_no_crash_guard_no_weight_change",
                "status": "blocked",
                "actual_data_end": "2026-07-17",
                "data": {"ohlcv_summary": {"distinct_tickers": 9, "rows": 1000}},
                "daily_ohlcv_liquidity_stress_proxy": {
                    "status": "available_research_proxy",
                    "paper_equivalent": False,
                    "stress_score": 0.2167,
                    "stress_state": "elevated",
                    "manual_review_required": True,
                    "coverage_tickers": 9,
                    "component_counts": {
                        "volume_drought": 0,
                        "range_spike": 3,
                        "negative_return": 4,
                        "limit_down_proxy": 1,
                    },
                },
                "blocking_reasons": ["missing_high_frequency_bid_ask"],
                "decision": {
                    "illiquidity_network_ready": False,
                    "crash_guard_allowed": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.illiquidity_network_readiness_review = str(illiquidity)

    report = _live_status_report(args)
    review = report["group_a_plus"]["illiquidity_network_readiness_review"]

    assert review["status"] == "blocked"
    assert review["decision"]["crash_guard_allowed"] is False
    assert report["source_paths"]["illiquidity_network_readiness_review"] == str(illiquidity)
    markdown = _markdown_text(report)
    assert "## Illiquidity Network Readiness" in markdown
    assert "Illiquidity network ready: `False`" in markdown
    assert "Crash guard allowed: `False`" in markdown
    assert "Daily OHLCV proxy: `available_research_proxy` paper-equivalent `False`" in markdown
    assert "Daily OHLCV proxy state: `elevated` manual-review `True`" in markdown
    assert "Daily OHLCV proxy score: `0.2167` coverage `9`" in markdown
    assert "Proxy components volume/range/negative/limit: `0` / `3` / `4` / `1`" in markdown


def test_live_status_includes_speculative_influence_network_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    speculative = tmp_path / "speculative.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(execution_plan, {})
    speculative.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_speculative_influence_network_readiness_review",
                "policy": "research_only_speculative_influence_network_readiness_no_weight_change",
                "status": "blocked",
                "actual_data_end": "2026-07-17",
                "data": {
                    "ohlcv_summary": {"distinct_tickers": 15, "rows": 29641},
                    "broad_universe_min_tickers": 50,
                    "broad_universe_ready": False,
                },
                "blocking_reasons": ["broad_stock_universe_insufficient_for_sin"],
                "decision": {
                    "speculative_influence_network_ready": False,
                    "hmm_bubble_state_ready": False,
                    "transfer_entropy_network_ready": False,
                    "maxloss_validation_ready": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.speculative_influence_network_readiness_review = str(speculative)

    report = _live_status_report(args)
    review = report["group_a_plus"]["speculative_influence_network_readiness_review"]

    assert review["status"] == "blocked"
    assert report["source_paths"]["speculative_influence_network_readiness_review"] == str(speculative)
    markdown = _markdown_text(report)
    assert "## Speculative Influence Network Readiness" in markdown
    assert "SIN ready: `False`" in markdown
    assert "HMM bubble state ready: `False`" in markdown
    assert "Transfer entropy network ready: `False`" in markdown
    assert "Max-loss validation ready: `False`" in markdown
    assert "OHLCV tickers / minimum: `15` / `50`" in markdown
    assert "Broad universe ready: `False`" in markdown


def test_live_status_includes_sin_lite_proxy(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    sin_lite = tmp_path / "sin_lite.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(execution_plan, {})
    sin_lite.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_sin_lite_proxy",
                "policy": "research_only_sin_lite_proxy_no_weight_change",
                "status": "blocked",
                "actual_data_end": "2026-07-17",
                "coverage": {"usable_ticker_count": 14},
                "latest": {
                    "state": "normal",
                    "sin_lite_score": 0.380094,
                    "manual_review_required": False,
                    "components": {
                        "correlation_density": 0.42,
                        "edge_density": 0.10,
                        "downside_comovement": 0.55,
                        "influence_concentration": 0.31,
                        "tsmc_lead_risk": 0.12,
                    },
                },
                "blocking_reasons": ["sin_lite_proxy_not_validated_for_live_weight_change"],
                "decision": {"allow_00631l_add": False, "allow_00632r_open": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.sin_lite_proxy = str(sin_lite)

    report = _live_status_report(args)
    proxy = report["group_a_plus"]["sin_lite_proxy"]

    assert proxy["latest"]["state"] == "normal"
    assert report["source_paths"]["sin_lite_proxy"] == str(sin_lite)
    markdown = _markdown_text(report)
    assert "## SIN-Lite Proxy" in markdown
    assert "State: `normal`" in markdown
    assert "SIN-lite score: `0.380094`" in markdown
    assert "Usable tickers: `14`" in markdown
    assert "00631L add: `blocked`" in markdown


def test_live_status_includes_hmm_wj_synthetic_scenario_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    hmm_wj = tmp_path / "hmm_wj.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    hmm_wj.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_hmm_wj_synthetic_scenario_readiness_review",
                "policy": "research_only_hmm_wj_readiness_no_synthetic_alpha_no_weight_change",
                "status": "blocked",
                "data_readiness": {"all_required_tickers_ready": True},
                "validation_readiness": {
                    "generator_implemented": False,
                    "taiwan_etf_walkforward_validated": False,
                },
                "blocking_reasons": [
                    "hmm_wj_generator_not_implemented",
                    "taiwan_etf_walkforward_validation_missing",
                ],
                "decision": {
                    "can_generate_scenarios_for_decision": False,
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.hmm_wj_synthetic_scenario_readiness_review = str(hmm_wj)

    report = _live_status_report(args)
    review = report["group_a_plus"]["hmm_wj_synthetic_scenario_readiness_review"]

    assert review["status"] == "blocked"
    assert review["data_readiness"]["all_required_tickers_ready"] is True
    assert review["decision"]["can_generate_scenarios_for_decision"] is False
    assert report["source_paths"]["hmm_wj_synthetic_scenario_readiness_review"] == str(hmm_wj)
    markdown = _markdown_text(report)
    assert "## HMM-WJ Synthetic Scenario Readiness" in markdown
    assert "Data ready: `True`" in markdown
    assert "Can generate scenarios for decision: `False`" in markdown


def test_live_status_includes_dynamic_cvar_tail_cost_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    dynamic_cvar = tmp_path / "dynamic_cvar.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    dynamic_cvar.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_dynamic_cvar_tail_cost_readiness_review",
                "policy": "research_only_dynamic_cvar_tail_cost_readiness_no_optimizer_no_weight_change",
                "status": "blocked",
                "component_readiness": {
                    "cvar_tail_risk": {
                        "00631l_hill_xi_95": 0.3263,
                        "00631l_pot_gpd_shape_xi_95": 0.1595,
                    },
                    "market_impact": {"turnover": 0.5916},
                },
                "blocking_reasons": [
                    "00631l_hill_tail_index_positive_heavy_tail",
                    "dynamic_cvar_optimizer_not_implemented",
                ],
                "decision": {
                    "tail_cost_readiness_ready": False,
                    "dynamic_optimizer_ready": False,
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.dynamic_cvar_tail_cost_readiness_review = str(dynamic_cvar)

    report = _live_status_report(args)
    review = report["group_a_plus"]["dynamic_cvar_tail_cost_readiness_review"]

    assert review["status"] == "blocked"
    assert review["decision"]["tail_cost_readiness_ready"] is False
    assert review["decision"]["dynamic_optimizer_ready"] is False
    assert report["source_paths"]["dynamic_cvar_tail_cost_readiness_review"] == str(dynamic_cvar)
    markdown = _markdown_text(report)
    assert "## Dynamic CVaR Tail/Cost Readiness" in markdown
    assert "Tail/cost ready: `False`" in markdown
    assert "00631L Hill xi 95: `0.3263`" in markdown
    assert "Turnover: `0.5916`" in markdown


def test_live_status_includes_synthetic_augmentation_validation_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    synthetic = tmp_path / "synthetic_augmentation.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    synthetic.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_synthetic_augmentation_validation_readiness_review",
                "policy": "research_only_synthetic_augmentation_validation_no_synthetic_alpha_no_weight_change",
                "status": "blocked",
                "validation_readiness": {
                    "size_matched_null_augmentation_implemented": False,
                    "block_permutation_test_implemented": False,
                    "walk_forward_oos_synthetic_validation_passed": False,
                    "directional_audit_passed": False,
                    "rare_regime_audit_passed": True,
                },
                "blocking_reasons": [
                    "size_matched_null_augmentation_missing",
                    "block_permutation_test_missing",
                ],
                "decision": {
                    "synthetic_validation_ready": False,
                    "directional_synthetic_alpha_allowed": False,
                    "synthetic_generator_promotion_allowed": False,
                    "allow_00631l_add": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.synthetic_augmentation_validation_readiness_review = str(synthetic)

    report = _live_status_report(args)
    review = report["group_a_plus"]["synthetic_augmentation_validation_readiness_review"]

    assert review["status"] == "blocked"
    assert review["decision"]["synthetic_validation_ready"] is False
    assert review["decision"]["directional_synthetic_alpha_allowed"] is False
    assert report["source_paths"]["synthetic_augmentation_validation_readiness_review"] == str(synthetic)
    markdown = _markdown_text(report)
    assert "## Synthetic Augmentation Validation Readiness" in markdown
    assert "Synthetic validation ready: `False`" in markdown
    assert "Directional synthetic alpha: `blocked`" in markdown
    assert "Size-matched null: `False`" in markdown
    assert "Directional audit passed: `False`" in markdown
    assert "Rare-regime audit passed: `True`" in markdown


def test_live_status_includes_intervention_fatigue_risk_budget_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    intervention = tmp_path / "intervention_fatigue.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(
        execution_plan,
        {
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "actual_data_date": "2026-07-09",
        },
    )
    intervention.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_intervention_fatigue_risk_budget_readiness_review",
                "policy": "research_only_intervention_fatigue_risk_budget_pacing_no_weight_change",
                "status": "blocked",
                "intervention_fatigue": {
                    "trade_count_nonzero": 1,
                    "leverage_change_count": 0,
                    "hedge_change_count": 0,
                    "normalized_history_available": True,
                    "history_entry_count": 40,
                    "history_blocked_entry_count": 21,
                    "history_leverage_intervention_count": 31,
                    "history_hedge_intervention_count": 0,
                },
                "broker_holdings_time_series": {
                    "status": "sample_available",
                    "authoritative_broker_export": False,
                    "transaction_count": 276,
                    "snapshot_count": 170,
                    "negative_position_count": 7,
                },
                "broker_holdings_reconciliation": {
                    "status": "blocked",
                    "matched_confirmed_count": 1,
                    "mismatched_confirmed_count": 1,
                    "can_generate_live_orders": False,
                },
                "risk_budget_pacing": {"turnover": 0.5006477801878955},
                "blocking_reasons": [
                    "intervention_history_not_normalized",
                    "turnover_at_or_above_pacing_limit",
                ],
                "decision": {
                    "intervention_fatigue_ready": False,
                    "risk_budget_pacing_ready": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                    "target_weight_change_allowed": False,
                    "auto_rebalance_allowed": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.intervention_fatigue_risk_budget_readiness_review = str(intervention)

    report = _live_status_report(args)
    review = report["group_a_plus"]["intervention_fatigue_risk_budget_readiness_review"]

    assert review["status"] == "blocked"
    assert review["decision"]["intervention_fatigue_ready"] is False
    assert review["decision"]["risk_budget_pacing_ready"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert report["source_paths"]["intervention_fatigue_risk_budget_readiness_review"] == str(intervention)
    markdown = _markdown_text(report)
    assert "## Intervention Fatigue / Risk-Budget Readiness" in markdown
    assert "00631L add: `blocked`" in markdown
    assert "00632R open: `blocked`" in markdown
    assert "Intervention fatigue ready: `False`" in markdown
    assert "Risk-budget pacing ready: `False`" in markdown
    assert "Nonzero trade count: `1`" in markdown
    assert "Leverage / hedge change count: `0` / `0`" in markdown
    assert "Normalized history available: `True`" in markdown
    assert "History entries / blocked: `40` / `21`" in markdown
    assert "History leverage / hedge interventions: `31` / `0`" in markdown
    assert "Broker holdings status: `sample_available` authoritative `False`" in markdown
    assert "Broker transactions / snapshots: `276` / `170`" in markdown
    assert "Broker negative positions: `7`" in markdown
    assert "Broker reconciliation status: `blocked`" in markdown
    assert "Confirmed matched / mismatched: `1` / `1`" in markdown
    assert "Can generate live orders: `False`" in markdown
    assert "Turnover: `0.5006477801878955`" in markdown


def test_live_status_includes_letf_tracking_error_effective_fee_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    letf = tmp_path / "letf_tracking.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(execution_plan, {})
    letf.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_letf_tracking_error_effective_fee_readiness_review",
                "policy": "research_only_letf_tracking_error_effective_fee_no_pair_trade_no_weight_change",
                "status": "blocked",
                "actual_data_end": "2026-07-17",
                "tracking_error_summary": {
                    "00631L.TW": {
                        "horizon_metrics": {"30": {"tracking_error": {"mean": -0.012, "latest": -0.004}}}
                    },
                    "00632R.TW": {
                        "horizon_metrics": {"30": {"tracking_error": {"mean": -0.006, "latest": -0.003}}}
                    },
                },
                "hedge_neutrality": {"00632R.TW": {"realized_beta": -0.91, "correlation": -0.98}},
                "blocking_reasons": [
                    "research_only_letf_tracking_error_review",
                    "00632r_hedge_neutrality_not_promoted",
                ],
                "decision": {
                    "tracking_error_readiness_ready": False,
                    "realized_effective_fee_proxy_ready": False,
                    "hedge_neutrality_ready": False,
                    "allow_00631l_add": False,
                    "allow_00632r_open": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.letf_tracking_error_effective_fee_readiness_review = str(letf)

    report = _live_status_report(args)
    review = report["group_a_plus"]["letf_tracking_error_effective_fee_readiness_review"]

    assert review["status"] == "blocked"
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert report["source_paths"]["letf_tracking_error_effective_fee_readiness_review"] == str(letf)
    markdown = _markdown_text(report)
    assert "## LETF Tracking Error / Effective Fee Readiness" in markdown
    assert "00631L add: `blocked`" in markdown
    assert "00632R open: `blocked`" in markdown
    assert "00632R hedge beta/corr: `-0.91` / `-0.98`" in markdown


def test_live_status_includes_asian_etf_tail_analytics_readiness_review(tmp_path: Path) -> None:
    live_signal = tmp_path / "live_signal.json"
    execution_plan = tmp_path / "execution_plan.json"
    asian = tmp_path / "asian_etf_tail.json"
    _write_standard(live_signal, _live_signal_data())
    _write_standard(execution_plan, {})
    asian.write_text(
        json.dumps(
            {
                "report_type": "group_a_plus_asian_etf_tail_analytics_readiness_review",
                "policy": "research_only_asian_etf_tail_analytics_no_optimizer_no_weight_change",
                "status": "blocked",
                "data_readiness": {
                    "paper_etf_coverage": {
                        "paper_etf_count": 29,
                        "available_paper_etf_count": 1,
                        "available_paper_etfs": ["EWT"],
                    }
                },
                "component_readiness": {
                    "cvar_tail_risk": {
                        "golden1_starr_95": 14.56,
                        "golden1_rachev_95_95": 1.03,
                        "00631l_rachev_95_95": 0.95,
                        "00631l_hill_xi_95": 0.36,
                    }
                },
                "tail_reward_risk_monitor": {
                    "status": "available",
                    "tier": "defensive_preference",
                    "golden1_rachev_95_95": 1.03,
                    "00631l_rachev_95_95": 0.95,
                    "golden1_beats_00631l_by_rachev": True,
                    "00631l_rachev_below_one": True,
                },
                "blocking_reasons": ["asian_29_etf_universe_not_available"],
                "decision": {
                    "tail_analytics_ready": False,
                    "optimizer_ready": False,
                    "allow_00631l_add": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = _args(live_signal, execution_plan)
    args.asian_etf_tail_analytics_readiness_review = str(asian)

    report = _live_status_report(args)
    review = report["group_a_plus"]["asian_etf_tail_analytics_readiness_review"]

    assert review["status"] == "blocked"
    assert review["decision"]["allow_00631l_add"] is False
    assert report["source_paths"]["asian_etf_tail_analytics_readiness_review"] == str(asian)
    markdown = _markdown_text(report)
    assert "## Asian ETF Tail Analytics Readiness" in markdown
    assert "Paper ETF coverage: `1` / `29`" in markdown
    assert "Available paper ETFs: `['EWT']`" in markdown
    assert "Golden1 STARR 95: `14.56`" in markdown
    assert "Golden1 Rachev 95/95: `1.03`" in markdown
    assert "00631L Rachev 95/95: `0.95`" in markdown
    assert "Tail reward/risk tier: `defensive_preference`" in markdown
