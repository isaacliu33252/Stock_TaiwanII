#!/usr/bin/env python3
"""Build a research-only intervention fatigue / risk-budget readiness review.

Inspired by arXiv 2605.12462. This translates demand-response fatigue and
finite operational-budget ideas into GroupA+ trading governance. It never
changes target weights or unlocks execution.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_REBALANCE = PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review_20260720.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_DYNAMIC_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_RESEARCH_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/research_shadow_decision_snapshot.json"
DEFAULT_INTERVENTION_HISTORY = PROJECT_ROOT / "report/group_a_plus/latest/intervention_history.json"
DEFAULT_BROKER_HOLDINGS_HISTORY = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_time_series_sample.json"
DEFAULT_BROKER_RECONCILIATION = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_reconciliation_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/intervention_fatigue_risk_budget_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _trade_rows(execution_plan: dict[str, Any], market_impact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _nested(market_impact, "computed", "trade_rows")
    if isinstance(rows, list) and rows:
        return [row for row in rows if isinstance(row, dict)]
    plan_rows = execution_plan.get("orders") or execution_plan.get("trades") or []
    return [row for row in plan_rows if isinstance(row, dict)]


def _abs_float(value: Any) -> float:
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0.0


def _intervention_summary(trade_rows: list[dict[str, Any]]) -> dict[str, Any]:
    nonzero = []
    leverage_changes = []
    hedge_changes = []
    for row in trade_rows:
        delta = row.get("delta_shares")
        if delta is None:
            delta = row.get("target_shares", 0) - row.get("current_shares", 0)
        if _abs_float(delta) <= 0:
            continue
        nonzero.append(row)
        ticker = str(row.get("ticker") or "")
        if ticker == "00631L.TW":
            leverage_changes.append(row)
        if ticker == "00632R.TW":
            hedge_changes.append(row)
    return {
        "trade_count_nonzero": len(nonzero),
        "leverage_change_count": len(leverage_changes),
        "hedge_change_count": len(hedge_changes),
        "has_00631l_add_attempt": any(_abs_float(row.get("target_shares")) > _abs_float(row.get("current_shares")) for row in leverage_changes),
        "has_00632r_open_attempt": any(_abs_float(row.get("target_shares")) > _abs_float(row.get("current_shares")) for row in hedge_changes),
    }


def _history_summary(history: dict[str, Any]) -> dict[str, Any]:
    coverage = history.get("coverage") or {}
    entries = history.get("entries") if isinstance(history.get("entries"), list) else []
    recent_entries = [entry for entry in entries if isinstance(entry, dict)]
    return {
        "status": history.get("status"),
        "history_type": history.get("history_type"),
        "entry_count": int(coverage.get("entry_count") or len(recent_entries)),
        "blocked_entry_count": int(coverage.get("blocked_entry_count") or 0),
        "leverage_intervention_count": int(coverage.get("leverage_intervention_count") or 0),
        "hedge_intervention_count": int(coverage.get("hedge_intervention_count") or 0),
        "first_check_date": coverage.get("first_check_date"),
        "last_check_date": coverage.get("last_check_date"),
        "source_file_count": int(coverage.get("source_file_count") or 0),
    }


def _broker_holdings_summary(sample: dict[str, Any]) -> dict[str, Any]:
    coverage = sample.get("coverage") or {}
    return {
        "status": sample.get("status"),
        "history_type": sample.get("history_type"),
        "authoritative_broker_export": sample.get("authoritative_broker_export") is True,
        "transaction_count": int(coverage.get("transaction_count") or 0),
        "snapshot_count": int(coverage.get("snapshot_count") or 0),
        "first_transaction_date": coverage.get("first_transaction_date"),
        "last_transaction_date": coverage.get("last_transaction_date"),
        "latest_position_count": int(coverage.get("latest_position_count") or 0),
        "negative_position_count": int(coverage.get("negative_position_count") or 0),
    }


def _broker_reconciliation_summary(review: dict[str, Any]) -> dict[str, Any]:
    summary = review.get("summary") or {}
    return {
        "status": review.get("status"),
        "broker_holdings_reconciled": (review.get("decision") or {}).get("broker_holdings_reconciled"),
        "can_generate_live_orders": (review.get("decision") or {}).get("can_generate_live_orders"),
        "matched_confirmed_count": int(summary.get("matched_confirmed_count") or 0),
        "mismatched_confirmed_count": int(summary.get("mismatched_confirmed_count") or 0),
        "missing_confirmed_count": int(summary.get("missing_confirmed_count") or 0),
        "negative_position_count": int(summary.get("negative_position_count") or 0),
        "authoritative_broker_export": summary.get("authoritative_broker_export") is True,
    }


def build_review(
    *,
    execution_plan_path: Path,
    rebalance_path: Path,
    market_impact_path: Path,
    dynamic_cvar_path: Path,
    research_shadow_path: Path,
    intervention_history_path: Path = DEFAULT_INTERVENTION_HISTORY,
    broker_holdings_history_path: Path = DEFAULT_BROKER_HOLDINGS_HISTORY,
    broker_reconciliation_path: Path = DEFAULT_BROKER_RECONCILIATION,
) -> dict[str, Any]:
    execution_plan = _unwrap(_load(execution_plan_path))
    rebalance = _unwrap(_load(rebalance_path))
    market_impact = _unwrap(_load(market_impact_path))
    dynamic_cvar = _unwrap(_load(dynamic_cvar_path))
    research_shadow = _unwrap(_load(research_shadow_path))
    intervention_history = _unwrap(_load(intervention_history_path))
    broker_holdings_history = _unwrap(_load(broker_holdings_history_path))
    broker_reconciliation_review = _unwrap(_load(broker_reconciliation_path))

    rebalance_decision = _decision(rebalance)
    market_decision = _decision(market_impact)
    dynamic_decision = _decision(dynamic_cvar)
    research_decision = _decision(research_shadow)
    rows = _trade_rows(execution_plan, market_impact)
    intervention = _intervention_summary(rows)
    history = _history_summary(intervention_history)
    broker_holdings = _broker_holdings_summary(broker_holdings_history)
    broker_reconciliation = _broker_reconciliation_summary(broker_reconciliation_review)

    turnover = _nested(market_impact, "computed", "turnover")
    cash_buffer_gap = _nested(rebalance, "weights", "cash_buffer_gap_reference")
    target_weights = _nested(rebalance, "weights", "target_weights") or {}
    leverage_budget_target = float(target_weights.get("00631L.TW", 0.0) or 0.0)
    cash_budget_target = float(target_weights.get("cash", 0.0) or 0.0)

    blockers: list[str] = []
    warnings: list[str] = []
    missing = [
        name
        for name, payload in {
            "execution_plan": execution_plan,
            "rebalance_review": rebalance,
            "market_impact_readiness_review": market_impact,
            "dynamic_cvar_tail_cost_readiness_review": dynamic_cvar,
            "research_shadow_decision_snapshot": research_shadow,
        }.items()
        if not payload
    ]
    if missing:
        blockers.append("missing_required_inputs:" + ",".join(sorted(missing)))

    blockers.extend(["risk_budget_policy_not_promoted", "rl_environment_not_validated"])
    if broker_holdings["transaction_count"] <= 0:
        blockers.append("broker_holdings_time_series_missing")
    elif not broker_holdings["authoritative_broker_export"]:
        blockers.append("broker_holdings_time_series_sample_only")
    if broker_holdings["negative_position_count"] > 0:
        blockers.append("broker_holdings_time_series_has_negative_positions")
    if not broker_reconciliation_review:
        blockers.append("broker_holdings_reconciliation_missing")
    elif broker_reconciliation_review.get("status") == "blocked":
        blockers.append("broker_holdings_reconciliation_blocked")
    if broker_reconciliation["can_generate_live_orders"] is not True:
        blockers.append("broker_holdings_not_order_authoritative")
    if history["status"] != "available" or history["entry_count"] <= 0:
        blockers.append("intervention_history_not_normalized")
    if market_impact.get("status") == "blocked":
        blockers.append("market_impact_readiness_blocked")
    if dynamic_cvar.get("status") == "blocked":
        blockers.append("dynamic_cvar_tail_cost_readiness_blocked")
    if research_shadow.get("status") == "blocked":
        blockers.append("research_shadow_decision_snapshot_blocked")
    if rebalance_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("rebalance_review_disallows_auto_rebalance")
    if rebalance_decision.get("target_weight_change_allowed") is not True:
        blockers.append("rebalance_review_disallows_target_weight_change")
    if market_decision.get("allow_00631l_add") is not True:
        blockers.append("market_impact_disallows_00631l_add")
    if dynamic_decision.get("tail_cost_readiness_ready") is not True:
        blockers.append("tail_cost_readiness_not_ready")
    if research_decision.get("allow_00631l_add") is not True:
        blockers.append("research_shadow_disallows_00631l_add")
    if isinstance(turnover, (int, float)) and turnover >= 0.5:
        blockers.append("turnover_at_or_above_pacing_limit")

    if intervention["trade_count_nonzero"]:
        warnings.append(f"pending_intervention_count:{intervention['trade_count_nonzero']}")
    if cash_buffer_gap is not None:
        warnings.append(f"cash_buffer_gap_reference:{cash_buffer_gap}")

    as_of = (
        _nested(rebalance, "dates", "requested_as_of_date")
        or dynamic_cvar.get("as_of")
        or "2026-07-20"
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_intervention_fatigue_risk_budget_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_intervention_fatigue_risk_budget_pacing_no_weight_change",
        "status": "blocked" if blockers else "research_ready",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.12462.pdf",
            "title": "Towards Affordable Energy: A Gymnasium Environment for Electric Utility Demand-Response Programs",
            "imported_concepts": [
                "modular_gym_style_environment",
                "multi_objective_reward_with_cvar_penalty",
                "intervention_fatigue",
                "finite_risk_budget_pacing",
                "baseline_policy_comparison_before_promotion",
            ],
            "not_imported": [
                "electricity_market_data",
                "ercot_caiso_calibration",
                "ppo_live_policy",
                "automatic_target_weight_change",
            ],
        },
        "component_readiness": {
            "rebalance": {
                "status": rebalance.get("status"),
                "auto_rebalance_allowed": rebalance_decision.get("auto_rebalance_allowed"),
                "target_weight_change_allowed": rebalance_decision.get("target_weight_change_allowed"),
                "allow_00631l_add": rebalance_decision.get("allow_00631l_add"),
                "cash_buffer_gap_reference": cash_buffer_gap,
            },
            "market_impact": {
                "status": market_impact.get("status"),
                "turnover": turnover,
                "auto_rebalance_allowed": market_decision.get("auto_rebalance_allowed"),
                "allow_00631l_add": market_decision.get("allow_00631l_add"),
            },
            "dynamic_cvar_tail_cost": {
                "status": dynamic_cvar.get("status"),
                "tail_cost_readiness_ready": dynamic_decision.get("tail_cost_readiness_ready"),
                "allow_00631l_add": dynamic_decision.get("allow_00631l_add"),
            },
            "research_shadow": {
                "status": research_shadow.get("status"),
                "allow_00631l_add": research_decision.get("allow_00631l_add"),
            },
        },
        "intervention_fatigue": {
            **intervention,
            "cooldown_policy_implemented": False,
            "recent_intervention_window_days": None,
            "normalized_history_available": history["status"] == "available" and history["entry_count"] > 0,
            "history_entry_count": history["entry_count"],
            "history_blocked_entry_count": history["blocked_entry_count"],
            "history_leverage_intervention_count": history["leverage_intervention_count"],
            "history_hedge_intervention_count": history["hedge_intervention_count"],
        },
        "intervention_history": history,
        "broker_holdings_time_series": broker_holdings,
        "broker_holdings_reconciliation": broker_reconciliation,
        "risk_budget_pacing": {
            "leverage_budget_target_weight": leverage_budget_target,
            "cash_budget_target_weight": cash_budget_target,
            "risk_budget_policy_promoted": False,
            "turnover_pacing_limit": 0.5,
            "turnover": turnover,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Intervention fatigue and risk-budget pacing are governance-only. "
                "Current input gates and missing intervention history prevent any "
                "automatic rebalance or leverage add."
            ),
            "intervention_fatigue_ready": False,
            "risk_budget_pacing_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "execution_plan": str(execution_plan_path),
            "rebalance": str(rebalance_path),
            "market_impact": str(market_impact_path),
            "dynamic_cvar_tail_cost": str(dynamic_cvar_path),
            "research_shadow": str(research_shadow_path),
            "intervention_history": str(intervention_history_path),
            "broker_holdings_time_series": str(broker_holdings_history_path),
            "broker_holdings_reconciliation": str(broker_reconciliation_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review.get("as_of")).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--rebalance", default=str(DEFAULT_REBALANCE))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--dynamic-cvar", default=str(DEFAULT_DYNAMIC_CVAR))
    parser.add_argument("--research-shadow", default=str(DEFAULT_RESEARCH_SHADOW))
    parser.add_argument("--intervention-history", default=str(DEFAULT_INTERVENTION_HISTORY))
    parser.add_argument("--broker-holdings-history", default=str(DEFAULT_BROKER_HOLDINGS_HISTORY))
    parser.add_argument("--broker-reconciliation", default=str(DEFAULT_BROKER_RECONCILIATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        execution_plan_path=_resolve(args.execution_plan),
        rebalance_path=_resolve(args.rebalance),
        market_impact_path=_resolve(args.market_impact),
        dynamic_cvar_path=_resolve(args.dynamic_cvar),
        research_shadow_path=_resolve(args.research_shadow),
        intervention_history_path=_resolve(args.intervention_history),
        broker_holdings_history_path=_resolve(args.broker_holdings_history),
        broker_reconciliation_path=_resolve(args.broker_reconciliation),
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_review(review, output, history_dir)
    print(f"Intervention fatigue/risk-budget readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "intervention_fatigue_ready": review["decision"]["intervention_fatigue_ready"],
                "risk_budget_pacing_ready": review["decision"]["risk_budget_pacing_ready"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
