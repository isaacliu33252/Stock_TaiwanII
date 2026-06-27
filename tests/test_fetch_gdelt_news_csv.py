#!/usr/bin/env python3
"""Tests for GDELT historical news export helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fetch_gdelt_news_csv import (
    TimeWindow,
    deduplicate_rows,
    extract_articles,
    gdelt_datetime,
    normalize_articles,
    parse_date,
    parse_gdelt_seendate,
)


class FetchGdeltNewsCsvTests(unittest.TestCase):
    def test_parse_date_end_of_day_is_exclusive_next_day(self) -> None:
        start = parse_date("2020-01-01")
        end = parse_date("2020-01-01", end_of_day=True)
        self.assertEqual(start.isoformat(), "2020-01-01T00:00:00+00:00")
        self.assertEqual(end.isoformat(), "2020-01-02T00:00:00+00:00")

    def test_gdelt_datetime(self) -> None:
        value = datetime(2026, 5, 18, 12, 34, 56, tzinfo=timezone.utc)
        self.assertEqual(gdelt_datetime(value), "20260518123456")

    def test_window_split(self) -> None:
        window = TimeWindow(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2020, 1, 3, tzinfo=timezone.utc),
        )
        left, right = window.split()
        self.assertEqual(left.start.isoformat(), "2020-01-01T00:00:00+00:00")
        self.assertEqual(right.end.isoformat(), "2020-01-03T00:00:00+00:00")
        self.assertEqual(left.end, right.start)

    def test_extract_articles(self) -> None:
        payload = {
            "articles": [
                {"url": "https://example.com/a", "title": "A"},
                {"url": "https://example.com/b", "title": "B"},
            ]
        }
        articles = extract_articles(payload)
        self.assertEqual(len(articles), 2)

    def test_parse_gdelt_seendate(self) -> None:
        parsed = parse_gdelt_seendate("20260518T123456Z")
        self.assertEqual(parsed, "2026-05-18T12:34:56+00:00")

    def test_normalize_and_deduplicate(self) -> None:
        articles = [
            {
                "url": "https://example.com/a",
                "title": "Title A",
                "seendate": "20260518T123456Z",
                "domain": "example.com",
                "language": "English",
                "sourcecountry": "US",
            },
            {
                "url": "https://example.com/a",
                "title": "Title A duplicate",
                "seendate": "20260518T123500Z",
                "domain": "example.com",
                "language": "English",
                "sourcecountry": "US",
            },
        ]
        rows = normalize_articles(articles, query="test", query_preset="group_a_market")
        frame = deduplicate_rows(rows)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["url"], "https://example.com/a")
        self.assertEqual(frame.iloc[0]["source"], "example.com")


if __name__ == "__main__":
    unittest.main()
