#!/usr/bin/env python3
"""Fetch Group A historical news from GDELT month by month."""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from convert_gdelt_raw_to_news_csv import NEWS_COLUMNS, convert_frame
from fetch_gdelt_group_a_news_bundle import get_query_specs, merge_news_frames
from fetch_gdelt_news_csv import (
    DEFAULT_MAX_RECORDS,
    DEFAULT_MIN_WINDOW_HOURS,
    DEFAULT_RATE_LIMIT_SLEEP_MS,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_BACKOFF_MS,
    DEFAULT_SLEEP_MS,
    DEFAULT_SPLIT_SLEEP_MS,
    DEFAULT_START,
    DEFAULT_TIMEOUT,
    DEFAULT_WINDOW_PAUSE_MS,
    fetch_gdelt_news,
    parse_date,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "news" / "group_a_market" / "raw"
DEFAULT_NEWS_DIR = PROJECT_ROOT.parent / "news" / "gdelt_group_a_market_monthly"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "news" / "group_a_market" / "monthly_manifest.json"
DEFAULT_MERGED_OUTPUT = PROJECT_ROOT.parent / "news" / "gdelt_group_a_market_merged.csv"
DEFAULT_END = "2026-05-18"


@dataclass(frozen=True)
class MonthWindow:
    start_date: date
    end_date: date

    @property
    def tag(self) -> str:
        return f"{self.start_date.strftime('%Y%m%d')}_{self.end_date.strftime('%Y%m%d')}"

    @property
    def month_key(self) -> str:
        return self.start_date.strftime("%Y-%m")


def parse_plain_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_month_windows(start_value: str, end_value: str) -> list[MonthWindow]:
    start = parse_plain_date(start_value)
    end = parse_plain_date(end_value)
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")

    windows: list[MonthWindow] = []
    year = start.year
    month = start.month
    while True:
        month_start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        window_start = max(start, month_start)
        window_end = min(end, month_end)
        if window_start <= window_end:
            windows.append(MonthWindow(start_date=window_start, end_date=window_end))
        if month_end >= end:
            break
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return windows


def resolve_path(text: str) -> Path:
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Group A market news from GDELT month by month.")
    parser.add_argument("--start-date", default=DEFAULT_START)
    parser.add_argument("--end-date", default=DEFAULT_END)
    parser.add_argument("--query-keys", nargs="*", default=["tw_macro_en"])
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--news-dir", default=str(DEFAULT_NEWS_DIR))
    parser.add_argument("--merged-output", default=str(DEFAULT_MERGED_OUTPUT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--min-window-hours", type=int, default=DEFAULT_MIN_WINDOW_HOURS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--sleep-ms", type=int, default=DEFAULT_SLEEP_MS)
    parser.add_argument("--retry-backoff-ms", type=int, default=DEFAULT_RETRY_BACKOFF_MS)
    parser.add_argument("--rate-limit-sleep-ms", type=int, default=DEFAULT_RATE_LIMIT_SLEEP_MS)
    parser.add_argument("--split-sleep-ms", type=int, default=DEFAULT_SPLIT_SLEEP_MS)
    parser.add_argument("--window-pause-ms", type=int, default=DEFAULT_WINDOW_PAUSE_MS)
    parser.add_argument("--max-months", type=int, default=None, help="Optional limit on how many calendar months to process in this run")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    raw_dir = resolve_path(args.raw_dir)
    news_dir = resolve_path(args.news_dir)
    merged_output = resolve_path(args.merged_output)
    manifest_path = resolve_path(args.manifest)
    raw_dir.mkdir(parents=True, exist_ok=True)
    news_dir.mkdir(parents=True, exist_ok=True)

    specs = get_query_specs(args.query_keys)
    month_windows = iter_month_windows(args.start_date, args.end_date)

    manifest: dict[str, object] = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "query_keys": [spec.key for spec in specs],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "months": [],
    }

    merged_frames: list[pd.DataFrame] = []

    processed_months = 0
    for month_window in month_windows:
        if args.max_months is not None and processed_months >= int(args.max_months):
            break
        month_record: dict[str, object] = {
            "month": month_window.month_key,
            "start_date": month_window.start_date.isoformat(),
            "end_date": month_window.end_date.isoformat(),
            "queries": [],
        }
        monthly_frames: list[pd.DataFrame] = []
        for spec in specs:
            raw_path = raw_dir / f"gdelt_{spec.key}_{month_window.tag}.csv"
            news_path = news_dir / f"gdelt_{spec.key}_{month_window.tag}.csv"
            query_record: dict[str, object] = {
                "key": spec.key,
                "raw_output": str(raw_path),
                "news_output": str(news_path),
            }
            try:
                frame = fetch_gdelt_news(
                    query=spec.query,
                    query_preset=spec.key,
                    start=parse_date(month_window.start_date.isoformat()),
                    end=parse_date(month_window.end_date.isoformat(), end_of_day=True),
                    base_window_days=spec.base_window_days,
                    min_window_hours=int(args.min_window_hours),
                    max_records=min(int(spec.max_records), DEFAULT_MAX_RECORDS),
                    timeout=int(args.timeout),
                    retries=int(args.retries),
                    sleep_ms=int(args.sleep_ms),
                    retry_backoff_ms=int(args.retry_backoff_ms),
                    rate_limit_sleep_ms=int(args.rate_limit_sleep_ms),
                    split_sleep_ms=int(args.split_sleep_ms),
                    window_pause_ms=int(args.window_pause_ms),
                    output_path=raw_path,
                    progress_path=raw_path.with_suffix(raw_path.suffix + ".progress.json"),
                    resume=bool(args.resume),
                    verbose=bool(args.verbose),
                )
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                frame.to_csv(raw_path, index=False, encoding="utf-8")
                news_frame = convert_frame(frame, timezone_name="Asia/Taipei")
                news_path.parent.mkdir(parents=True, exist_ok=True)
                news_frame.to_csv(news_path, index=False, encoding="utf-8")
                monthly_frames.append(news_frame)
                query_record["status"] = "ok"
                query_record["rows"] = int(len(news_frame))
            except Exception as exc:
                query_record["status"] = "error"
                query_record["error"] = str(exc)
                if args.verbose:
                    print(f"[Monthly] {month_window.month_key} {spec.key} failed: {exc}")
            month_record["queries"].append(query_record)

        merged_month = merge_news_frames(monthly_frames)
        month_record["merged_rows"] = int(len(merged_month))
        month_record["status"] = (
            "ok" if all(item.get("status") == "ok" for item in month_record["queries"]) else "partial"
        )
        if not merged_month.empty:
            monthly_merged_path = news_dir / f"gdelt_group_a_market_{month_window.tag}.csv"
            merged_month.to_csv(monthly_merged_path, index=False, encoding="utf-8")
            month_record["merged_output"] = str(monthly_merged_path)
            merged_frames.append(merged_month)
        manifest["months"].append(month_record)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        processed_months += 1

    merged_all = merge_news_frames(merged_frames)
    merged_output.parent.mkdir(parents=True, exist_ok=True)
    merged_all.to_csv(merged_output, index=False, encoding="utf-8")

    manifest["merged_output"] = str(merged_output)
    manifest["merged_rows"] = int(len(merged_all))
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("GDELT Group A monthly fetch complete")
    print(f"Merged output: {merged_output}")
    print(f"Merged rows:   {len(merged_all)}")
    print(f"Manifest:      {manifest_path}")


if __name__ == "__main__":
    main()
