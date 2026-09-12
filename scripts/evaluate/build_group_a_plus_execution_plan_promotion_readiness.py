#!/usr/bin/env python3
"""Assess whether a same-day shadow execution plan can replace the live plan.

This is a promotion-readiness report only. It never overwrites
report/group_a_plus/latest/execution_plan.json and never creates orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHADOW_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_same_day_shadow.json"
DEFAULT_SHADOW_INTEGRITY = PROJECT_ROOT / "report/group_a_plus/latest/daily_artifact_integrity_shadow_same_day.json"
DEFAULT_BROKER_RECONCILIATION = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_reconciliation_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_promotion_readiness.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_promotion_readiness.md"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load(path: str | Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def build_execution_plan_promotion_readiness(
    *,
    shadow_plan: dict[str, Any],
    shadow_integrity: dict[str, Any],
    broker_reconciliation: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not shadow_plan:
        blockers.append("shadow_execution_plan_missing")
    if not shadow_integrity:
        blockers.append("shadow_daily_artifact_integrity_missing")
    if not broker_reconciliation:
        blockers.append("broker_reconciliation_missing")

    if shadow_integrity and shadow_integrity.get("status") == "error":
        blockers.append("shadow_artifact_integrity_has_errors")
    if shadow_integrity:
        warnings.extend(f"shadow_integrity:{item}" for item in _list(shadow_integrity, "warnings"))

    if broker_reconciliation.get("status") != "reconciled_for_manual_review":
        blockers.append("broker_reconciliation_not_reconciled")
    broker_decision = broker_reconciliation.get("decision") if isinstance(broker_reconciliation.get("decision"), dict) else {}
    if broker_decision.get("can_generate_live_orders") is not True:
        blockers.append("broker_gate_disallows_live_orders")
    if broker_decision.get("target_weight_change_allowed") is not True:
        blockers.append("broker_gate_disallows_target_weight_change")

    cash_input = shadow_plan.get("current_cash_input")
    cash_assumption = str(shadow_plan.get("cash_assumption") or "")
    nonzero_trades = [
        row
        for row in _list(shadow_plan, "trades")
        if isinstance(row, dict) and int(row.get("delta_shares") or 0) != 0
    ]
    if cash_input is None:
        blockers.append("shadow_plan_cash_input_missing")
    elif float(cash_input) == 0.0 and nonzero_trades:
        blockers.append("shadow_plan_zero_cash_with_nonzero_trades")
    if "explicit" not in cash_assumption.lower():
        blockers.append("shadow_plan_cash_source_not_explicit")
    if str(shadow_plan.get("holdings_source") or "").endswith(".xlsx"):
        blockers.append("shadow_plan_uses_workbook_holdings_not_authoritative_broker_export")

    plan_holdings = shadow_plan.get("current_holdings") if isinstance(shadow_plan.get("current_holdings"), dict) else {}
    broker_comparison = _list(broker_reconciliation, "comparison")
    missing_nonzero_broker_holdings = [
        str(row.get("ticker"))
        for row in broker_comparison
        if isinstance(row, dict)
        and int(row.get("confirmed_shares") or 0) != 0
        and str(row.get("ticker")) not in plan_holdings
    ]
    if missing_nonzero_broker_holdings:
        blockers.append("broker_nonzero_holding_missing_from_execution_plan")

    if shadow_plan.get("actual_data_date") != ((shadow_integrity.get("dates") or {}).get("execution_plan_actual_data_date")):
        warnings.append("shadow_plan_date_not_equal_shadow_integrity_plan_date")

    status = "ready_for_human_promotion_review" if not blockers else "blocked"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_execution_plan_promotion_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "promotion_readiness_only_no_file_replacement_no_orders",
        "live_execution_effect": "none",
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "summary": {
            "shadow_plan_actual_data_date": shadow_plan.get("actual_data_date"),
            "shadow_integrity_status": shadow_integrity.get("status"),
            "shadow_integrity_errors": _list(shadow_integrity, "errors"),
            "broker_reconciliation_status": broker_reconciliation.get("status"),
            "shadow_plan_current_cash_input": cash_input,
            "shadow_plan_holdings_source": shadow_plan.get("holdings_source"),
            "shadow_plan_nonzero_trade_count": len(nonzero_trades),
            "broker_nonzero_holdings_missing_from_plan": missing_nonzero_broker_holdings,
        },
        "decision": {
            "can_replace_live_execution_plan": status == "ready_for_human_promotion_review",
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "requires_authoritative_broker_export": "broker_reconciliation_not_reconciled" in blockers,
        },
        "next_commands_after_blockers_clear": [
            ".venv/bin/python scripts/run/run_group_a_plus_broker_export_reconciliation.py --apply",
            ".venv/bin/python -m group_a_plus.operations.execution_plan --as-of YYYY-MM-DD --cash-balance CASH --output results/group_a_plus_execution_plan_v2_YYYYMMDD.json --latest-pointer report/group_a_plus/latest/execution_plan.json",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_daily_artifact_integrity.py --check-date YYYY-MM-DD",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_consistency_review.py",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_summary.py",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_profit_deployment_readiness.py",
        ],
    }


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Group A+ Execution Plan Promotion Readiness",
        "",
        f"- Status: `{payload['status']}`",
        f"- Live effect: `{payload['live_execution_effect']}`",
        f"- Can replace live execution plan: `{payload['decision']['can_replace_live_execution_plan']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{item}`" for item in payload["warnings"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow-plan", default=str(DEFAULT_SHADOW_PLAN))
    parser.add_argument("--shadow-integrity", default=str(DEFAULT_SHADOW_INTEGRITY))
    parser.add_argument("--broker-reconciliation", default=str(DEFAULT_BROKER_RECONCILIATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    args = parser.parse_args()

    payload = build_execution_plan_promotion_readiness(
        shadow_plan=_load(args.shadow_plan),
        shadow_integrity=_load(args.shadow_integrity),
        broker_reconciliation=_load(args.broker_reconciliation),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(_resolve(args.output_md), payload)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = _resolve(args.results_dir) / f"group_a_plus_execution_plan_promotion_readiness_{stamp}.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
