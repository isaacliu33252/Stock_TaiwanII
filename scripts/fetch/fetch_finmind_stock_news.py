#!/usr/bin/env python3
"""Fetch FinMind TaiwanStockNews as a shadow-only alternative to the LTN scraper.

Context: MOPS material-information-disclosure (重大訊息公告) scraping is blocked
by mops.twse.com.tw's WAF from this environment's network, so this uses FinMind's
aggregated news dataset instead (already an authenticated vendor in this project,
see scripts/fetch/fetch_finmind_chip_data.py). FinMind's TaiwanStockNews is
media-aggregated headlines (CMoney/ETtoday/Yahoo/etc), not the structured MOPS
filing format -- title only, no article body/snippet.

Output is a JSONL file with the same field shape as the existing
news/ltn_mainstream_*.jsonl cache (date, source, title, url, category, snippet)
so it is a drop-in input for group_a_plus.integrations.watchlist_news-style
tooling and scripts/evaluate/evaluate_event_sentiment_attribution_shadow.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockNews"
DEFAULT_WATCHLIST_CONFIG = PROJECT_ROOT / "config/group_a_plus_watchlist.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "news"


def _load_watchlist_tickers(config_path: Path) -> list[str]:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    return [str(item["symbol"]) for item in config.get("symbols", []) if item.get("symbol")]


def _finmind_stock_id(ticker: str) -> str:
    return ticker.split(".")[0]


def _daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def fetch_day(ticker: str, day: date, *, token: str, session: requests.Session) -> list[dict[str, Any]]:
    params = {
        "dataset": DATASET,
        "data_id": _finmind_stock_id(ticker),
        "start_date": day.isoformat(),
    }
    if token:
        params["token"] = token
    resp = session.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != 200:
        return []
    rows = []
    for row in payload.get("data", []):
        rows.append(
            {
                "date": str(row.get("date", ""))[:10],
                "source": row.get("source") or "finmind",
                "title": row.get("title") or "",
                "url": row.get("link") or "",
                "category": "finmind_stock_news",
                "snippet": "",  # FinMind TaiwanStockNews does not include article body.
                "match_scope": ticker,
                "provider": "finmind",
                "finmind_stock_id": row.get("stock_id"),
            }
        )
    return rows


def fetch_range(
    tickers: list[str],
    *,
    start: date,
    end: date,
    token: str,
    request_delay: float = 0.3,
) -> tuple[list[dict[str, Any]], str | None]:
    """Returns (rows, stop_reason). stop_reason is set when the API quota is hit,
    so callers can persist whatever was fetched before stopping instead of losing it.
    """
    session = requests.Session()
    seen_urls: set[str] = set()
    out: list[dict[str, Any]] = []
    for ticker in tickers:
        for day in _daterange(start, end):
            try:
                rows = fetch_day(ticker, day, token=token, session=session)
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (402, 429):
                    return out, f"quota_exceeded (HTTP {status}) at ticker={ticker} day={day.isoformat()}"
                raise
            for row in rows:
                url = row.get("url") or ""
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                out.append(row)
            time.sleep(request_delay)
    out.sort(key=lambda r: (r.get("date", ""), r.get("title", "")))
    return out, None


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers, e.g. 0050.TW,00631L.TW")
    parser.add_argument("--watchlist-config", default=str(DEFAULT_WATCHLIST_CONFIG))
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--token", default=os.environ.get("FINMIND_API_TOKEN", ""))
    parser.add_argument("--request-delay", type=float, default=0.3)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    tickers = (
        [t.strip() for t in args.tickers.split(",") if t.strip()]
        if args.tickers
        else _load_watchlist_tickers(Path(args.watchlist_config))
    )
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    rows, stop_reason = fetch_range(tickers, start=start, end=end, token=args.token, request_delay=args.request_delay)

    out_path = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"finmind_stock_news_{start.isoformat()}_to_{end.isoformat()}.jsonl"
    write_jsonl(rows, out_path)
    print(f"finmind stock news: {len(rows)} articles -> {out_path}")
    if stop_reason:
        print(f"WARNING: fetch stopped early: {stop_reason}")


if __name__ == "__main__":
    main()
