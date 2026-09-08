#!/usr/bin/env python3
"""Build an auto-generated index of Group A+ handoff Markdown files.

This scans for files whose name contains "HANDOFF" and heuristically
extracts a date, title, adoption status, and follow-up flag from each one.
Status classification is keyword-based and best-effort: it flags candidates
for human review, it does not replace reading the file.

Rerun this script (instead of hand-editing an index) whenever new handoff
files are added, so the index does not go stale.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = [".", "docs", "handoff"]
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "GROUP_A_PLUS_HANDOFF_INDEX.md"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results" / "group_a_plus_handoff_index_latest.json"

FILENAME_DATE_RE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
H1_RE = re.compile(r"^#\s+(.*\S)\s*$")
METADATA_LINE_RE = re.compile(r"^(date|paper|status|author|source|arxiv|link)\s*:", re.IGNORECASE)

STATUS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("closed_negative", ("closed_negative",)),
    (
        "adopted",
        (
            "promoted to production",
            "promote to production",
            "already in production",
            "已導入",
            "已生效",
            "promoted_to_production",
        ),
    ),
    (
        "not_adopted",
        (
            "do not promote",
            "not promote",
            "not recommended",
            "不建議promote",
            "不建議採用",
        ),
    ),
    (
        "shadow_track",
        (
            "shadow_track",
            "shadow candidate",
            "shadow候選",
            "shadow-only",
        ),
    ),
]

FOLLOW_UP_MARKERS = (
    "follow-up",
    "follow up",
    "todo",
    "待驗證",
    "待追蹤",
    "後續追蹤",
    "後續驗證",
    "next step",
    "尚未",
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _extract_date(path: Path, text: str) -> str | None:
    match = FILENAME_DATE_RE.search(path.name)
    if not match:
        match = FILENAME_DATE_RE.search(text[:2000])
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = H1_RE.match(line.strip())
        if match:
            return match.group(1)
    return fallback


def _extract_excerpt(text: str, title: str) -> str:
    lines = text.splitlines()
    seen_title = False
    for line in lines:
        stripped = line.strip()
        if not seen_title:
            if stripped.startswith("# "):
                seen_title = True
            continue
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("-"):
            continue
        if METADATA_LINE_RE.match(stripped):
            continue
        return stripped[:200]
    return ""


def _classify_status(lowered_text: str) -> str:
    for status, markers in STATUS_RULES:
        if any(marker in lowered_text for marker in markers):
            return status
    return "unclassified"


def _needs_follow_up(lowered_text: str) -> bool:
    return any(marker in lowered_text for marker in FOLLOW_UP_MARKERS)


def _git_tracked_or_untracked_files(root_path: Path) -> list[Path] | None:
    """List files under root_path via git (fast: skips gitignored generated-output
    directories entirely) rather than walking the whole tree by hand. Returns None
    when root_path is not inside this project's git repo, so callers can fall back
    to a plain filesystem walk (used by tests against an unrelated tmp_path)."""
    if not (PROJECT_ROOT / ".git").exists():
        return None
    try:
        rel = root_path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    pathspec = "." if str(rel) == "." else str(rel)
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", pathspec],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return [PROJECT_ROOT / line for line in result.stdout.splitlines() if line]


def _collect_files(roots: list[str], pattern: str, exclude: set[Path]) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for root in roots:
        root_path = _resolve(root)
        if not root_path.exists():
            continue
        candidates = _git_tracked_or_untracked_files(root_path)
        if candidates is None:
            candidates = [item for item in root_path.rglob("*") if item.is_file()]
        for candidate in candidates:
            if not candidate.is_file() or not fnmatch.fnmatch(candidate.name, pattern):
                continue
            if any(part in {"__pycache__", ".git", "node_modules"} for part in candidate.parts):
                continue
            resolved = candidate.resolve()
            if resolved in seen or resolved in exclude:
                continue
            seen.add(resolved)
            files.append(candidate)
    return sorted(files, key=lambda item: str(item))


def build_record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lowered = text.lower()
    title = _extract_title(text, path.stem)
    try:
        display_path = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        display_path = str(path)
    return {
        "path": display_path,
        "date": _extract_date(path, text),
        "title": title,
        "status": _classify_status(lowered),
        "follow_up_needed": _needs_follow_up(lowered),
        "excerpt": _extract_excerpt(text, title),
    }


def build_index(
    *,
    roots: list[str] | None = None,
    pattern: str = "*HANDOFF*.md",
    exclude: list[str] | None = None,
) -> dict[str, Any]:
    exclude_paths = {_resolve(item).resolve() for item in (exclude or [])}
    files = _collect_files(roots or DEFAULT_ROOTS, pattern, exclude_paths)
    records = [build_record(path) for path in files]
    records.sort(key=lambda row: (row["date"] or "0000-00-00", row["path"]), reverse=True)
    status_counts: dict[str, int] = {}
    for row in records:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_handoff_index",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "heuristic_keyword_scan_review_before_trusting",
        "file_count": len(records),
        "status_counts": status_counts,
        "follow_up_needed_count": sum(1 for row in records if row["follow_up_needed"]),
        "records": records,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Group A+ Handoff Index",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Files indexed: {report['file_count']}",
        f"- Status counts: {report['status_counts']}",
        f"- Files flagged needing follow-up: {report['follow_up_needed_count']}",
        "",
        "Auto-generated by `scripts/report/build_group_a_plus_handoff_index.py`. "
        "Status/follow-up flags are a heuristic keyword scan over each file's text — "
        "treat them as a starting point, not ground truth. Rerun the script after adding "
        "new handoff files instead of hand-editing this table.",
        "",
        "| Date | File | Title | Status | Follow-up? | Excerpt |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["records"]:
        title = row["title"].replace("|", "\\|")
        excerpt = row["excerpt"].replace("|", "\\|")
        lines.append(
            f"| {row['date'] or 'unknown'} | `{row['path']}` | {title} | {row['status']} | "
            f"{'yes' if row['follow_up_needed'] else ''} | {excerpt} |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_md: Path, output_json: Path) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS)
    parser.add_argument("--pattern", default="*HANDOFF*.md")
    parser.add_argument("--exclude", nargs="*", default=[str(DEFAULT_OUTPUT_MD)])
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_index(roots=args.roots, pattern=args.pattern, exclude=args.exclude)
    write_outputs(report, output_md=_resolve(args.output_md), output_json=_resolve(args.output_json))
    print(f"Group A+ handoff index: {_resolve(args.output_md)} ({report['file_count']} files)")
    print(json.dumps(report["status_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
