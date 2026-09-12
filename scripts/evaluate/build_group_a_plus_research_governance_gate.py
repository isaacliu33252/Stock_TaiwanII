#!/usr/bin/env python3
"""Audit research/shadow reports for accidental live-policy permissions.

This gate is intentionally generic: it scans latest research-like JSON
artifacts and verifies that they do not grant live weight, golden, NCF gate, or
order permissions. It is a governance dashboard only and never promotes a
strategy by itself.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = DEFAULT_REPORTS_DIR / "research_governance_gate.json"
DEFAULT_OUTPUT_MD = DEFAULT_REPORTS_DIR / "research_governance_gate.md"

RESEARCH_HINTS = (
    "research",
    "shadow",
    "readiness",
    "review",
    "gate",
    "paper",
    "promotion",
    "no_weight_change",
)
LIVE_MUTATION_KEYS = frozenset(
    {
        "changes_latest_strategy",
        "changes_latest_strategy_live_weights",
        "changes_golden1_0531",
        "changes_golden01_0531",
        "changes_golden2_0830",
        "changes_ncf_live_gate",
        "changes_ncf_gate",
        "changes_ncf_live_threshold",
        "target_weight_change_allowed",
        "live_weight_change_allowed",
        "order_generation_allowed",
        "orders_allowed",
    }
)
PROMOTION_KEYS = frozenset({"promotion_allowed", "promotion_allowed_now"})


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        value = PROJECT_ROOT / value
    return value.resolve()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _iter_json_paths(reports_dir: Path) -> list[Path]:
    if not reports_dir.exists():
        return []
    return sorted(
        path
        for path in reports_dir.glob("*.json")
        if path.name not in {DEFAULT_OUTPUT.name, "daily_status.json"}
    )


def _walk_flags(payload: Any, *, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            if key in LIVE_MUTATION_KEYS or key in PROMOTION_KEYS:
                yield field, value
            yield from _walk_flags(value, prefix=field)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            yield from _walk_flags(value, prefix=f"{prefix}[{idx}]")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "allow", "allowed"}
    return False


def _is_research_like(path: Path, payload: dict[str, Any]) -> bool:
    text_parts = [path.stem]
    for key in ("report_type", "policy", "status"):
        value = payload.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    decision = payload.get("decision")
    if isinstance(decision, dict):
        value = decision.get("decision")
        if isinstance(value, str):
            text_parts.append(value)
    haystack = " ".join(text_parts).lower()
    if any(hint in haystack for hint in RESEARCH_HINTS):
        return True
    return any(field.rsplit(".", 1)[-1] in LIVE_MUTATION_KEYS or field.rsplit(".", 1)[-1] in PROMOTION_KEYS for field, _ in _walk_flags(payload))


def build_gate(*, reports_dir: Path, report_paths: list[Path] | None = None, as_of: str | None = None) -> dict[str, Any]:
    paths = report_paths if report_paths is not None else _iter_json_paths(reports_dir)
    included: list[dict[str, Any]] = []
    unreadable: list[dict[str, str]] = []
    live_mutation_violations: list[dict[str, Any]] = []
    promotion_manual_review: list[dict[str, Any]] = []

    for path in paths:
        resolved = _resolve(path)
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - governance report should capture parse failures.
            unreadable.append({"path": _rel(resolved), "error": str(exc)})
            continue
        if not isinstance(payload, dict) or not _is_research_like(resolved, payload):
            continue

        flags = [{"field": field, "value": value} for field, value in _walk_flags(payload)]
        mutation_flags = [
            flag
            for flag in flags
            if flag["field"].rsplit(".", 1)[-1] in LIVE_MUTATION_KEYS and _truthy(flag["value"])
        ]
        promotion_flags = [
            flag for flag in flags if flag["field"].rsplit(".", 1)[-1] in PROMOTION_KEYS and _truthy(flag["value"])
        ]
        record = {
            "path": _rel(resolved),
            "report_type": payload.get("report_type"),
            "policy": payload.get("policy"),
            "status": payload.get("status"),
            "live_mutation_true_count": len(mutation_flags),
            "promotion_true_count": len(promotion_flags),
        }
        included.append(record)
        for flag in mutation_flags:
            live_mutation_violations.append({"path": record["path"], **flag})
        for flag in promotion_flags:
            promotion_manual_review.append({"path": record["path"], **flag})

    blockers = []
    if unreadable:
        blockers.append("unreadable_research_like_reports")
    if live_mutation_violations:
        blockers.append("research_report_declares_live_mutation_permission")

    warnings = []
    if promotion_manual_review:
        warnings.append("promotion_true_requires_separate_manual_promotion_review")
    if not included:
        warnings.append("no_research_like_reports_found")

    status = "blocked" if blockers else ("manual_review_required" if warnings else "passed")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_research_governance_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "governance_audit_only_no_weight_change",
        "status": status,
        "summary": {
            "included_reports": len(included),
            "unreadable_reports": len(unreadable),
            "live_mutation_violations": len(live_mutation_violations),
            "promotion_manual_review_items": len(promotion_manual_review),
        },
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "changes_ncf_live_gate": False,
            "order_generation_allowed": False,
        },
        "blockers": blockers,
        "warnings": warnings,
        "live_mutation_violations": live_mutation_violations,
        "promotion_manual_review": promotion_manual_review,
        "unreadable_reports": unreadable,
        "included_reports": included,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# GroupA++ Research Governance Gate",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- As of: `{report.get('as_of')}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Included reports: `{summary['included_reports']}`",
        f"- Unreadable reports: `{summary['unreadable_reports']}`",
        f"- Live mutation violations: `{summary['live_mutation_violations']}`",
        f"- Promotion manual-review items: `{summary['promotion_manual_review_items']}`",
        "",
        "## Decision",
        "",
        "- Promotion allowed: `False`",
        "- Target weight change allowed: `False`",
        "- Latest strategy change allowed: `False`",
        "- Golden changes allowed: `False`",
        "- NCF live gate change allowed: `False`",
        "- Order generation allowed: `False`",
        "",
        "## Blockers",
        "",
    ]
    blockers = report.get("blockers") or []
    lines.extend([f"- `{item}`" for item in blockers] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings") or []
    lines.extend([f"- `{item}`" for item in warnings] or ["- None"])
    lines.extend(["", "## Live Mutation Violations", ""])
    violations = report.get("live_mutation_violations") or []
    lines.extend(
        [f"- `{item['path']}` `{item['field']}` = `{item['value']}`" for item in violations[:40]]
        or ["- None"]
    )
    if len(violations) > 40:
        lines.append(f"- ... truncated `{len(violations) - 40}` more")
    lines.extend(["", "## Promotion Manual Review Queue", ""])
    queue = report.get("promotion_manual_review") or []
    lines.extend([f"- `{item['path']}` `{item['field']}` = `{item['value']}`" for item in queue[:40]] or ["- None"])
    if len(queue) > 40:
        lines.append(f"- ... truncated `{len(queue) - 40}` more")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--report", action="append", default=None, help="Specific JSON report to include; repeatable.")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    reports_dir = _resolve(args.reports_dir)
    report_paths = [_resolve(item) for item in args.report] if args.report else None
    report = build_gate(reports_dir=reports_dir, report_paths=report_paths, as_of=args.as_of)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
