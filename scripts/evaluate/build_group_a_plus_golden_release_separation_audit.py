#!/usr/bin/env python3
"""Audit that latest/research pipeline outputs stay separate from Golden releases."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run.run_ncf_daily_pipeline import (  # noqa: E402
    OUTPUT_TARGET_FLAGS,
    PROTECTED_GOLDEN1_RELEASE_ARTIFACTS,
    PROTECTED_GOLDEN2_RELEASE_ARTIFACTS,
    _normalize_project_path,
)


LATEST_DIR = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = LATEST_DIR / "golden_release_separation_audit.json"
DEFAULT_OUTPUT_MD = LATEST_DIR / "golden_release_separation_audit.md"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _release_records(paths: set[Path] | frozenset[Path]) -> list[dict[str, Any]]:
    return [
        {"path": _rel(_normalize_project_path(path)), "exists": _normalize_project_path(path).exists(), "mtime_utc": _mtime(_normalize_project_path(path))}
        for path in sorted(paths, key=lambda item: str(item))
    ]


def _output_violations(commands: dict[str, list[str]], protected: set[Path]) -> list[dict[str, str]]:
    protected_norm = {_normalize_project_path(path) for path in protected}
    protected_prefixes = tuple(str(path) for path in protected_norm)
    violations: list[dict[str, str]] = []
    for step, cmd in commands.items():
        for index, token in enumerate(cmd[:-1]):
            if token not in OUTPUT_TARGET_FLAGS:
                continue
            candidate = _normalize_project_path(cmd[index + 1])
            candidate_str = str(candidate)
            if candidate in protected_norm or any(candidate_str.startswith(prefix + ".") for prefix in protected_prefixes):
                violations.append({"step": step, "flag": token, "path": _rel(candidate)})
    return violations


def build_audit(*, commands: dict[str, list[str]] | None = None, as_of: str | None = None) -> dict[str, Any]:
    golden1 = set(PROTECTED_GOLDEN1_RELEASE_ARTIFACTS)
    golden2 = set(PROTECTED_GOLDEN2_RELEASE_ARTIFACTS)
    all_protected = golden1 | golden2
    violations = _output_violations(commands or {}, all_protected)
    missing = [
        item
        for item in _release_records(all_protected)
        if not item["exists"]
    ]
    warnings = []
    if missing:
        warnings.append("some_protected_golden_release_files_are_not_present_on_disk")
    blockers = []
    if violations:
        blockers.append("pipeline_output_targets_frozen_golden_release_artifacts")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_golden_release_separation_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "audit_only_no_golden_change_no_latest_change",
        "status": "blocked" if blockers else ("warning" if warnings else "passed"),
        "summary": {
            "protected_golden1_artifacts": len(golden1),
            "protected_golden2_artifacts": len(golden2),
            "missing_protected_artifacts": len(missing),
            "output_target_violations": len(violations),
        },
        "decision": {
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "changes_latest_strategy": False,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "creates_orders": False,
        },
        "blockers": blockers,
        "warnings": warnings,
        "output_target_violations": violations,
        "missing_protected_artifacts": missing,
        "protected_releases": {
            "golden1_0531": _release_records(golden1),
            "golden2_0830": _release_records(golden2),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# GroupA++ Golden Release Separation Audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- As of: `{report.get('as_of')}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Protected Golden1 artifacts: `{summary['protected_golden1_artifacts']}`",
        f"- Protected Golden2 artifacts: `{summary['protected_golden2_artifacts']}`",
        f"- Missing protected artifacts: `{summary['missing_protected_artifacts']}`",
        f"- Output target violations: `{summary['output_target_violations']}`",
        "",
        "## Decision",
        "",
        "- Changes Golden1_0531: `False`",
        "- Changes Golden2_0830: `False`",
        "- Changes latest strategy: `False`",
        "- Promotion allowed: `False`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- `{item}`" for item in report.get("blockers") or []] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- `{item}`" for item in report.get("warnings") or []] or ["- None"])
    lines.extend(["", "## Output Target Violations", ""])
    violations = report.get("output_target_violations") or []
    lines.extend([f"- `{item['step']}` `{item['flag']}` -> `{item['path']}`" for item in violations] or ["- None"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    report = build_audit(as_of=args.as_of)
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = Path(args.output_md)
    if not output_md.is_absolute():
        output_md = PROJECT_ROOT / output_md
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
