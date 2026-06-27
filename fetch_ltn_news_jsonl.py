#!/usr/bin/env python3
"""Search public Liberty Times pages and export result metadata as JSONL."""

from __future__ import annotations

import argparse
import calendar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
LTN_SEARCH_URL = "https://search.ltn.com.tw/list"
DEFAULT_SOURCE = "自由時報"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_PAGES = 20
DEFAULT_SLEEP_MS = 300
DEFAULT_TYPE = "all"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "news" / "liberty_times" / "ltn_search_results.jsonl"
OUTPUT_FIELDS = ["date", "source", "title", "url", "category", "snippet"]


def parse_cli_date(value: str) -> str:
    text = str(value).strip()
    patterns = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d")
    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value!r}")


def parse_cli_month(value: str) -> tuple[int, int]:
    text = str(value).strip()
    patterns = ("%Y-%m", "%Y/%m", "%Y%m")
    for pattern in patterns:
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.year, parsed.month
        except ValueError:
            continue
    raise ValueError(f"Unsupported month format: {value!r}")


def month_date_range(value: str) -> tuple[str, str]:
    year, month = parse_cli_month(value)
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def date_to_search_token(value: str) -> str:
    normalized = parse_cli_date(value)
    return normalized.replace("-", "")


def normalize_page_date(value: str, *, fallback_date: str | None = None) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text == "剛剛" or text.endswith("前"):
        if fallback_date:
            return parse_cli_date(fallback_date)
        raise ValueError(f"Relative date requires fallback date: {value!r}")
    return parse_cli_date(text)


def collapse_text(value: str) -> str:
    return " ".join(str(value or "").split())


def build_search_url(
    *,
    keyword: str,
    start_date: str,
    end_date: str,
    news_type: str = DEFAULT_TYPE,
    page: int = 1,
) -> str:
    params = {
        "keyword": keyword,
        "sort": "date",
        "type": news_type,
        "start_time": date_to_search_token(start_date),
        "end_time": date_to_search_token(end_date),
    }
    if page > 1:
        params["page"] = str(page)
    return LTN_SEARCH_URL + "?" + urllib.parse.urlencode(params)


def resolve_output_path(path: str | Path) -> Path:
    output_path = Path(path).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    return output_path


def default_prompt_output_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_suffix(".prompt.txt")
    return output_path.parent / f"{output_path.name}.prompt.txt"


class LtnSearchResultParser(HTMLParser):
    """Parse Liberty Times public search result pages without fetching article bodies."""

    def __init__(self, *, fallback_date: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self._fallback_date = fallback_date
        self.records: list[dict[str, str]] = []
        self._in_result_list = False
        self._result_list_depth = 0
        self._in_item = False
        self._item_depth = 0
        self._current: dict[str, str] | None = None
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())

        if tag == "ul" and {"list", "boxTitle"}.issubset(classes) and not self._in_result_list:
            self._in_result_list = True
            self._result_list_depth = 1
            return

        if self._in_result_list and tag == "ul":
            self._result_list_depth += 1

        if not self._in_result_list:
            return

        if tag == "li":
            if not self._in_item:
                self._in_item = True
                self._item_depth = 1
                self._current = {
                    "date": "",
                    "source": DEFAULT_SOURCE,
                    "title": "",
                    "url": "",
                    "category": "",
                    "snippet": "",
                }
            else:
                self._item_depth += 1
            return

        if not self._in_item or self._current is None:
            return

        if tag == "a" and "tit" in classes:
            self._current["url"] = collapse_text(attr_map.get("href", ""))
            self._start_capture("title", tag)
            return

        if tag == "i" and "immtag" in classes:
            self._start_capture("category", tag)
            return

        if tag == "span" and "time" in classes:
            self._start_capture("date", tag)
            return

        if tag == "p":
            self._start_capture("snippet", tag)

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._capture_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field is not None and tag == self._capture_tag and self._current is not None:
            value = collapse_text("".join(self._capture_parts))
            if value:
                self._current[self._capture_field] = value
            self._capture_field = None
            self._capture_tag = None
            self._capture_parts = []
            return

        if not self._in_result_list:
            return

        if tag == "li" and self._in_item:
            self._item_depth -= 1
            if self._item_depth <= 0:
                self._finish_item()
            return

        if tag == "ul":
            self._result_list_depth -= 1
            if self._result_list_depth <= 0:
                self._in_result_list = False

    def _start_capture(self, field: str, tag: str) -> None:
        self._capture_field = field
        self._capture_tag = tag
        self._capture_parts = []

    def _finish_item(self) -> None:
        record = dict(self._current or {})
        self._current = None
        self._in_item = False
        self._item_depth = 0
        self._capture_field = None
        self._capture_tag = None
        self._capture_parts = []

        record["date"] = normalize_page_date(
            record.get("date", ""),
            fallback_date=self._fallback_date,
        )
        record["title"] = collapse_text(record.get("title", ""))
        record["url"] = collapse_text(record.get("url", ""))
        record["category"] = collapse_text(record.get("category", ""))
        record["snippet"] = collapse_text(record.get("snippet", ""))

        if record["title"] and record["url"] and record["date"]:
            self.records.append({field: record.get(field, "") for field in OUTPUT_FIELDS})


def extract_records_from_html(html_text: str, *, fallback_date: str | None = None) -> list[dict[str, str]]:
    parser = LtnSearchResultParser(fallback_date=fallback_date)
    parser.feed(html_text)
    return parser.records


def deduplicate_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    seen_fallback: set[tuple[str, str, str]] = set()

    for record in records:
        url = collapse_text(record.get("url", ""))
        key = (record.get("date", ""), record.get("title", ""), record.get("snippet", ""))
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        else:
            if key in seen_fallback:
                continue
            seen_fallback.add(key)
        deduped.append({field: collapse_text(record.get(field, "")) for field in OUTPUT_FIELDS})
    return deduped


def fetch_html(url: str, *, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "StockTaiwan2-LTN-NewsFetcher/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
        charset = response.headers.get_content_charset("utf-8") or "utf-8"
    return payload.decode(charset, errors="replace")


def fetch_search_results(
    *,
    keyword: str,
    start_date: str,
    end_date: str,
    news_type: str,
    max_pages: int,
    timeout: int,
    sleep_ms: int,
    verbose: bool = False,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []

    for page in range(1, max_pages + 1):
        url = build_search_url(
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            news_type=news_type,
            page=page,
        )
        if verbose:
            print(f"[LTN] page {page}: {url}")

        try:
            html_text = fetch_html(url, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if page > 1 and exc.code == 404:
                if verbose:
                    print(f"[LTN] page {page}: no more pages (HTTP 404)")
                break
            raise
        page_records = extract_records_from_html(html_text, fallback_date=end_date)
        fresh_records = deduplicate_records(records + page_records)
        added = len(fresh_records) - len(records)
        records = fresh_records

        if verbose:
            print(f"[LTN] page {page}: parsed {len(page_records)} results, added {added}")

        if not page_records or added == 0:
            break

        if sleep_ms > 0 and page < max_pages:
            time.sleep(sleep_ms / 1000.0)

    return records


def write_jsonl(records: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_prompt_template(
    *,
    keyword: str,
    start_date: str,
    end_date: str,
    jsonl_path: Path,
    record_count: int,
) -> str:
    return f"""你是新聞整理與市場情緒標註助手。

資料來源限制：
1. 輸入資料來自自由時報公開搜尋頁，不含全文。
2. 只能使用每行 JSON 內既有欄位：date、source、title、url、category、snippet。
3. 不可要求額外抓取全文，也不可推測未出現在 title 或 snippet 的內容。

任務：
1. 逐行閱讀新聞 JSONL。
2. 每行輸入輸出一行 JSON，不要輸出額外說明文字。
3. 若 snippet 資訊不足，請降低 confidence，而不是臆測內容。

建議輸出 JSONL schema：
{{"date":"YYYY-MM-DD","source":"自由時報","title":"...","url":"...","category":"...","snippet":"...","summary":"不超過40字","topic_tags":["tag1","tag2"],"market_relevance":0.0,"sentiment_score":0.0,"confidence":0.0,"risk_off_score":0.0}}

分數規則：
- market_relevance: 0.0 到 1.0，越高代表越可能影響市場或產業情緒
- sentiment_score: -1.0 到 1.0，負值偏利空，正值偏利多
- confidence: 0.0 到 1.0，越高代表根據 title/snippet 判斷越有把握
- risk_off_score: 0.0 到 1.0，越高代表越偏避險、風險事件或市場壓力

本次輸入背景：
- keyword: {keyword}
- date_range: {start_date} ~ {end_date}
- jsonl_path: {jsonl_path}
- record_count: {record_count}

請把要分析的 JSONL 內容貼在下面：
<news_jsonl>
{{paste_jsonl_here}}
</news_jsonl>
"""


def write_prompt_template(prompt_output_path: Path, prompt_text: str) -> None:
    prompt_output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_output_path.write_text(prompt_text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search public Liberty Times pages and export result metadata as JSONL."
    )
    parser.add_argument("--keyword", required=True, help="Search keyword for Liberty Times")
    parser.add_argument("--month", help="Whole month, e.g. 2024-01")
    parser.add_argument("--date", help="Single date, e.g. 2024-01-31")
    parser.add_argument("--start-date", help="Start date, e.g. 2024-01-01")
    parser.add_argument("--end-date", help="End date, e.g. 2024-01-31")
    parser.add_argument("--type", dest="news_type", default=DEFAULT_TYPE, help="Search type, default: all")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Maximum search result pages")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds")
    parser.add_argument("--sleep-ms", type=int, default=DEFAULT_SLEEP_MS, help="Delay between page fetches")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--prompt-output", help="Optional prompt template output path")
    parser.add_argument("--verbose", action="store_true", help="Print fetch progress")
    return parser.parse_args()


def resolve_date_range(args: argparse.Namespace) -> tuple[str, str]:
    if args.month:
        if args.date or args.start_date or args.end_date:
            raise ValueError("Use either --month or --date/--start-date/--end-date, not both")
        return month_date_range(args.month)

    if args.date:
        single_date = parse_cli_date(args.date)
        return single_date, single_date

    if not args.start_date:
        raise ValueError("Provide --date or --start-date")

    start_date = parse_cli_date(args.start_date)
    end_date = parse_cli_date(args.end_date or args.start_date)
    if end_date < start_date:
        raise ValueError("--end-date must be on or after --start-date")
    return start_date, end_date


def main() -> None:
    args = parse_args()
    start_date, end_date = resolve_date_range(args)
    output_path = resolve_output_path(args.output)
    prompt_output_path = resolve_output_path(args.prompt_output) if args.prompt_output else default_prompt_output_path(output_path)

    records = fetch_search_results(
        keyword=args.keyword,
        start_date=start_date,
        end_date=end_date,
        news_type=args.news_type,
        max_pages=max(args.max_pages, 1),
        timeout=max(args.timeout, 1),
        sleep_ms=max(args.sleep_ms, 0),
        verbose=args.verbose,
    )

    write_jsonl(records, output_path)
    prompt_text = build_prompt_template(
        keyword=args.keyword,
        start_date=start_date,
        end_date=end_date,
        jsonl_path=output_path,
        record_count=len(records),
    )
    write_prompt_template(prompt_output_path, prompt_text)

    print("=" * 72)
    print("Liberty Times search export complete")
    print(f"Keyword:      {args.keyword}")
    print(f"Date range:   {start_date} ~ {end_date}")
    print(f"Search type:  {args.news_type}")
    print(f"Output JSONL: {output_path}")
    print(f"Prompt file:  {prompt_output_path}")
    print(f"Records:      {len(records)}")


if __name__ == "__main__":
    main()
