#!/usr/bin/env python3
"""Build a repeatable pin-refresh recommendation from an outcome-aware NCF panel drift audit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DRIFT_AUDIT = PROJECT_ROOT / "results/ncf_panel_drift_active_vs_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ncf_panel_refresh_recommendation.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ncf_panel_refresh_recommendation.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ncf_panel_refresh_recommendation/history"
DEFAULT_SNAPSHOT_OUTPUT = PROJECT_ROOT / "results" / f"ncf_panel_refresh_recommendation_{datetime.now().strftime('%Y%m%d')}.json"
DEFAULT_REVIEW_COLUMNS = (
    "h20_prob_up",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _column_review(
    name: str,
    column: dict[str, Any],
    *,
    min_resolved_rows: int,
    min_candidate_favorable_rate: float,
    max_risk_relevant_delta: float,
) -> dict[str, Any]:
    outcome = column.get("outcome_aware") if isinstance(column.get("outcome_aware"), dict) else {}
    resolved_rows = int(outcome.get("resolved_rows") or 0)
    candidate_favorable_rows = int(outcome.get("candidate_favorable_rows") or 0)
    baseline_favorable_rows = int(outcome.get("baseline_favorable_rows") or 0)
    tie_rows = int(outcome.get("tie_rows") or 0)
    candidate_favorable_rate = (
        candidate_favorable_rows / resolved_rows if resolved_rows > 0 else None
    )
    risk_relevant_max_abs_delta = _as_float(outcome.get("risk_relevant_max_abs_delta"))
    has_enough_outcomes = resolved_rows >= int(min_resolved_rows)
    candidate_accuracy_supported = (
        candidate_favorable_rate is not None
        and candidate_favorable_rate >= float(min_candidate_favorable_rate)
    )
    risk_delta_within_limit = (
        risk_relevant_max_abs_delta is not None
        and risk_relevant_max_abs_delta <= float(max_risk_relevant_delta)
    )
    if not outcome:
        verdict = "missing_outcome_aware"
    elif not has_enough_outcomes:
        verdict = "insufficient_resolved_outcomes"
    elif not candidate_accuracy_supported:
        verdict = "candidate_not_more_accurate"
    elif not risk_delta_within_limit:
        verdict = "candidate_accuracy_supported_but_risk_delta_high"
    else:
        verdict = "candidate_supported"
    return {
        "column": name,
        "actual_column": outcome.get("actual_column"),
        "resolved_rows": resolved_rows,
        "candidate_favorable_rows": candidate_favorable_rows,
        "baseline_favorable_rows": baseline_favorable_rows,
        "tie_rows": tie_rows,
        "candidate_favorable_rate": candidate_favorable_rate,
        "min_candidate_favorable_rate": float(min_candidate_favorable_rate),
        "risk_relevant_max_abs_delta": risk_relevant_max_abs_delta,
        "risk_relevant_max_abs_delta_date": outcome.get("risk_relevant_max_abs_delta_date"),
        "max_risk_relevant_delta": float(max_risk_relevant_delta),
        "has_enough_outcomes": has_enough_outcomes,
        "candidate_accuracy_supported": candidate_accuracy_supported,
        "risk_delta_within_limit": risk_delta_within_limit,
        "raw_max_abs_delta": column.get("max_abs_delta"),
        "raw_max_abs_delta_date": column.get("max_abs_delta_date"),
        "verdict": verdict,
    }


def build_refresh_recommendation(
    drift_audit_path: str | Path = DEFAULT_DRIFT_AUDIT,
    *,
    columns: list[str] | None = None,
    min_resolved_rows: int = 30,
    min_candidate_favorable_rate: float = 0.55,
    max_risk_relevant_delta: float = 0.13,
) -> dict[str, Any]:
    drift_path = _resolve(drift_audit_path)
    audit = _load(drift_path)
    column_summary = audit.get("column_summary") if isinstance(audit.get("column_summary"), dict) else {}
    review_columns = list(columns or DEFAULT_REVIEW_COLUMNS)
    reviews = [
        _column_review(
            name,
            column_summary[name],
            min_resolved_rows=min_resolved_rows,
            min_candidate_favorable_rate=min_candidate_favorable_rate,
            max_risk_relevant_delta=max_risk_relevant_delta,
        )
        for name in review_columns
        if isinstance(column_summary.get(name), dict)
    ]

    missing_columns = [name for name in review_columns if name not in column_summary]
    evaluable = [
        review for review in reviews
        if review["verdict"] not in {"missing_outcome_aware", "insufficient_resolved_outcomes"}
    ]
    low_accuracy = [review for review in evaluable if review["verdict"] == "candidate_not_more_accurate"]
    high_risk_delta = [
        review for review in evaluable
        if review["verdict"] == "candidate_accuracy_supported_but_risk_delta_high"
    ]
    supported = [review for review in evaluable if review["verdict"] == "candidate_supported"]

    if not reviews or missing_columns == review_columns:
        recommendation = "manual_review"
        reason = "requested_review_columns_missing"
    elif not evaluable:
        recommendation = "manual_review"
        reason = "outcome_aware_evidence_unavailable_or_too_sparse"
    elif low_accuracy:
        recommendation = "keep_current_pin"
        reason = "candidate_not_more_accurate_on_resolved_outcomes"
    elif high_risk_delta:
        recommendation = "manual_review"
        reason = "candidate_accuracy_supported_but_risk_relevant_drift_still_high"
    elif len(supported) == len(evaluable):
        recommendation = "refresh_candidate_supported"
        reason = "candidate_more_accurate_and_risk_relevant_drift_within_limits"
    else:
        recommendation = "manual_review"
        reason = "mixed_outcome_aware_evidence"

    return {
        "schema_version": 1,
        "report_type": "ncf_panel_refresh_recommendation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "diagnostic_only_no_strategy_change_no_weight_change",
        "drift_audit": str(drift_path),
        "baseline_panel": audit.get("baseline_panel"),
        "candidate_panel": audit.get("candidate_panel"),
        "overlap": {
            "start": audit.get("overlap_start"),
            "end": audit.get("overlap_end"),
            "rows": audit.get("overlap_rows"),
            "window_start": audit.get("window_start"),
        },
        "thresholds": {
            "min_resolved_rows": int(min_resolved_rows),
            "min_candidate_favorable_rate": float(min_candidate_favorable_rate),
            "max_risk_relevant_delta": float(max_risk_relevant_delta),
        },
        "review_columns": review_columns,
        "missing_review_columns": missing_columns,
        "columns": reviews,
        "summary": {
            "recommendation": recommendation,
            "reason": reason,
            "evaluable_columns": [review["column"] for review in evaluable],
            "low_accuracy_columns": [review["column"] for review in low_accuracy],
            "high_risk_delta_columns": [review["column"] for review in high_risk_delta],
            "supported_columns": [review["column"] for review in supported],
        },
        "decision": {
            "auto_pin_update_allowed": False,
            "target_weight_change_allowed": False,
            "creates_orders": False,
            "recommended_action": recommendation,
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NCF Panel Refresh Recommendation",
        "",
        f"- Recommendation: `{report['summary']['recommendation']}`",
        f"- Reason: `{report['summary']['reason']}`",
        f"- Baseline panel: `{report.get('baseline_panel')}`",
        f"- Candidate panel: `{report.get('candidate_panel')}`",
        "",
        "## Outcome-Aware Columns",
        "",
    ]
    for column in report.get("columns") or []:
        rate = column.get("candidate_favorable_rate")
        rate_text = "None" if rate is None else f"{rate:.4f}"
        lines.append(
            f"- `{column['column']}`: verdict `{column['verdict']}`, "
            f"candidate_favorable `{column['candidate_favorable_rows']}/{column['resolved_rows']}` "
            f"rate `{rate_text}`, risk_delta `{column.get('risk_relevant_max_abs_delta')}`"
        )
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            f"- Auto pin update allowed: `{report['decision']['auto_pin_update_allowed']}`",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Creates orders: `{report['decision']['creates_orders']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path) -> Path:
    return history_dir / f"ncf_panel_refresh_recommendation_{datetime.now().strftime('%Y%m%d')}.json"


def write_outputs(
    report: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    snapshot_output: Path | None = None,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    if snapshot_output is not None:
        snapshot_output.parent.mkdir(parents=True, exist_ok=True)
        snapshot_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drift-audit", default=str(DEFAULT_DRIFT_AUDIT))
    parser.add_argument("--columns", nargs="*", default=None)
    parser.add_argument("--min-resolved-rows", type=int, default=30)
    parser.add_argument("--min-candidate-favorable-rate", type=float, default=0.55)
    parser.add_argument("--max-risk-relevant-delta", type=float, default=0.13)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--snapshot-output",
        default=str(DEFAULT_SNAPSHOT_OUTPUT),
        help="Optional dated JSON snapshot for replay/debug. Use an empty value to skip.",
    )
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_refresh_recommendation(
        args.drift_audit,
        columns=args.columns,
        min_resolved_rows=args.min_resolved_rows,
        min_candidate_favorable_rate=args.min_candidate_favorable_rate,
        max_risk_relevant_delta=args.max_risk_relevant_delta,
    )
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        snapshot_output=_resolve(args.snapshot_output) if args.snapshot_output else None,
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"NCF panel refresh recommendation: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "recommendation": report["summary"]["recommendation"],
                "reason": report["summary"]["reason"],
                "low_accuracy_columns": report["summary"]["low_accuracy_columns"],
                "high_risk_delta_columns": report["summary"]["high_risk_delta_columns"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
