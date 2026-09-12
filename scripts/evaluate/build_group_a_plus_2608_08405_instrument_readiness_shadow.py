#!/usr/bin/env python3
"""Build natural-experiment instrument readiness shadow for GroupA+.

arXiv 2608.08405 discusses using credible instruments or natural experiments
to study capacity/crowding. This report only checks whether GroupA+ has enough
evidence to use securities-lending supply shifts or index events as future
shadow instruments. It cannot change live weights or make capacity claims.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECURITIES_LENDING_STATUS = (
    PROJECT_ROOT / "report/group_a_plus/latest/securities_lending_0050_source_status.json"
)
DEFAULT_ASSIGNED_REALIZED = (
    PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_08405_instrument_readiness_shadow/history"


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


def _has_recent_lending_source(status: dict[str, Any]) -> bool:
    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    return bool(summary.get("latest_available_dt")) and summary.get("db_lagged_after_query") is False


def build_report(
    *,
    securities_lending_status_path: Path,
    assigned_realized_path: Path,
    index_event_panel_path: Path | None,
    exclusion_protocol_path: Path | None,
) -> dict[str, Any]:
    lending_status = _unwrap(_load(securities_lending_status_path))
    assigned_realized = _unwrap(_load(assigned_realized_path))
    index_event_panel = _unwrap(_load(index_event_panel_path)) if index_event_panel_path is not None else {}
    exclusion_protocol = _unwrap(_load(exclusion_protocol_path)) if exclusion_protocol_path is not None else {}

    lending_source_ready = _has_recent_lending_source(lending_status)
    index_panel_ready = bool(index_event_panel.get("events") or index_event_panel.get("event_windows"))
    exclusion_ready = bool(exclusion_protocol.get("pre_registered_exclusion_restriction"))
    first_stage_reported = bool(
        lending_status.get("first_stage")
        or index_event_panel.get("first_stage")
        or exclusion_protocol.get("first_stage_specification")
    )
    realized_ready = assigned_realized.get("status") == "ready_for_capacity_shadow_review"

    candidates = [
        {
            "candidate": "securities_lending_supply_shifts",
            "data_source_status": lending_status.get("status") or "missing",
            "latest_available_dt": (lending_status.get("summary") or {}).get("latest_available_dt"),
            "db_lagged_after_query": (lending_status.get("summary") or {}).get("db_lagged_after_query"),
            "first_stage_reported": bool(lending_status.get("first_stage")),
            "exclusion_restriction_pre_registered": exclusion_ready,
            "instrument_ready": False,
        },
        {
            "candidate": "index_reconstitution_or_index_weight_events",
            "event_panel_path": None if index_event_panel_path is None else str(index_event_panel_path),
            "event_panel_available": index_panel_ready,
            "first_stage_reported": bool(index_event_panel.get("first_stage")),
            "exclusion_restriction_pre_registered": exclusion_ready,
            "instrument_ready": False,
        },
    ]

    blockers: list[str] = []
    if not lending_source_ready:
        blockers.append("securities_lending_source_stale_or_missing_for_instrument")
    if not index_panel_ready:
        blockers.append("index_reconstitution_event_panel_missing")
    if not first_stage_reported:
        blockers.append("first_stage_not_reported")
    if not exclusion_ready:
        blockers.append("exclusion_restriction_not_documented")
    if not realized_ready:
        blockers.append("realized_deployment_series_missing")
    blockers.append("natural_experiment_not_promotable_without_manual_causal_review")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_08405_instrument_readiness_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": lending_status.get("as_of") or assigned_realized.get("as_of"),
        "status": "blocked_shadow_only",
        "policy": "natural_experiment_instrument_readiness_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf",
            "concept": "natural_experiments_require_exclusion_restriction_and_reported_first_stage",
        },
        "instrument_candidates": candidates,
        "checks": {
            "securities_lending_source_ready_for_first_stage": lending_source_ready,
            "index_event_panel_available": index_panel_ready,
            "first_stage_reported": first_stage_reported,
            "exclusion_restriction_pre_registered": exclusion_ready,
            "realized_deployment_logged": realized_ready,
            "manual_causal_review_completed": False,
        },
        "blocking_reasons": blockers,
        "decision": {
            "instrument_promotable": False,
            "capacity_claim_allowed": False,
            "capacity_scaling_allowed": False,
            "latest_strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "golden1_0531_change_allowed": False,
            "golden2_0830_change_allowed": False,
            "summary": (
                "Securities-lending and index-event ideas remain future shadow instruments only. "
                "The current artifacts do not report a first stage, a pre-registered exclusion "
                "restriction, an index-event panel, or realized deployment needed for a capacity claim."
            ),
        },
        "inputs": {
            "securities_lending_status": str(securities_lending_status_path),
            "assigned_realized": str(assigned_realized_path),
            "index_event_panel": None if index_event_panel_path is None else str(index_event_panel_path),
            "exclusion_protocol": None if exclusion_protocol_path is None else str(exclusion_protocol_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    decision = report["decision"]
    checks = report["checks"]
    lines = [
        "# 2608.08405 Instrument Readiness Shadow",
        "",
        f"- status: {report['status']}",
        f"- as_of: {report.get('as_of')}",
        f"- policy: {report['policy']}",
        f"- instrument_promotable: {decision['instrument_promotable']}",
        f"- capacity_claim_allowed: {decision['capacity_claim_allowed']}",
        f"- latest_strategy_change_allowed: {decision['latest_strategy_change_allowed']}",
        "",
        "## Checks",
    ]
    lines.extend(f"- {key}: {value}" for key, value in checks.items())
    lines.extend(["", "## Blocking Reasons"])
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Candidates"])
    for item in report["instrument_candidates"]:
        lines.append(
            "- {candidate}: ready={ready}, first_stage_reported={first_stage}, exclusion_pre_registered={exclusion}".format(
                candidate=item.get("candidate"),
                ready=item.get("instrument_ready"),
                first_stage=item.get("first_stage_reported"),
                exclusion=item.get("exclusion_restriction_pre_registered"),
            )
        )
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    date = str(report.get("as_of") or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2608_08405_instrument_readiness_shadow_{date}.json"


def write_report(report: dict[str, Any], *, output_path: Path, markdown_path: Path | None, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--securities-lending-status", default=str(DEFAULT_SECURITIES_LENDING_STATUS))
    parser.add_argument("--assigned-realized", default=str(DEFAULT_ASSIGNED_REALIZED))
    parser.add_argument("--index-event-panel", default="")
    parser.add_argument("--exclusion-protocol", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    index_event_panel = _resolve(args.index_event_panel) if args.index_event_panel else None
    exclusion_protocol = _resolve(args.exclusion_protocol) if args.exclusion_protocol else None
    report = build_report(
        securities_lending_status_path=_resolve(args.securities_lending_status),
        assigned_realized_path=_resolve(args.assigned_realized),
        index_event_panel_path=index_event_panel,
        exclusion_protocol_path=exclusion_protocol,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown) if args.markdown else None
    history = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output_path=output, markdown_path=markdown, history_dir=history)
    print(f"2608.08405 instrument readiness shadow: {output}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
