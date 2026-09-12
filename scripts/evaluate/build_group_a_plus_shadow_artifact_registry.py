#!/usr/bin/env python3
"""Build an index of GroupA++ research/shadow artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_research_governance_gate import (
    _is_research_like,
    _rel,
    _resolve,
    _truthy,
    _walk_flags,
    LIVE_MUTATION_KEYS,
    PROMOTION_KEYS,
)


DEFAULT_REPORTS_DIR = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = DEFAULT_REPORTS_DIR / "shadow_artifact_registry.json"
DEFAULT_OUTPUT_MD = DEFAULT_REPORTS_DIR / "shadow_artifact_registry.md"
EXCLUDED_JSON_NAMES = {
    "daily_status.json",
    "research_governance_gate.json",
    "shadow_artifact_registry.json",
}


def _iter_json_paths(reports_dir: Path) -> list[Path]:
    if not reports_dir.exists():
        return []
    return sorted(path for path in reports_dir.glob("*.json") if path.name not in EXCLUDED_JSON_NAMES)


def _iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _artifact_family(path: Path, payload: dict[str, Any]) -> str:
    text = " ".join(
        str(item).lower()
        for item in (
            path.stem,
            payload.get("report_type"),
            payload.get("policy"),
            payload.get("status"),
        )
        if item is not None
    )
    if "promotion" in text or "readiness" in text or "gate" in text:
        return "governance_gate"
    if "shadow" in text:
        return "shadow_backtest_or_monitor"
    if "review" in text or "paper" in text:
        return "research_review"
    return "research_related"


def build_registry(*, reports_dir: Path, as_of: str | None = None) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    unreadable: list[dict[str, str]] = []
    missing_markdown: list[str] = []
    by_family: dict[str, int] = {}
    by_status: dict[str, int] = {}

    for path in _iter_json_paths(reports_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - registry should preserve parse failures.
            unreadable.append({"path": _rel(path), "error": str(exc)})
            continue
        if not isinstance(payload, dict) or not _is_research_like(path, payload):
            continue

        flags = [{"field": field, "value": value} for field, value in _walk_flags(payload)]
        live_mutation_true_count = sum(
            1 for flag in flags if flag["field"].rsplit(".", 1)[-1] in LIVE_MUTATION_KEYS and _truthy(flag["value"])
        )
        promotion_true_count = sum(
            1 for flag in flags if flag["field"].rsplit(".", 1)[-1] in PROMOTION_KEYS and _truthy(flag["value"])
        )
        md_path = path.with_suffix(".md")
        family = _artifact_family(path, payload)
        status = str(payload.get("status") or "unknown")
        record = {
            "path": _rel(path),
            "markdown_path": _rel(md_path) if md_path.exists() else None,
            "mtime_utc": _iso_mtime(path),
            "family": family,
            "report_type": payload.get("report_type"),
            "policy": payload.get("policy"),
            "status": payload.get("status"),
            "has_decision": isinstance(payload.get("decision"), dict),
            "live_mutation_true_count": live_mutation_true_count,
            "promotion_true_count": promotion_true_count,
        }
        artifacts.append(record)
        by_family[family] = by_family.get(family, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        if not md_path.exists():
            missing_markdown.append(record["path"])

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_shadow_artifact_registry",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "registry_only_no_weight_change",
        "status": "blocked" if unreadable else "available",
        "summary": {
            "artifact_count": len(artifacts),
            "unreadable_count": len(unreadable),
            "missing_markdown_count": len(missing_markdown),
            "live_mutation_true_count": sum(item["live_mutation_true_count"] for item in artifacts),
            "promotion_true_count": sum(item["promotion_true_count"] for item in artifacts),
            "by_family": dict(sorted(by_family.items())),
            "by_status": dict(sorted(by_status.items())),
        },
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "order_generation_allowed": False,
        },
        "unreadable_reports": unreadable,
        "missing_markdown": missing_markdown,
        "artifacts": artifacts,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# GroupA++ Shadow Artifact Registry",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- As of: `{report.get('as_of')}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Artifact count: `{summary['artifact_count']}`",
        f"- Unreadable count: `{summary['unreadable_count']}`",
        f"- Missing markdown count: `{summary['missing_markdown_count']}`",
        f"- Live mutation true count: `{summary['live_mutation_true_count']}`",
        f"- Promotion true count: `{summary['promotion_true_count']}`",
        "",
        "## Families",
        "",
    ]
    lines.extend([f"- `{key}`: `{value}`" for key, value in summary["by_family"].items()] or ["- None"])
    lines.extend(["", "## Missing Markdown", ""])
    missing = report.get("missing_markdown") or []
    lines.extend([f"- `{item}`" for item in missing[:60]] or ["- None"])
    if len(missing) > 60:
        lines.append(f"- ... truncated `{len(missing) - 60}` more")
    lines.extend(["", "## Recent Artifacts", ""])
    recent = sorted(report.get("artifacts") or [], key=lambda item: item.get("mtime_utc") or "", reverse=True)
    for item in recent[:60]:
        lines.append(
            f"- `{item['path']}` family=`{item['family']}` status=`{item.get('status')}` "
            f"md=`{item.get('markdown_path')}`"
        )
    if len(recent) > 60:
        lines.append(f"- ... truncated `{len(recent) - 60}` more")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    report = build_registry(reports_dir=_resolve(args.reports_dir), as_of=args.as_of)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
