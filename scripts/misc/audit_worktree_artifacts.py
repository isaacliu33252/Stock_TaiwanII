#!/usr/bin/env python3
"""Summarize generated-artifact pressure in the current Git worktree.

This tool is intentionally read-only. It helps keep source changes separate
from daily reports, caches, and model outputs before review or commit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ARTIFACT_PREFIXES = (
    "results/",
    "report/",
    "outputs/",
    "models/",
    "news/",
    "log/",
    "logs/",
    "catboost_info/",
    "data/cache/",
    "data/news/",
    "data/private/",
    "data/portfolio_cache/",
    "data/raw/",
    "data/taifex/",
    "FinRL/models/",
    "FinRL/results/",
    "FinRL/log/",
    "FinRL/logs/",
    "FinRL/catboost_info/",
)

DEFAULT_CLEANUP_EXCLUDE_PATTERNS = (
    "*.md",
    "*.py",
    "models/MODEL_REGISTRY.json",
)


@dataclass(frozen=True)
class WorktreeEntry:
    status: str
    path: str


def run_git(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def parse_status_porcelain(raw_status: str) -> list[WorktreeEntry]:
    entries: list[WorktreeEntry] = []
    for line in raw_status.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        entries.append(WorktreeEntry(status=status, path=path))
    return entries


def is_artifact_path(path: str, prefixes: Iterable[str] = DEFAULT_ARTIFACT_PREFIXES) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in prefixes)


def top_level_name(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized.split("/", 1)[0] if "/" in normalized else ".root"


def summarize_entries(entries: Iterable[WorktreeEntry]) -> dict[str, object]:
    entry_list = list(entries)
    artifact_entries = [entry for entry in entry_list if is_artifact_path(entry.path)]
    source_entries = [entry for entry in entry_list if not is_artifact_path(entry.path)]

    status_counts = Counter(entry.status for entry in entry_list)
    artifact_top_levels = Counter(top_level_name(entry.path) for entry in artifact_entries)
    source_top_levels = Counter(top_level_name(entry.path) for entry in source_entries)

    return {
        "total_changed_paths": len(entry_list),
        "artifact_changed_paths": len(artifact_entries),
        "source_changed_paths": len(source_entries),
        "status_counts": dict(sorted(status_counts.items())),
        "artifact_top_levels": dict(artifact_top_levels.most_common()),
        "source_top_levels": dict(source_top_levels.most_common()),
        "artifact_samples": [entry.path for entry in artifact_entries[:20]],
        "source_samples": [entry.path for entry in source_entries[:20]],
    }


def count_tracked_under_prefixes(prefixes: Iterable[str], *, cwd: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prefix in prefixes:
        raw = run_git(["ls-files", "--", prefix], cwd=cwd)
        counts[prefix] = sum(1 for line in raw.splitlines() if line.strip())
    return counts


def list_tracked_artifact_paths(prefixes: Iterable[str], *, cwd: Path) -> list[str]:
    paths: list[str] = []
    for prefix in prefixes:
        raw = run_git(["ls-files", "--", prefix], cwd=cwd)
        paths.extend(line.strip() for line in raw.splitlines() if line.strip())
    return sorted(set(paths))


def is_cleanup_candidate(
    path: str,
    exclude_patterns: Iterable[str] = DEFAULT_CLEANUP_EXCLUDE_PATTERNS,
) -> bool:
    normalized = path.replace("\\", "/")
    if not is_artifact_path(normalized):
        return False
    return not any(fnmatch(normalized, pattern) for pattern in exclude_patterns)


def select_cleanup_candidates(paths: Iterable[str]) -> list[str]:
    return [path for path in sorted(set(paths)) if is_cleanup_candidate(path)]


def build_report(
    *,
    cwd: Path,
    include_tracked_counts: bool,
    include_cleanup_candidates: bool,
    candidate_limit: int,
) -> dict[str, object]:
    raw_status = run_git(["status", "--porcelain=v1"], cwd=cwd)
    entries = parse_status_porcelain(raw_status)
    report = summarize_entries(entries)
    if include_tracked_counts:
        tracked_counts = count_tracked_under_prefixes(DEFAULT_ARTIFACT_PREFIXES, cwd=cwd)
        report["tracked_artifact_paths"] = {
            prefix: count for prefix, count in tracked_counts.items() if count > 0
        }
    if include_cleanup_candidates:
        candidates = select_cleanup_candidates(
            list_tracked_artifact_paths(DEFAULT_ARTIFACT_PREFIXES, cwd=cwd)
        )
        report["cleanup_candidate_count"] = len(candidates)
        report["cleanup_candidate_exclude_patterns"] = list(DEFAULT_CLEANUP_EXCLUDE_PATTERNS)
        report["cleanup_candidate_samples"] = candidates[:candidate_limit]
    return report


def write_cleanup_candidates(path: Path, candidates: Iterable[str]) -> int:
    candidate_list = list(candidates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{candidate}\n" for candidate in candidate_list), encoding="utf-8")
    return len(candidate_list)


def format_text_report(report: dict[str, object]) -> str:
    lines = [
        "Worktree artifact audit",
        f"- changed paths: {report['total_changed_paths']}",
        f"- artifact-like changed paths: {report['artifact_changed_paths']}",
        f"- source-like changed paths: {report['source_changed_paths']}",
    ]
    if "cleanup_candidate_count" in report:
        lines.append(f"- tracked cleanup candidates: {report['cleanup_candidate_count']}")

    status_counts = report.get("status_counts", {})
    if isinstance(status_counts, dict) and status_counts:
        lines.append("- status counts:")
        lines.extend(f"  - {status!r}: {count}" for status, count in status_counts.items())

    for key, title in (
        ("artifact_top_levels", "artifact-like top levels"),
        ("source_top_levels", "source-like top levels"),
        ("tracked_artifact_paths", "tracked paths under artifact prefixes"),
    ):
        values = report.get(key, {})
        if isinstance(values, dict) and values:
            lines.append(f"- {title}:")
            lines.extend(f"  - {name}: {count}" for name, count in values.items())

    for key, title in (
        ("artifact_samples", "artifact-like samples"),
        ("source_samples", "source-like samples"),
        ("cleanup_candidate_samples", "tracked cleanup candidate samples"),
    ):
        values = report.get(key, [])
        if isinstance(values, list) and values:
            lines.append(f"- {title}:")
            lines.extend(f"  - {value}" for value in values[:20])

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a text summary.",
    )
    parser.add_argument(
        "--tracked-counts",
        action="store_true",
        help="Also count tracked files under known generated-artifact prefixes.",
    )
    parser.add_argument(
        "--cleanup-candidates",
        action="store_true",
        help=(
            "List tracked artifact paths that are likely candidates for "
            "git rm --cached. This is read-only and excludes Markdown docs "
            "and models/MODEL_REGISTRY.json by default."
        ),
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=50,
        help="Maximum cleanup candidate samples to include in JSON output. Default: 50.",
    )
    parser.add_argument(
        "--write-cleanup-candidates",
        metavar="PATH",
        help="Write the full cleanup candidate list to PATH, one path per line. This is read-only for Git.",
    )
    parser.add_argument(
        "--root",
        default=str(PROJECT_ROOT),
        help="Repository root to audit. Defaults to this project.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).resolve()
    report = build_report(
        cwd=root,
        include_tracked_counts=args.tracked_counts,
        include_cleanup_candidates=args.cleanup_candidates,
        candidate_limit=args.candidate_limit,
    )
    if args.write_cleanup_candidates:
        candidates = select_cleanup_candidates(
            list_tracked_artifact_paths(DEFAULT_ARTIFACT_PREFIXES, cwd=root)
        )
        written = write_cleanup_candidates(Path(args.write_cleanup_candidates), candidates)
        report["cleanup_candidate_list_path"] = args.write_cleanup_candidates
        report["cleanup_candidate_list_written"] = written
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
