#!/usr/bin/env python3
"""Backtest Moira execution-guard hard-stop proposal on saved live signals."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.moira_execution_guard_backtest import (  # noqa: E402
    build_execution_guard_hard_stop_backtest,
)
from group_a_plus.integrations.moira_policy_critic_validation import load_signal_records  # noqa: E402


DEFAULT_SIGNAL_GLOB = "results/group_a_plus_live_signal_v2_2026*.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/moira_execution_guard_hard_stop_backtest_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/moira_execution_guard_hard_stop_backtest_shadow/history"


def _glob_paths(pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_absolute():
        return sorted(path.parent.glob(path.name))
    return sorted(PROJECT_ROOT.glob(pattern))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"moira_execution_guard_hard_stop_backtest_shadow_{stamp}.json"


def build_report(
    *,
    signal_glob: str = DEFAULT_SIGNAL_GLOB,
    as_of: str | None = None,
    min_trigger_count: int = 5,
) -> dict[str, Any]:
    report = build_execution_guard_hard_stop_backtest(
        signal_records=load_signal_records(_glob_paths(signal_glob)),
        as_of=as_of,
        min_trigger_count=min_trigger_count,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {"signal_glob": signal_glob},
        }
    )
    return report


def write_report(
    report: dict[str, Any],
    *,
    output_path: Path = DEFAULT_OUTPUT,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-glob", default=DEFAULT_SIGNAL_GLOB)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--min-trigger-count", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        signal_glob=args.signal_glob,
        as_of=args.as_of,
        min_trigger_count=args.min_trigger_count,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
    )
    print(
        "as_of={as_of} triggers={triggers} recommendation={rec} target_allowed={target}".format(
            as_of=report.get("as_of"),
            triggers=report.get("input_coverage", {}).get("trigger_count"),
            rec=report.get("summary", {}).get("recommendation"),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
