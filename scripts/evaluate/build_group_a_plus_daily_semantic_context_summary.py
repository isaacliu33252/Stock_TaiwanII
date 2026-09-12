#!/usr/bin/env python3
"""Build compact GroupA+ daily semantic context summary."""

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

from group_a_plus.integrations.daily_semantic_context import (  # noqa: E402
    append_daily_semantic_context_log,
    build_daily_semantic_context,
)


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json"
DEFAULT_SIGNAL_ALIGNMENT = PROJECT_ROOT / "report/group_a_plus/latest/signal_alignment.json"
DEFAULT_RISK_MECHANISM = PROJECT_ROOT / "report/group_a_plus/latest/risk_mechanism.json"
DEFAULT_WATCHLIST_NEWS = PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news.json"
DEFAULT_CREDIT = PROJECT_ROOT / "report/group_a_plus/latest/hierarchical_credit_review_shadow.json"
DEFAULT_EXECUTION = PROJECT_ROOT / "report/group_a_plus/latest/event_aware_execution_quality_shadow.json"
DEFAULT_THESIS = PROJECT_ROOT / "report/group_a_plus/latest/relative_exposure_thesis_shadow.json"
DEFAULT_CRITIC = PROJECT_ROOT / "report/group_a_plus/latest/moira_policy_critic_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/daily_semantic_context_summary.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/daily_semantic_context_summary/history"
DEFAULT_LOG = PROJECT_ROOT / "results/daily_semantic_context_summary_log.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"daily_semantic_context_summary_{stamp}.json"


def build_report(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    signal_alignment_path: Path = DEFAULT_SIGNAL_ALIGNMENT,
    risk_mechanism_path: Path = DEFAULT_RISK_MECHANISM,
    watchlist_news_path: Path = DEFAULT_WATCHLIST_NEWS,
    credit_path: Path = DEFAULT_CREDIT,
    execution_path: Path = DEFAULT_EXECUTION,
    thesis_path: Path = DEFAULT_THESIS,
    critic_path: Path = DEFAULT_CRITIC,
    as_of: str | None = None,
) -> dict[str, Any]:
    report = build_daily_semantic_context(
        live_signal=_load_json(live_signal_path),
        signal_alignment=_load_json(signal_alignment_path),
        risk_mechanism=_load_json(risk_mechanism_path),
        watchlist_news=_load_json(watchlist_news_path),
        hierarchical_credit_review=_load_json(credit_path),
        event_execution_quality=_load_json(execution_path),
        relative_exposure_thesis=_load_json(thesis_path),
        moira_policy_critic=_load_json(critic_path),
        as_of=as_of,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "live_signal": str(live_signal_path),
                "signal_alignment": str(signal_alignment_path),
                "risk_mechanism": str(risk_mechanism_path),
                "watchlist_news": str(watchlist_news_path),
                "hierarchical_credit_review": str(credit_path),
                "event_aware_execution_quality": str(execution_path),
                "relative_exposure_thesis": str(thesis_path),
                "moira_policy_critic": str(critic_path),
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
        append_daily_semantic_context_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--signal-alignment", default=str(DEFAULT_SIGNAL_ALIGNMENT))
    parser.add_argument("--risk-mechanism", default=str(DEFAULT_RISK_MECHANISM))
    parser.add_argument("--watchlist-news", default=str(DEFAULT_WATCHLIST_NEWS))
    parser.add_argument("--credit", default=str(DEFAULT_CREDIT))
    parser.add_argument("--execution", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--thesis", default=str(DEFAULT_THESIS))
    parser.add_argument("--critic", default=str(DEFAULT_CRITIC))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=Path(args.live_signal),
        signal_alignment_path=Path(args.signal_alignment),
        risk_mechanism_path=Path(args.risk_mechanism),
        watchlist_news_path=Path(args.watchlist_news),
        credit_path=Path(args.credit),
        execution_path=Path(args.execution),
        thesis_path=Path(args.thesis),
        critic_path=Path(args.critic),
        as_of=args.as_of,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} blockers={blockers} target_allowed={target}".format(
            as_of=report.get("as_of"),
            blockers=len(report.get("compressed_takeaways", {}).get("hard_blockers") or []),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
