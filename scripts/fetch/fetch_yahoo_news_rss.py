#!/usr/bin/env python3
"""Fetch Yahoo奇摩股市/Yahoo奇摩新聞 finance RSS feeds as a news source.

Context: 2026-08-17, reviewing the current news-source landscape for the
Group A+ event-sentiment shadow line (see project_llm_feature_generator_news
memory) found that the two sources actually running daily -- FinMind
TaiwanStockNews (title only, snippet always empty) and the LTN scraper
(rich ~150-char snippets, but not scheduled and frequently stale) -- leave a
real content-quality gap. Yahoo's native RSS feeds turn out to carry real,
non-empty article-lead snippets (confirmed manually, ~130+ chars of genuine
financial reporting text), so this adds them as a third, independently
useful source rather than a redundant one.

Two feeds are fetched:
  - https://tw.stock.yahoo.com/rss?category=news  (Yahoo股市 - 最新新聞)
  - https://tw.news.yahoo.com/rss/finance          (財經新聞 - Yahoo奇摩新聞)

Output is a JSONL file with the same field shape as the existing
news/ltn_mainstream_*.jsonl cache (date, source, title, url, category,
snippet) so it is a drop-in input for group_a_plus.integrations.watchlist_news
and scripts/evaluate/evaluate_event_sentiment_attribution_shadow.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUT_DIR = PROJECT_ROOT / "news"
DEFAULT_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; StockTaiwan2-YahooRSSFetcher/1.0)"

FEEDS = {
    "stock_news": {
        "url": "https://tw.stock.yahoo.com/rss?category=news",
        "category": "yahoo_stock_news",
        "source": "Yahoo奇摩股市",
    },
    "finance_news": {
        "url": "https://tw.news.yahoo.com/rss/finance",
        "category": "yahoo_finance_news",
        "source": "Yahoo奇摩新聞",
    },
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _fetch_url(url: str, *, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, text/xml"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_rss(xml_bytes: bytes, *, category: str, default_source: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = _strip_html((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        description = _strip_html((item.findtext("description") or "").strip())
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        try:
            parsed = parsedate_to_datetime(pub_date_raw) if pub_date_raw else None
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        date_str = parsed.strftime("%Y-%m-%d") if parsed else ""
        rows.append(
            {
                "date": date_str,
                "source": default_source,
                "title": title,
                "url": link,
                "category": category,
                "snippet": description,
            }
        )
    return rows


def fetch_feed(feed_key: str, *, timeout: int = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    spec = FEEDS[feed_key]
    xml_bytes = _fetch_url(spec["url"], timeout=timeout)
    return parse_rss(xml_bytes, category=spec["category"], default_source=spec["source"])


def fetch_all(*, timeout: int = DEFAULT_TIMEOUT) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (rows, errors). A feed failing is non-fatal to the other feed."""
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    for feed_key in FEEDS:
        try:
            feed_rows = fetch_feed(feed_key, timeout=timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError) as exc:
            errors.append(f"{feed_key}: {exc}")
            continue
        for row in feed_rows:
            url = row.get("url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            rows.append(row)
    rows.sort(key=lambda r: (r.get("date", ""), r.get("title", "")))
    return rows, errors


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    rows, errors = fetch_all(timeout=args.timeout)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"yahoo_news_rss_{stamp}.jsonl"
    write_jsonl(rows, out_path)
    print(f"yahoo news rss: {len(rows)} articles -> {out_path}")
    for err in errors:
        print(f"WARNING: feed fetch failed: {err}")


if __name__ == "__main__":
    main()
