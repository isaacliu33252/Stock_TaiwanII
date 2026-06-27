#!/usr/bin/env python3
"""Convert raw GDELT article-list CSV into the project's news CSV format."""

from __future__ import annotations

import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


NEWS_COLUMNS = ["date", "title", "description", "link", "pub_date", "category"]
DEFAULT_TIMEZONE = "Asia/Taipei"


def convert_frame(frame: pd.DataFrame, *, timezone_name: str) -> pd.DataFrame:
    required = ["published_at", "title", "description", "content", "url", "domain", "query_preset"]
    for column in required:
        if column not in frame.columns:
            frame[column] = ""

    published = pd.to_datetime(frame["published_at"], errors="coerce", utc=True)
    local = published.dt.tz_convert(ZoneInfo(timezone_name))

    description = frame["description"].fillna("").astype(str).str.strip()
    content = frame["content"].fillna("").astype(str).str.strip()
    description = description.mask(description == "", content)

    category = frame["query_preset"].fillna("").astype(str).str.strip()
    domain = frame["domain"].fillna("").astype(str).str.strip()
    category = category.mask(category == "", "GDELT")
    category = category.mask((category == "GDELT") & (domain != ""), "GDELT:" + domain)

    news = pd.DataFrame(
        {
            "date": local.dt.strftime("%Y-%m-%d"),
            "title": frame["title"].fillna("").astype(str).str.strip(),
            "description": description,
            "link": frame["url"].fillna("").astype(str).str.strip(),
            "pub_date": local.dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            "category": category,
        }
    )
    news = news[news["title"] != ""].copy()
    news = news.sort_values(["date", "pub_date", "title", "link"]).drop_duplicates(["link", "title"], keep="first")
    news = news.reset_index(drop=True)
    return news[NEWS_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert raw GDELT CSV into news CSV format.")
    parser.add_argument("--input", required=True, help="Raw GDELT CSV path")
    parser.add_argument("--output", required=True, help="Destination news CSV path")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Timezone for date/pub_date fields")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    if not input_path.is_absolute():
        input_path = (Path.cwd() / input_path).resolve()
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()

    frame = pd.read_csv(input_path)
    news = convert_frame(frame, timezone_name=args.timezone)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    news.to_csv(output_path, index=False, encoding="utf-8")

    print("=" * 72)
    print("Converted GDELT raw CSV to news CSV")
    print(f"Input:        {input_path}")
    print(f"Output:       {output_path}")
    print(f"Rows:         {len(news)}")
    if not news.empty:
        print(f"Date range:   {news['date'].min()} ~ {news['date'].max()}")


if __name__ == "__main__":
    main()
