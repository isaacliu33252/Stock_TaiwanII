#!/usr/bin/env python3
"""Build a balanced local-news summary for the GroupA+ strategy watchlist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from group_a_plus.integrations.watchlist_news import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    DEFAULT_NEWS_GLOB,
    DEFAULT_OUTPUT_PATH,
    write_watchlist_news_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Signal date, YYYY-MM-DD.")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--max-articles", type=int, default=8)
    parser.add_argument("--per-symbol-limit", type=int, default=2)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--news-glob", default=DEFAULT_NEWS_GLOB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    summary = write_watchlist_news_summary(
        output_path=args.output,
        signal_date=args.date,
        lookback_days=args.lookback_days,
        max_articles=args.max_articles,
        per_symbol_limit=args.per_symbol_limit,
        config_path=args.config,
        news_glob=args.news_glob,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
