#!/usr/bin/env python3
"""Build the disabled-by-default GroupA+ defensive cash-floor candidate report."""

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

from group_a_plus.integrations.defensive_cash_floor_guard import (  # noqa: E402
    append_guarded_candidate_log,
    build_guarded_candidate,
)


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_SIGNED_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/defensive_cash_floor_guarded_candidate/history"
DEFAULT_LOG = PROJECT_ROOT / "results/defensive_cash_floor_guarded_candidate_log.jsonl"


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"defensive_cash_floor_guarded_candidate_{stamp}.json"


def build_report(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    signed_review_path: Path | None = DEFAULT_SIGNED_REVIEW,
    enabled: bool = False,
    as_of: str | None = None,
) -> dict[str, Any]:
    live_payload = _load_json(live_signal_path)
    if live_payload is None:
        raise FileNotFoundError(f"missing live signal: {live_signal_path}")
    live_signal = _unwrap(live_payload)
    signed_review = _load_json(signed_review_path)
    report = build_guarded_candidate(live_signal, signed_review=signed_review, enabled=enabled)
    report_as_of = as_of or str(live_signal.get("actual_data_date") or live_signal.get("requested_as_of_date") or "")
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": report_as_of,
            "sources": {
                "live_signal": str(live_signal_path),
                "signed_promotion_review": str(signed_review_path) if signed_review_path else None,
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
        append_guarded_candidate_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--signed-review", default=str(DEFAULT_SIGNED_REVIEW))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=Path(args.live_signal),
        signed_review_path=Path(args.signed_review) if args.signed_review else None,
        enabled=args.enable,
        as_of=args.as_of,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} enabled={enabled} triggered={triggered} changed={changed} target_allowed={allowed}".format(
            as_of=report.get("as_of"),
            enabled=report.get("enabled"),
            triggered=report.get("triggered"),
            changed=report.get("changed"),
            allowed=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
