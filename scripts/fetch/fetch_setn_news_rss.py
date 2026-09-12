#!/usr/bin/env python3
"""Fetch 三立新聞網 (SETN) finance articles via Google News RSS.

Context: 2026-08-17, adding SETN as a third news source alongside the LTN
scraper and FinMind. SETN's own search page (setn.com/search) is a
client-side-rendered SPA -- fetching it returns an empty document body, so
the LTN-style raw-HTML scraping approach does not work. SETN does not
expose a working RSS feed either (all attempted paths redirect to the
homepage). Google News RSS supports a `site:` restricted search that
returns real, dated, linkable SETN articles in structured RSS, so this uses
that as the retrieval channel instead of scraping setn.com directly.

Caveat: Google News RSS descriptions do not carry real article-lead text
(the <description> is just the title repeated plus a source tag), so the
"snippet" field here is intentionally left empty rather than populated with
a fake duplicate of the title -- callers relying on snippet content (as
opposed to title) should prefer the Yahoo or LTN sources for that.

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
import urllib.parse
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
DEFAULT_LOOKBACK_DAYS = 2
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
SITE_DOMAIN = "setn.com"
DEFAULT_KEYWORDS = ("台股", "0050", "00631L", "00632R", "台積電", "美股")
TITLE_SUFFIX_RE = re.compile(r"\s*-\s*三立新聞\s*$")


def build_query_url(keyword: str, *, lookback_days: int) -> str:
    query = f"site:{SITE_DOMAIN} {keyword} when:{lookback_days}d"
    params = {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    return GOOGLE_NEWS_RSS_URL + "?" + urllib.parse.urlencode(params)


def _fetch_url(url: str, *, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; StockTaiwan2-SetnRSSFetcher/1.0)", "Accept": "application/rss+xml"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_rss(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict[str, Any]] = []
    for item in root.iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        title = TITLE_SUFFIX_RE.sub("", raw_title).strip()
        link = (item.findtext("link") or "").strip()
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
                "source": "三立新聞",
                "title": title,
                "url": link,
                "category": "setn_google_news_rss",
                "snippet": "",  # Google News RSS description carries no real lead text; see module docstring.
            }
        )
    return rows


def fetch_keyword(keyword: str, *, lookback_days: int, timeout: int) -> list[dict[str, Any]]:
    url = build_query_url(keyword, lookback_days=lookback_days)
    xml_bytes = _fetch_url(url, timeout=timeout)
    return parse_rss(xml_bytes)


def fetch_all(
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (rows, errors). One keyword's failure does not abort the others."""
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    for keyword in keywords:
        try:
            keyword_rows = fetch_keyword(keyword, lookback_days=lookback_days, timeout=timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError) as exc:
            errors.append(f"{keyword}: {exc}")
            continue
        for row in keyword_rows:
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
    parser.add_argument("--keywords", default=None, help="Comma-separated keywords; default covers Group A+ watchlist scope")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    keywords = tuple(k.strip() for k in args.keywords.split(",") if k.strip()) if args.keywords else DEFAULT_KEYWORDS
    rows, errors = fetch_all(keywords, lookback_days=args.lookback_days, timeout=args.timeout)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"setn_news_rss_{stamp}.jsonl"
    write_jsonl(rows, out_path)
    print(f"setn news rss: {len(rows)} articles -> {out_path}")
    for err in errors:
        print(f"WARNING: keyword fetch failed: {err}")


if __name__ == "__main__":
    main()
