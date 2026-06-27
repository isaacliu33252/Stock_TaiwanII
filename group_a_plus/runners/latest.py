"""Dispatch the schema-v2 active GroupA+ strategy runner."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest
from group_a_plus.runners.a207 import run_a207
from group_a_plus.runners.a213 import run_a213
from group_a_plus.runners.a214 import run_a214
from group_a_plus.runners.a215 import run_a215
from group_a_plus.runners.a217 import run_a217
from group_a_plus.runners.a2111 import run_a2111
from group_a_plus.runners.a2112 import run_a2112
from group_a_plus.runners.a2113 import run_a2113
from group_a_plus.runners.a2114 import run_a2114
from tw_output_standard import OutputStandardizer, write_standard_output


def run_latest(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    manifest_path: Path = DEFAULT_LATEST_STRATEGY,
) -> tuple[dict[str, Any], pd.DataFrame]:
    manifest = resolve_latest(manifest_path)
    strategy_id = manifest["active_strategy"]["id"]
    if strategy_id == "a213_cash30_recovery_ramp":
        report, frame = run_a213(start, end, initial_value, db)
    elif strategy_id == "a214_bond30c30_mw60":
        report, frame = run_a214(start, end, initial_value, db)
    elif strategy_id == "a215_cash40_mw80":
        report, frame = run_a215(start, end, initial_value, db)
    elif strategy_id == "a207":
        report, frame = run_a207(start, end, initial_value, db)
    elif strategy_id == "a217_tight_entry_mw100":
        report, frame = run_a217(start, end, initial_value, db)
    elif strategy_id == "a2111_tight_entry_bond30c30":
        report, frame = run_a2111(start, end, initial_value, db)
    elif strategy_id == "a2112_ma80_tight_entry_bond30c30_lrx":
        report, frame = run_a2112(start, end, initial_value, db)
    elif strategy_id == "a2113_a2111_ncf_overlay":
        report, frame = run_a2113(start, end, initial_value, db)
    elif strategy_id == "a2114_a2111_ncf_exit_gate":
        report, frame = run_a2114(start, end, initial_value, db)
    else:
        raise ValueError(f"No dispatcher for active strategy: {strategy_id}")
    report = dict(report)
    report["candidate_status"] = report.get("status")
    report["status"] = manifest["active_strategy"].get("status", "active")
    report["latest_manifest"] = str(manifest_path)
    report["latest_schema_version"] = manifest["schema_version"]
    report["active_strategy_id"] = strategy_id
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default="results/group_a_plus_runner_latest_20260620.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_latest_20260620_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.latest")
    try:
        report, frame = run_latest(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            Path(args.manifest),
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Latest runner JSON: {Path(args.output).resolve()}")
    print(f"Latest runner frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
