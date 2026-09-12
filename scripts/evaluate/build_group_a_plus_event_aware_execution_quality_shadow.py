#!/usr/bin/env python3
"""Build GroupA+ event-aware execution quality shadow report."""

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

from group_a_plus.integrations.event_aware_execution_quality import (  # noqa: E402
    append_event_aware_execution_quality_log,
    build_event_aware_execution_quality,
)


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json"
DEFAULT_EXECUTION_PLAN = (
    PROJECT_ROOT / "report/group_a_plus/latest/execution_plan_20260807_1m_workbook_20260806_latest_strategy_preview.json"
)
DEFAULT_RELATIVE_THESIS = PROJECT_ROOT / "report/group_a_plus/latest/relative_exposure_thesis_shadow.json"
DEFAULT_LIQUIDITY_FEEDBACK = PROJECT_ROOT / "report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/event_aware_execution_quality_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/event_aware_execution_quality_shadow/history"
DEFAULT_LOG = PROJECT_ROOT / "results/event_aware_execution_quality_shadow_log.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"event_aware_execution_quality_shadow_{stamp}.json"


def build_report(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    execution_plan_path: Path | None = DEFAULT_EXECUTION_PLAN,
    relative_thesis_path: Path | None = DEFAULT_RELATIVE_THESIS,
    liquidity_feedback_path: Path | None = DEFAULT_LIQUIDITY_FEEDBACK,
    as_of: str | None = None,
) -> dict[str, Any]:
    report = build_event_aware_execution_quality(
        _load_json(live_signal_path),
        _load_json(execution_plan_path) if execution_plan_path is not None else None,
        _load_json(relative_thesis_path) if relative_thesis_path is not None else None,
        _load_json(liquidity_feedback_path) if liquidity_feedback_path is not None else None,
        as_of=as_of,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "live_signal": str(live_signal_path),
                "execution_plan": str(execution_plan_path) if execution_plan_path is not None else None,
                "relative_exposure_thesis": str(relative_thesis_path) if relative_thesis_path is not None else None,
                "liquidity_feedback": str(liquidity_feedback_path) if liquidity_feedback_path is not None else None,
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
        append_event_aware_execution_quality_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--relative-thesis", default=str(DEFAULT_RELATIVE_THESIS))
    parser.add_argument("--liquidity-feedback", default=str(DEFAULT_LIQUIDITY_FEEDBACK))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-execution-plan", action="store_true")
    parser.add_argument("--no-relative-thesis", action="store_true")
    parser.add_argument("--no-liquidity-feedback", action="store_true")
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=Path(args.live_signal),
        execution_plan_path=None if args.no_execution_plan else Path(args.execution_plan),
        relative_thesis_path=None if args.no_relative_thesis else Path(args.relative_thesis),
        liquidity_feedback_path=None if args.no_liquidity_feedback else Path(args.liquidity_feedback),
        as_of=args.as_of,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} status={status} quality={quality} target_allowed={target}".format(
            as_of=report.get("as_of"),
            status=report.get("status"),
            quality=report.get("quality_score"),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
