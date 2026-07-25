#!/usr/bin/env python3
"""Attribute why the GroupA+ multi-window promotion gate failed."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MULTI_WINDOW_GATE = PROJECT_ROOT / "results/group_a_plus_multi_window_gate_20260706.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/multi_window_failure_attribution.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/multi_window_failure_attribution.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/multi_window_failure_attribution/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _criteria(gate: dict[str, Any]) -> dict[str, Any]:
    raw = gate.get("criteria") if isinstance(gate.get("criteria"), dict) else {}
    return {
        "min_pass_ratio": _float(raw.get("min_pass_ratio"), 1.0),
        "max_final_drawdown_pct": _float(raw.get("max_final_drawdown_pct"), 0.02),
        "min_sharpe_delta": _float(raw.get("min_sharpe_delta"), 0.0),
        "require_mdd_nonworse": raw.get("require_mdd_nonworse") is not False,
    }


def _row_attribution(row: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    delta_final_pct = _float(row.get("delta_final_pct"))
    delta_sharpe = _float(row.get("delta_sharpe"))
    delta_max_drawdown = _float(row.get("delta_max_drawdown"))
    final_threshold = -_float(criteria.get("max_final_drawdown_pct"))
    sharpe_threshold = _float(criteria.get("min_sharpe_delta"))
    mdd_threshold = 0.0
    fail_reasons = list(row.get("window_fail_reasons") or [])
    return {
        "window": row.get("window"),
        "experiment": row.get("experiment"),
        "baseline": row.get("baseline"),
        "candidate": row.get("candidate"),
        "window_pass": row.get("window_pass") is True,
        "fail_reasons": fail_reasons,
        "delta_final_pct": delta_final_pct,
        "final_value_threshold": final_threshold,
        "final_value_shortfall": max(0.0, final_threshold - delta_final_pct),
        "delta_sharpe": delta_sharpe,
        "sharpe_threshold": sharpe_threshold,
        "sharpe_shortfall": max(0.0, sharpe_threshold - delta_sharpe),
        "delta_max_drawdown": delta_max_drawdown,
        "max_drawdown_threshold": mdd_threshold,
        "max_drawdown_shortfall": max(0.0, mdd_threshold - delta_max_drawdown)
        if criteria.get("require_mdd_nonworse")
        else 0.0,
    }


def _candidate_attribution(candidate: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    rows = [_row_attribution(row, criteria) for row in candidate.get("rows", []) if isinstance(row, dict)]
    failed_rows = [row for row in rows if not row["window_pass"]]
    reason_counts: Counter[str] = Counter()
    for row in failed_rows:
        reason_counts.update(row.get("fail_reasons") or [])
    min_pass_ratio = _float(criteria.get("min_pass_ratio"), 1.0)
    pass_ratio = _float(candidate.get("pass_ratio"))
    pass_ratio_shortfall = max(0.0, min_pass_ratio - pass_ratio)
    primary_reason = reason_counts.most_common(1)[0][0] if reason_counts else (
        "pass_ratio_shortfall" if pass_ratio_shortfall > 0 else "none"
    )
    drag_windows = sorted(
        failed_rows,
        key=lambda row: (
            row["final_value_shortfall"],
            row["sharpe_shortfall"],
            row["max_drawdown_shortfall"],
        ),
        reverse=True,
    )
    return {
        "candidate": candidate.get("candidate"),
        "decision": candidate.get("decision"),
        "window_count": candidate.get("window_count"),
        "pass_count": candidate.get("pass_count"),
        "pass_ratio": pass_ratio,
        "required_pass_ratio": min_pass_ratio,
        "pass_ratio_shortfall": pass_ratio_shortfall,
        "primary_failure_reason": primary_reason,
        "failure_reason_counts": dict(sorted(reason_counts.items())),
        "worst_delta_final_pct": candidate.get("worst_delta_final_pct"),
        "worst_delta_sharpe": candidate.get("worst_delta_sharpe"),
        "worst_delta_max_drawdown": candidate.get("worst_delta_max_drawdown"),
        "drag_windows": drag_windows[:5],
    }


def build_attribution(multi_window_gate_path: Path = DEFAULT_MULTI_WINDOW_GATE) -> dict[str, Any]:
    gate = _load(multi_window_gate_path)
    criteria = _criteria(gate)
    candidates = [
        _candidate_attribution(candidate, criteria)
        for candidate in gate.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    reason_counts: Counter[str] = Counter()
    for candidate in candidates:
        reason_counts.update(candidate.get("failure_reason_counts") or {})
    ranked_candidates = sorted(
        candidates,
        key=lambda item: (
            _float(item.get("pass_ratio")),
            _float(item.get("worst_delta_final_pct")),
            _float(item.get("worst_delta_sharpe")),
            _float(item.get("worst_delta_max_drawdown")),
        ),
        reverse=True,
    )
    nearest_candidates = sorted(
        candidates,
        key=lambda item: (
            _float(item.get("pass_ratio_shortfall")),
            -_float(item.get("worst_delta_final_pct")),
            -_float(item.get("worst_delta_sharpe")),
        ),
    )
    status = "blocked" if gate.get("decision") != "candidate_available" else "not_blocked"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_multi_window_failure_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "policy": "diagnostic_only_no_strategy_change_no_weight_change",
        "active_allocation_impact": "none",
        "source_decision": gate.get("decision"),
        "criteria": criteria,
        "candidate_count": gate.get("candidate_count"),
        "row_count": gate.get("row_count"),
        "summary": {
            "passed_candidates": [
                item.get("candidate") for item in candidates if item.get("decision") == "multi_window_pass"
            ],
            "nearest_candidates": [item.get("candidate") for item in nearest_candidates[:3]],
            "top_failure_reasons": [
                {"reason": reason, "count": count}
                for reason, count in reason_counts.most_common()
            ],
        },
        "candidates": ranked_candidates,
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {"multi_window_gate": str(multi_window_gate_path)},
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Multi-Window Failure Attribution",
        "",
        f"- Source decision: `{report.get('source_decision')}`",
        f"- Status: `{report.get('status')}`",
        f"- Candidate count: `{report.get('candidate_count')}`",
        f"- Criteria: `{report.get('criteria')}`",
        "",
        "## Top Failure Reasons",
        "",
    ]
    reasons = report.get("summary", {}).get("top_failure_reasons") or []
    if not reasons:
        lines.append("- None")
    for row in reasons:
        lines.append(f"- `{row.get('reason')}`: `{row.get('count')}`")
    lines.extend(["", "## Candidates", ""])
    for item in report.get("candidates") or []:
        lines.append(
            f"- `{item.get('candidate')}` pass `{item.get('pass_count')}/{item.get('window_count')}` "
            f"primary `{item.get('primary_failure_reason')}` pass-ratio shortfall "
            f"`{item.get('pass_ratio_shortfall')}`"
        )
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


def _history_path(history_dir: Path) -> Path:
    return history_dir / f"multi_window_failure_attribution_{datetime.now().strftime('%Y%m%d')}.json"


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
    parser.add_argument("--multi-window-gate", default=str(DEFAULT_MULTI_WINDOW_GATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_attribution(_resolve(args.multi_window_gate))
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Multi-window failure attribution: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "source_decision": report["source_decision"],
                "nearest_candidates": report["summary"]["nearest_candidates"],
                "top_failure_reasons": report["summary"]["top_failure_reasons"],
                "keep_golden1_0531_unchanged": report["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
