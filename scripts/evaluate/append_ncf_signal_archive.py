#!/usr/bin/env python3
"""Append today's NCF signal snapshot(s) to the research archive.

Research-only, logging step: never changes a live decision. Reads the daily
NCF JSON files already produced by the model runners and appends one row per
ticker to results/ncf_signal_archive.jsonl (deduplicated by ticker+date), so
that scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py can eventually
compare blend_live_auc candidates once enough forward-realized outcomes exist.

Safe to run standalone, or add as a best-effort step in
scripts/run/run_ncf_daily_pipeline.py -- a failure here should never block the
rest of the pipeline (see BEST_EFFORT_STEP_NAMES there for the existing
convention).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.ncf import load_ncf_signal
from group_a_plus.integrations.ncf_signal_archive import append_archive_rows, build_archive_row

DEFAULT_ARCHIVE_PATH = PROJECT_ROOT / "results" / "ncf_signal_archive.jsonl"
RESULTS_DIR = PROJECT_ROOT / "results"
DATED_FILE_PATTERNS = ("ncf_00631l_latest_{stamp}.json", "ncf_00632r_latest_{stamp}.json")


def _dated_sources(stamp: str) -> list[Path]:
    return [RESULTS_DIR / pattern.format(stamp=stamp) for pattern in DATED_FILE_PATTERNS]


def _all_backfillable_sources() -> list[Path]:
    """Every ncf_{00631l,00632r}_latest_YYYYMMDD.json already on disk."""
    found = []
    for prefix in ("ncf_00631l_latest_", "ncf_00632r_latest_"):
        for path in sorted(RESULTS_DIR.glob(f"{prefix}*.json")):
            stamp = path.stem[len(prefix) :]
            if len(stamp) == 8 and stamp.isdigit():
                found.append(path)
    return found


def _load_rows(sources: list[Path]) -> list[dict]:
    rows = []
    for path in sources:
        if not path.exists():
            print(f"skip (not found): {path}")
            continue
        signal = load_ncf_signal(path)
        row = build_archive_row(signal)
        if row is None:
            print(f"skip (no horizon data): {path}")
            continue
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[], help="One or more NCF JSON files to append (repeatable). Overrides --date-stamp/--backfill.")
    parser.add_argument("--date-stamp", default=date.today().strftime("%Y%m%d"), help="YYYYMMDD stamp used to locate today's ncf_00631l_latest_<stamp>.json / ncf_00632r_latest_<stamp>.json.")
    parser.add_argument("--backfill", action="store_true", help="Scan results/ for every existing dated ncf_{00631l,00632r}_latest_YYYYMMDD.json and append all of them.")
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE_PATH))
    args = parser.parse_args()

    if args.source:
        sources = [Path(p) for p in args.source]
    elif args.backfill:
        sources = _all_backfillable_sources()
    else:
        sources = _dated_sources(args.date_stamp)

    rows = _load_rows(sources)
    appended = append_archive_rows(rows, Path(args.archive))
    print(f"Scanned {len(sources)} source file(s); appended {appended} new row(s) to {args.archive}")


if __name__ == "__main__":
    main()
