#!/usr/bin/env python3
"""Build GroupA+ hierarchical forecast-vs-actual credit review shadow report."""

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

from group_a_plus.integrations.hierarchical_credit_review import (  # noqa: E402
    append_hierarchical_credit_review_log,
    build_hierarchical_credit_review,
)


DEFAULT_FORECAST = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260807_1m_latest_strategy_preview.json"
DEFAULT_ACTUAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/hierarchical_credit_review_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/hierarchical_credit_review_shadow/history"
DEFAULT_LOG = PROJECT_ROOT / "results/hierarchical_credit_review_shadow_log.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"hierarchical_credit_review_shadow_{stamp}.json"


def build_report(
    *,
    forecast_path: Path = DEFAULT_FORECAST,
    actual_path: Path = DEFAULT_ACTUAL,
    as_of: str | None = None,
) -> dict[str, Any]:
    report = build_hierarchical_credit_review(_load_json(forecast_path), _load_json(actual_path), as_of=as_of)
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "forecast_signal": str(forecast_path),
                "actual_signal": str(actual_path),
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
        append_hierarchical_credit_review_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", default=str(DEFAULT_FORECAST))
    parser.add_argument("--actual", default=str(DEFAULT_ACTUAL))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(forecast_path=Path(args.forecast), actual_path=Path(args.actual), as_of=args.as_of)
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} primary={primary} confidence={confidence} target_allowed={target}".format(
            as_of=report.get("as_of"),
            primary=report.get("primary_attribution"),
            confidence=report.get("confidence"),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
