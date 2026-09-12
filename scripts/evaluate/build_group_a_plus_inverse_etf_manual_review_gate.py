#!/usr/bin/env python3
"""Build a research-only 00632R inverse ETF manual-review gate report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from group_a_plus.operations.execution_guard import apply_inverse_etf_manual_review_gate  # noqa: E402


DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/inverse_etf_manual_review_gate.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/inverse_etf_manual_review_gate.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/inverse_etf_manual_review_gate/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def build_report(
    *,
    execution_plan_path: Path,
    as_of: str,
    realized_pnl_review_available: bool = False,
    cost_basis_available: bool = False,
    artifact_freshness_verified: bool = False,
    hedge_rationale_available: bool = False,
    manual_approval_record_available: bool = False,
) -> dict[str, Any]:
    plan = _load_plan(execution_plan_path)
    current = {str(k): int(v) for k, v in (plan.get("current_holdings") or {}).items()}
    target = {str(k): int(v) for k, v in (plan.get("target_shares") or {}).items()}
    guarded, guard = apply_inverse_etf_manual_review_gate(
        current,
        target,
        realized_pnl_review_available=realized_pnl_review_available,
        cost_basis_available=cost_basis_available,
        artifact_freshness_verified=artifact_freshness_verified,
        hedge_rationale_available=hedge_rationale_available,
        manual_approval_record_available=manual_approval_record_available,
    )
    blockers: list[str] = []
    if guard["status"] == "blocked":
        blockers.append("inverse_etf_trade_requires_manual_review")
        blockers.extend(f"missing_{item}" for item in guard.get("missing_checks", []))
    if plan.get("planning_status") == "manual_review_required":
        blockers.append("execution_plan_manual_review_required")
    if plan.get("manual_confirmation_required") is True:
        blockers.append("execution_plan_manual_confirmation_required")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_inverse_etf_manual_review_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_review",
        "policy": "research_only_inverse_etf_gate_no_live_weight_change",
        "source_incident": "docs/INCIDENT_20260804_GROUPA_PLUS_00632R_REALIZED_LOSS_AND_PREVENTION.md",
        "execution_plan": str(execution_plan_path),
        "plan_snapshot": {
            "requested_as_of_date": plan.get("requested_as_of_date"),
            "actual_data_date": plan.get("actual_data_date"),
            "planning_status": plan.get("planning_status"),
            "manual_confirmation_required": plan.get("manual_confirmation_required"),
            "execution_regime": plan.get("execution_regime"),
            "current_00632r_shares": current.get("00632R.TW", 0),
            "target_00632r_shares": target.get("00632R.TW", current.get("00632R.TW", 0)),
        },
        "guarded_target_shares": guarded,
        "guard": guard,
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00632r_open": False,
            "allow_00632r_auto_trade": False,
            "manual_review_required": bool(blockers),
            "keep_golden1_0531_unchanged": True,
            "recommended_use": "shadow_gate_input_for_retraining_candidate_review",
        },
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    snap = report["plan_snapshot"]
    guard = report["guard"]
    lines = [
        "# GroupA+ 00632R Inverse ETF Manual-Review Gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Execution plan: `{report['execution_plan']}`",
        "",
        "## Plan Snapshot",
        "",
        f"- Requested as-of: `{snap['requested_as_of_date']}`",
        f"- Actual data date: `{snap['actual_data_date']}`",
        f"- Planning status: `{snap['planning_status']}`",
        f"- Manual confirmation required: `{snap['manual_confirmation_required']}`",
        f"- Current 00632R shares: `{snap['current_00632r_shares']}`",
        f"- Target 00632R shares: `{snap['target_00632r_shares']}`",
        "",
        "## Gate",
        "",
        f"- Gate status: `{guard['status']}`",
        f"- Side: `{guard['side']}`",
        f"- Missing checks: `{guard['missing_checks']}`",
        f"- Allow 00632R auto trade: `{guard['allow_00632r_auto_trade']}`",
        "",
        "## Blocking Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in report["blocking_reasons"])
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Recommended use: `{report['decision']['recommended_use']}`",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Auto rebalance allowed: `{report['decision']['auto_rebalance_allowed']}`",
            "- No latest strategy, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(report["as_of"]).replace("-", "")
        (history_dir / f"inverse_etf_manual_review_gate_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--realized-pnl-review-available", action="store_true")
    parser.add_argument("--cost-basis-available", action="store_true")
    parser.add_argument("--artifact-freshness-verified", action="store_true")
    parser.add_argument("--hedge-rationale-available", action="store_true")
    parser.add_argument("--manual-approval-record-available", action="store_true")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        execution_plan_path=_resolve(args.execution_plan),
        as_of=str(args.as_of),
        realized_pnl_review_available=bool(args.realized_pnl_review_available),
        cost_basis_available=bool(args.cost_basis_available),
        artifact_freshness_verified=bool(args.artifact_freshness_verified),
        hedge_rationale_available=bool(args.hedge_rationale_available),
        manual_approval_record_available=bool(args.manual_approval_record_available),
    )
    write_report(
        report,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "guard_status": report["guard"]["status"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
