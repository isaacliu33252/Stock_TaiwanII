#!/usr/bin/env python3
"""Build GroupA+ news event-prior shadow from current watchlist news.

Research-only implementation inspired by arXiv:2608.14014. It classifies
headlines into coarse event buckets and emits context/width priors only; it
does not create orders and must not affect target weights.
"""

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

from group_a_plus.integrations.news_event_prior_shadow import (  # noqa: E402
    append_news_event_prior_shadow_log,
    build_news_event_prior_shadow,
)

DEFAULT_WATCHLIST_NEWS = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "watchlist_news.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "news_event_prior_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "news_event_prior_shadow" / "history"
DEFAULT_LOG = PROJECT_ROOT / "results" / "news_event_prior_shadow_log.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"news_event_prior_shadow_{stamp}.json"


def build_report(
    *,
    watchlist_news_path: Path = DEFAULT_WATCHLIST_NEWS,
    as_of: str | None = None,
    max_articles: int = 80,
) -> dict[str, Any]:
    watchlist_news = _load_json(watchlist_news_path)
    report = build_news_event_prior_shadow(
        watchlist_news=watchlist_news,
        as_of=as_of,
        max_articles=max_articles,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "watchlist_news": str(watchlist_news_path),
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
    if log_path is not None:
        append_news_event_prior_shadow_log(log_path, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist-news", default=str(DEFAULT_WATCHLIST_NEWS))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--max-articles", type=int, default=80)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        watchlist_news_path=Path(args.watchlist_news),
        as_of=args.as_of,
        max_articles=args.max_articles,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} status={status} articles={articles} target_allowed={target}".format(
            as_of=report.get("as_of"),
            status=report.get("status"),
            articles=report.get("article_count"),
            target=report.get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
