#!/usr/bin/env python3
"""Fetch Group A historical market news from GDELT using multiple narrow queries."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from convert_gdelt_raw_to_news_csv import NEWS_COLUMNS, convert_frame
from fetch_gdelt_news_csv import (
    DEFAULT_END,
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
DEFAULT_NEWS_OUTPUT = PROJECT_ROOT.parent / "news" / "gdelt_group_a_market_20200101_20260518.csv"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "news" / "group_a_market" / "bundle_manifest.json"


@dataclass(frozen=True)
class QuerySpec:
    key: str
    query: str
    base_window_days: int
    max_records: int = DEFAULT_MAX_RECORDS


GROUP_A_QUERY_SPECS = [
    QuerySpec(
        key="tw_macro_en",
        query='(TAIEX OR "Taiwan Weighted Index" OR "Taiwan Stock Exchange" OR "Taiwan stocks")',
        base_window_days=1,
        max_records=100,
    ),
    QuerySpec(
        key="etf_0050",
        query='("Yuanta Taiwan 50" OR "Taiwan 50 ETF" OR "0050.TW" OR "元大台灣50")',
        base_window_days=30,
        max_records=100,
    ),
    QuerySpec(
        key="etf_00631l",
        query='("Yuanta Daily Taiwan 50 Bull 2X" OR "00631L.TW" OR "台灣50正2" OR "元大台灣50正2")',
        base_window_days=30,
        max_records=100,
    ),
    QuerySpec(
        key="etf_00632r",
        query='("Yuanta Daily Taiwan 50 Bear 1X" OR "00632R.TW" OR "台灣50反1" OR "元大台灣50反1")',
        base_window_days=30,
        max_records=100,
    ),
    QuerySpec(
        key="dji_fed",
        query='("Dow Jones" OR DJI OR "Federal Reserve" OR FOMC)',
        base_window_days=7,
        max_records=100,
    ),
    QuerySpec(
        key="macro_risk",
        query='((inflation OR CPI OR tariff OR tariffs OR recession OR geopolitical OR liquidity) AND (TAIEX OR "Dow Jones" OR "Federal Reserve"))',
        base_window_days=7,
        max_records=100,
    ),
]


def get_query_specs(selected_keys: list[str] | None) -> list[QuerySpec]:
    if not selected_keys:
        return GROUP_A_QUERY_SPECS
    selected = {key.strip() for key in selected_keys if key.strip()}
    specs = [spec for spec in GROUP_A_QUERY_SPECS if spec.key in selected]
    missing = sorted(selected - {spec.key for spec in specs})
    if missing:
        supported = ", ".join(spec.key for spec in GROUP_A_QUERY_SPECS)
        raise ValueError(f"Unknown query keys: {', '.join(missing)}. Supported: {supported}")
    return specs


def merge_news_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=NEWS_COLUMNS)
    merged = pd.concat(frames, ignore_index=True)
    for column in NEWS_COLUMNS:
        if column not in merged.columns:
            merged[column] = ""
    merged["date"] = merged["date"].fillna("").astype(str)
    merged["title"] = merged["title"].fillna("").astype(str)
    merged["link"] = merged["link"].fillna("").astype(str)
    merged["pub_date"] = merged["pub_date"].fillna("").astype(str)
    merged = merged.sort_values(["date", "pub_date", "title", "link"])
    merged = merged.drop_duplicates(["link", "title"], keep="first").reset_index(drop=True)
    return merged[NEWS_COLUMNS]


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Group A market news from GDELT using multiple narrow queries.")
    parser.add_argument("--start-date", default=DEFAULT_START)
    parser.add_argument("--end-date", default=DEFAULT_END)
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--output", default=str(DEFAULT_NEWS_OUTPUT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--query-keys", nargs="*", default=None, help="Subset of query keys to run")
    parser.add_argument("--min-window-hours", type=int, default=DEFAULT_MIN_WINDOW_HOURS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--sleep-ms", type=int, default=DEFAULT_SLEEP_MS)
    parser.add_argument("--retry-backoff-ms", type=int, default=DEFAULT_RETRY_BACKOFF_MS)
    parser.add_argument("--rate-limit-sleep-ms", type=int, default=DEFAULT_RATE_LIMIT_SLEEP_MS)
    parser.add_argument("--split-sleep-ms", type=int, default=DEFAULT_SPLIT_SLEEP_MS)
    parser.add_argument("--window-pause-ms", type=int, default=DEFAULT_WINDOW_PAUSE_MS)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    start = parse_date(args.start_date)
    end = parse_date(args.end_date, end_of_day=True)
    if end <= start:
        raise ValueError("--end-date must be after --start-date")

    raw_dir = Path(args.raw_dir).expanduser()
    if not raw_dir.is_absolute():
        raw_dir = (Path.cwd() / raw_dir).resolve()
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()

    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "output": str(output_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": [],
    }

    news_frames: list[pd.DataFrame] = []
    specs = get_query_specs(args.query_keys)
    date_tag = f"{args.start_date.replace('-', '')}_{args.end_date.replace('-', '')}"

    for spec in specs:
        raw_path = raw_dir / f"gdelt_{spec.key}_{date_tag}.csv"
        query_manifest: dict[str, object] = {
            "key": spec.key,
            "query": spec.query,
            "raw_output": str(raw_path),
        }
        try:
            frame = fetch_gdelt_news(
                query=spec.query,
                query_preset=spec.key,
                start=start,
                end=end,
                base_window_days=spec.base_window_days,
                min_window_hours=int(args.min_window_hours),
                max_records=spec.max_records,
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
            news_frames.append(news_frame)
            query_manifest["rows"] = int(len(frame))
            query_manifest["status"] = "ok"
            if not frame.empty:
                query_manifest["published_at_min"] = str(frame["published_at"].min())
                query_manifest["published_at_max"] = str(frame["published_at"].max())
        except Exception as exc:
            query_manifest["status"] = "error"
            query_manifest["error"] = str(exc)
            if args.verbose:
                print(f"[Bundle] {spec.key} failed: {exc}")
        manifest["queries"].append(query_manifest)
        write_manifest(manifest_path, manifest)

    merged_news = merge_news_frames(news_frames)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_news.to_csv(output_path, index=False, encoding="utf-8")

    success_count = sum(1 for item in manifest["queries"] if item.get("status") == "ok")
    error_count = sum(1 for item in manifest["queries"] if item.get("status") == "error")
    manifest["success_count"] = success_count
    manifest["error_count"] = error_count
    manifest["merged_rows"] = int(len(merged_news))
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_manifest(manifest_path, manifest)

    print("=" * 72)
    print("GDELT Group A bundle complete")
    print(f"Output:       {output_path}")
    print(f"Merged rows:  {len(merged_news)}")
    print(f"Queries ok:   {success_count}")
    print(f"Queries err:  {error_count}")
    print(f"Manifest:     {manifest_path}")


if __name__ == "__main__":
    main()
