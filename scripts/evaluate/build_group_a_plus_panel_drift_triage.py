#!/usr/bin/env python3
"""Build a compact governance triage for GroupA+ NCF panel drift failures."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIAGNOSIS = PROJECT_ROOT / "results/ncf_panel_drift_diagnosis_20260722.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/panel_drift_triage.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/panel_drift_triage.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/panel_drift_triage/history"


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


def _top_months(column: dict[str, Any]) -> list[dict[str, Any]]:
    rows = column.get("top_months_by_exceed_count") if isinstance(column.get("top_months_by_exceed_count"), list) else []
    return [
        {
            "month": row.get("month"),
            "exceed_count": row.get("exceed_count"),
            "row_count": row.get("row_count"),
            "mean_abs_delta": row.get("mean_abs_delta"),
            "max_abs_delta": row.get("max_abs_delta"),
        }
        for row in rows[:3]
        if isinstance(row, dict)
    ]


def _source_hypotheses(diagnosis: dict[str, Any], exceeded_columns: list[str]) -> list[str]:
    source = _dict(diagnosis, "source_diagnosis")
    panel_methods = _dict(source, "panel_methods")
    model_sets = _dict(source, "model_sets")
    run_context = _dict(source, "run_context")
    sensitivity = _dict(source, "sensitivity_audit")
    hypotheses: list[str] = []

    if model_sets.get("status") == "changed":
        hypotheses.append("model_set_changed")
    changed_settings = [
        key
        for key, value in _dict(run_context, "settings").items()
        if isinstance(value, dict) and value.get("changed") is True
    ]
    if changed_settings:
        hypotheses.append("run_context_settings_changed")
    if run_context.get("candidate_stale_sources"):
        hypotheses.append("candidate_external_source_stale")
    if (
        panel_methods.get("baseline_has_horizon_ensemble_method")
        != panel_methods.get("candidate_has_horizon_ensemble_method")
        or panel_methods.get("baseline_has_ensemble_weights") != panel_methods.get("candidate_has_ensemble_weights")
    ):
        hypotheses.append("panel_method_schema_changed")
    if sensitivity.get("status") == "available":
        sensitivity_columns = _dict(sensitivity, "column_summary")
        if any(column in sensitivity_columns for column in exceeded_columns):
            hypotheses.append("external_feature_sensitivity_visible")
    if "confidence" in exceeded_columns or "ensemble_prob_up" in exceeded_columns:
        hypotheses.append("horizon_ensemble_or_confidence_blend_check_needed")
    if not hypotheses:
        hypotheses.append("panel_value_drift_without_available_source_context")
    return hypotheses


def _column_triage(name: str, column: dict[str, Any]) -> dict[str, Any]:
    signed_delta = column.get("signed_delta_at_max")
    direction = "positive" if isinstance(signed_delta, (int, float)) and signed_delta > 0 else (
        "negative" if isinstance(signed_delta, (int, float)) and signed_delta < 0 else "unknown"
    )
    return {
        "column": name,
        "tier": column.get("tier"),
        "limit": column.get("limit"),
        "max_abs_delta": column.get("max_abs_delta"),
        "max_abs_delta_date": column.get("max_abs_delta_date"),
        "signed_delta_at_max": signed_delta,
        "direction": direction,
        "baseline_value_at_max": column.get("baseline_value_at_max"),
        "candidate_value_at_max": column.get("candidate_value_at_max"),
        "top_months": _top_months(column),
    }


def build_triage(diagnosis_path: Path = DEFAULT_DIAGNOSIS) -> dict[str, Any]:
    diagnosis = _load(diagnosis_path)
    exceeded_columns = list(diagnosis.get("exceeded_columns") or [])
    trigger_critical = list(diagnosis.get("trigger_critical_exceeded") or [])
    columns = _dict(diagnosis, "columns")
    column_triage = [
        _column_triage(name, columns[name])
        for name in exceeded_columns
        if isinstance(columns.get(name), dict)
    ]
    month_counts: Counter[str] = Counter()
    for column in column_triage:
        for month in column.get("top_months") or []:
            if month.get("month"):
                month_counts[str(month["month"])] += int(month.get("exceed_count") or 0)
    source_hypotheses = _source_hypotheses(diagnosis, exceeded_columns)
    next_checks = []
    if "model_set_changed" in source_hypotheses:
        next_checks.append("compare baseline/candidate horizon model sets and best-model selections")
    if "candidate_external_source_stale" in source_hypotheses or "external_feature_sensitivity_visible" in source_hypotheses:
        next_checks.append("rerun or isolate external-feature and no-external panel sensitivity")
    if "horizon_ensemble_or_confidence_blend_check_needed" in source_hypotheses:
        next_checks.append("inspect horizon ensemble weights/confidence blend around max-drift dates")
    if not next_checks:
        next_checks.append("inspect row-level panel values around max-drift dates")
    status = "blocked" if exceeded_columns else "pass"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_panel_drift_triage",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "policy": "diagnostic_only_no_strategy_change_no_weight_change",
        "active_allocation_impact": "none",
        "source_diagnosis": str(diagnosis_path),
        "overlap": {
            "start": diagnosis.get("overlap_start"),
            "end": diagnosis.get("overlap_end"),
            "rows": diagnosis.get("overlap_rows"),
        },
        "summary": {
            "exceeded_columns": exceeded_columns,
            "trigger_critical_exceeded": trigger_critical,
            "source_hypotheses": source_hypotheses,
            "top_exceed_months": [
                {"month": month, "exceed_count": count}
                for month, count in month_counts.most_common(5)
            ],
            "next_checks": next_checks,
        },
        "columns": column_triage,
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Panel Drift Triage",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Exceeded columns: `{report['summary'].get('exceeded_columns')}`",
        f"- Trigger-critical exceeded: `{report['summary'].get('trigger_critical_exceeded')}`",
        f"- Source hypotheses: `{report['summary'].get('source_hypotheses')}`",
        "",
        "## Columns",
        "",
    ]
    for column in report.get("columns") or []:
        lines.append(
            f"- `{column.get('column')}` tier `{column.get('tier')}` delta `{column.get('max_abs_delta')}` "
            f"limit `{column.get('limit')}` date `{column.get('max_abs_delta_date')}` direction `{column.get('direction')}`"
        )
    lines.extend(["", "## Next Checks", ""])
    for item in report["summary"].get("next_checks") or []:
        lines.append(f"- {item}")
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
    return history_dir / f"panel_drift_triage_{datetime.now().strftime('%Y%m%d')}.json"


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
    parser.add_argument("--diagnosis", default=str(DEFAULT_DIAGNOSIS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_triage(_resolve(args.diagnosis))
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Panel drift triage: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "exceeded_columns": report["summary"]["exceeded_columns"],
                "trigger_critical_exceeded": report["summary"]["trigger_critical_exceeded"],
                "source_hypotheses": report["summary"]["source_hypotheses"],
                "keep_golden1_0531_unchanged": report["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
