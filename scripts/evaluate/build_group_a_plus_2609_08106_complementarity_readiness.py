#!/usr/bin/env python3
"""Summarize 2609.08106 complementarity sleeve backtest readiness."""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_readiness.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_readiness.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(pattern: str, *, threshold: float, shift_weight: float, risk_gate: str) -> dict[str, Any]:
    paths = sorted(Path(p) for p in glob.glob(str(_resolve(pattern))))
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = _load(path)
        if payload.get("report_type") != "group_a_plus_2609_08106_complementarity_sleeve_backtest":
            continue
        inputs = payload["inputs"]
        sim = payload["simulation"]
        delta = sim["delta_shadow_minus_baseline"]
        if (
            inputs.get("threshold") != threshold
            or inputs.get("shift_weight") != shift_weight
            or inputs.get("risk_gate", "none") != risk_gate
        ):
            continue
        rows.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path),
                "start": inputs["start"],
                "end": inputs["end"],
                "window": inputs["window"],
                "threshold": inputs["threshold"],
                "shift_weight": inputs["shift_weight"],
                "risk_gate": inputs.get("risk_gate", "none"),
                "event_count": sim["event_count"],
                "delta_total_return": delta["total_return"],
                "delta_sharpe": delta["sharpe_ratio"],
                "delta_max_drawdown": delta["max_drawdown"],
                "total_turnover": sim["total_turnover"],
                "promotion_ready_in_single_window": payload["decision"]["promotion_ready"],
            }
        )
    unique: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in rows:
        unique[(row["start"], row["end"], row["window"])] = row
    rows = sorted(unique.values(), key=lambda item: (item["start"], item["end"], item["window"]))
    positive_return = sum(1 for row in rows if float(row["delta_total_return"] or 0.0) > 0)
    positive_sharpe = sum(1 for row in rows if float(row["delta_sharpe"] or 0.0) > 0)
    non_worse_drawdown = sum(1 for row in rows if float(row["delta_max_drawdown"] or 0.0) >= 0)
    passed = sum(1 for row in rows if row["promotion_ready_in_single_window"])
    blockers: list[str] = []
    if positive_sharpe < len(rows):
        blockers.append("not_all_windows_positive_sharpe")
    if passed < len(rows):
        blockers.append("not_all_windows_pass_single_window_gate")
    if not rows:
        blockers.append("no_backtest_rows")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_complementarity_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "readiness_summary_only_no_orders_no_weight_change",
        "candidate": {
            "name": f"complementarity_sleeve_window42_threshold{threshold:g}_shift{shift_weight:.0%}_{risk_gate}",
            "source_paper": "2609.08106",
            "live_effect_if_ever_promoted": "small capped shift from 00631L to best bond complement",
        },
        "windows": rows,
        "aggregate": {
            "window_count": len(rows),
            "positive_return_windows": positive_return,
            "positive_sharpe_windows": positive_sharpe,
            "non_worse_drawdown_windows": non_worse_drawdown,
            "single_window_pass_count": passed,
        },
        "blocking_reasons": blockers,
        "decision": {
            "shadow_candidate_survives_initial_screen": bool(rows and positive_return == len(rows) and non_worse_drawdown == len(rows)),
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "next_step": "Continue daily forward shadow logging with realized after-cost attribution; do not promote without enough live-period observations.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.08106 Complementarity Readiness",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- candidate: `{report['candidate']['name']}`",
        f"- policy: `{report['policy']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| start | end | window | events | d_return | d_sharpe | d_mdd | turnover | pass |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["windows"]:
        lines.append(
            "| {start} | {end} | {window} | {events} | {dr:.4%} | {ds:.4f} | {dm:.4%} | {to:.3f} | {passed} |".format(
                start=row["start"],
                end=row["end"],
                window=row["window"],
                events=row["event_count"],
                dr=float(row["delta_total_return"] or 0.0),
                ds=float(row["delta_sharpe"] or 0.0),
                dm=float(row["delta_max_drawdown"] or 0.0),
                to=float(row["total_turnover"] or 0.0),
                passed=row["promotion_ready_in_single_window"],
            )
        )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            f"- positive_return_windows: `{report['aggregate']['positive_return_windows']}/{report['aggregate']['window_count']}`",
            f"- positive_sharpe_windows: `{report['aggregate']['positive_sharpe_windows']}/{report['aggregate']['window_count']}`",
            f"- non_worse_drawdown_windows: `{report['aggregate']['non_worse_drawdown_windows']}/{report['aggregate']['window_count']}`",
            f"- blockers: `{report['blocking_reasons']}`",
            "",
            "## Decision",
            "",
            "- Keep as forward shadow candidate.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.",
            "- Do not change latest GroupA++ target weights.",
            f"- Next step: {report['decision']['next_step']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pattern",
        default="report/group_a_plus/latest/2609_08106_complementarity_sleeve_backtest*thr2_shift3.json",
    )
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--shift-weight", type=float, default=0.03)
    parser.add_argument("--risk-gate", default="none")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    report = build_report(args.pattern, threshold=args.threshold, shift_weight=args.shift_weight, risk_gate=args.risk_gate)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Readiness JSON: {output}")
    print(f"Readiness Markdown: {markdown}")


if __name__ == "__main__":
    main()
