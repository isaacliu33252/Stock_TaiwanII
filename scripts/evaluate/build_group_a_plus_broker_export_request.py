#!/usr/bin/env python3
"""Build a broker export request checklist for Group A+ reconciliation.

This creates an operational handoff artifact only. It does not read broker
accounts, generate orders, or modify target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECONCILIATION = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_reconciliation_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_export_request.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/broker_export_request.md"
DEFAULT_TEMPLATE = PROJECT_ROOT / "report/group_a_plus/latest/broker_authoritative_export_template.csv"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"
GROUP_A_PLUS_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash")


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
    return payload if isinstance(payload, dict) else {}


def build_broker_export_request(reconciliation: dict[str, Any]) -> dict[str, Any]:
    blockers = reconciliation.get("blocking_reasons") if isinstance(reconciliation.get("blocking_reasons"), list) else []
    comparison = reconciliation.get("comparison") if isinstance(reconciliation.get("comparison"), list) else []
    mismatches = [
        row
        for row in comparison
        if isinstance(row, dict) and row.get("matches_confirmed") is False
    ]
    required_fields = [
        "as_of_date",
        "account_id_or_alias",
        "ticker",
        "shares",
        "market_value",
        "cash_balance",
        "currency",
        "source_file_name",
        "export_generated_at",
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_export_request",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "request_only_no_order_generation_no_weight_change",
        "live_execution_effect": "none",
        "status": "required" if blockers else "not_required",
        "why_required": [
            "authoritative broker holdings/cash export is required before live order generation",
            "transaction-derived sample currently has negative positions or confirmed-share mismatches",
        ]
        if blockers
        else [],
        "current_reconciliation_status": reconciliation.get("status"),
        "current_reconciliation_as_of": reconciliation.get("as_of"),
        "current_blocking_reasons": blockers,
        "current_mismatches": mismatches,
        "required_export_fields": required_fields,
        "required_tickers": list(GROUP_A_PLUS_TICKERS),
        "acceptance_criteria": [
            "export as_of_date matches the intended execution date",
            "cash_balance is explicit and non-null",
            "all Group A+ tickers are present with zero shares when absent from the account",
            "no negative long-only ETF share positions unless separately documented as short inventory",
            "broker reconciliation can be rerun without authoritative_broker_export_missing",
        ],
        "next_commands_after_export_is_available": [
            ".venv/bin/python scripts/run/run_group_a_plus_broker_export_reconciliation.py --apply",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_consistency_review.py",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_summary.py",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_profit_deployment_readiness.py",
        ],
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "broker_export_required": bool(blockers),
        },
    }


def _write_template(path: Path) -> None:
    lines = [
        "as_of_date,account_id_or_alias,ticker,shares,market_value,cash_balance,currency,source_file_name,export_generated_at",
    ]
    for ticker in GROUP_A_PLUS_TICKERS:
        lines.append(f",,{ticker},,,,,,")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_md(path: Path, payload: dict[str, Any], template: Path) -> None:
    lines = [
        "# Group A+ Broker Export Request",
        "",
        f"- Status: `{payload['status']}`",
        f"- Live effect: `{payload['live_execution_effect']}`",
        f"- Current reconciliation: `{payload.get('current_reconciliation_status')}`",
        f"- Template: `{template}`",
        "",
        "## Current Blockers",
        "",
    ]
    blockers = payload.get("current_blocking_reasons") or []
    lines.extend(f"- `{item}`" for item in blockers)
    lines.extend(["", "## Required Fields", ""])
    lines.extend(f"- `{item}`" for item in payload["required_export_fields"])
    lines.extend(["", "## Acceptance Criteria", ""])
    lines.extend(f"- {item}" for item in payload["acceptance_criteria"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", default=str(DEFAULT_RECONCILIATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    args = parser.parse_args()

    payload = build_broker_export_request(_load(args.reconciliation))
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = _resolve(args.template)
    _write_template(template)
    _write_md(_resolve(args.output_md), payload, template)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = _resolve(args.results_dir) / f"group_a_plus_broker_export_request_{stamp}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "template": str(template), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
