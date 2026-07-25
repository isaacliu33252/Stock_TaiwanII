#!/usr/bin/env python3
"""Build a compact diagnostic for why the GroupA+ promotion gate is blocked."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMOTION_GATE = PROJECT_ROOT / "results/group_a_plus_promotion_gate_20260722.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/promotion_blocked_diagnostic.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/promotion_blocked_diagnostic.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/promotion_blocked_diagnostic/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _failed_drift_checks(panel_drift_gate: dict[str, Any]) -> list[dict[str, Any]]:
    checks = _dict(panel_drift_gate, "checks")
    out: list[dict[str, Any]] = []
    for name, check in checks.items():
        if not isinstance(check, dict) or check.get("status") != "fail":
            continue
        out.append(
            {
                "name": name,
                "tier": check.get("tier"),
                "max_abs_delta": check.get("max_abs_delta"),
                "limit": check.get("limit"),
                "max_abs_delta_date": check.get("max_abs_delta_date"),
            }
        )
    return out


def _top_metric_failures(metrics_gate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = metrics_gate.get("top_candidates") if isinstance(metrics_gate.get("top_candidates"), list) else []
    out: list[dict[str, Any]] = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "variant": row.get("variant"),
                "promotion_objective_status": row.get("promotion_objective_status"),
                "final_value": row.get("final_value"),
                "final_value_floor": row.get("final_value_floor"),
                "delta_final": row.get("delta_final"),
                "sharpe_non_worse_pass": row.get("sharpe_non_worse_pass"),
                "max_drawdown_non_worse_pass": row.get("max_drawdown_non_worse_pass"),
            }
        )
    return out


def build_diagnostic(promotion_gate_path: Path = DEFAULT_PROMOTION_GATE) -> dict[str, Any]:
    gate = _load(promotion_gate_path)
    panel_drift = _dict(gate, "panel_drift_gate")
    multi_window = _dict(gate, "multi_window_gate")
    deployment = _dict(gate, "deployment_consistency_gate")
    deployment_summary = _dict(gate, "deployment_summary_gate")
    metrics = _dict(gate, "metrics_gate")
    blocking_gates = gate.get("blocking_gates") or []

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_promotion_blocked_diagnostic",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blocking_gates else "not_blocked",
        "promotion_decision": gate.get("decision"),
        "blocking_gates": blocking_gates,
        "summary": {
            "panel_drift_failed": "panel_drift" in blocking_gates,
            "multi_window_failed": "multi_window" in blocking_gates,
            "deployment_consistency_failed": "deployment_consistency" in blocking_gates,
            "deployment_summary_failed": "deployment_summary" in blocking_gates,
            "manual_approval_pending": bool(deployment.get("manual_approval_pending_reasons")),
            "metrics_status": metrics.get("status"),
            "deployment_summary_gate_status": deployment_summary.get("status"),
        },
        "metrics_gate": {
            "status": metrics.get("status"),
            "formal_upgrade_pass_count": metrics.get("formal_upgrade_pass_count"),
            "research_watchlist_pass_count": metrics.get("research_watchlist_pass_count"),
            "top_failures": _top_metric_failures(metrics),
        },
        "panel_drift_gate": {
            "status": panel_drift.get("status"),
            "reason": panel_drift.get("reason"),
            "path": panel_drift.get("path"),
            "overlap_rows": panel_drift.get("overlap_rows"),
            "overlap_start": panel_drift.get("overlap_start"),
            "overlap_end": panel_drift.get("overlap_end"),
            "failed_checks": _failed_drift_checks(panel_drift),
        },
        "multi_window_gate": {
            "status": multi_window.get("status"),
            "reason": multi_window.get("reason"),
            "source_decision": multi_window.get("source_decision"),
            "candidate_count": multi_window.get("candidate_count"),
            "pass_candidates": multi_window.get("pass_candidates") or [],
            "criteria": multi_window.get("criteria") or {},
        },
        "deployment_consistency_gate": {
            "status": deployment.get("status"),
            "reason": deployment.get("reason"),
            "blocking_reasons": deployment.get("blocking_reasons") or [],
            "hard_blocking_reasons": deployment.get("hard_blocking_reasons") or [],
            "manual_approval_pending_reasons": deployment.get("manual_approval_pending_reasons") or [],
            "warning_reasons": deployment.get("warning_reasons") or [],
            "all_reasons": deployment.get("all_reasons") or deployment.get("blocking_reasons") or [],
        },
        "deployment_summary_gate": {
            "status": deployment_summary.get("status"),
            "reason": deployment_summary.get("reason"),
            "blocking_reasons": deployment_summary.get("blocking_reasons") or [],
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {"promotion_gate": str(promotion_gate_path)},
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Promotion Blocked Diagnostic",
        "",
        f"- Promotion decision: `{report.get('promotion_decision')}`",
        f"- Blocking gates: `{report.get('blocking_gates')}`",
        f"- Metrics status: `{report['metrics_gate'].get('status')}`",
        f"- Deployment summary gate: `{report['deployment_summary_gate'].get('status')}`",
        "",
        "## Panel Drift",
        "",
        f"- Status: `{report['panel_drift_gate'].get('status')}`",
        f"- Reason: `{report['panel_drift_gate'].get('reason')}`",
    ]
    for row in report["panel_drift_gate"].get("failed_checks") or []:
        lines.append(
            f"- `{row.get('name')}` tier `{row.get('tier')}` delta `{row.get('max_abs_delta')}` "
            f"limit `{row.get('limit')}` date `{row.get('max_abs_delta_date')}`"
        )
    lines.extend(
        [
            "",
            "## Multi-Window",
            "",
            f"- Status: `{report['multi_window_gate'].get('status')}`",
            f"- Reason: `{report['multi_window_gate'].get('reason')}`",
            f"- Criteria: `{report['multi_window_gate'].get('criteria')}`",
            "",
            "## Deployment Consistency",
            "",
            f"- Status: `{report['deployment_consistency_gate'].get('status')}`",
        ]
    )
    for reason in report["deployment_consistency_gate"].get("hard_blocking_reasons") or []:
        lines.append(f"- `{reason}`")
    manual_pending = report["deployment_consistency_gate"].get("manual_approval_pending_reasons") or []
    if manual_pending:
        lines.extend(["", "## Manual Approval Pending", ""])
        for reason in manual_pending:
            lines.append(f"- `{reason}`")
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            f"- Creates orders: `{report['decision']['creates_orders']}`",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Auto rebalance allowed: `{report['decision']['auto_rebalance_allowed']}`",
            f"- Golden1_0531 unchanged: `{report['decision']['keep_golden1_0531_unchanged']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None = None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"promotion_blocked_diagnostic_{stamp}.json"


def write_outputs(
    report: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promotion-gate", default=str(DEFAULT_PROMOTION_GATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_diagnostic(_resolve(args.promotion_gate))
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Promotion blocked diagnostic: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "promotion_decision": report["promotion_decision"],
                "blocking_gates": report["blocking_gates"],
                "keep_golden1_0531_unchanged": report["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
