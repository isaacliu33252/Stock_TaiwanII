#!/usr/bin/env python3
"""Audit top-level repository layout pressure.

This tool is read-only. It highlights files that could be moved behind
compatibility wrappers or documented migration plans, without moving anything.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ROOT_KEEP_FILES = {
    ".gitignore",
    "README.md",
    "__init__.py",
    "config.py",
    "portfolio_config.py",
    "pytest.ini",
    "requirements.txt",
    "requirements_final.txt",
}

SCRIPT_PREFIXES = (
    "apply_",
    "backtest_",
    "build_",
    "compare_",
    "convert_",
    "evaluate_",
    "fetch_",
    "filter_",
    "generate_",
    "prepare_",
    "refresh_",
    "research_",
    "taifex_",
    "train_",
    "walk_forward",
)

DOC_HINTS = (
    "HANDOFF",
    "HANDOVER",
    "REVIEW",
    "REPORT",
    "RESULT",
    "RESULTS",
    "RELEASE",
    "CHECKLIST",
    "DECISION",
    "GOVERNANCE",
    "IMPORT",
    "OPTIMIZATION",
)

DATA_SUFFIXES = {".csv", ".db", ".duckdb", ".parquet", ".xls", ".xlsx"}
RUNNER_SUFFIXES = {".bat", ".sh"}


@dataclass(frozen=True)
class LayoutEntry:
    path: str
    category: str
    suggested_location: str
    reason: str


def classify_root_file(path: Path) -> LayoutEntry:
    name = path.name
    suffix = path.suffix.lower()
    upper_name = name.upper()

    if name in ROOT_KEEP_FILES:
        return LayoutEntry(name, "keep_root", ".", "known root-level project entry/config")

    if suffix == ".md":
        if any(hint in upper_name for hint in DOC_HINTS):
            return LayoutEntry(name, "root_doc_candidate", "docs/ or handoff/", "top-level handoff/review/report doc")
        return LayoutEntry(name, "root_doc", "docs/", "top-level markdown doc")

    if suffix == ".py":
        if name.startswith("_"):
            return LayoutEntry(name, "scratch_script_candidate", "scripts/misc/", "underscore-prefixed root script")
        if name.startswith(SCRIPT_PREFIXES):
            return LayoutEntry(name, "script_candidate", "scripts/", "root script with workflow prefix")
        return LayoutEntry(name, "module_candidate", "package or scripts/", "root Python module outside package")

    if suffix in DATA_SUFFIXES:
        return LayoutEntry(name, "data_artifact_candidate", "data/ or local artifact store", "top-level data/cache file")

    if suffix == ".json":
        return LayoutEntry(name, "config_candidate", "config/", "top-level JSON config")

    if suffix in RUNNER_SUFFIXES:
        return LayoutEntry(name, "runner_candidate", "scripts/run/", "top-level runner script")

    return LayoutEntry(name, "misc_candidate", "docs/ or scripts/misc/", "uncategorized top-level file")


def iter_root_files(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_file())


def build_layout_report(root: Path, *, sample_limit: int) -> dict[str, object]:
    entries = [classify_root_file(path) for path in iter_root_files(root)]
    category_counts = Counter(entry.category for entry in entries)
    destination_counts = Counter(entry.suggested_location for entry in entries)
    relocation_entries = [entry for entry in entries if entry.category != "keep_root"]

    samples_by_category: dict[str, list[dict[str, str]]] = {}
    for entry in entries:
        samples = samples_by_category.setdefault(entry.category, [])
        if len(samples) < sample_limit:
            samples.append(
                {
                    "path": entry.path,
                    "suggested_location": entry.suggested_location,
                    "reason": entry.reason,
                }
            )

    return {
        "root_file_count": len(entries),
        "keep_root_count": category_counts.get("keep_root", 0),
        "relocation_candidate_count": len(relocation_entries),
        "category_counts": dict(category_counts.most_common()),
        "suggested_location_counts": dict(destination_counts.most_common()),
        "samples_by_category": samples_by_category,
    }


def format_text_report(report: dict[str, object]) -> str:
    lines = [
        "Repository layout audit",
        f"- root files: {report['root_file_count']}",
        f"- keep-root files: {report['keep_root_count']}",
        f"- relocation candidates: {report['relocation_candidate_count']}",
    ]

    for key, title in (
        ("category_counts", "categories"),
        ("suggested_location_counts", "suggested locations"),
    ):
        values = report.get(key, {})
        if isinstance(values, dict) and values:
            lines.append(f"- {title}:")
            lines.extend(f"  - {name}: {count}" for name, count in values.items())

    samples_by_category = report.get("samples_by_category", {})
    if isinstance(samples_by_category, dict):
        lines.append("- samples:")
        for category, samples in samples_by_category.items():
            lines.append(f"  - {category}:")
            if isinstance(samples, list):
                for sample in samples:
                    if isinstance(sample, dict):
                        lines.append(
                            "    - "
                            f"{sample['path']} -> {sample['suggested_location']} "
                            f"({sample['reason']})"
                        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Repository root to audit.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--sample-limit", type=int, default=8, help="Samples per category. Default: 8.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_layout_report(Path(args.root).resolve(), sample_limit=args.sample_limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
