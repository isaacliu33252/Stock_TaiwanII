#!/usr/bin/env python3
"""Build GroupA+ Moira-style policy critic shadow report."""

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

from group_a_plus.integrations.moira_policy_critic import (  # noqa: E402
    append_moira_policy_critic_log,
    build_moira_policy_critic,
)


DEFAULT_CREDIT = PROJECT_ROOT / "report/group_a_plus/latest/hierarchical_credit_review_shadow.json"
DEFAULT_EXECUTION = PROJECT_ROOT / "report/group_a_plus/latest/event_aware_execution_quality_shadow.json"
DEFAULT_THESIS = PROJECT_ROOT / "report/group_a_plus/latest/relative_exposure_thesis_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/moira_policy_critic_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/moira_policy_critic_shadow/history"
DEFAULT_LOG = PROJECT_ROOT / "results/moira_policy_critic_shadow_log.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"moira_policy_critic_shadow_{stamp}.json"


def build_report(
    *,
    credit_path: Path = DEFAULT_CREDIT,
    execution_path: Path = DEFAULT_EXECUTION,
    thesis_path: Path = DEFAULT_THESIS,
    as_of: str | None = None,
) -> dict[str, Any]:
    report = build_moira_policy_critic(
        hierarchical_credit_review=_load_json(credit_path),
        event_execution_quality=_load_json(execution_path),
        relative_exposure_thesis=_load_json(thesis_path),
        as_of=as_of,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "hierarchical_credit_review": str(credit_path),
                "event_aware_execution_quality": str(execution_path),
                "relative_exposure_thesis": str(thesis_path),
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
        append_moira_policy_critic_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credit", default=str(DEFAULT_CREDIT))
    parser.add_argument("--execution", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--thesis", default=str(DEFAULT_THESIS))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        credit_path=Path(args.credit),
        execution_path=Path(args.execution),
        thesis_path=Path(args.thesis),
        as_of=args.as_of,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} status={status} proposals={count} target_allowed={target}".format(
            as_of=report.get("as_of"),
            status=report.get("status"),
            count=report.get("proposal_count"),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
