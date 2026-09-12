#!/usr/bin/env python3
"""Build assigned-vs-realized deployment shadow audit for GroupA+.

This implements a research-only check from arXiv 2608.08405: capacity claims
must separate assigned target exposure from realized deployment/fills. The audit
does not create orders and cannot change target weights.
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
DEFAULT_BROKER_SAMPLE = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_time_series_sample.json"
DEFAULT_BROKER_RECONCILIATION = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_reconciliation_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_08405_assigned_realized_deployment_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _int_map(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = int(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _float_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _date_key(payload: dict[str, Any]) -> str | None:
    value = payload.get("actual_data_date") or payload.get("requested_as_of_date") or payload.get("as_of")
    return str(value) if value else None


def _comparison_rows(
    *,
    live_shares: dict[str, int],
    plan_shares: dict[str, int],
    broker_positions: dict[str, int],
) -> list[dict[str, Any]]:
    tickers = sorted(set(live_shares) | set(plan_shares) | set(broker_positions))
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        assigned = live_shares.get(ticker)
        planned = plan_shares.get(ticker)
        realized = broker_positions.get(ticker)
        rows.append(
            {
                "ticker": ticker,
                "assigned_live_target_shares": assigned,
                "execution_plan_target_shares": planned,
                "broker_sample_latest_position": realized,
                "plan_minus_assigned": None if assigned is None or planned is None else planned - assigned,
                "realized_minus_assigned": None if assigned is None or realized is None else realized - assigned,
                "realized_position_available": realized is not None,
            }
        )
    return rows


def build_report(
    *,
    live_signal_path: Path,
    execution_plan_path: Path,
    broker_sample_path: Path,
    broker_reconciliation_path: Path,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    plan = _unwrap(_load(execution_plan_path))
    broker_sample = _load(broker_sample_path)
    broker_reconciliation = _load(broker_reconciliation_path)

    live_shares = _int_map(live.get("reference_target_shares_before_cost") or live.get("target_shares"))
    plan_shares = _int_map(plan.get("target_shares"))
    theoretical_plan_shares = _int_map(plan.get("theoretical_target_shares"))
    broker_positions = _int_map(broker_sample.get("latest_positions"))
    live_weights = _float_map(live.get("target_weights"))
    plan_weights = _float_map(plan.get("target_weights"))

    live_date = _date_key(live)
    plan_date = _date_key(plan)
    broker_date = str((broker_sample.get("coverage") or {}).get("last_transaction_date") or broker_sample.get("as_of") or "")
    broker_authoritative = broker_sample.get("authoritative_broker_export") is True
    broker_reconciled = (broker_reconciliation.get("decision") or {}).get("broker_holdings_reconciled") is True

    rows = _comparison_rows(
        live_shares=live_shares,
        plan_shares=plan_shares or theoretical_plan_shares,
        broker_positions=broker_positions,
    )
    assigned_logged = bool(live_weights or live_shares)
    planned_logged = bool(plan_weights or plan_shares or theoretical_plan_shares)
    realized_logged = bool(broker_authoritative and broker_reconciled and broker_positions)

    blockers: list[str] = []
    if not assigned_logged:
        blockers.append("assigned_live_target_missing")
    if not planned_logged:
        blockers.append("execution_plan_target_missing")
    if live_date and plan_date and live_date != plan_date:
        blockers.append("execution_plan_stale_vs_live_signal")
    if broker_sample and not broker_authoritative:
        blockers.append("broker_positions_not_authoritative")
    if broker_reconciliation and not broker_reconciled:
        blockers.append("broker_holdings_not_reconciled")
    if not realized_logged:
        blockers.append("realized_fill_or_deployment_series_missing")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_08405_assigned_realized_deployment_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blockers else "ready_for_capacity_shadow_review",
        "policy": "research_only_assigned_realized_deployment_audit_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf",
            "concept": "assigned_and_realized_deployment_must_be_separated_before_capacity_claims",
        },
        "dates": {
            "live_signal_date": live_date,
            "execution_plan_date": plan_date,
            "broker_sample_last_transaction_date": broker_date or None,
        },
        "coverage": {
            "assigned_live_targets_logged": assigned_logged,
            "execution_plan_targets_logged": planned_logged,
            "realized_authoritative_positions_logged": realized_logged,
            "broker_authoritative_export": broker_authoritative,
            "broker_holdings_reconciled": broker_reconciled,
            "comparison_ticker_count": len(rows),
        },
        "comparison": rows,
        "blocking_reasons": blockers,
        "decision": {
            "capacity_claim_allowed": False,
            "capacity_scaling_allowed": False,
            "latest_strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "live_order_generation_allowed": False,
            "summary": (
                "Assigned targets are available, but realized deployment/fill evidence is not "
                "authoritative and reconciled. Treat capacity evidence as blocked until same-run "
                "assigned, planned, and realized deployment series are logged."
            ),
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path),
            "broker_sample": str(broker_sample_path),
            "broker_reconciliation": str(broker_reconciliation_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    decision = report["decision"]
    lines = [
        "# 2608.08405 Assigned Vs Realized Deployment Shadow",
        "",
        f"- status: {report['status']}",
        f"- policy: {report['policy']}",
        f"- live_signal_date: {report['dates'].get('live_signal_date')}",
        f"- execution_plan_date: {report['dates'].get('execution_plan_date')}",
        f"- broker_sample_last_transaction_date: {report['dates'].get('broker_sample_last_transaction_date')}",
        f"- assigned_live_targets_logged: {coverage['assigned_live_targets_logged']}",
        f"- execution_plan_targets_logged: {coverage['execution_plan_targets_logged']}",
        f"- realized_authoritative_positions_logged: {coverage['realized_authoritative_positions_logged']}",
        f"- capacity_scaling_allowed: {decision['capacity_scaling_allowed']}",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Comparison"])
    for row in report["comparison"]:
        lines.append(
            "- {ticker}: assigned={assigned}, plan={planned}, broker_sample={realized}, "
            "plan_minus_assigned={plan_delta}, realized_minus_assigned={realized_delta}".format(
                ticker=row["ticker"],
                assigned=row["assigned_live_target_shares"],
                planned=row["execution_plan_target_shares"],
                realized=row["broker_sample_latest_position"],
                plan_delta=row["plan_minus_assigned"],
                realized_delta=row["realized_minus_assigned"],
            )
        )
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    date = str(report["dates"].get("live_signal_date") or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2608_08405_assigned_realized_deployment_shadow_{date}.json"


def write_report(report: dict[str, Any], *, output_path: Path, markdown_path: Path | None, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--broker-sample", default=str(DEFAULT_BROKER_SAMPLE))
    parser.add_argument("--broker-reconciliation", default=str(DEFAULT_BROKER_RECONCILIATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        broker_sample_path=_resolve(args.broker_sample),
        broker_reconciliation_path=_resolve(args.broker_reconciliation),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown) if args.markdown else None
    history = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output_path=output, markdown_path=markdown, history_dir=history)
    print(f"2608.08405 assigned/realized deployment shadow: {output}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
