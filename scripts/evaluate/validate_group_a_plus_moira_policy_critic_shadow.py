#!/usr/bin/env python3
"""Validate Moira policy critic proposals with historical artifact replay."""

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

from group_a_plus.integrations.moira_policy_critic_validation import (  # noqa: E402
    append_moira_policy_critic_validation_log,
    build_moira_policy_critic_validation,
    load_plan_records,
    load_signal_records,
)


DEFAULT_SIGNAL_GLOB = "results/group_a_plus_live_signal_v2_2026*.json"
DEFAULT_PLAN_GLOB = "results/group_a_plus_execution_plan_v2_2026*.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/moira_policy_critic_validation_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/moira_policy_critic_validation_shadow/history"
DEFAULT_LOG = PROJECT_ROOT / "results/moira_policy_critic_validation_shadow_log.jsonl"


def _glob_paths(pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_absolute():
        return sorted(path.parent.glob(path.name))
    return sorted(PROJECT_ROOT.glob(pattern))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"moira_policy_critic_validation_shadow_{stamp}.json"


def build_report(
    *,
    signal_glob: str = DEFAULT_SIGNAL_GLOB,
    plan_glob: str = DEFAULT_PLAN_GLOB,
    as_of: str | None = None,
    min_trigger_count: int = 5,
) -> dict[str, Any]:
    signal_records = load_signal_records(_glob_paths(signal_glob))
    plan_records = load_plan_records(_glob_paths(plan_glob))
    report = build_moira_policy_critic_validation(
        signal_records=signal_records,
        plan_records=plan_records,
        as_of=as_of,
        min_trigger_count_for_backtest=min_trigger_count,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "signal_glob": signal_glob,
                "plan_glob": plan_glob,
            },
        }
    )
    return report


def write_report(
    report: dict[str, Any],
    *,
    output_path: Path = DEFAULT_OUTPUT,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
    log_path: Path | None = DEFAULT_LOG,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if log_path is not None and report.get("as_of"):
        append_moira_policy_critic_validation_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-glob", default=DEFAULT_SIGNAL_GLOB)
    parser.add_argument("--plan-glob", default=DEFAULT_PLAN_GLOB)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--min-trigger-count", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        signal_glob=args.signal_glob,
        plan_glob=args.plan_glob,
        as_of=args.as_of,
        min_trigger_count=args.min_trigger_count,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} signals={signals} ready={ready} target_allowed={target}".format(
            as_of=report.get("as_of"),
            signals=report.get("input_coverage", {}).get("signal_record_count"),
            ready=len(report.get("summary", {}).get("ready_for_shadow_backtest") or []),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
