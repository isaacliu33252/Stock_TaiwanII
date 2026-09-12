#!/usr/bin/env python3
"""Build GroupA+ relative exposure thesis shadow report."""

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

from group_a_plus.integrations.relative_exposure_thesis import (  # noqa: E402
    append_relative_exposure_thesis_log,
    build_relative_exposure_thesis,
)


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/relative_exposure_thesis_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/relative_exposure_thesis_shadow/history"
DEFAULT_LOG = PROJECT_ROOT / "results/relative_exposure_thesis_shadow_log.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"relative_exposure_thesis_shadow_{stamp}.json"


def build_report(*, live_signal_path: Path = DEFAULT_LIVE_SIGNAL, as_of: str | None = None) -> dict[str, Any]:
    live_signal = _unwrap(_load_json(live_signal_path))
    report = build_relative_exposure_thesis(live_signal)
    report_as_of = as_of or str(live_signal.get("actual_data_date") or live_signal.get("requested_as_of_date") or "")
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": report_as_of,
            "sources": {"live_signal": str(live_signal_path)},
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
        append_relative_exposure_thesis_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(live_signal_path=Path(args.live_signal), as_of=args.as_of)
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} thesis={thesis} quality={quality} target_allowed={target}".format(
            as_of=report.get("as_of"),
            thesis=report.get("thesis_class"),
            quality=report.get("thesis_quality_score"),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
