#!/usr/bin/env python3
"""Build staged re-entry promotion readiness review.

This reviews whether the staged 0050-only re-entry shadow has enough historical
and forward evidence to be promoted. It never changes target weights or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGED = PROJECT_ROOT / "report/group_a_plus/latest/staged_reentry_shadow.json"
DEFAULT_EVENT_STUDY = PROJECT_ROOT / "report/group_a_plus/latest/staged_reentry_shadow_event_study.json"
DEFAULT_CANDIDATE_TAIL = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_candidate_tail_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/staged_reentry_promotion_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/staged_reentry_promotion_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _stats_count(event_study: dict[str, Any], key: str) -> int:
    value = (event_study.get("summary") or {}).get(key, {})
    return int(value.get("count") or 0) if isinstance(value, dict) else 0


def _candidate_tail_status(candidate_tail: dict[str, Any], candidate: str) -> str | None:
    statuses = (candidate_tail.get("candidate_reviews") or [])
    for row in statuses:
        if isinstance(row, dict) and row.get("name") == candidate:
            return row.get("tail_review_status")
    return None


def build_promotion_review(
    *,
    staged_path: Path,
    event_study_path: Path,
    candidate_tail_path: Path | None = DEFAULT_CANDIDATE_TAIL,
    min_active_events: int = 20,
    min_forward_edge_rows: int = 10,
) -> dict[str, Any]:
    staged = _load(staged_path)
    event_study = _load(event_study_path)
    candidate_tail = _load(candidate_tail_path)

    blockers: list[str] = []
    warnings: list[str] = []
    if not staged:
        blockers.append("missing_staged_reentry_shadow")
    if not event_study:
        blockers.append("missing_staged_reentry_event_study")

    active_event_count = int(event_study.get("active_event_count") or 0)
    if active_event_count < min_active_events:
        blockers.append("staged_reentry_active_event_count_below_promotion_minimum")

    forward_counts = {
        "edge_5d": _stats_count(event_study, "edge_5d"),
        "edge_10d": _stats_count(event_study, "edge_10d"),
        "edge_20d": _stats_count(event_study, "edge_20d"),
    }
    if any(count < min_forward_edge_rows for count in forward_counts.values()):
        blockers.append("staged_reentry_forward_edge_rows_below_promotion_minimum")

    tail_status = _candidate_tail_status(candidate_tail, "staged_reentry")
    if tail_status not in {None, "tail_acceptable_shadow_only"}:
        blockers.append("staged_reentry_tail_review_not_acceptable")
    if tail_status == "tail_acceptable_shadow_only":
        warnings.append("staged_reentry_tail_review_shadow_only")

    if staged.get("status") == "active_shadow_candidate":
        warnings.extend(staged.get("warnings") or [])
    else:
        blockers.extend(staged.get("blockers") or [])

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_staged_reentry_promotion_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_no_target_weight_change",
        "status": "blocked_for_live_promotion" if blockers else "ready_for_human_promotion_review",
        "actual_data_date": staged.get("actual_data_date") or event_study.get("as_of"),
        "candidate_status": staged.get("status"),
        "candidate_policy": staged.get("candidate_policy"),
        "event_study": {
            "unique_signal_dates": event_study.get("unique_signal_dates"),
            "active_event_count": active_event_count,
            "forward_edge_counts": forward_counts,
            "summary": event_study.get("summary"),
        },
        "tail_review": {
            "candidate_tail_status": tail_status,
        },
        "decision": {
            "shadow_monitoring_allowed": True,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "summary": "Staged 0050-only re-entry remains a shadow candidate; event-study evidence is too sparse for live promotion.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {
            "staged_reentry": str(staged_path),
            "event_study": str(event_study_path),
            "candidate_tail_review": str(candidate_tail_path) if candidate_tail_path else None,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"staged_reentry_promotion_review_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review.get("actual_data_date")).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-reentry", default=str(DEFAULT_STAGED))
    parser.add_argument("--event-study", default=str(DEFAULT_EVENT_STUDY))
    parser.add_argument("--candidate-tail", default=str(DEFAULT_CANDIDATE_TAIL))
    parser.add_argument("--min-active-events", type=int, default=20)
    parser.add_argument("--min-forward-edge-rows", type=int, default=10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_promotion_review(
        staged_path=_resolve(args.staged_reentry),
        event_study_path=_resolve(args.event_study),
        candidate_tail_path=_resolve(args.candidate_tail) if args.candidate_tail else None,
        min_active_events=int(args.min_active_events),
        min_forward_edge_rows=int(args.min_forward_edge_rows),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_review(review, output, history_dir)
    print(f"Staged re-entry promotion review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('actual_data_date'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "active_event_count": review["event_study"]["active_event_count"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
