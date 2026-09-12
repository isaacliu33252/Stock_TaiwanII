#!/usr/bin/env python3
"""Build a shadow-only alpha-translation readiness report for Group A++.

This imports the governance framework from arXiv 2609.04917. The paper is a
critical review, not a trading signal, so this report only grades whether a
profit candidate has enough evidence to be considered for promotion review.
It never changes live target weights or creates orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFIT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/profit_deployment_readiness.json"
DEFAULT_SHADOW_REGISTRY = PROJECT_ROOT / "report/group_a_plus/latest/shadow_artifact_registry.json"
DEFAULT_DAILY_ARTIFACT_INTEGRITY = PROJECT_ROOT / "report/group_a_plus/latest/daily_artifact_integrity.json"
DEFAULT_OPS_HEALTH = PROJECT_ROOT / "report/group_a_plus/latest/ops_health.json"
DEFAULT_EXECUTION_PLAN_PROMOTION = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_promotion_readiness.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_CAPACITY_CROWDING = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_capacity_crowding_readiness.json"
DEFAULT_SELECTION_LEDGER = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_selection_ledger.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_alpha_translation_readiness.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_alpha_translation_readiness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2609_04917_alpha_translation_readiness/history"


DIMENSIONS = (
    "temporality",
    "selection_control",
    "portfolio_mapping",
    "implementation_realism",
    "risk_benchmark",
    "external_validity",
    "operational_provenance",
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _truthy(value: Any) -> bool:
    return bool(value) and str(value).lower() not in {"false", "none", "null", "0"}


def _status(blockers: list[str], warnings: list[str]) -> str:
    if blockers:
        return "blocked"
    if warnings:
        return "warning"
    return "pass"


def _dimension(status: str, evidence: list[str], blockers: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "evidence": evidence,
        "blockers": blockers,
        "warnings": warnings,
    }


def _registry_count(registry: dict[str, Any]) -> int | None:
    for key in ("artifacts", "entries", "items", "rows"):
        value = registry.get(key)
        if isinstance(value, list):
            return len(value)
    if isinstance(registry.get("by_path"), dict):
        return len(registry["by_path"])
    return None


def _temporality(
    *,
    live_signal: dict[str, Any],
    daily_artifact_integrity: dict[str, Any],
    ops_health: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    actual_date = live_signal.get("actual_data_date") or live_signal.get("date")
    if actual_date:
        evidence.append(f"live_signal_actual_data_date={actual_date}")
    else:
        blockers.append("live_signal_actual_data_date_missing")
    integrity_status = str(daily_artifact_integrity.get("status") or "missing")
    if integrity_status == "missing":
        warnings.append("daily_artifact_integrity_missing")
    elif integrity_status.lower() in {"error", "blocked"}:
        blockers.append(f"daily_artifact_integrity_status={integrity_status}")
    else:
        evidence.append(f"daily_artifact_integrity_status={integrity_status}")
    ops_status = str(ops_health.get("status") or "missing")
    if ops_status == "missing":
        warnings.append("ops_health_missing")
    elif ops_status.lower() in {"error", "blocked"}:
        blockers.append(f"ops_health_status={ops_status}")
    else:
        evidence.append(f"ops_health_status={ops_status}")
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def _selection_control(
    *,
    registry: dict[str, Any],
    profit_readiness: dict[str, Any],
    selection_ledger: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    count = _registry_count(registry)
    if count is None:
        warnings.append("shadow_artifact_registry_count_unavailable")
    else:
        evidence.append(f"shadow_artifact_registry_count={count}")
    active = _as_list(profit_readiness.get("active_shadow_candidates"))
    if active:
        evidence.append("active_shadow_candidates=" + ",".join(map(str, active)))
    else:
        warnings.append("no_active_shadow_candidates_to_score")
    if selection_ledger:
        ledger_status = str(selection_ledger.get("status") or "unknown")
        evidence.append(f"selection_ledger_status={ledger_status}")
        if not (selection_ledger.get("decision") or {}).get("selection_ledger_available"):
            blockers.append("selection_ledger_not_available")
        if not (selection_ledger.get("decision") or {}).get("confirmatory_specification_frozen"):
            blockers.append("confirmatory_specification_not_frozen_for_2609_04917_gate")
        blockers.extend(f"selection_ledger:{item}" for item in _as_list(selection_ledger.get("blocking_reasons")))
    else:
        blockers.append("model_selection_budget_ledger_not_consolidated")
        blockers.append("confirmatory_specification_not_frozen_for_2609_04917_gate")
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def _portfolio_mapping(*, profit_readiness: dict[str, Any], live_signal: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    weights = live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {}
    if weights:
        evidence.append("live_signal_target_weights_available")
    else:
        warnings.append("live_signal_target_weights_missing")
    decision = profit_readiness.get("decision") if isinstance(profit_readiness.get("decision"), dict) else {}
    if decision.get("creates_orders") is False:
        evidence.append("profit_readiness_creates_orders=false")
    if decision.get("target_weight_change_allowed") is False:
        evidence.append("profit_readiness_target_weight_change_allowed=false")
    if not profit_readiness:
        warnings.append("profit_deployment_readiness_missing")
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def _implementation_realism(
    *,
    market_impact: dict[str, Any],
    execution_plan_promotion: dict[str, Any],
    profit_readiness: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    impact_status = str(market_impact.get("status") or "missing")
    if impact_status == "missing":
        blockers.append("market_impact_readiness_missing")
    elif impact_status.lower() in {"blocked", "error"}:
        blockers.append(f"market_impact_readiness_status={impact_status}")
    else:
        evidence.append(f"market_impact_readiness_status={impact_status}")
    promotion_status = str(execution_plan_promotion.get("status") or "missing")
    if promotion_status == "missing":
        blockers.append("execution_plan_promotion_readiness_missing")
    elif promotion_status.lower() in {"blocked", "error"}:
        blockers.append(f"execution_plan_promotion_status={promotion_status}")
    else:
        evidence.append(f"execution_plan_promotion_status={promotion_status}")
    cost_status = (
        profit_readiness.get("turnover_cost_robustness_review", {}).get("status")
        if isinstance(profit_readiness.get("turnover_cost_robustness_review"), dict)
        else None
    )
    if cost_status:
        evidence.append(f"turnover_cost_robustness_status={cost_status}")
        if str(cost_status).startswith("blocked"):
            blockers.append(f"turnover_cost_robustness_status={cost_status}")
    else:
        warnings.append("turnover_cost_robustness_status_missing")
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def _risk_benchmark(*, profit_readiness: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    for key in ("tail_sensitive_review", "candidate_tail_review", "bootstrap_promotion_gate"):
        item = profit_readiness.get(key) if isinstance(profit_readiness.get(key), dict) else {}
        status = item.get("status")
        if status:
            evidence.append(f"{key}_status={status}")
        else:
            warnings.append(f"{key}_missing")
    bootstrap = profit_readiness.get("bootstrap_promotion_gate")
    if isinstance(bootstrap, dict) and str(bootstrap.get("status") or "").startswith("blocked"):
        blockers.append(f"bootstrap_promotion_gate_status={bootstrap.get('status')}")
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def _external_validity(
    *,
    profit_readiness: dict[str, Any],
    capacity_crowding: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    staged = profit_readiness.get("staged_reentry_promotion_review")
    if isinstance(staged, dict) and staged.get("status"):
        evidence.append(f"staged_reentry_promotion_status={staged.get('status')}")
        if str(staged.get("status")).startswith("blocked"):
            blockers.append(f"staged_reentry_promotion_status={staged.get('status')}")
    else:
        warnings.append("staged_reentry_promotion_review_missing")
    capacity_status = capacity_crowding.get("status")
    if capacity_status:
        evidence.append(f"capacity_crowding_status={capacity_status}")
        if str(capacity_status).startswith("blocked"):
            blockers.append(f"capacity_crowding_status={capacity_status}")
    else:
        warnings.append("capacity_crowding_readiness_missing")
    blockers.append("prospective_precommitted_decision_record_not_sufficient_for_live_claim")
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def _operational_provenance(
    *,
    profit_readiness: dict[str, Any],
    execution_plan: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = []
    source_status = profit_readiness.get("source_status") if isinstance(profit_readiness.get("source_status"), dict) else {}
    if source_status:
        evidence.append("profit_readiness_source_status_available")
    else:
        warnings.append("profit_readiness_source_status_missing")
    plan_status = execution_plan.get("planning_status") or execution_plan.get("status")
    if plan_status:
        evidence.append(f"execution_plan_status={plan_status}")
    else:
        warnings.append("execution_plan_status_missing")
    blockers.extend(map(str, _as_list(profit_readiness.get("deployment_blockers"))))
    return _dimension(_status(blockers, warnings), evidence, blockers, warnings)


def build_report(
    *,
    profit_readiness_path: Path,
    shadow_registry_path: Path,
    daily_artifact_integrity_path: Path,
    ops_health_path: Path,
    execution_plan_promotion_path: Path,
    market_impact_path: Path,
    capacity_crowding_path: Path,
    selection_ledger_path: Path,
    live_signal_path: Path,
    execution_plan_path: Path,
    as_of: str | None = None,
) -> dict[str, Any]:
    profit_readiness = _load_optional(profit_readiness_path)
    registry = _load_optional(shadow_registry_path)
    daily_artifact_integrity = _load_optional(daily_artifact_integrity_path)
    ops_health = _load_optional(ops_health_path)
    execution_plan_promotion = _load_optional(execution_plan_promotion_path)
    market_impact = _load_optional(market_impact_path)
    capacity_crowding = _load_optional(capacity_crowding_path)
    selection_ledger = _load_optional(selection_ledger_path)
    live_signal = _load_optional(live_signal_path)
    execution_plan = _load_optional(execution_plan_path)

    dimensions = {
        "temporality": _temporality(
            live_signal=live_signal,
            daily_artifact_integrity=daily_artifact_integrity,
            ops_health=ops_health,
        ),
        "selection_control": _selection_control(
            registry=registry,
            profit_readiness=profit_readiness,
            selection_ledger=selection_ledger,
        ),
        "portfolio_mapping": _portfolio_mapping(profit_readiness=profit_readiness, live_signal=live_signal),
        "implementation_realism": _implementation_realism(
            market_impact=market_impact,
            execution_plan_promotion=execution_plan_promotion,
            profit_readiness=profit_readiness,
        ),
        "risk_benchmark": _risk_benchmark(profit_readiness=profit_readiness),
        "external_validity": _external_validity(
            profit_readiness=profit_readiness,
            capacity_crowding=capacity_crowding,
        ),
        "operational_provenance": _operational_provenance(
            profit_readiness=profit_readiness,
            execution_plan=execution_plan,
        ),
    }
    blocked_dimensions = [name for name, item in dimensions.items() if item["status"] == "blocked"]
    warning_dimensions = [name for name, item in dimensions.items() if item["status"] == "warning"]
    status = "blocked_for_live_promotion" if blocked_dimensions else "available_for_human_review"
    if not blocked_dimensions and warning_dimensions:
        status = "available_with_warnings"

    active = _as_list(profit_readiness.get("active_shadow_candidates"))
    live_ready = _as_list(profit_readiness.get("live_ready_shadow_candidates"))
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_alpha_translation_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "shadow_only_alpha_translation_governance_no_weight_change",
        "live_execution_effect": "none",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2609.04917_ai_equity_crypto_markets_profitability_limits.pdf",
            "arxiv": "2609.04917",
            "title": "Artificial Intelligence in Equity and Crypto Markets: Progress, Profitability Evidence, and the Limits of Automated Investing",
            "imported_concepts": [
                "alpha_translation_chain",
                "multidimensional_evidence_profile",
                "point_in_time_information_and_model_versions",
                "decision_aligned_objectives_with_abstention",
                "joint_signal_portfolio_execution_evaluation",
                "controlled_adaptation_and_authority_matched_governance",
            ],
        },
        "status": status,
        "dimensions": dimensions,
        "blocked_dimensions": blocked_dimensions,
        "warning_dimensions": warning_dimensions,
        "active_shadow_candidates": active,
        "live_ready_shadow_candidates_before_2609_04917_gate": live_ready,
        "live_ready_shadow_candidates_after_2609_04917_gate": [] if blocked_dimensions else live_ready,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "creates_orders": False,
            "latest_strategy_change_allowed": False,
            "human_promotion_review_allowed": not bool(blocked_dimensions),
            "requires_alpha_translation_gate_before_live": True,
            "blocks_live_due_to_dimensions": blocked_dimensions,
        },
        "recommended_next_actions": [
            "consolidate a model-selection budget ledger for active shadow candidates",
            "freeze one confirmatory specification before the next OOS/prospective window",
            "require same-date signal, portfolio, execution-cost, and capacity evidence before promotion",
            "keep every 2609.04917-derived check shadow-only until all seven dimensions pass",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Alpha-Translation Readiness",
        "",
        f"- status: {report['status']}",
        f"- policy: {report['policy']}",
        f"- live_execution_effect: {report['live_execution_effect']}",
        f"- active_shadow_candidates: {', '.join(map(str, report['active_shadow_candidates'])) or 'none'}",
        f"- blocked_dimensions: {', '.join(report['blocked_dimensions']) or 'none'}",
        "",
        "## Dimension Summary",
        "",
        "| dimension | status | blockers | warnings |",
        "| --- | --- | --- | --- |",
    ]
    for name in DIMENSIONS:
        item = report["dimensions"][name]
        lines.append(
            "| {name} | {status} | {blockers} | {warnings} |".format(
                name=name,
                status=item["status"],
                blockers=", ".join(item["blockers"]) or "none",
                warnings=", ".join(item["warnings"]) or "none",
            )
        )
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in report["recommended_next_actions"])
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = as_of or datetime.now().strftime("%Y%m%d")
    return history_dir / f"2609_04917_alpha_translation_readiness_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profit-readiness", default=str(DEFAULT_PROFIT_READINESS))
    parser.add_argument("--shadow-registry", default=str(DEFAULT_SHADOW_REGISTRY))
    parser.add_argument("--daily-artifact-integrity", default=str(DEFAULT_DAILY_ARTIFACT_INTEGRITY))
    parser.add_argument("--ops-health", default=str(DEFAULT_OPS_HEALTH))
    parser.add_argument("--execution-plan-promotion", default=str(DEFAULT_EXECUTION_PLAN_PROMOTION))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--capacity-crowding", default=str(DEFAULT_CAPACITY_CROWDING))
    parser.add_argument("--selection-ledger", default=str(DEFAULT_SELECTION_LEDGER))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    report = build_report(
        profit_readiness_path=_resolve(args.profit_readiness),
        shadow_registry_path=_resolve(args.shadow_registry),
        daily_artifact_integrity_path=_resolve(args.daily_artifact_integrity),
        ops_health_path=_resolve(args.ops_health),
        execution_plan_promotion_path=_resolve(args.execution_plan_promotion),
        market_impact_path=_resolve(args.market_impact),
        capacity_crowding_path=_resolve(args.capacity_crowding),
        selection_ledger_path=_resolve(args.selection_ledger),
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        as_of=args.as_of,
    )

    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    history = _history_path(_resolve(args.history_dir), args.as_of)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    history.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
