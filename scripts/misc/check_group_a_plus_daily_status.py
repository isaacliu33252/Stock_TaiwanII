#!/usr/bin/env python3
"""Daily status check for the active GroupA+ baseline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"
sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus_report_manager import GroupAPlusReportManager


def _load(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return json.loads(candidate.read_text(encoding="utf-8"))


def _load_optional(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _unwrap_standard_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _latest_compounding_regime_path() -> Path | None:
    matches = sorted(
        (PROJECT_ROOT / "results").glob("00631l_leveraged_compounding_regime_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _latest_promotion_gate_path() -> Path | None:
    matches = sorted(
        (PROJECT_ROOT / "results").glob("group_a_plus_promotion_gate_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _load_promotion_gate_summary(path: str | Path | None) -> dict[str, Any]:
    candidate: Path | None
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
    else:
        candidate = _latest_promotion_gate_path()
    if candidate is None or not candidate.exists():
        return {}
    payload = _load(candidate)
    summary_context = (
        (payload.get("governance_context") or {}).get("deployment_summary")
        if isinstance(payload.get("governance_context"), dict)
        else {}
    )
    consistency = (
        summary_context.get("consistency_review")
        if isinstance(summary_context, dict) and isinstance(summary_context.get("consistency_review"), dict)
        else {}
    )
    summary_gate = (
        payload.get("deployment_summary_gate")
        if isinstance(payload.get("deployment_summary_gate"), dict)
        else {}
    )
    return {
        "status": "available",
        "source_path": str(candidate),
        "decision": payload.get("decision"),
        "blocking_gates": payload.get("blocking_gates") or [],
        "deployment_summary_gate_status": summary_gate.get("status"),
        "deployment_summary_gate_reason": summary_gate.get("reason"),
        "deployment_summary_gate_blocking_reasons": summary_gate.get("blocking_reasons") or [],
        "deployment_summary_consistency_status": (
            summary_context.get("consistency_review_status")
            if isinstance(summary_context, dict)
            else consistency.get("status")
        ),
        "deployment_summary_consistency_errors": (
            summary_context.get("consistency_review_errors")
            if isinstance(summary_context, dict)
            else consistency.get("errors") or []
        )
        or [],
    }


def _load_compounding_regime(path: str | Path | None) -> dict[str, Any]:
    candidate: Path | None
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
    else:
        candidate = _latest_compounding_regime_path()
    if candidate is None or not candidate.exists():
        return {"status": "unavailable", "reason": "compounding_regime_report_missing"}
    payload = _load(candidate)
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else {}
    regime = latest.get("compounding_regime")
    return {
        "status": "ok" if regime else "unavailable",
        "source_path": str(candidate),
        "report_type": payload.get("report_type"),
        "generated_at": payload.get("generated_at"),
        "date": latest.get("date"),
        "compounding_regime": regime,
        "recommended_policy": latest.get("recommended_policy"),
        "trend_score": latest.get("trend_score"),
        "mean_reversion_score": latest.get("mean_reversion_score"),
        "features": {
            "rolling_AR1_5d": latest.get("rolling_AR1_5d"),
            "rolling_AR1_20d": latest.get("rolling_AR1_20d"),
            "variance_ratio": latest.get("variance_ratio"),
            "trend_persistence": latest.get("trend_persistence"),
            "reversal_speed": latest.get("reversal_speed"),
            "positive_return_streak": latest.get("positive_return_streak"),
            "negative_return_streak": latest.get("negative_return_streak"),
            "drawdown_recovery_ratio": latest.get("drawdown_recovery_ratio"),
            "00631L_vs_0050_relative_momentum": latest.get("00631L_vs_0050_relative_momentum"),
        },
        "regime_policy": payload.get("regime_policy"),
        "active_allocation_impact": payload.get("active_allocation_impact", "none"),
    }


def _dfl_frozen_input_staleness(dfl_advisory: dict[str, Any] | None, check_date: str) -> dict[str, Any]:
    """Fable audit (2026-07-16, combination opportunities #2): dfl_advisory
    only ever matches decisions whose date equals today's live-signal date
    against a fixed backtest file (see build_a2118_dfl_advisory.py) that is
    never re-run. Once the file's own live-window coverage falls behind
    check_date, matched_decision_count is structurally guaranteed to be 0
    forever -- the advisory step keeps "running" but can never again report
    a non-KEEP action. This surfaces that gap instead of letting it look
    like ordinary sparse-output KEEP behavior.
    """
    if not dfl_advisory or dfl_advisory.get("status") != "available":
        return {"status": "not_applicable", "detail": "dfl_advisory unavailable"}
    input_path_raw = dfl_advisory.get("input")
    if not input_path_raw:
        return {"status": "not_applicable", "detail": "dfl_advisory has no input path"}
    input_path = Path(input_path_raw)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not input_path.exists():
        return {"status": "unavailable", "detail": f"frozen input missing: {input_path}"}
    try:
        source = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "detail": f"failed to read frozen input: {exc}"}

    live_dates: list[str] = []
    for window in source.get("results") or []:
        if not isinstance(window, dict) or window.get("bucket") == "out_of_sample":
            continue
        for row in window.get("recent_decisions") or []:
            if isinstance(row, dict) and row.get("date"):
                live_dates.append(str(row["date"]))

    if not live_dates:
        return {"status": "unavailable", "detail": "frozen input has no tuning-window decisions"}

    max_live_date = max(live_dates)
    calendar_gap = int((pd.Timestamp(check_date).normalize() - pd.Timestamp(max_live_date).normalize()).days)
    return {
        "status": "ok",
        "frozen_input_path": str(input_path),
        "frozen_input_generated_at": source.get("generated_at"),
        "max_live_window_decision_date": max_live_date,
        "calendar_gap_days": calendar_gap,
    }


def _business_days_between(start: str, end: str) -> int:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts <= start_ts:
        return 0
    return int(len(pd.bdate_range(start_ts + pd.Timedelta(days=1), end_ts)))


def _status(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "block"
    if warn:
        return "warn"
    return "ok"


def _gift_signed_approval_governance(
    research_shadow_snapshot: dict[str, Any] | None,
    checklist_review: dict[str, Any] | None = None,
    validator_smoke: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(research_shadow_snapshot, dict) or not research_shadow_snapshot:
        summary = {}
        signed_warnings: list[str] = []
    else:
        summary = (
            research_shadow_snapshot.get("summary")
            if isinstance(research_shadow_snapshot.get("summary"), dict)
            else {}
        )
        signed_warnings = [
            reason
            for reason in research_shadow_snapshot.get("warning_reasons") or []
            if isinstance(reason, str) and "signed_approval" in reason
        ]
    checklist_summary = (
        checklist_review.get("summary")
        if isinstance(checklist_review, dict) and isinstance(checklist_review.get("summary"), dict)
        else {}
    )
    checklist_decision = (
        checklist_review.get("decision")
        if isinstance(checklist_review, dict) and isinstance(checklist_review.get("decision"), dict)
        else {}
    )
    smoke_summary = (
        validator_smoke.get("summary")
        if isinstance(validator_smoke, dict) and isinstance(validator_smoke.get("summary"), dict)
        else {}
    )
    smoke_decision = (
        validator_smoke.get("decision")
        if isinstance(validator_smoke, dict) and isinstance(validator_smoke.get("decision"), dict)
        else {}
    )
    if not summary and not checklist_summary and not smoke_summary:
        return {}
    return {
        "source": "research_shadow_decision_snapshot",
        "validation_status": summary.get("llm_state_reward_signed_approval_validation_status"),
        "signed_approval_record_valid": summary.get("llm_state_reward_signed_approval_record_valid"),
        "human_exception_approved": summary.get("llm_state_reward_signed_approval_human_exception_approved"),
        "non_ppo_shadow_queue_review_allowed": summary.get(
            "llm_state_reward_signed_approval_non_ppo_shadow_queue_review_allowed"
        ),
        "training_queue_allowed": summary.get("llm_state_reward_signed_approval_training_queue_allowed"),
        "model_training_allowed": summary.get("llm_state_reward_signed_approval_model_training_allowed"),
        "ppo_training_allowed": summary.get("llm_state_reward_signed_approval_ppo_training_allowed"),
        "promote_to_live": summary.get("llm_state_reward_signed_approval_promote_to_live"),
        "manual_approval_to_queue_training_allowed": summary.get(
            "llm_state_reward_manual_approval_to_queue_training_allowed"
        ),
        "training_queue_blocking_reasons": summary.get(
            "llm_state_reward_manual_approval_queue_blocking_reasons"
        )
        or [],
        "signed_approval_warnings": signed_warnings,
        "checklist_status": checklist_review.get("status") if isinstance(checklist_review, dict) else None,
        "checklist_available_for_manual_completion": checklist_decision.get(
            "checklist_available_for_manual_completion"
        ),
        "checklist_manual_completion_ready": checklist_summary.get("manual_completion_ready"),
        "checklist_manual_completion_pending": checklist_summary.get("manual_completion_pending"),
        "checklist_signed_record_exists": checklist_summary.get("signed_record_exists"),
        "validator_smoke_status": validator_smoke.get("status") if isinstance(validator_smoke, dict) else None,
        "validator_smoke_passed": smoke_decision.get("validator_smoke_passed"),
        "validator_smoke_valid_record_accepted": smoke_summary.get("valid_non_ppo_shadow_record_accepted"),
        "validator_smoke_blocks_00631l_add": smoke_summary.get("invalid_allow_00631l_add_blocked"),
        "validator_smoke_blocks_model_training": smoke_summary.get(
            "invalid_allow_model_training_command_blocked"
        ),
        "formal_signed_record_written_by_smoke": smoke_summary.get("formal_signed_record_written"),
    }


def _execution_plan_cash_summary(execution_plan: dict[str, Any] | None, *, aligned: bool) -> dict[str, Any]:
    if not aligned or not isinstance(execution_plan, dict) or not execution_plan:
        return {
            "available": False,
            "aligned": bool(aligned),
            "current_cash_input": None,
            "cash_assumption": None,
            "nonzero_trade_count": None,
        }
    trades = [row for row in execution_plan.get("trades") or [] if isinstance(row, dict)]
    nonzero_trade_count = sum(1 for row in trades if int(row.get("delta_shares") or 0) != 0)
    return {
        "available": True,
        "aligned": True,
        "current_cash_input": execution_plan.get("current_cash_input"),
        "cash_assumption": execution_plan.get("cash_assumption"),
        "nonzero_trade_count": nonzero_trade_count,
        "execution_allowed": execution_plan.get("execution_allowed"),
        "manual_confirmation_required": execution_plan.get("manual_confirmation_required"),
    }


def _markdown_text(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Daily Status",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Check date: `{report['check_date']}`",
        f"Status stage: `{report.get('status_stage')}`",
        f"Overall: `{report['overall_status']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['name']} | `{check['status']}` | {check['detail']} |")
    lines.extend(
        [
            "",
            "## Signal",
            "",
            f"- Group A status: `{report['signal']['signal_status']}`",
            f"- Reason: `{report['signal']['signal_reason']}`",
            f"- Actual data date: `{report['signal']['actual_data_date']}`",
            f"- Business stale days: `{report['signal']['business_stale_days']}`",
            f"- Calendar stale days: `{report['signal']['calendar_stale_days']}`",
            "",
            "## GroupA+",
            "",
            f"- Profile: `{report['profile']}`",
            f"- Overlay regime: `{report['group_a_plus']['overlay_regime']}`",
            f"- 00679B target weight: `{report['group_a_plus']['overlay_00679b_weight']:.2%}`",
            f"- Cash after cost: `{report['group_a_plus']['cash_after_cost']:,.0f}`",
        ]
    )
    execution_plan_cash = report["group_a_plus"].get("execution_plan_cash") or {}
    if execution_plan_cash:
        lines.extend(
            [
                f"- Execution plan cash input: `{execution_plan_cash.get('current_cash_input')}`",
                f"- Execution plan cash assumption: `{execution_plan_cash.get('cash_assumption')}`",
                f"- Execution plan nonzero trades: `{execution_plan_cash.get('nonzero_trade_count')}`",
            ]
        )
    pre_trade_guard = report["group_a_plus"].get("pre_trade_guard") or {}
    compounding_guard = report["group_a_plus"].get("compounding_regime_pre_trade_guard") or {}
    dfl_advisory = report["group_a_plus"].get("dfl_advisory") or {}
    dfl_shadow_ensemble = report["group_a_plus"].get("dfl_shadow_ensemble") or {}
    dfl_active_date_audit = report["group_a_plus"].get("dfl_active_date_audit") or {}
    finstressts_snapshot = report["group_a_plus"].get("finstressts_decision_snapshot") or {}
    trigate_vol_memory = report["group_a_plus"].get("trigate_vol_memory_shadow") or {}
    systemic_bubble_review = report["group_a_plus"].get("systemic_bubble_time_at_risk_review") or {}
    illiquidity_network_readiness = report["group_a_plus"].get("illiquidity_network_readiness_review") or {}
    speculative_influence_readiness = (
        report["group_a_plus"].get("speculative_influence_network_readiness_review") or {}
    )
    sin_lite_proxy = report["group_a_plus"].get("sin_lite_proxy") or {}
    hmm_wj_readiness = report["group_a_plus"].get("hmm_wj_synthetic_scenario_readiness_review") or {}
    dynamic_cvar_readiness = report["group_a_plus"].get("dynamic_cvar_tail_cost_readiness_review") or {}
    synthetic_augmentation_readiness = (
        report["group_a_plus"].get("synthetic_augmentation_validation_readiness_review") or {}
    )
    intervention_fatigue_readiness = (
        report["group_a_plus"].get("intervention_fatigue_risk_budget_readiness_review") or {}
    )
    letf_tracking_readiness = (
        report["group_a_plus"].get("letf_tracking_error_effective_fee_readiness_review") or {}
    )
    asian_etf_tail_analytics_readiness = (
        report["group_a_plus"].get("asian_etf_tail_analytics_readiness_review") or {}
    )
    research_shadow_snapshot = report["group_a_plus"].get("research_shadow_decision_snapshot") or {}
    gift_signed_approval_governance = report["group_a_plus"].get("gift_signed_approval_governance") or {}
    promotion_gate = report["group_a_plus"].get("promotion_gate") or {}
    if promotion_gate:
        lines.extend(
            [
                "",
                "## Promotion Gate",
                "",
                f"- Decision: `{promotion_gate.get('decision')}`",
                f"- Blocking gates: `{promotion_gate.get('blocking_gates')}`",
                f"- Deployment summary gate: `{promotion_gate.get('deployment_summary_gate_status')}`",
                f"- Deployment summary consistency: `{promotion_gate.get('deployment_summary_consistency_status')}`",
                f"- Deployment summary blockers: `{promotion_gate.get('deployment_summary_gate_blocking_reasons')}`",
            ]
        )
    if pre_trade_guard:
        lines.extend(
            [
                "",
                "## Pre-Trade Guard",
                "",
                f"- Status: `{pre_trade_guard.get('status')}`",
                f"- 00631L add: `{'allowed' if pre_trade_guard.get('allow_00631l_add') else 'blocked'}`",
                f"- Policy: `{pre_trade_guard.get('policy')}`",
            ]
        )
        for blocked in pre_trade_guard.get("blocked_trades", []) or []:
            if not isinstance(blocked, dict):
                continue
            lines.append(
                "- Blocked: `{ticker}` `{side}` current `{current}` requested `{requested}` guarded `{guarded}`".format(
                    ticker=blocked.get("ticker"),
                    side=blocked.get("side"),
                    current=blocked.get("current_shares"),
                    requested=blocked.get("requested_target_shares"),
                    guarded=blocked.get("guarded_target_shares"),
                )
            )
    if dfl_shadow_ensemble and dfl_shadow_ensemble.get("status") == "available":
        lines.extend(
            [
                "",
                "## A21.18 DFL Shadow Ensemble",
                "",
                f"- Level: `{dfl_shadow_ensemble.get('ensemble_level')}`",
                f"- Manual review: `{dfl_shadow_ensemble.get('manual_review_required')}`",
                f"- Policy: `{dfl_shadow_ensemble.get('policy')}`",
            ]
        )
        signals = dfl_shadow_ensemble.get("signals") or {}
        for name in ("base", "p50", "p70"):
            signal = signals.get(name) if isinstance(signals.get(name), dict) else {}
            if signal:
                lines.append(
                    "- `{name}` action `{action}` active `{active}` reliability `{reliability}`".format(
                        name=name,
                        action=signal.get("action"),
                        active=signal.get("active"),
                        reliability=signal.get("reliability_error_percentile"),
                    )
                )
    if compounding_guard:
        lines.extend(
            [
                "",
                "## 00631L Compounding Guard",
                "",
                f"- Status: `{compounding_guard.get('status')}`",
                f"- 00631L add: `{'allowed' if compounding_guard.get('allow_00631l_add') else 'blocked'}`",
                f"- Regime: `{compounding_guard.get('compounding_regime')}`",
                f"- Policy: `{compounding_guard.get('recommended_policy')}`",
            ]
        )
    compounding = report["group_a_plus"].get("compounding_regime_diagnostic") or {}
    if compounding and compounding.get("status") == "ok":
        features = compounding.get("features") or {}
        lines.extend(
            [
                "",
                "## 00631L Compounding Regime",
                "",
                f"- Regime: `{compounding.get('compounding_regime')}`",
                f"- Policy: `{compounding.get('recommended_policy')}`",
                f"- Trend score: `{compounding.get('trend_score')}`",
                f"- Mean-reversion score: `{compounding.get('mean_reversion_score')}`",
                f"- AR1 5d / 20d: `{features.get('rolling_AR1_5d')}` / `{features.get('rolling_AR1_20d')}`",
                f"- Variance ratio: `{features.get('variance_ratio')}`",
                f"- 00631L vs 0050 relative momentum: `{features.get('00631L_vs_0050_relative_momentum')}`",
            ]
        )
    if dfl_advisory and dfl_advisory.get("status") == "available":
        lines.extend(
            [
                "",
                "## A21.18 DFL Advisory",
                "",
                f"- Action: `{dfl_advisory.get('action')}`",
                f"- Active: `{dfl_advisory.get('advisory_active')}`",
                f"- Policy: `{dfl_advisory.get('policy')}`",
            ]
        )
        selected = dfl_advisory.get("selected_decision") or {}
        if selected:
            lines.append(f"- Predicted regret: `{selected.get('predicted_regret')}`")
        selective_variants = dfl_advisory.get("selective_variants") or {}
        if selective_variants:
            lines.extend(["", "### Selective Variants", ""])
            for name, variant in sorted(selective_variants.items()):
                if not isinstance(variant, dict):
                    continue
                selected_variant = variant.get("selected_decision") or {}
                lines.append(
                    "- `{name}` action `{action}` active `{active}` reliability `{reliability}`".format(
                        name=name,
                        action=variant.get("action"),
                        active=variant.get("advisory_active"),
                        reliability=selected_variant.get("reliability_error_percentile"),
                    )
                )
    if dfl_active_date_audit and dfl_active_date_audit.get("status") == "research_only":
        summary = dfl_active_date_audit.get("summary") or {}
        lines.extend(
            [
                "",
                "## A21.18 DFL Active-Date Audit",
                "",
                f"- Conclusion: `{dfl_active_date_audit.get('conclusion')}`",
                f"- Active days: `{summary.get('active_days')}`",
                f"- Hard checks pass: `{summary.get('all_checks_pass')}`",
                f"- Warning days: `{summary.get('warning_days')}`",
                f"- Existing guard overlap days: `{summary.get('existing_guard_overlap_days')}`",
                f"- Total estimated cost bps / 1M: `{summary.get('total_estimated_cost_bps')}`",
                "- Policy: `shadow_only_no_auto_weight_change`",
            ]
        )
    if finstressts_snapshot:
        summary = finstressts_snapshot.get("summary") or {}
        decision = finstressts_snapshot.get("decision") or {}
        lines.extend(
            [
                "",
                "## FinStressTS Shadow Snapshot",
                "",
                f"- Status: `{finstressts_snapshot.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Blocked mechanisms: `{summary.get('blocked_mechanisms')}`",
                f"- Reference loses to no-00631L: `{summary.get('reference_loses_to_no_00631l_scenarios')}`",
                f"- Reference tail failures: `{summary.get('reference_tail_failure_scenarios')}`",
                f"- Best shadow candidate: `{summary.get('baseline_best_shadow_candidate')}`",
                "- Policy: `research_only_summary_no_weight_change`",
            ]
        )
    if trigate_vol_memory:
        latest = trigate_vol_memory.get("latest") or {}
        state = trigate_vol_memory.get("tri_gate_state") or {}
        decision = trigate_vol_memory.get("decision") or {}
        lines.extend(
            [
                "",
                "## Tri-Gate Volatility Memory Shadow",
                "",
                f"- State: `{state.get('state')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Stress gate count: `{state.get('stress_gate_count')}`",
                f"- Level / shape / tempo active: `{state.get('level_gate_active')}` / `{state.get('shape_gate_active')}` / `{state.get('tempo_gate_active')}`",
                f"- Vol level percentile: `{latest.get('vol_level_percentile_252d')}`",
                f"- Shape percentile: `{latest.get('memory_shape_percentile_252d')}`",
                f"- Tempo percentile: `{latest.get('tempo_percentile_252d')}`",
                "- Policy: `research_only_vol_memory_decomposition_no_weight_change`",
            ]
        )
    if systemic_bubble_review:
        latest = systemic_bubble_review.get("latest") or {}
        states = systemic_bubble_review.get("states") or {}
        decision = systemic_bubble_review.get("decision") or {}
        lines.extend(
            [
                "",
                "## Systemic Bubble Time-At-Risk Review",
                "",
                f"- State: `{states.get('overall_state')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Systemic score: `{states.get('systemic_score')}`",
                f"- Time-at-risk / ETF coupling / reflexivity: `{states.get('time_at_risk_state')}` / `{states.get('etf_coupling_state')}` / `{states.get('reflexivity_proxy_state')}`",
                f"- 2330/0050 corr 60d: `{latest.get('2330_0050_corr_60d')}`",
                f"- ETF coupling score: `{latest.get('etf_coupling_score')}`",
                "- Policy: `research_only_systemic_bubble_time_at_risk_no_weight_change`",
            ]
        )
    if illiquidity_network_readiness:
        decision = illiquidity_network_readiness.get("decision") or {}
        data = illiquidity_network_readiness.get("data") or {}
        ohlcv = data.get("ohlcv_summary") or {}
        daily_proxy = illiquidity_network_readiness.get("daily_ohlcv_liquidity_stress_proxy") or {}
        proxy_counts = daily_proxy.get("component_counts") or {}
        lines.extend(
            [
                "",
                "## Illiquidity Network Readiness",
                "",
                f"- Status: `{illiquidity_network_readiness.get('status')}`",
                f"- Actual data end: `{illiquidity_network_readiness.get('actual_data_end')}`",
                f"- Illiquidity network ready: `{decision.get('illiquidity_network_ready')}`",
                f"- Crash guard allowed: `{decision.get('crash_guard_allowed')}`",
                f"- Daily OHLCV proxy: `{daily_proxy.get('status')}` paper-equivalent `{daily_proxy.get('paper_equivalent')}`",
                f"- Daily OHLCV proxy state: `{daily_proxy.get('stress_state')}` manual-review `{daily_proxy.get('manual_review_required')}`",
                f"- Daily OHLCV proxy score: `{daily_proxy.get('stress_score')}` coverage `{daily_proxy.get('coverage_tickers')}`",
                f"- Proxy components volume/range/negative/limit: `{proxy_counts.get('volume_drought')}` / `{proxy_counts.get('range_spike')}` / `{proxy_counts.get('negative_return')}` / `{proxy_counts.get('limit_down_proxy')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- 00632R open: `{'allowed' if decision.get('allow_00632r_open') else 'blocked'}`",
                f"- OHLCV tickers / rows: `{ohlcv.get('distinct_tickers')}` / `{ohlcv.get('rows')}`",
                f"- Blocking reasons: `{illiquidity_network_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_illiquidity_network_readiness_no_crash_guard_no_weight_change`",
            ]
        )
    if speculative_influence_readiness:
        decision = speculative_influence_readiness.get("decision") or {}
        data = speculative_influence_readiness.get("data") or {}
        ohlcv = data.get("ohlcv_summary") or {}
        lines.extend(
            [
                "",
                "## Speculative Influence Network Readiness",
                "",
                f"- Status: `{speculative_influence_readiness.get('status')}`",
                f"- Actual data end: `{speculative_influence_readiness.get('actual_data_end')}`",
                f"- SIN ready: `{decision.get('speculative_influence_network_ready')}`",
                f"- HMM bubble state ready: `{decision.get('hmm_bubble_state_ready')}`",
                f"- Transfer entropy network ready: `{decision.get('transfer_entropy_network_ready')}`",
                f"- Max-loss validation ready: `{decision.get('maxloss_validation_ready')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- 00632R open: `{'allowed' if decision.get('allow_00632r_open') else 'blocked'}`",
                f"- OHLCV tickers / minimum: `{ohlcv.get('distinct_tickers')}` / `{data.get('broad_universe_min_tickers')}`",
                f"- Broad universe ready: `{data.get('broad_universe_ready')}`",
                f"- Blocking reasons: `{speculative_influence_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_speculative_influence_network_readiness_no_weight_change`",
            ]
        )
    if sin_lite_proxy:
        latest = sin_lite_proxy.get("latest") or {}
        coverage = sin_lite_proxy.get("coverage") or {}
        decision = sin_lite_proxy.get("decision") or {}
        components = latest.get("components") or {}
        lines.extend(
            [
                "",
                "## SIN-Lite Proxy",
                "",
                f"- Status: `{sin_lite_proxy.get('status')}`",
                f"- Actual data end: `{sin_lite_proxy.get('actual_data_end')}`",
                f"- State: `{latest.get('state')}`",
                f"- SIN-lite score: `{latest.get('sin_lite_score')}`",
                f"- Manual review required: `{latest.get('manual_review_required')}`",
                f"- Usable tickers: `{coverage.get('usable_ticker_count')}`",
                f"- Components corr/edge/downside/concentration/TSMC: `{components.get('correlation_density')}` / `{components.get('edge_density')}` / `{components.get('downside_comovement')}` / `{components.get('influence_concentration')}` / `{components.get('tsmc_lead_risk')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- 00632R open: `{'allowed' if decision.get('allow_00632r_open') else 'blocked'}`",
                f"- Blocking reasons: `{sin_lite_proxy.get('blocking_reasons')}`",
                "- Policy: `research_only_sin_lite_proxy_no_weight_change`",
            ]
        )
    if hmm_wj_readiness:
        validation = hmm_wj_readiness.get("validation_readiness") or {}
        data_readiness = hmm_wj_readiness.get("data_readiness") or {}
        decision = hmm_wj_readiness.get("decision") or {}
        lines.extend(
            [
                "",
                "## HMM-WJ Synthetic Scenario Readiness",
                "",
                f"- Status: `{hmm_wj_readiness.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Data ready: `{data_readiness.get('all_required_tickers_ready')}`",
                f"- Can generate scenarios for decision: `{decision.get('can_generate_scenarios_for_decision')}`",
                f"- Generator implemented: `{validation.get('generator_implemented')}`",
                f"- Taiwan ETF walk-forward validated: `{validation.get('taiwan_etf_walkforward_validated')}`",
                f"- Blocking reasons: `{hmm_wj_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_hmm_wj_readiness_no_synthetic_alpha_no_weight_change`",
            ]
        )
    if dynamic_cvar_readiness:
        component = dynamic_cvar_readiness.get("component_readiness") or {}
        cvar = component.get("cvar_tail_risk") or {}
        market_impact = component.get("market_impact") or {}
        decision = dynamic_cvar_readiness.get("decision") or {}
        lines.extend(
            [
                "",
                "## Dynamic CVaR Tail/Cost Readiness",
                "",
                f"- Status: `{dynamic_cvar_readiness.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Tail/cost ready: `{decision.get('tail_cost_readiness_ready')}`",
                f"- Dynamic optimizer ready: `{decision.get('dynamic_optimizer_ready')}`",
                f"- 00631L Hill xi 95: `{cvar.get('00631l_hill_xi_95')}`",
                f"- 00631L POT-GPD xi 95: `{cvar.get('00631l_pot_gpd_shape_xi_95')}`",
                f"- Turnover: `{market_impact.get('turnover')}`",
                f"- Blocking reasons: `{dynamic_cvar_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_dynamic_cvar_tail_cost_readiness_no_optimizer_no_weight_change`",
            ]
        )
    if synthetic_augmentation_readiness:
        validation = synthetic_augmentation_readiness.get("validation_readiness") or {}
        decision = synthetic_augmentation_readiness.get("decision") or {}
        lines.extend(
            [
                "",
                "## Synthetic Augmentation Validation Readiness",
                "",
                f"- Status: `{synthetic_augmentation_readiness.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Synthetic validation ready: `{decision.get('synthetic_validation_ready')}`",
                f"- Directional synthetic alpha: `{'allowed' if decision.get('directional_synthetic_alpha_allowed') else 'blocked'}`",
                f"- Generator promotion: `{'allowed' if decision.get('synthetic_generator_promotion_allowed') else 'blocked'}`",
                f"- Size-matched null: `{validation.get('size_matched_null_augmentation_implemented')}`",
                f"- Block permutation test: `{validation.get('block_permutation_test_implemented')}`",
                f"- Directional audit passed: `{validation.get('directional_audit_passed')}`",
                f"- Rare-regime audit passed: `{validation.get('rare_regime_audit_passed')}`",
                f"- Blocking reasons: `{synthetic_augmentation_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_synthetic_augmentation_validation_no_synthetic_alpha_no_weight_change`",
            ]
        )
    if intervention_fatigue_readiness:
        fatigue = intervention_fatigue_readiness.get("intervention_fatigue") or {}
        broker_holdings = intervention_fatigue_readiness.get("broker_holdings_time_series") or {}
        broker_reconciliation = intervention_fatigue_readiness.get("broker_holdings_reconciliation") or {}
        pacing = intervention_fatigue_readiness.get("risk_budget_pacing") or {}
        decision = intervention_fatigue_readiness.get("decision") or {}
        lines.extend(
            [
                "",
                "## Intervention Fatigue / Risk-Budget Readiness",
                "",
                f"- Status: `{intervention_fatigue_readiness.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- 00632R open: `{'allowed' if decision.get('allow_00632r_open') else 'blocked'}`",
                f"- Intervention fatigue ready: `{decision.get('intervention_fatigue_ready')}`",
                f"- Risk-budget pacing ready: `{decision.get('risk_budget_pacing_ready')}`",
                f"- Nonzero trade count: `{fatigue.get('trade_count_nonzero')}`",
                f"- Leverage / hedge change count: `{fatigue.get('leverage_change_count')}` / `{fatigue.get('hedge_change_count')}`",
                f"- Normalized history available: `{fatigue.get('normalized_history_available')}`",
                f"- History entries / blocked: `{fatigue.get('history_entry_count')}` / `{fatigue.get('history_blocked_entry_count')}`",
                f"- History leverage / hedge interventions: `{fatigue.get('history_leverage_intervention_count')}` / `{fatigue.get('history_hedge_intervention_count')}`",
                f"- Broker holdings status: `{broker_holdings.get('status')}` authoritative `{broker_holdings.get('authoritative_broker_export')}`",
                f"- Broker transactions / snapshots: `{broker_holdings.get('transaction_count')}` / `{broker_holdings.get('snapshot_count')}`",
                f"- Broker negative positions: `{broker_holdings.get('negative_position_count')}`",
                f"- Broker reconciliation status: `{broker_reconciliation.get('status')}`",
                f"- Confirmed matched / mismatched: `{broker_reconciliation.get('matched_confirmed_count')}` / `{broker_reconciliation.get('mismatched_confirmed_count')}`",
                f"- Can generate live orders: `{broker_reconciliation.get('can_generate_live_orders')}`",
                f"- Turnover: `{pacing.get('turnover')}`",
                f"- Blocking reasons: `{intervention_fatigue_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_intervention_fatigue_risk_budget_pacing_no_weight_change`",
            ]
        )
    if letf_tracking_readiness:
        decision = letf_tracking_readiness.get("decision") or {}
        tracking = letf_tracking_readiness.get("tracking_error_summary") or {}
        hedge = (letf_tracking_readiness.get("hedge_neutrality") or {}).get("00632R.TW") or {}
        l31_h30 = (((tracking.get("00631L.TW") or {}).get("horizon_metrics") or {}).get("30") or {})
        r32_h30 = (((tracking.get("00632R.TW") or {}).get("horizon_metrics") or {}).get("30") or {})
        l31_te = l31_h30.get("tracking_error") or {}
        r32_te = r32_h30.get("tracking_error") or {}
        lines.extend(
            [
                "",
                "## LETF Tracking Error / Effective Fee Readiness",
                "",
                f"- Status: `{letf_tracking_readiness.get('status')}`",
                f"- Actual data end: `{letf_tracking_readiness.get('actual_data_end')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- 00632R open: `{'allowed' if decision.get('allow_00632r_open') else 'blocked'}`",
                f"- Tracking-error readiness: `{decision.get('tracking_error_readiness_ready')}`",
                f"- Effective-fee proxy ready: `{decision.get('realized_effective_fee_proxy_ready')}`",
                f"- Hedge-neutrality ready: `{decision.get('hedge_neutrality_ready')}`",
                f"- 00631L 30d mean/latest tracking error: `{l31_te.get('mean')}` / `{l31_te.get('latest')}`",
                f"- 00632R 30d mean/latest tracking error: `{r32_te.get('mean')}` / `{r32_te.get('latest')}`",
                f"- 00632R hedge beta/corr: `{hedge.get('realized_beta')}` / `{hedge.get('correlation')}`",
                f"- Blocking reasons: `{letf_tracking_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_letf_tracking_error_effective_fee_no_pair_trade_no_weight_change`",
            ]
        )
    if asian_etf_tail_analytics_readiness:
        decision = asian_etf_tail_analytics_readiness.get("decision") or {}
        coverage = ((asian_etf_tail_analytics_readiness.get("data_readiness") or {}).get("paper_etf_coverage") or {})
        cvar = ((asian_etf_tail_analytics_readiness.get("component_readiness") or {}).get("cvar_tail_risk") or {})
        tail_monitor = asian_etf_tail_analytics_readiness.get("tail_reward_risk_monitor") or {}
        lines.extend(
            [
                "",
                "## Asian ETF Tail Analytics Readiness",
                "",
                f"- Status: `{asian_etf_tail_analytics_readiness.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- Tail analytics ready: `{decision.get('tail_analytics_ready')}`",
                f"- Optimizer ready: `{decision.get('optimizer_ready')}`",
                f"- Paper ETF coverage: `{coverage.get('available_paper_etf_count')}` / `{coverage.get('paper_etf_count')}`",
                f"- Available paper ETFs: `{coverage.get('available_paper_etfs')}`",
                f"- Golden1 STARR 95: `{cvar.get('golden1_starr_95')}`",
                f"- Golden1 Rachev 95/95: `{cvar.get('golden1_rachev_95_95')}`",
                f"- 00631L Rachev 95/95: `{cvar.get('00631l_rachev_95_95')}`",
                f"- Tail reward/risk tier: `{tail_monitor.get('tier')}`",
                f"- 00631L Hill xi 95: `{cvar.get('00631l_hill_xi_95')}`",
                f"- Blocking reasons: `{asian_etf_tail_analytics_readiness.get('blocking_reasons')}`",
                "- Policy: `research_only_asian_etf_tail_analytics_no_optimizer_no_weight_change`",
            ]
        )
    if research_shadow_snapshot:
        summary = research_shadow_snapshot.get("summary") or {}
        decision = research_shadow_snapshot.get("decision") or {}
        lines.extend(
            [
                "",
                "## Research Shadow Decision Snapshot",
                "",
                f"- Status: `{research_shadow_snapshot.get('status')}`",
                f"- 00631L add: `{'allowed' if decision.get('allow_00631l_add') else 'blocked'}`",
                f"- FinStressTS status: `{summary.get('finstressts_status')}`",
                f"- Tri-gate state: `{summary.get('trigate_state')}`",
                f"- Tri-gate stress count: `{summary.get('trigate_stress_gate_count')}`",
                f"- Illiquidity network status: `{summary.get('illiquidity_network_status')}`",
                f"- Illiquidity crash guard allowed: `{summary.get('illiquidity_network_crash_guard_allowed')}`",
                f"- Illiquidity daily proxy score: `{summary.get('illiquidity_daily_proxy_stress_score')}`",
                f"- Illiquidity daily proxy state: `{summary.get('illiquidity_daily_proxy_stress_state')}`",
                f"- Speculative influence status: `{summary.get('speculative_influence_network_status')}`",
                f"- Speculative influence ready: `{summary.get('speculative_influence_network_ready')}`",
                f"- SIN-lite state: `{summary.get('sin_lite_proxy_state')}`",
                f"- SIN-lite score: `{summary.get('sin_lite_proxy_score')}`",
                f"- Dynamic CVaR status: `{summary.get('dynamic_cvar_status')}`",
                f"- Dynamic CVaR tail/cost ready: `{summary.get('dynamic_cvar_tail_cost_ready')}`",
                f"- Dynamic CVaR optimizer ready: `{summary.get('dynamic_cvar_optimizer_ready')}`",
                f"- Synthetic augmentation status: `{summary.get('synthetic_augmentation_status')}`",
                f"- Synthetic validation ready: `{summary.get('synthetic_validation_ready')}`",
                f"- Directional synthetic alpha: `{summary.get('directional_synthetic_alpha_allowed')}`",
                f"- Intervention fatigue status: `{summary.get('intervention_fatigue_status')}`",
                f"- Risk-budget pacing ready: `{summary.get('risk_budget_pacing_ready')}`",
                f"- LETF tracking status: `{summary.get('letf_tracking_status')}`",
                f"- LETF hedge neutrality ready: `{summary.get('letf_hedge_neutrality_ready')}`",
                f"- Asian ETF tail analytics status: `{summary.get('asian_etf_tail_analytics_status')}`",
                f"- Asian ETF tail analytics ready: `{summary.get('asian_etf_tail_analytics_ready')}`",
                f"- GIFT signed approval validation: `{summary.get('llm_state_reward_signed_approval_validation_status')}`",
                f"- GIFT signed approval record valid: `{summary.get('llm_state_reward_signed_approval_record_valid')}`",
                f"- GIFT human exception approved: `{summary.get('llm_state_reward_signed_approval_human_exception_approved')}`",
                f"- GIFT non-PPO shadow queue review allowed: `{summary.get('llm_state_reward_signed_approval_non_ppo_shadow_queue_review_allowed')}`",
                f"- GIFT manual approval queue allowed: `{summary.get('llm_state_reward_manual_approval_to_queue_training_allowed')}`",
                f"- GIFT training queue blockers: `{summary.get('llm_state_reward_manual_approval_queue_blocking_reasons')}`",
                f"- GIFT checklist status: `{gift_signed_approval_governance.get('checklist_status')}`",
                f"- GIFT validator smoke status: `{gift_signed_approval_governance.get('validator_smoke_status')}`",
                "- Policy: `research_shadow_summary_no_weight_change`",
            ]
        )
    if gift_signed_approval_governance:
        lines.extend(
            [
                "",
                "## GIFT Signed Approval Governance",
                "",
                f"- Validation status: `{gift_signed_approval_governance.get('validation_status')}`",
                f"- Signed approval record valid: `{gift_signed_approval_governance.get('signed_approval_record_valid')}`",
                f"- Human exception approved: `{gift_signed_approval_governance.get('human_exception_approved')}`",
                f"- Non-PPO shadow queue review allowed: `{gift_signed_approval_governance.get('non_ppo_shadow_queue_review_allowed')}`",
                f"- Manual approval queue allowed: `{gift_signed_approval_governance.get('manual_approval_to_queue_training_allowed')}`",
                f"- Training queue allowed: `{gift_signed_approval_governance.get('training_queue_allowed')}`",
                f"- Model training allowed: `{gift_signed_approval_governance.get('model_training_allowed')}`",
                f"- PPO training allowed: `{gift_signed_approval_governance.get('ppo_training_allowed')}`",
                f"- Promote to live: `{gift_signed_approval_governance.get('promote_to_live')}`",
                f"- Queue blockers: `{gift_signed_approval_governance.get('training_queue_blocking_reasons')}`",
                f"- Signed approval warnings: `{gift_signed_approval_governance.get('signed_approval_warnings')}`",
                f"- Checklist status: `{gift_signed_approval_governance.get('checklist_status')}`",
                f"- Checklist manual completion ready: `{gift_signed_approval_governance.get('checklist_manual_completion_ready')}`",
                f"- Checklist manual completion pending: `{gift_signed_approval_governance.get('checklist_manual_completion_pending')}`",
                f"- Checklist signed record exists: `{gift_signed_approval_governance.get('checklist_signed_record_exists')}`",
                f"- Validator smoke status: `{gift_signed_approval_governance.get('validator_smoke_status')}`",
                f"- Validator smoke passed: `{gift_signed_approval_governance.get('validator_smoke_passed')}`",
                f"- Validator blocks 00631L add: `{gift_signed_approval_governance.get('validator_smoke_blocks_00631l_add')}`",
                f"- Validator blocks model training: `{gift_signed_approval_governance.get('validator_smoke_blocks_model_training')}`",
                f"- Smoke wrote formal signed record: `{gift_signed_approval_governance.get('formal_signed_record_written_by_smoke')}`",
                "- Policy: `research_only_signed_approval_governance_no_training_no_live_action`",
            ]
        )
    return "\n".join(lines) + "\n"


def _write_markdown(path: Path, report: dict[str, Any]) -> str:
    text = _markdown_text(report)
    path.write_text(text, encoding="utf-8")
    return text


def _live_status_report(args: argparse.Namespace) -> dict[str, Any]:
    live_signal = _load(args.live_signal)
    data = live_signal.get("data") if isinstance(live_signal.get("data"), dict) else live_signal
    execution_plan = _unwrap_standard_payload(_load_optional(getattr(args, "execution_plan", None)))
    check_date = str(args.check_date)
    actual_data_date = str(data.get("actual_data_date") or data.get("requested_as_of_date") or check_date)
    business_stale = _business_days_between(actual_data_date, check_date)
    calendar_stale = int((pd.Timestamp(check_date).normalize() - pd.Timestamp(actual_data_date).normalize()).days)

    execution_allowed = bool(data.get("execution_allowed"))
    guard_reasons = list(data.get("execution_guard_reasons") or [])
    warning_reasons = list(data.get("execution_warning_reasons") or [])
    target_shares = data.get("reference_target_shares_before_cost") or {}
    cash_after_cost = float(data.get("estimated_cash_after_rounding_before_cost", 0.0) or 0.0)
    target_weights = dict(data.get("target_weights") or {})
    overlay_00679b_weight = float(target_weights.get("00679B.TWO", 0.0) or 0.0)
    execution_regime = str(data.get("execution_regime") or data.get("base_regime") or "unknown")
    strategy_status = str(data.get("strategy_status") or "unknown")
    execution_plan_path = Path(getattr(args, "execution_plan", ""))
    execution_plan_exists = False
    if str(execution_plan_path):
        execution_plan_exists = execution_plan_path.is_absolute() and execution_plan_path.exists()
        execution_plan_exists = execution_plan_exists or (PROJECT_ROOT / execution_plan_path).exists()
    execution_plan_aligned = False
    pre_trade_guard: dict[str, Any] = {}
    pre_trade_guards: list[dict[str, Any]] = []
    compounding_regime_pre_trade_guard: dict[str, Any] = {}
    if execution_plan:
        execution_plan_aligned = (
            str(execution_plan.get("actual_data_date") or "") == actual_data_date
            and str(execution_plan.get("strategy_id") or "") == str(data.get("strategy_id") or "")
        )
        if execution_plan_aligned and isinstance(execution_plan.get("pre_trade_guard"), dict):
            pre_trade_guard = dict(execution_plan["pre_trade_guard"])
        if execution_plan_aligned and isinstance(execution_plan.get("compounding_regime_pre_trade_guard"), dict):
            compounding_regime_pre_trade_guard = dict(execution_plan["compounding_regime_pre_trade_guard"])
        if execution_plan_aligned and isinstance(execution_plan.get("pre_trade_guards"), list):
            pre_trade_guards = [
                dict(guard) for guard in execution_plan["pre_trade_guards"] if isinstance(guard, dict)
            ]
    compounding_regime = _load_compounding_regime(getattr(args, "compounding_regime", None))
    dfl_advisory = _unwrap_standard_payload(_load_optional(getattr(args, "dfl_advisory", None)))
    dfl_shadow_ensemble = _unwrap_standard_payload(_load_optional(getattr(args, "dfl_shadow_ensemble", None)))
    dfl_active_date_audit = _unwrap_standard_payload(_load_optional(getattr(args, "dfl_active_date_audit", None)))
    finstressts_decision_snapshot = _unwrap_standard_payload(
        _load_optional(getattr(args, "finstressts_decision_snapshot", None))
    )
    trigate_vol_memory_shadow = _unwrap_standard_payload(
        _load_optional(getattr(args, "trigate_vol_memory_shadow", None))
    )
    systemic_bubble_time_at_risk_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "systemic_bubble_time_at_risk_review", None))
    )
    illiquidity_network_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "illiquidity_network_readiness_review", None))
    )
    speculative_influence_network_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "speculative_influence_network_readiness_review", None))
    )
    sin_lite_proxy = _unwrap_standard_payload(_load_optional(getattr(args, "sin_lite_proxy", None)))
    hmm_wj_synthetic_scenario_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "hmm_wj_synthetic_scenario_readiness_review", None))
    )
    dynamic_cvar_tail_cost_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "dynamic_cvar_tail_cost_readiness_review", None))
    )
    synthetic_augmentation_validation_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "synthetic_augmentation_validation_readiness_review", None))
    )
    intervention_fatigue_risk_budget_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "intervention_fatigue_risk_budget_readiness_review", None))
    )
    letf_tracking_error_effective_fee_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "letf_tracking_error_effective_fee_readiness_review", None))
    )
    asian_etf_tail_analytics_readiness_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "asian_etf_tail_analytics_readiness_review", None))
    )
    research_shadow_decision_snapshot = _unwrap_standard_payload(
        _load_optional(getattr(args, "research_shadow_decision_snapshot", None))
    )
    gift_signed_approval_checklist_review = _unwrap_standard_payload(
        _load_optional(getattr(args, "gift_signed_approval_checklist_review", None))
    )
    gift_signed_approval_validator_smoke = _unwrap_standard_payload(
        _load_optional(getattr(args, "gift_signed_approval_validator_smoke", None))
    )
    promotion_gate = _load_promotion_gate_summary(getattr(args, "promotion_gate", None))
    gift_signed_approval_governance = _gift_signed_approval_governance(
        research_shadow_decision_snapshot,
        gift_signed_approval_checklist_review,
        gift_signed_approval_validator_smoke,
    )
    dfl_frozen_input_staleness = _dfl_frozen_input_staleness(dfl_advisory, check_date)
    max_dfl_frozen_staleness_days = int(getattr(args, "max_dfl_frozen_staleness_days", 14))
    execution_plan_cash = _execution_plan_cash_summary(execution_plan, aligned=execution_plan_aligned)

    optional_sources = ((data.get("data_freshness") or {}).get("optional_sources") or {})
    hard_source_blocks = [
        name for name, source in optional_sources.items()
        if source.get("severity") == "hard" and source.get("status") not in {"ok", "warn"}
    ]
    soft_source_warnings = [
        name for name, source in optional_sources.items()
        if source.get("severity") != "hard" and source.get("status") not in {"ok", None}
    ]

    checks = [
        {
            "name": "live_signal_success",
            "status": _status(bool(live_signal.get("success", True))),
            "detail": "live signal loaded" if live_signal.get("success", True) else str(live_signal.get("error")),
        },
        {
            "name": "execution_allowed",
            "status": _status(execution_allowed),
            "detail": "allowed" if execution_allowed else "; ".join(guard_reasons) or "blocked",
        },
        {
            "name": "data_freshness",
            "status": _status(
                business_stale <= int(args.max_business_stale_days),
                warn=calendar_stale > business_stale,
            ),
            "detail": f"{business_stale} business days stale, {calendar_stale} calendar days stale",
        },
        {
            "name": "strategy_status",
            "status": _status(strategy_status == "active", warn=strategy_status not in {"active", "unknown"}),
            "detail": f"strategy_status={strategy_status}, strategy_id={data.get('strategy_id')}",
        },
        {
            "name": "source_freshness",
            "status": _status(not hard_source_blocks, warn=bool(warning_reasons or soft_source_warnings)),
            "detail": (
                "all required sources ok"
                if not hard_source_blocks and not warning_reasons and not soft_source_warnings
                else "; ".join(guard_reasons + warning_reasons + hard_source_blocks + soft_source_warnings)
            ),
        },
        {
            "name": "cash_constraint",
            "status": _status(cash_after_cost >= 0),
            "detail": f"estimated_cash_after_rounding_before_cost={cash_after_cost:,.0f}",
        },
        {
            "name": "execution_plan_pre_trade_guard",
            "status": _status(
                True,
                warn=bool(execution_plan_exists and execution_plan and not execution_plan_aligned),
            ),
            "detail": (
                "pre_trade_guards="
                + ",".join(
                    str(guard.get("status"))
                    for guard in pre_trade_guards
                    if guard.get("status") not in {None, "inactive", "unavailable"}
                )
                if pre_trade_guards
                else "execution plan unavailable"
                if not execution_plan_exists
                else "execution plan has no aligned pre_trade_guard"
            ),
        },
        {
            "name": "dfl_advisory_frozen_input_staleness",
            # research-only/advisory input, so this never blocks the run --
            # it only warns when the frozen backtest has gone stale.
            "status": _status(
                True,
                warn=dfl_frozen_input_staleness.get("status") == "ok"
                and int(dfl_frozen_input_staleness.get("calendar_gap_days", 0)) > max_dfl_frozen_staleness_days,
            ),
            "detail": (
                f"frozen backtest last covers {dfl_frozen_input_staleness.get('max_live_window_decision_date')} "
                f"({dfl_frozen_input_staleness.get('calendar_gap_days')} calendar days behind check_date); "
                "matched_decision_count is structurally 0 until this is re-run"
                if dfl_frozen_input_staleness.get("status") == "ok"
                else dfl_frozen_input_staleness.get("detail", "dfl_advisory not in use")
            ),
        },
    ]
    if promotion_gate:
        checks.append(
            {
                "name": "promotion_gate_deployment_summary",
                "status": _status(
                    True,
                    warn=promotion_gate.get("deployment_summary_gate_status") != "pass"
                    or promotion_gate.get("deployment_summary_consistency_status") != "ok",
                ),
                "detail": (
                    f"deployment_summary_gate={promotion_gate.get('deployment_summary_gate_status')}, "
                    f"consistency={promotion_gate.get('deployment_summary_consistency_status')}, "
                    f"blockers={promotion_gate.get('deployment_summary_gate_blocking_reasons')}"
                ),
            }
        )
    overall = "block" if any(item["status"] == "block" for item in checks) else "warn" if any(item["status"] == "warn" for item in checks) else "ok"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "check_date": check_date,
        "status_stage": str(getattr(args, "status_stage", "pre_promotion")),
        "overall_status": overall,
        "profile": str(data.get("strategy_id") or "group_a_plus_live"),
        "mode": "live_signal",
        "source_paths": {
            "live_signal": str(Path(args.live_signal)),
            "execution_plan": str(Path(getattr(args, "execution_plan", ""))),
            "compounding_regime": compounding_regime.get("source_path"),
            "dfl_advisory": str(Path(getattr(args, "dfl_advisory", ""))),
            "dfl_shadow_ensemble": str(Path(getattr(args, "dfl_shadow_ensemble", ""))),
            "dfl_active_date_audit": str(Path(getattr(args, "dfl_active_date_audit", ""))),
            "finstressts_decision_snapshot": str(Path(getattr(args, "finstressts_decision_snapshot", ""))),
            "trigate_vol_memory_shadow": str(Path(getattr(args, "trigate_vol_memory_shadow", ""))),
            "systemic_bubble_time_at_risk_review": str(
                Path(getattr(args, "systemic_bubble_time_at_risk_review", ""))
            ),
            "illiquidity_network_readiness_review": str(
                Path(getattr(args, "illiquidity_network_readiness_review", ""))
            ),
            "speculative_influence_network_readiness_review": str(
                Path(getattr(args, "speculative_influence_network_readiness_review", ""))
            ),
            "sin_lite_proxy": str(Path(getattr(args, "sin_lite_proxy", ""))),
            "hmm_wj_synthetic_scenario_readiness_review": str(
                Path(getattr(args, "hmm_wj_synthetic_scenario_readiness_review", ""))
            ),
            "dynamic_cvar_tail_cost_readiness_review": str(
                Path(getattr(args, "dynamic_cvar_tail_cost_readiness_review", ""))
            ),
            "synthetic_augmentation_validation_readiness_review": str(
                Path(getattr(args, "synthetic_augmentation_validation_readiness_review", ""))
            ),
            "intervention_fatigue_risk_budget_readiness_review": str(
                Path(getattr(args, "intervention_fatigue_risk_budget_readiness_review", ""))
            ),
            "letf_tracking_error_effective_fee_readiness_review": str(
                Path(getattr(args, "letf_tracking_error_effective_fee_readiness_review", ""))
            ),
            "asian_etf_tail_analytics_readiness_review": str(
                Path(getattr(args, "asian_etf_tail_analytics_readiness_review", ""))
            ),
            "research_shadow_decision_snapshot": str(Path(getattr(args, "research_shadow_decision_snapshot", ""))),
            "gift_signed_approval_checklist_review": str(
                Path(getattr(args, "gift_signed_approval_checklist_review", ""))
            ),
            "gift_signed_approval_validator_smoke": str(
                Path(getattr(args, "gift_signed_approval_validator_smoke", ""))
            ),
            "promotion_gate": str(
                getattr(args, "promotion_gate", None) or _latest_promotion_gate_path() or ""
            ),
        },
        "checks": checks,
        "signal": {
            "signal_status": str(data.get("action") or ""),
            "signal_reason": str(data.get("regime_reason") or ""),
            "actual_data_date": actual_data_date,
            "requested_as_of_date": data.get("requested_as_of_date"),
            "business_stale_days": business_stale,
            "calendar_stale_days": calendar_stale,
        },
        "group_a_plus": {
            "overlay_regime": execution_regime,
            "overlay_00679b_weight": overlay_00679b_weight,
            "cash_after_cost": cash_after_cost,
            "target_shares": target_shares,
            "execution_plan_cash": execution_plan_cash,
            "pre_trade_guard": pre_trade_guard,
            "pre_trade_guards": pre_trade_guards,
            "compounding_regime_pre_trade_guard": compounding_regime_pre_trade_guard,
            "compounding_regime_diagnostic": compounding_regime,
            "dfl_advisory": dfl_advisory or {},
            "dfl_shadow_ensemble": dfl_shadow_ensemble or {},
            "dfl_active_date_audit": dfl_active_date_audit or {},
            "dfl_frozen_input_staleness": dfl_frozen_input_staleness,
            "finstressts_decision_snapshot": finstressts_decision_snapshot or {},
            "trigate_vol_memory_shadow": trigate_vol_memory_shadow or {},
            "systemic_bubble_time_at_risk_review": systemic_bubble_time_at_risk_review or {},
            "illiquidity_network_readiness_review": illiquidity_network_readiness_review or {},
            "speculative_influence_network_readiness_review": (
                speculative_influence_network_readiness_review or {}
            ),
            "sin_lite_proxy": sin_lite_proxy or {},
            "hmm_wj_synthetic_scenario_readiness_review": hmm_wj_synthetic_scenario_readiness_review or {},
            "dynamic_cvar_tail_cost_readiness_review": dynamic_cvar_tail_cost_readiness_review or {},
            "synthetic_augmentation_validation_readiness_review": (
                synthetic_augmentation_validation_readiness_review or {}
            ),
            "intervention_fatigue_risk_budget_readiness_review": (
                intervention_fatigue_risk_budget_readiness_review or {}
            ),
            "letf_tracking_error_effective_fee_readiness_review": (
                letf_tracking_error_effective_fee_readiness_review or {}
            ),
            "asian_etf_tail_analytics_readiness_review": asian_etf_tail_analytics_readiness_review or {},
            "research_shadow_decision_snapshot": research_shadow_decision_snapshot or {},
            "gift_signed_approval_checklist_review": gift_signed_approval_checklist_review or {},
            "gift_signed_approval_validator_smoke": gift_signed_approval_validator_smoke or {},
            "gift_signed_approval_governance": gift_signed_approval_governance,
            "promotion_gate": promotion_gate,
        },
    }


def _baseline_status_report(args: argparse.Namespace) -> dict[str, Any]:
    baseline = _load(args.baseline)
    signal_path = baseline["latest_group_a_signal"]
    plus_signal_path = baseline["latest_group_a_plus_final_signal"]
    clean_payload_path = baseline["clean_payload"]
    stress_path = baseline["stress_test_result"]
    strict_cost_path = baseline["strict_cost_result"]

    signal = _load(signal_path)
    plus_signal = _load(plus_signal_path)
    actual_data_date = str(signal.get("actual_data_date"))
    check_date = str(args.check_date)
    calendar_stale = int((pd.Timestamp(check_date).normalize() - pd.Timestamp(actual_data_date).normalize()).days)
    business_stale = _business_days_between(actual_data_date, check_date)

    signal_status = str(signal.get("signal_status"))
    signal_reason = str(signal.get("signal_reason"))
    guard_reasons = list(signal.get("guard_reasons") or [])
    cash_after_cost = float((plus_signal.get("execution_summary") or {}).get("cash_after_cost", 0.0))
    overlay_regime = str((plus_signal.get("overlay_policy") or {}).get("regime"))
    overlay_00679b_weight = float(plus_signal.get("overlay_00679b_weight", 0.0))

    required_paths = [signal_path, plus_signal_path, clean_payload_path, stress_path, strict_cost_path]
    missing = [path for path in required_paths if not (PROJECT_ROOT / path).exists()]

    checks = [
        {
            "name": "required_files",
            "status": _status(not missing),
            "detail": "all required files present" if not missing else f"missing: {missing}",
        },
        {
            "name": "data_freshness",
            "status": _status(business_stale <= int(args.max_business_stale_days), warn=calendar_stale > business_stale),
            "detail": f"{business_stale} business days stale, {calendar_stale} calendar days stale",
        },
        {
            "name": "signal_guard",
            "status": _status(signal_status != "guard_blocked"),
            "detail": signal_reason if not guard_reasons else "; ".join(guard_reasons),
        },
        {
            "name": "group_a_plus_cash_constraint",
            "status": _status(cash_after_cost >= 0),
            "detail": f"cash_after_cost={cash_after_cost:,.0f}",
        },
        {
            "name": "overlay_regime",
            "status": _status(overlay_regime in {"risk_on", "caution", "risk_off", "severe"}),
            "detail": f"regime={overlay_regime}, 00679B_weight={overlay_00679b_weight:.2%}",
        },
    ]
    overall = "block" if any(item["status"] == "block" for item in checks) else "warn" if any(item["status"] == "warn" for item in checks) else "ok"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "check_date": check_date,
        "status_stage": str(getattr(args, "status_stage", "baseline")),
        "overall_status": overall,
        "profile": baseline["profile"],
        "baseline": str(Path(args.baseline)),
        "mode": "baseline",
        "source_paths": {
            "latest_group_a_signal": signal_path,
            "latest_group_a_plus_final_signal": plus_signal_path,
            "clean_payload": clean_payload_path,
            "stress_test_result": stress_path,
            "strict_cost_result": strict_cost_path,
        },
        "checks": checks,
        "signal": {
            "signal_status": signal_status,
            "signal_reason": signal_reason,
            "actual_data_date": actual_data_date,
            "requested_as_of_date": signal.get("requested_as_of_date"),
            "business_stale_days": business_stale,
            "calendar_stale_days": calendar_stale,
        },
        "group_a_plus": {
            "overlay_regime": overlay_regime,
            "overlay_00679b_weight": overlay_00679b_weight,
            "cash_after_cost": cash_after_cost,
            "target_shares": plus_signal.get("target_shares"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "baseline"], default="live")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--live-signal", default="report/group_a_plus/latest/live_signal.json")
    parser.add_argument("--execution-plan", default="report/group_a_plus/latest/execution_plan.json")
    parser.add_argument(
        "--compounding-regime",
        default=None,
        help="Optional 00631L leveraged compounding regime JSON. Defaults to latest matching result; missing file is non-blocking.",
    )
    parser.add_argument(
        "--dfl-advisory",
        default="report/group_a_plus/latest/a2118_dfl_advisory.json",
        help="Optional A21.18 decision-focused advisory JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--dfl-active-date-audit",
        default="results/a2118_dfl_active_date_audit_latest.json",
        help="Optional A21.18 DFL active-date audit JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--dfl-shadow-ensemble",
        default="report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json",
        help="Optional A21.18 DFL shadow ensemble JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--finstressts-decision-snapshot",
        default="report/group_a_plus/latest/finstressts_decision_snapshot.json",
        help="Optional FinStressTS consolidated decision snapshot JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--trigate-vol-memory-shadow",
        default="report/group_a_plus/latest/trigate_vol_memory_shadow.json",
        help="Optional tri-gate volatility-memory shadow JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--systemic-bubble-time-at-risk-review",
        default="report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json",
        help="Optional systemic bubble time-at-risk review JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--illiquidity-network-readiness-review",
        default="report/group_a_plus/latest/illiquidity_network_readiness_review.json",
        help="Optional illiquidity-network readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--speculative-influence-network-readiness-review",
        default="report/group_a_plus/latest/speculative_influence_network_readiness_review.json",
        help="Optional speculative-influence-network readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--sin-lite-proxy",
        default="report/group_a_plus/latest/sin_lite_proxy.json",
        help="Optional SIN-lite daily OHLCV proxy JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--hmm-wj-synthetic-scenario-readiness-review",
        default="report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json",
        help="Optional HMM-WJ synthetic scenario readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--dynamic-cvar-tail-cost-readiness-review",
        default="report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json",
        help="Optional dynamic CVaR tail/cost readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--synthetic-augmentation-validation-readiness-review",
        default="report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json",
        help="Optional synthetic augmentation validation readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--intervention-fatigue-risk-budget-readiness-review",
        default="report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json",
        help="Optional intervention fatigue/risk-budget readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--letf-tracking-error-effective-fee-readiness-review",
        default="report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json",
        help="Optional LETF tracking-error/effective-fee readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--asian-etf-tail-analytics-readiness-review",
        default="report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json",
        help="Optional Asian ETF tail-analytics readiness JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--research-shadow-decision-snapshot",
        default="report/group_a_plus/latest/research_shadow_decision_snapshot.json",
        help="Optional consolidated research-shadow decision snapshot JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--gift-signed-approval-checklist-review",
        default="report/group_a_plus/latest/gift_signed_approval_checklist_review.json",
        help="Optional GIFT signed approval checklist review JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--gift-signed-approval-validator-smoke",
        default="report/group_a_plus/latest/gift_signed_approval_validator_smoke.json",
        help="Optional GIFT signed approval validator smoke JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--promotion-gate",
        default=None,
        help="Optional GroupA+ promotion gate JSON. Defaults to latest matching result when omitted.",
    )
    parser.add_argument("--check-date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--status-stage",
        default="pre_promotion",
        choices=["pre_promotion", "final", "baseline"],
        help="Label whether this daily status was built before or after promotion-gate outputs.",
    )
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument(
        "--max-dfl-frozen-staleness-days",
        type=int,
        default=14,
        help=(
            "Warn when the DFL advisory's frozen backtest file's live-window "
            "decisions fall this many calendar days behind check-date (it is "
            "never re-run automatically, so matched_decision_count becomes "
            "structurally 0 once this gap opens up)."
        ),
    )
    parser.add_argument("--output-prefix", default="results/group_a_plus_daily_status")
    parser.add_argument("--report-dir", default="report/group_a_plus")
    parser.add_argument("--skip-managed-report", action="store_true")
    args = parser.parse_args()

    report = _live_status_report(args) if args.mode == "live" else _baseline_status_report(args)

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = PROJECT_ROOT / prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = _write_markdown(md_path, report)
    managed_paths: dict[str, str] | None = None
    if not args.skip_managed_report:
        manager = GroupAPlusReportManager(args.report_dir)
        managed_paths = manager.save_daily_status(
            report,
            markdown=markdown,
            metadata={
                "legacy_json_path": str(json_path.relative_to(PROJECT_ROOT)),
                "legacy_markdown_path": str(md_path.relative_to(PROJECT_ROOT)),
                "baseline_path": str(Path(args.baseline)),
            },
        )
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    if managed_paths:
        print(f"Managed HTML: {managed_paths['html']}")
        print(f"Managed JSON: {managed_paths['json']}")
        print(f"Managed MD:   {managed_paths['markdown']}")
        print(f"Managed meta: {managed_paths['metadata']}")
        print(f"Latest ptr:   {managed_paths['latest']}")
    print(f"Overall: {report['overall_status']}")
    for check in report["checks"]:
        print(f"{check['name']}: {check['status']} - {check['detail']}")


if __name__ == "__main__":
    main()
