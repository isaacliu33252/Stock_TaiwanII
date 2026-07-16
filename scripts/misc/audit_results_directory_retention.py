#!/usr/bin/env python3
"""Audit results/ for disk-space retention candidates (2026-07-07 Fable audit).

results/ has no retention policy and grows every pipeline run -- found at
1.6GB / 2,947 files with the live disk at 1.3% free (see
group_a_plus.operations.ops_health's new disk warn/error thresholds). Most of
that footprint is a handful of large one-off sweep/backtest JSON files from
concluded (often since-rejected) experiments, not the many small daily-dated
pipeline snapshots.

This is a read-only report tool. It does NOT delete anything -- this project
keeps an audit trail in strategy.json / *_HANDOFF_*.md of exactly which
results/ files justified each production decision, so a blind "keep only
latest N per family" policy risks deleting evidence a human would want to
keep. A file is only listed as a deletion candidate when its exact filename
has zero references anywhere else in the tracked repo (*.md, *.json, *.py).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"

_DATE_SUFFIX_RE = re.compile(r"_\d{8}(_\d{6})?")


def _family(name: str) -> str:
    stem = Path(name).stem
    stem = _DATE_SUFFIX_RE.sub("", stem)
    return stem or Path(name).suffix


def _is_referenced_elsewhere(filename: str, *, search_root: Path) -> bool:
    """grep for the exact filename across tracked text files.

    Excludes .git (huge object store, makes `grep -r` time out on this repo's
    WSL/9p-mounted filesystem) and results/ itself -- self-references there
    are meaningless (e.g. a prior run of this same audit tool writes its own
    report into results/, which would otherwise make every candidate filename
    look "referenced" by that report on the next run -- caught during manual
    verification of this tool's first real run, 2026-07-07: every one of 40
    candidates came back as a false-positive "referenced" hit against
    results/results_retention_audit_*.json before this exclusion was added).
    """
    try:
        out = subprocess.run(
            [
                "grep", "-rl", "--include=*.md", "--include=*.json", "--include=*.py",
                "--exclude-dir=.git", "--exclude-dir=__pycache__", "--exclude-dir=results",
                "-F", filename, str(search_root),
            ],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return True  # fail safe: treat as referenced (protected) on any error
    return bool(out.stdout.strip())


def audit_results_directory(
    *,
    results_dir: Path = RESULTS_DIR,
    search_root: Path = PROJECT_ROOT,
    min_size_bytes: int = 1_000_000,
    top_n: int = 40,
) -> dict[str, Any]:
    files = [p for p in results_dir.iterdir() if p.is_file()]
    total_size = sum(p.stat().st_size for p in files)

    large_files = sorted(
        (p for p in files if p.stat().st_size >= min_size_bytes),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )[:top_n]

    candidates = []
    protected = []
    for path in large_files:
        size = path.stat().st_size
        referenced = _is_referenced_elsewhere(path.name, search_root=search_root)
        row = {
            "path": f"results/{path.name}",
            "family": _family(path.name),
            "size_bytes": size,
            "size_mb": round(size / 1_000_000, 1),
            "referenced_elsewhere": referenced,
        }
        (protected if referenced else candidates).append(row)

    families: dict[str, dict[str, Any]] = {}
    for path in files:
        fam = _family(path.name)
        entry = families.setdefault(fam, {"count": 0, "total_size_bytes": 0})
        entry["count"] += 1
        entry["total_size_bytes"] += path.stat().st_size
    family_summary = sorted(
        ({"family": name, **info} for name, info in families.items()),
        key=lambda row: row["total_size_bytes"],
        reverse=True,
    )[:20]

    return {
        "report_type": "results_directory_retention_audit",
        "results_dir": str(results_dir),
        "total_files": len(files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1_000_000, 1),
        "min_size_bytes_scanned": min_size_bytes,
        "large_file_deletion_candidates": candidates,
        "large_file_deletion_candidates_total_mb": round(
            sum(row["size_bytes"] for row in candidates) / 1_000_000, 1
        ),
        "large_files_protected_referenced_elsewhere": protected,
        "top_families_by_size": family_summary,
        "note": "Read-only report. No files were deleted. Review candidates "
                "manually -- filename has zero references elsewhere in the "
                "repo, but that is a heuristic, not a guarantee of safety.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default=str(RESULTS_DIR))
    parser.add_argument("--min-size-mb", type=float, default=1.0)
    parser.add_argument("--top-n", type=int, default=40)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = audit_results_directory(
        results_dir=Path(args.results_dir),
        min_size_bytes=int(args.min_size_mb * 1_000_000),
        top_n=args.top_n,
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved: {out}")

    print(
        f"results/: {report['total_files']} files, {report['total_size_mb']} MB total"
    )
    print(
        f"Deletion candidates (unreferenced, >= {args.min_size_mb} MB): "
        f"{len(report['large_file_deletion_candidates'])} files, "
        f"{report['large_file_deletion_candidates_total_mb']} MB"
    )
    for row in report["large_file_deletion_candidates"]:
        print(f"  {row['size_mb']:>8.1f} MB  {row['path']}")


if __name__ == "__main__":
    main()
