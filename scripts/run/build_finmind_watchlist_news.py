#!/usr/bin/env python3
"""Build a watchlist_news.json-shaped summary from FinMind TaiwanStockNews.

Unlike group_a_plus.integrations.watchlist_news (keyword matching over
generic LTN articles), FinMind news is already ticker-tagged at the source
(fetched per data_id), so match_scope is trusted as-is rather than
re-derived from keywords. Output schema matches watchlist_news.json so it
is a drop-in --watchlist-news input for
scripts/evaluate/evaluate_event_sentiment_attribution_shadow.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_NEWS_GLOB = "news/finmind_stock_news_*.jsonl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news_finmind.json"


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _iter_rows(news_glob: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for path in sorted(PROJECT_ROOT.glob(news_glob)):
        with path.open(encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = str(row.get("url") or "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                rows.append(row)
    rows.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("title") or "")), reverse=True)
    return rows


def build_finmind_watchlist_news_summary(
    *,
    signal_date: str | None = None,
    lookback_days: int = 7,
    max_articles: int = 20,
    per_symbol_limit: int = 8,
    news_glob: str = DEFAULT_NEWS_GLOB,
) -> dict[str, Any]:
    target_date = _parse_date(signal_date) or date.today()
    start_date = target_date - timedelta(days=max(lookback_days - 1, 0))

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _iter_rows(news_glob):
        row_date = _parse_date(row.get("date"))
        if row_date is None or row_date < start_date or row_date > target_date:
            continue
        symbol = str(row.get("match_scope") or "")
        if not symbol or len(by_symbol[symbol]) >= per_symbol_limit:
            continue
        by_symbol[symbol].append(
            {
                "date": row.get("date"),
                "source": row.get("source"),
                "title": row.get("title"),
                "url": row.get("url"),
                "category": row.get("category"),
                "snippet": row.get("snippet") or "",
                "matched_keywords": [],
                "match_scope": symbol,
            }
        )

    symbols = sorted(by_symbol.keys())
    selected: list[dict[str, Any]] = []
    for round_idx in range(per_symbol_limit):
        for symbol in symbols:
            articles = by_symbol.get(symbol, [])
            if round_idx < len(articles):
                selected.append(articles[round_idx])
                if len(selected) >= max_articles:
                    break
        if len(selected) >= max_articles:
            break

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "signal_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "source": "finmind_stock_news",
        "news_glob": news_glob,
        "watchlist": [
            {"symbol": symbol, "matched_count": len(by_symbol.get(symbol, []))} for symbol in symbols
        ],
        "article_count": len(selected),
        "articles": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Signal date, YYYY-MM-DD.")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--max-articles", type=int, default=40)
    parser.add_argument("--per-symbol-limit", type=int, default=10)
    parser.add_argument("--news-glob", default=DEFAULT_NEWS_GLOB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    summary = build_finmind_watchlist_news_summary(
        signal_date=args.date,
        lookback_days=args.lookback_days,
        max_articles=args.max_articles,
        per_symbol_limit=args.per_symbol_limit,
        news_glob=args.news_glob,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"finmind watchlist news: {summary['article_count']} articles -> {args.output}")


if __name__ == "__main__":
    main()
