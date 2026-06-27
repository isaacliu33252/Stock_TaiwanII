#!/usr/bin/env python3
"""Fetch historical market news from the GDELT DOC 2.0 API and export a CSV."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "news" / "group_a_market" / "gdelt_group_a_market_20200101_20260518.csv"
DEFAULT_START = "2020-01-01"
DEFAULT_END = "2026-05-18"
DEFAULT_BASE_WINDOW_DAYS = 30
DEFAULT_MIN_WINDOW_HOURS = 6
DEFAULT_MAX_RECORDS = 250
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 3
DEFAULT_SLEEP_MS = 200
DEFAULT_SPLIT_SLEEP_MS = 50
DEFAULT_RETRY_BACKOFF_MS = 1500
DEFAULT_RATE_LIMIT_SLEEP_MS = 30000
DEFAULT_WINDOW_PAUSE_MS = 500

GROUP_A_MARKET_QUERY = (
    "("
    "\"台股\" OR \"台灣加權指數\" OR \"加權指數\" OR TAIEX OR "
    "\"Taiwan Weighted Index\" OR \"Taiwan Stock Exchange\" OR "
    "\"Taiwan stocks\" OR \"0050\" OR \"00631L\" OR \"00632R\" OR "
    "\"Dow Jones\" OR DJI OR \"Federal Reserve\" OR FOMC OR "
    "inflation OR CPI OR tariff OR tariffs OR recession OR "
    "geopolitical OR liquidity"
    ")"
)

QUERY_PRESETS = {
    "group_a_market": GROUP_A_MARKET_QUERY,
}

OUTPUT_COLUMNS = [
    "published_at",
    "title",
    "description",
    "content",
    "source",
    "domain",
    "language",
    "source_country",
    "url",
    "url_mobile",
    "socialimage",
    "seendate",
    "query_preset",
    "query",
]


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("window end must be after start")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def split(self) -> tuple["TimeWindow", "TimeWindow"]:
        midpoint = self.start + (self.duration / 2)
        midpoint = midpoint.replace(microsecond=0)
        if midpoint <= self.start:
            midpoint = self.start + timedelta(seconds=1)
        if midpoint >= self.end:
            midpoint = self.end - timedelta(seconds=1)
        if midpoint <= self.start or midpoint >= self.end:
            raise ValueError("window too small to split further")
        return TimeWindow(self.start, midpoint), TimeWindow(midpoint, self.end)


def parse_date(value: str, *, end_of_day: bool = False) -> datetime:
    text = str(value).strip()
    if len(text) == 10:
        parsed = datetime.strptime(text, "%Y-%m-%d")
        if end_of_day:
            parsed = parsed + timedelta(days=1)
        return parsed.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    if end_of_day and parsed.time() == datetime.min.time():
        parsed = parsed + timedelta(days=1)
    return parsed


def gdelt_datetime(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    return utc_value.strftime("%Y%m%d%H%M%S")


def parse_gdelt_seendate(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    patterns = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%d%H%M%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    )
    for pattern in patterns:
        try:
            parsed = datetime.strptime(text, pattern)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return text


def build_request_url(
    *,
    query: str,
    window: TimeWindow,
    max_records: int,
    sort: str = "dateasc",
) -> str:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": sort,
        "maxrecords": str(max_records),
        "startdatetime": gdelt_datetime(window.start),
        "enddatetime": gdelt_datetime(window.end),
    }
    return GDELT_DOC_API + "?" + urllib.parse.urlencode(params)


def window_key(window: TimeWindow) -> str:
    return f"{gdelt_datetime(window.start)}::{gdelt_datetime(window.end)}"


def parse_retry_after(headers: object) -> float | None:
    if headers is None:
        return None
    retry_after = None
    try:
        retry_after = headers.get("Retry-After")
    except AttributeError:
        retry_after = None
    if retry_after is None:
        return None
    text = str(retry_after).strip()
    if not text:
        return None
    try:
        return max(float(text), 0.0)
    except ValueError:
        return None


def fetch_json(
    url: str,
    *,
    timeout: int,
    retries: int,
    sleep_ms: int,
    retry_backoff_ms: int,
    rate_limit_sleep_ms: int,
    verbose: bool = False,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "StockTaiwan2-GDELT-NewsFetcher/1.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
            text = payload.strip()
            if not text:
                raise json.JSONDecodeError("Empty response body", payload, 0)
            if text[:1] == "<":
                raise json.JSONDecodeError("Non-JSON response body", payload, 0)
            return json.loads(payload)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                retry_after = parse_retry_after(getattr(exc, "headers", None))
                wait_seconds = retry_after
                if wait_seconds is None:
                    wait_seconds = max(rate_limit_sleep_ms / 1000.0, 1.0) * (attempt + 1)
                if verbose:
                    print(f"[GDELT] rate limited (429), sleeping {wait_seconds:.1f}s before retry")
                time.sleep(wait_seconds)
                continue
            if attempt < retries - 1:
                backoff_seconds = max(retry_backoff_ms / 1000.0, 0.0) * (attempt + 1)
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
            continue
        except json.JSONDecodeError as exc:
            last_error = exc
            wait_seconds = max(rate_limit_sleep_ms / 1000.0, 1.0) * (attempt + 1)
            if verbose:
                print(f"[GDELT] non-JSON/empty response, sleeping {wait_seconds:.1f}s before retry")
            if attempt < retries - 1:
                time.sleep(wait_seconds)
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries - 1:
                backoff_seconds = max(max(sleep_ms, retry_backoff_ms) / 1000.0, 0.0) * (attempt + 1)
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
    raise RuntimeError(f"Failed to fetch GDELT after {retries} attempts: {url}") from last_error


def extract_articles(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("articles", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def normalize_article(
    article: dict,
    *,
    query: str,
    query_preset: str | None,
) -> dict[str, object]:
    seendate = parse_gdelt_seendate(article.get("seendate"))
    domain = str(article.get("domain") or "").strip()
    row = {
        "published_at": seendate,
        "title": str(article.get("title") or "").strip(),
        "description": "",
        "content": "",
        "source": domain,
        "domain": domain,
        "language": str(article.get("language") or "").strip(),
        "source_country": str(article.get("sourcecountry") or "").strip(),
        "url": str(article.get("url") or "").strip(),
        "url_mobile": str(article.get("url_mobile") or "").strip(),
        "socialimage": str(article.get("socialimage") or "").strip(),
        "seendate": seendate,
        "query_preset": str(query_preset or ""),
        "query": query,
    }
    return row


def normalize_articles(
    articles: Iterable[dict],
    *,
    query: str,
    query_preset: str | None,
) -> list[dict[str, object]]:
    rows = [
        normalize_article(article, query=query, query_preset=query_preset)
        for article in articles
    ]
    return [row for row in rows if row["url"] or row["title"]]


def deduplicate_rows(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if frame.empty:
        return frame
    frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce", utc=True)
    frame["seendate"] = frame["published_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna(frame["seendate"])
    frame["published_at"] = frame["published_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    frame["url"] = frame["url"].fillna("").astype(str).str.strip()
    frame["title"] = frame["title"].fillna("").astype(str).str.strip()
    frame["_dedupe_key"] = frame["url"]
    missing_url = frame["_dedupe_key"] == ""
    frame.loc[missing_url, "_dedupe_key"] = (
        frame.loc[missing_url, "published_at"].fillna("")
        + "::"
        + frame.loc[missing_url, "title"].fillna("")
    )
    frame = frame.sort_values(["published_at", "title", "url"]).drop_duplicates("_dedupe_key", keep="first")
    frame = frame.drop(columns=["_dedupe_key"]).reset_index(drop=True)
    return frame[OUTPUT_COLUMNS]


def iter_base_windows(
    start: datetime,
    end: datetime,
    *,
    window_days: int,
) -> list[TimeWindow]:
    windows: list[TimeWindow] = []
    cursor = start
    step = timedelta(days=max(window_days, 1))
    while cursor < end:
        next_cursor = min(cursor + step, end)
        windows.append(TimeWindow(cursor, next_cursor))
        cursor = next_cursor
    return windows


def load_existing_output(output_path: Path) -> list[dict[str, object]]:
    if not output_path.exists():
        return []
    frame = pd.read_csv(output_path)
    if frame.empty:
        return []
    for column in OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[OUTPUT_COLUMNS].fillna("").to_dict("records")


def load_progress(progress_path: Path) -> dict[str, object] | None:
    if not progress_path.exists():
        return None
    return json.loads(progress_path.read_text(encoding="utf-8"))


def save_progress(
    *,
    progress_path: Path,
    query: str,
    query_preset: str | None,
    start: datetime,
    end: datetime,
    base_window_days: int,
    completed_windows: set[str],
) -> None:
    payload = {
        "query": query,
        "query_preset": query_preset or "",
        "startdatetime": gdelt_datetime(start),
        "enddatetime": gdelt_datetime(end),
        "base_window_days": int(base_window_days),
        "completed_windows": sorted(completed_windows),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_progress(
    *,
    progress_payload: dict[str, object] | None,
    query: str,
    query_preset: str | None,
    start: datetime,
    end: datetime,
    base_window_days: int,
) -> set[str]:
    if not progress_payload:
        return set()
    expected = {
        "query": query,
        "query_preset": query_preset or "",
        "startdatetime": gdelt_datetime(start),
        "enddatetime": gdelt_datetime(end),
    }
    for key, value in expected.items():
        if progress_payload.get(key) != value:
            raise ValueError(
                f"Progress file does not match current run for {key}: "
                f"{progress_payload.get(key)!r} != {value!r}"
            )
    if progress_payload.get("base_window_days") != int(base_window_days):
        return set()
    completed = progress_payload.get("completed_windows")
    if not isinstance(completed, list):
        return set()
    return {str(item) for item in completed if str(item).strip()}


def fetch_window_recursive(
    *,
    query: str,
    query_preset: str | None,
    window: TimeWindow,
    max_records: int,
    timeout: int,
    retries: int,
    sleep_ms: int,
    retry_backoff_ms: int,
    rate_limit_sleep_ms: int,
    split_sleep_ms: int,
    min_window_hours: int,
    verbose: bool = False,
) -> list[dict[str, object]]:
    url = build_request_url(query=query, window=window, max_records=max_records)
    payload = fetch_json(
        url,
        timeout=timeout,
        retries=retries,
        sleep_ms=sleep_ms,
        retry_backoff_ms=retry_backoff_ms,
        rate_limit_sleep_ms=rate_limit_sleep_ms,
        verbose=verbose,
    )
    articles = extract_articles(payload)
    if verbose:
        print(
            "[GDELT]",
            window.start.strftime("%Y-%m-%d"),
            "->",
            window.end.strftime("%Y-%m-%d"),
            f"rows={len(articles)}",
        )

    if len(articles) < max_records or window.duration <= timedelta(hours=max(min_window_hours, 1)):
        return normalize_articles(articles, query=query, query_preset=query_preset)

    left, right = window.split()
    if split_sleep_ms > 0:
        time.sleep(split_sleep_ms / 1000.0)
    return (
        fetch_window_recursive(
            query=query,
            query_preset=query_preset,
            window=left,
            max_records=max_records,
            timeout=timeout,
            retries=retries,
            sleep_ms=sleep_ms,
            retry_backoff_ms=retry_backoff_ms,
            rate_limit_sleep_ms=rate_limit_sleep_ms,
            split_sleep_ms=split_sleep_ms,
            min_window_hours=min_window_hours,
            verbose=verbose,
        )
        + fetch_window_recursive(
            query=query,
            query_preset=query_preset,
            window=right,
            max_records=max_records,
            timeout=timeout,
            retries=retries,
            sleep_ms=sleep_ms,
            retry_backoff_ms=retry_backoff_ms,
            rate_limit_sleep_ms=rate_limit_sleep_ms,
            split_sleep_ms=split_sleep_ms,
            min_window_hours=min_window_hours,
            verbose=verbose,
        )
    )


def fetch_gdelt_news(
    *,
    query: str,
    query_preset: str | None,
    start: datetime,
    end: datetime,
    base_window_days: int,
    min_window_hours: int,
    max_records: int,
    timeout: int,
    retries: int,
    sleep_ms: int,
    retry_backoff_ms: int,
    rate_limit_sleep_ms: int,
    split_sleep_ms: int,
    window_pause_ms: int,
    output_path: Path | None = None,
    progress_path: Path | None = None,
    resume: bool = False,
    verbose: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    completed_windows: set[str] = set()
    if resume and output_path is not None:
        rows = load_existing_output(output_path)
        if progress_path is not None:
            completed_windows = validate_progress(
                progress_payload=load_progress(progress_path),
                query=query,
                query_preset=query_preset,
                start=start,
                end=end,
                base_window_days=base_window_days,
            )
        if verbose and rows:
            print(f"[Resume] loaded {len(rows)} existing rows from {output_path}")

    base_windows = iter_base_windows(start, end, window_days=base_window_days)
    for index, window in enumerate(base_windows, start=1):
        current_key = window_key(window)
        if current_key in completed_windows:
            if verbose:
                print(
                    f"[Window {index}/{len(base_windows)}] "
                    f"{window.start.strftime('%Y-%m-%d')} -> {window.end.strftime('%Y-%m-%d')} (skip, already done)"
                )
            continue
        if verbose:
            print(
                f"[Window {index}/{len(base_windows)}] "
                f"{window.start.strftime('%Y-%m-%d')} -> {window.end.strftime('%Y-%m-%d')}"
            )
        rows.extend(
            fetch_window_recursive(
                query=query,
                query_preset=query_preset,
                window=window,
                max_records=max_records,
                timeout=timeout,
                retries=retries,
                sleep_ms=sleep_ms,
                retry_backoff_ms=retry_backoff_ms,
                rate_limit_sleep_ms=rate_limit_sleep_ms,
                split_sleep_ms=split_sleep_ms,
                min_window_hours=min_window_hours,
                verbose=verbose,
            )
        )
        if output_path is not None:
            deduplicate_rows(rows).to_csv(output_path, index=False, encoding="utf-8")
        completed_windows.add(current_key)
        if progress_path is not None:
            save_progress(
                progress_path=progress_path,
                query=query,
                query_preset=query_preset,
                start=start,
                end=end,
                base_window_days=base_window_days,
                completed_windows=completed_windows,
            )
        if window_pause_ms > 0:
            time.sleep(window_pause_ms / 1000.0)
    return deduplicate_rows(rows)


def resolve_query(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.query:
        return args.query, None
    if args.query_preset:
        query = QUERY_PRESETS.get(args.query_preset)
        if query is None:
            supported = ", ".join(sorted(QUERY_PRESETS))
            raise ValueError(f"Unknown --query-preset {args.query_preset!r}. Choices: {supported}")
        return query, args.query_preset
    return QUERY_PRESETS["group_a_market"], "group_a_market"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch historical GDELT market news and export CSV.")
    parser.add_argument("--query", default=None, help="Raw GDELT query string")
    parser.add_argument(
        "--query-preset",
        default="group_a_market",
        choices=sorted(QUERY_PRESETS.keys()),
        help="Named preset for the GDELT query",
    )
    parser.add_argument("--start-date", default=DEFAULT_START, help="Inclusive start date in YYYY-MM-DD")
    parser.add_argument("--end-date", default=DEFAULT_END, help="Inclusive end date in YYYY-MM-DD")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Destination CSV path")
    parser.add_argument("--base-window-days", type=int, default=DEFAULT_BASE_WINDOW_DAYS)
    parser.add_argument("--min-window-hours", type=int, default=DEFAULT_MIN_WINDOW_HOURS)
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--sleep-ms", type=int, default=DEFAULT_SLEEP_MS)
    parser.add_argument("--retry-backoff-ms", type=int, default=DEFAULT_RETRY_BACKOFF_MS)
    parser.add_argument("--rate-limit-sleep-ms", type=int, default=DEFAULT_RATE_LIMIT_SLEEP_MS)
    parser.add_argument("--split-sleep-ms", type=int, default=DEFAULT_SPLIT_SLEEP_MS)
    parser.add_argument("--window-pause-ms", type=int, default=DEFAULT_WINDOW_PAUSE_MS)
    parser.add_argument("--resume", action="store_true", help="Resume from existing CSV/progress file if present")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    query, query_preset = resolve_query(args)
    start = parse_date(args.start_date)
    end = parse_date(args.end_date, end_of_day=True)
    if end <= start:
        raise ValueError("--end-date must be after --start-date")
    if not 1 <= int(args.max_records) <= 250:
        raise ValueError("--max-records must be between 1 and 250 for GDELT artlist")
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    progress_path = output_path.with_suffix(output_path.suffix + ".progress.json")

    frame = fetch_gdelt_news(
        query=query,
        query_preset=query_preset,
        start=start,
        end=end,
        base_window_days=int(args.base_window_days),
        min_window_hours=int(args.min_window_hours),
        max_records=int(args.max_records),
        timeout=int(args.timeout),
        retries=int(args.retries),
        sleep_ms=int(args.sleep_ms),
        retry_backoff_ms=int(args.retry_backoff_ms),
        rate_limit_sleep_ms=int(args.rate_limit_sleep_ms),
        split_sleep_ms=int(args.split_sleep_ms),
        window_pause_ms=int(args.window_pause_ms),
        output_path=output_path,
        progress_path=progress_path,
        resume=bool(args.resume),
        verbose=bool(args.verbose),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, encoding="utf-8")

    print("=" * 72)
    print("GDELT news export complete")
    print(f"Query preset: {query_preset or 'custom'}")
    print(f"Output:       {output_path}")
    print(f"Rows:         {len(frame)}")
    if not frame.empty:
        print(f"Date range:   {frame['published_at'].min()} ~ {frame['published_at'].max()}")
        unique_domains = int(frame['domain'].replace('', pd.NA).dropna().nunique())
        print(f"Domains:      {unique_domains}")


if __name__ == "__main__":
    main()
