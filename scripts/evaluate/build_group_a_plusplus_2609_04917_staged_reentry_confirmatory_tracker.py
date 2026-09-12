#!/usr/bin/env python3
"""Track staged-reentry progress against the 2609.04917 frozen spec."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_staged_reentry_frozen_confirmatory_spec.json"
DEFAULT_EVENT_STUDY = PROJECT_ROOT / "report/group_a_plus/latest/staged_reentry_shadow_event_study.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_staged_reentry_confirmatory_tracker.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_staged_reentry_confirmatory_tracker.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


def _edge(event: dict[str, Any], horizon: str) -> float | None:
    forward = event.get("forward") if isinstance(event.get("forward"), dict) else {}
    value = forward.get(f"edge_{horizon}")
    return float(value) if isinstance(value, (int, float)) else None


def _stats(events: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    values = [_edge(event, horizon) for event in events]
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"resolved_rows": 0, "mean_edge": None, "positive_rate": None, "worst_edge": None}
    return {
        "resolved_rows": len(clean),
        "mean_edge": sum(clean) / len(clean),
        "positive_rate": sum(1 for value in clean if value > 0.0) / len(clean),
        "worst_edge": min(clean),
    }


def build_tracker(*, spec: dict[str, Any], event_study: dict[str, Any]) -> dict[str, Any]:
    rule = spec.get("confirmatory_window_rule") if isinstance(spec.get("confirmatory_window_rule"), dict) else {}
    start_after = str(rule.get("start_after") or "")
    start_dt = _date(start_after)
    horizons = [str(item).replace("d", "") + "d" for item in rule.get("required_forward_horizons", ["5d", "10d", "20d"])]
    min_events = int(rule.get("minimum_active_events") or 10)
    min_rows = int(rule.get("minimum_resolved_rows_per_horizon") or 10)
    min_positive = float(rule.get("minimum_positive_rate_per_horizon") or 0.6)
    min_mean = float(rule.get("minimum_mean_edge_per_horizon") or 0.0)
    max_worst = float(rule.get("maximum_worst_edge_per_horizon") or 0.0)

    all_events = [event for event in event_study.get("events", []) if isinstance(event, dict)]
    confirmatory: list[dict[str, Any]] = []
    pre_freeze: list[dict[str, Any]] = []
    for event in all_events:
        event_dt = _date(event.get("actual_data_date"))
        if start_dt is not None and event_dt is not None and event_dt > start_dt:
            confirmatory.append(event)
        else:
            pre_freeze.append(event)

    horizon_progress = {}
    blockers: list[str] = []
    for horizon in horizons:
        stats = _stats(confirmatory, horizon)
        rows_missing = max(0, min_rows - int(stats["resolved_rows"]))
        passed = bool(
            stats["resolved_rows"] >= min_rows
            and stats["mean_edge"] is not None
            and float(stats["mean_edge"]) >= min_mean
            and stats["positive_rate"] is not None
            and float(stats["positive_rate"]) >= min_positive
            and stats["worst_edge"] is not None
            and float(stats["worst_edge"]) >= max_worst
        )
        if not passed:
            blockers.append(f"confirmatory_{horizon}_not_passed")
        horizon_progress[horizon] = {
            **stats,
            "minimum_resolved_rows": min_rows,
            "rows_missing": rows_missing,
            "minimum_positive_rate": min_positive,
            "minimum_mean_edge": min_mean,
            "maximum_worst_edge": max_worst,
            "passed": passed,
        }

    event_missing = max(0, min_events - len(confirmatory))
    if event_missing:
        blockers.append("confirmatory_active_event_count_below_minimum")
    if not spec:
        blockers.append("missing_frozen_confirmatory_spec")
    if not event_study:
        blockers.append("missing_staged_reentry_event_study")

    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_staged_reentry_confirmatory_tracker",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_confirmatory_progress_no_weight_change",
        "status": "confirmatory_passed_for_human_review" if not blockers else "collecting_confirmatory_evidence",
        "candidate": (spec.get("candidate") or {}).get("name") or "staged_reentry",
        "start_after": start_after,
        "pre_freeze_event_count": len(pre_freeze),
        "confirmatory_event_count": len(confirmatory),
        "minimum_active_events": min_events,
        "confirmatory_events_missing": event_missing,
        "horizon_progress": horizon_progress,
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "human_review_after_pass_required": True,
            "summary": "Continue collecting post-freeze staged-reentry evidence; pre-freeze events are exploratory only.",
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Staged Reentry Confirmatory Tracker",
        "",
        f"- status: {report['status']}",
        f"- start_after: {report['start_after']}",
        f"- pre_freeze_event_count: {report['pre_freeze_event_count']}",
        f"- confirmatory_event_count: {report['confirmatory_event_count']}",
        f"- confirmatory_events_missing: {report['confirmatory_events_missing']}",
        f"- promotion_allowed: {report['decision']['promotion_allowed']}",
        "",
        "| horizon | resolved | missing | mean edge | positive rate | worst edge | passed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for horizon, row in report["horizon_progress"].items():
        lines.append(
            f"| {horizon} | {row['resolved_rows']} | {row['rows_missing']} | {row['mean_edge']} | "
            f"{row['positive_rate']} | {row['worst_edge']} | {row['passed']} |"
        )
    lines.extend(["", "## Decision", "", report["decision"]["summary"], ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--event-study", default=str(DEFAULT_EVENT_STUDY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    spec_path = _resolve(args.spec)
    event_path = _resolve(args.event_study)
    report = build_tracker(spec=_load(spec_path), event_study=_load(event_path))
    report["inputs"] = {"spec": str(spec_path), "event_study": str(event_path)}
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": report["status"],
                "confirmatory_event_count": report["confirmatory_event_count"],
                "confirmatory_events_missing": report["confirmatory_events_missing"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
