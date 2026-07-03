"""Dispatch the schema-v2 active GroupA+ strategy runner."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import (
    DEFAULT_LATEST_STRATEGY,
    SUPPORTED_STRATEGIES,
    resolve_latest,
)
from tw_output_standard import OutputStandardizer, write_standard_output


def _load_runner(strategy_id: str, module_name: str):
    expected_module = SUPPORTED_STRATEGIES.get(strategy_id)
    if expected_module != module_name:
        raise ValueError(f"Runner mismatch for {strategy_id}: expected {expected_module}")
    module = importlib.import_module(module_name)
    runner_name = f"run_{module_name.rsplit('.', 1)[-1]}"
    runner = getattr(module, runner_name, None)
    if runner is None:
        raise ValueError(f"Runner module {module_name} is missing {runner_name}")
    return runner


def run_latest(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    manifest_path: Path = DEFAULT_LATEST_STRATEGY,
) -> tuple[dict[str, Any], pd.DataFrame]:
    manifest = resolve_latest(manifest_path)
    active = manifest["active_strategy"]
    strategy_id = active["id"]
    runner = _load_runner(strategy_id, active["runner"])
    runner_params = dict(active.get("runner_params") or {})
    report, frame = runner(start, end, initial_value, db, **runner_params)
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
