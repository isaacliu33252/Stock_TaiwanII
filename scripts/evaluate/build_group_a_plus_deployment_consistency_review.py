#!/usr/bin/env python3
"""Build a read-only deployment-consistency review for GroupA+.

Inspired by FinRL-X's weight-centric research-to-execution interface. This is a
governance artifact only: it verifies that live signal, execution plan, guards,
and health reports are aligned before any broker-actionable decision is trusted.
It never changes target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_DAILY_STATUS = PROJECT_ROOT / "report/group_a_plus/latest/daily_status.json"
DEFAULT_OPS_HEALTH = PROJECT_ROOT / "report/group_a_plus/latest/ops_health.json"
DEFAULT_SECURITIES_LENDING_SOURCE_STATUS = (
    PROJECT_ROOT / "report/group_a_plus/latest/securities_lending_0050_source_status.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/deployment_consistency_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/deployment_consistency/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if payload.get("success") is True and isinstance(data, dict) else payload


def _unwrap_daily_status(payload: dict[str, Any]) -> dict[str, Any]:
    unwrapped = _unwrap(payload)
    if unwrapped.get("report_type") == "daily_status" and isinstance(unwrapped.get("json"), str):
        managed_json = _resolve(unwrapped["json"])
        managed_payload = _load(managed_json)
        if managed_payload:
            return _unwrap(managed_payload)
    return unwrapped


def _check_map(daily_status: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in daily_status.get("checks") or []:
        if isinstance(row, dict) and row.get("name"):
            out[str(row["name"])] = str(row.get("status", "unknown"))
    return out


def _check_detail_map(daily_status: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in daily_status.get("checks") or []:
        if isinstance(row, dict) and row.get("name"):
            out[str(row["name"])] = str(row.get("detail", ""))
    return out


def _source_freshness_summary(checks: dict[str, str], details: dict[str, str]) -> dict[str, Any]:
    status = checks.get("source_freshness")
    detail = details.get("source_freshness", "")
    detail_lower = detail.lower()
    has_required_stale = (
        "required strategy sources are stale or missing" in detail_lower
        or "hard strategy sources are stale or missing" in detail_lower
    )
    has_soft_stale = "soft strategy sources are stale or missing" in detail_lower
    return {
        "status": status,
        "detail": detail,
        "has_required_stale": has_required_stale,
        "has_soft_stale": has_soft_stale,
        "blocks_deployment": bool(status not in {None, "ok"} and (has_required_stale or not has_soft_stale)),
    }


def _nonzero_trade_count(plan: dict[str, Any]) -> int:
    trades = plan.get("trades")
    if isinstance(trades, list):
        return sum(1 for row in trades if isinstance(row, dict) and int(row.get("delta_shares") or 0) != 0)
    current = plan.get("current_holdings") or {}
    target = plan.get("target_shares") or {}
    return sum(
        1
        for ticker in set(current) | set(target)
        if int(current.get(ticker, 0) or 0) != int(target.get(ticker, 0) or 0)
    )


def _guard_summary(plan: dict[str, Any]) -> dict[str, Any]:
    guards = [row for row in plan.get("pre_trade_guards") or [] if isinstance(row, dict)]
    blocked = [row for row in guards if str(row.get("status")) == "blocked"]
    active = [row for row in guards if str(row.get("status")) in {"active", "blocked"}]
    impact = plan.get("guard_impact_summary") if isinstance(plan.get("guard_impact_summary"), dict) else {}
    return {
        "guard_count": len(guards),
        "active_guard_names": [str(row.get("name")) for row in active],
        "blocked_guard_names": [str(row.get("name")) for row in blocked],
        "blocked_trade_count": int(impact.get("combined_blocked_trade_count") or 0),
        "blocked_buy_notional": float(impact.get("combined_blocked_buy_notional") or 0.0),
        "combined_blocked_buys": impact.get("combined_blocked_buys") or [],
    }


def _gift_governance_summary(daily_status: dict[str, Any]) -> dict[str, Any]:
    group = daily_status.get("group_a_plus") if isinstance(daily_status.get("group_a_plus"), dict) else {}
    gift = (
        group.get("gift_signed_approval_governance")
        if isinstance(group.get("gift_signed_approval_governance"), dict)
        else {}
    )
    research = (
        group.get("research_shadow_decision_snapshot")
        if isinstance(group.get("research_shadow_decision_snapshot"), dict)
        else {}
    )
    research_summary = research.get("summary") if isinstance(research.get("summary"), dict) else {}
    if not gift and research_summary:
        gift = {
            "source": "research_shadow_decision_snapshot",
            "validation_status": research_summary.get("llm_state_reward_signed_approval_validation_status"),
            "signed_approval_record_valid": research_summary.get(
                "llm_state_reward_signed_approval_record_valid"
            ),
            "human_exception_approved": research_summary.get(
                "llm_state_reward_signed_approval_human_exception_approved"
            ),
            "non_ppo_shadow_queue_review_allowed": research_summary.get(
                "llm_state_reward_signed_approval_non_ppo_shadow_queue_review_allowed"
            ),
            "training_queue_allowed": research_summary.get("llm_state_reward_signed_approval_training_queue_allowed"),
            "model_training_allowed": research_summary.get("llm_state_reward_signed_approval_model_training_allowed"),
            "ppo_training_allowed": research_summary.get("llm_state_reward_signed_approval_ppo_training_allowed"),
            "promote_to_live": research_summary.get("llm_state_reward_signed_approval_promote_to_live"),
            "manual_approval_to_queue_training_allowed": research_summary.get(
                "llm_state_reward_manual_approval_to_queue_training_allowed"
            ),
            "training_queue_blocking_reasons": research_summary.get(
                "llm_state_reward_manual_approval_queue_blocking_reasons"
            )
            or [],
        }
    checklist = (
        group.get("gift_signed_approval_checklist_review")
        if isinstance(group.get("gift_signed_approval_checklist_review"), dict)
        else {}
    )
    smoke = (
        group.get("gift_signed_approval_validator_smoke")
        if isinstance(group.get("gift_signed_approval_validator_smoke"), dict)
        else {}
    )
    checklist_summary = checklist.get("summary") if isinstance(checklist.get("summary"), dict) else {}
    smoke_summary = smoke.get("summary") if isinstance(smoke.get("summary"), dict) else {}
    out = dict(gift)
    out.update(
        {
            "checklist_status": out.get("checklist_status", checklist.get("status")),
            "checklist_available_for_manual_completion": out.get(
                "checklist_available_for_manual_completion",
                (checklist.get("decision") or {}).get("checklist_available_for_manual_completion")
                if isinstance(checklist.get("decision"), dict)
                else None,
            ),
            "checklist_manual_completion_ready": out.get(
                "checklist_manual_completion_ready", checklist_summary.get("manual_completion_ready")
            ),
            "checklist_manual_completion_pending": out.get(
                "checklist_manual_completion_pending", checklist_summary.get("manual_completion_pending")
            ),
            "checklist_signed_record_exists": out.get(
                "checklist_signed_record_exists", checklist_summary.get("signed_record_exists")
            ),
            "validator_smoke_status": out.get("validator_smoke_status", smoke.get("status")),
            "validator_smoke_passed": out.get(
                "validator_smoke_passed",
                (smoke.get("decision") or {}).get("validator_smoke_passed")
                if isinstance(smoke.get("decision"), dict)
                else None,
            ),
            "validator_smoke_valid_record_accepted": out.get(
                "validator_smoke_valid_record_accepted",
                smoke_summary.get("valid_non_ppo_shadow_record_accepted"),
            ),
            "validator_smoke_blocks_00631l_add": out.get(
                "validator_smoke_blocks_00631l_add", smoke_summary.get("invalid_allow_00631l_add_blocked")
            ),
            "validator_smoke_blocks_model_training": out.get(
                "validator_smoke_blocks_model_training",
                smoke_summary.get("invalid_allow_model_training_command_blocked"),
            ),
            "formal_signed_record_written_by_smoke": out.get(
                "formal_signed_record_written_by_smoke", smoke_summary.get("formal_signed_record_written")
            ),
        }
    )
    return out


def build_review(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    execution_plan_path: Path = DEFAULT_EXECUTION_PLAN,
    daily_status_path: Path = DEFAULT_DAILY_STATUS,
    ops_health_path: Path = DEFAULT_OPS_HEALTH,
    securities_lending_source_status_path: Path = DEFAULT_SECURITIES_LENDING_SOURCE_STATUS,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    plan = _unwrap(_load(execution_plan_path))
    daily = _unwrap_daily_status(_load(daily_status_path))
    ops = _unwrap(_load(ops_health_path))
    securities_lending_source_status = _unwrap(_load(securities_lending_source_status_path))

    live_date = live.get("actual_data_date")
    plan_date = plan.get("actual_data_date")
    live_strategy = live.get("strategy_id")
    plan_strategy = plan.get("strategy_id")
    checks = _check_map(daily)
    check_details = _check_detail_map(daily)
    source_freshness = _source_freshness_summary(checks, check_details)
    guard_summary = _guard_summary(plan)
    gift_governance = _gift_governance_summary(daily)

    blockers: list[str] = []
    warnings: list[str] = []

    if not live:
        blockers.append("live_signal_missing")
    if not plan:
        blockers.append("execution_plan_missing")
    if live_date and plan_date and str(live_date) != str(plan_date):
        blockers.append("execution_plan_date_mismatch")
    if live_strategy and plan_strategy and str(live_strategy) != str(plan_strategy):
        blockers.append("strategy_id_mismatch")
    if guard_summary["guard_count"] == 0:
        blockers.append("pre_trade_guards_missing")
    if source_freshness["blocks_deployment"]:
        blockers.append("source_freshness_not_ok")
    elif checks.get("source_freshness") not in {None, "ok"}:
        warnings.append("source_freshness_soft_warning")
    if ops.get("errors"):
        blockers.append("ops_health_errors_present")
    if gift_governance:
        if gift_governance.get("signed_approval_record_valid") is not True:
            warnings.append("gift_signed_approval_record_missing_or_invalid")
        if gift_governance.get("human_exception_approved") is not True:
            warnings.append("gift_human_exception_not_approved")
        if gift_governance.get("training_queue_allowed") is True:
            blockers.append("gift_governance_unexpectedly_allows_training_queue")
        if gift_governance.get("model_training_allowed") is True:
            blockers.append("gift_governance_unexpectedly_allows_model_training")
        if gift_governance.get("ppo_training_allowed") is True:
            blockers.append("gift_governance_unexpectedly_allows_ppo_training")
        if gift_governance.get("promote_to_live") is True:
            blockers.append("gift_governance_unexpectedly_promotes_to_live")
        if gift_governance.get("validator_smoke_passed") is False:
            blockers.append("gift_signed_approval_validator_smoke_failed")
        if gift_governance.get("validator_smoke_blocks_00631l_add") is False:
            blockers.append("gift_validator_does_not_block_00631l_add")
        if gift_governance.get("validator_smoke_blocks_model_training") is False:
            blockers.append("gift_validator_does_not_block_model_training")
        if gift_governance.get("formal_signed_record_written_by_smoke") is True:
            blockers.append("gift_validator_smoke_wrote_formal_signed_record")
        if gift_governance.get("checklist_manual_completion_pending") is True:
            warnings.append("gift_signed_approval_manual_completion_pending")

    cash_input = plan.get("current_cash_input")
    cash_assumption = str(plan.get("cash_assumption") or "")
    cash_source_explicit = cash_input is not None and "explicit" in cash_assumption.lower()
    broker_actionable = True
    if not cash_source_explicit:
        warnings.append("cash_source_not_explicit")
        broker_actionable = False
    elif float(cash_input or 0.0) == 0.0 and _nonzero_trade_count(plan) > 0:
        warnings.append("cash_balance_zero_with_nonzero_trades")
        broker_actionable = False

    if plan.get("execution_allowed") is not True:
        warnings.append("execution_plan_not_allowed")
        broker_actionable = False
    if plan.get("manual_confirmation_required") is True:
        warnings.append("manual_confirmation_required")
        broker_actionable = False
    if checks.get("execution_plan_pre_trade_guard") not in {None, "ok"}:
        warnings.append("daily_status_pre_trade_guard_not_ok")
        broker_actionable = False

    status = "blocked" if blockers else ("manual_review_required" if warnings else "ok")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_deployment_consistency_review",
        "status": status,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "diagnostic_only_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2603.21330.pdf",
            "title": "FinRL-X: An AI-Native Modular Infrastructure for Quantitative Trading",
            "imported_concepts": [
                "weight_centric_interface",
                "research_to_execution_consistency",
                "execution_guard_monitoring",
                "target_vs_realized_allocation_tracking",
                "broker_actionability_gate",
            ],
            "not_imported": [
                "FinRL_X_engine",
                "DRL_allocator",
                "US_equity_paper_trading_performance",
                "automatic_weight_change",
            ],
        },
        "as_of": live.get("requested_as_of_date") or live_date or plan.get("requested_as_of_date"),
        "computed": {
            "live_actual_data_date": live_date,
            "execution_plan_actual_data_date": plan_date,
            "dates_aligned": bool(live_date and plan_date and str(live_date) == str(plan_date)),
            "live_strategy_id": live_strategy,
            "execution_plan_strategy_id": plan_strategy,
            "strategy_ids_aligned": bool(live_strategy and plan_strategy and str(live_strategy) == str(plan_strategy)),
            "daily_status_overall": daily.get("overall_status"),
            "daily_status_checks": checks,
            "daily_status_check_details": check_details,
            "source_freshness": source_freshness,
            "securities_lending_0050_source_status": securities_lending_source_status,
            "ops_health_status": ops.get("status"),
            "ops_health_errors": ops.get("errors") or [],
            "ops_health_warnings": ops.get("warnings") or [],
            "cash_source_explicit": cash_source_explicit,
            "cash_balance": float(cash_input or 0.0),
            "nonzero_trade_count": _nonzero_trade_count(plan),
            "execution_plan_allowed": bool(plan.get("execution_allowed") is True),
            "manual_confirmation_required": bool(plan.get("manual_confirmation_required") is True),
            "broker_actionable": bool(broker_actionable and not blockers),
            "guard_summary": guard_summary,
            "target_weights": live.get("target_weights") or plan.get("target_weights") or {},
            "execution_target_shares": plan.get("target_shares") or {},
            "gift_signed_approval_governance": gift_governance,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "broker_actionable": bool(broker_actionable and not blockers),
            "manual_review_required": bool(status != "ok"),
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
            "summary": (
                "Deployment-consistency review is diagnostic only. It may block or force manual review, "
                "but it never changes GroupA+ target weights."
            ),
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path),
            "daily_status": str(daily_status_path),
            "ops_health": str(ops_health_path),
            "securities_lending_0050_source_status": str(securities_lending_source_status_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(
    review: dict[str, Any],
    *,
    output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--daily-status", default=str(DEFAULT_DAILY_STATUS))
    parser.add_argument("--ops-health", default=str(DEFAULT_OPS_HEALTH))
    parser.add_argument("--securities-lending-source-status", default=str(DEFAULT_SECURITIES_LENDING_SOURCE_STATUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        daily_status_path=_resolve(args.daily_status),
        ops_health_path=_resolve(args.ops_health),
        securities_lending_source_status_path=_resolve(args.securities_lending_source_status),
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_review(review, output_path=output, history_dir=history_dir)
    print(f"Deployment consistency review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "broker_actionable": review["decision"]["broker_actionable"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
