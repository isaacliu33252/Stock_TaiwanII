"""Balanced local-news selection for the GroupA+ strategy watchlist."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from group_a_plus.outputs import output_path as canonical_output_path
from group_a_plus.outputs import write_json_report
from group_a_plus.paths import PROJECT_ROOT


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config/group_a_plus_watchlist.json"
DEFAULT_NEWS_GLOB = "news/ltn_mainstream_*.jsonl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news.json"


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_watchlist_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _iter_news_records(news_glob: str) -> list[dict[str, Any]]:
    paths = sorted(PROJECT_ROOT.glob(news_glob))
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for path in paths:
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
                records.append(row)
    records.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("title") or "")), reverse=True)
    return records


def _text_blob(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "snippet", "category", "source"))


def _article_summary(row: dict[str, Any], *, matched_keywords: list[str], match_scope: str) -> dict[str, Any]:
    return {
        "date": row.get("date"),
        "source": row.get("source"),
        "title": row.get("title"),
        "url": row.get("url"),
        "category": row.get("category"),
        "snippet": str(row.get("snippet") or "")[:180],
        "matched_keywords": matched_keywords,
        "match_scope": match_scope,
    }


def build_watchlist_news_summary(
    *,
    signal_date: str | None = None,
    lookback_days: int = 7,
    max_articles: int = 8,
    per_symbol_limit: int = 2,
    config_path: Path = DEFAULT_CONFIG_PATH,
    news_glob: str = DEFAULT_NEWS_GLOB,
) -> dict[str, Any]:
    config = load_watchlist_config(config_path)
    symbols = config.get("symbols") or []
    target_date = _parse_date(signal_date) or date.today()
    start_date = target_date - timedelta(days=max(lookback_days - 1, 0))
    rows = []
    for row in _iter_news_records(news_glob):
        row_date = _parse_date(row.get("date"))
        if row_date is None or row_date < start_date or row_date > target_date:
            continue
        rows.append(row)

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_urls: set[str] = set()
    for item in symbols:
        symbol = str(item.get("symbol") or "")
        keywords = [str(keyword) for keyword in item.get("keywords", []) if str(keyword)]
        for row in rows:
            url = str(row.get("url") or "")
            if url in used_urls:
                continue
            blob = _text_blob(row)
            matched = [keyword for keyword in keywords if keyword in blob]
            if not matched:
                continue
            by_symbol[symbol].append(_article_summary(row, matched_keywords=matched, match_scope=symbol))
            used_urls.add(url)
            if len(by_symbol[symbol]) >= per_symbol_limit:
                break

    selected: list[dict[str, Any]] = []
    for round_idx in range(per_symbol_limit):
        for item in symbols:
            symbol = str(item.get("symbol") or "")
            articles = by_symbol.get(symbol, [])
            if round_idx < len(articles):
                selected.append(articles[round_idx])
                if len(selected) >= max_articles:
                    break
        if len(selected) >= max_articles:
            break

    fallback_keywords = [str(keyword) for keyword in config.get("market_fallback_keywords", []) if str(keyword)]
    fallback_used = False
    if len(selected) < max_articles and fallback_keywords:
        fallback_used = True
        selected_urls = {str(article.get("url") or "") for article in selected}
        for row in rows:
            url = str(row.get("url") or "")
            if url in selected_urls or url in used_urls:
                continue
            blob = _text_blob(row)
            matched = [keyword for keyword in fallback_keywords if keyword in blob]
            if not matched:
                continue
            selected.append(_article_summary(row, matched_keywords=matched, match_scope="market_fallback"))
            selected_urls.add(url)
            if len(selected) >= max_articles:
                break

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "signal_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "source": "local_ltn_jsonl",
        "config": str(config_path),
        "news_glob": news_glob,
        "watchlist": [
            {
                "symbol": item.get("symbol"),
                "label": item.get("label"),
                "matched_count": len(by_symbol.get(str(item.get("symbol") or ""), [])),
            }
            for item in symbols
        ],
        "fallback_used": fallback_used,
        "article_count": len(selected),
        "articles": selected,
    }


def write_watchlist_news_summary(
    *,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    canonical_path: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    summary = build_watchlist_news_summary(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if canonical_path is None and output_path == DEFAULT_OUTPUT_PATH:
        canonical_path = canonical_output_path("watchlist_news", kind="pipeline", run_mode="production", latest=True)
    if canonical_path is not None:
        write_json_report(
            canonical_path,
            artifact_name="watchlist_news",
            kind="pipeline",
            run_mode="production",
            payload=summary,
        )
    return summary
