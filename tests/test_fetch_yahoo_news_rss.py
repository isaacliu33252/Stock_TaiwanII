#!/usr/bin/env python3
"""Tests for the Yahoo finance RSS fetcher."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.fetch.fetch_yahoo_news_rss import parse_rss, write_jsonl


SAMPLE_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<title>Yahoo股市</title>
<item>
  <title><![CDATA[子公司虧損拖累，上曜H1 EPS-0.36元]]></title>
  <link>https://tw.stock.yahoo.com/news/example-000957856.html</link>
  <pubDate>Mon, 17 Aug 2026 00:09:57 GMT</pubDate>
  <description><![CDATA[<b>【財訊快報】</b>上曜公布第二季財報，單季虧損擴大]]></description>
</item>
</channel></rss>
""".encode("utf-8")


class FetchYahooNewsRssTests(unittest.TestCase):
    def test_parse_rss_extracts_fields(self) -> None:
        rows = parse_rss(SAMPLE_RSS, category="yahoo_stock_news", default_source="Yahoo奇摩股市")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["date"], "2026-08-17")
        self.assertEqual(row["source"], "Yahoo奇摩股市")
        self.assertEqual(row["category"], "yahoo_stock_news")
        self.assertIn("子公司虧損拖累", row["title"])
        self.assertIn("上曜公布第二季財報", row["snippet"])
        self.assertNotIn("<b>", row["snippet"])
        self.assertEqual(row["url"], "https://tw.stock.yahoo.com/news/example-000957856.html")

    def test_parse_rss_skips_items_missing_title_or_link(self) -> None:
        empty = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        rows = parse_rss(empty, category="c", default_source="s")
        self.assertEqual(rows, [])

    def test_write_jsonl_round_trips(self) -> None:
        import json
        import tempfile

        rows = [{"date": "2026-08-17", "source": "s", "title": "t", "url": "u", "category": "c", "snippet": "sn"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jsonl"
            write_jsonl(rows, path)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0]), rows[0])


if __name__ == "__main__":
    unittest.main()
