#!/usr/bin/env python3
"""Tests for the SETN (via Google News RSS) fetcher."""

from __future__ import annotations

import unittest

from scripts.fetch.fetch_setn_news_rss import build_query_url, parse_rss


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rss version="2.0"><channel>
<title>"site:setn.com 台股" - Google 新聞</title>
<item>
  <title>【台股盤前】美股消費降溫收黑！台指夜盤跌85點 - 三立新聞</title>
  <link>https://news.google.com/rss/articles/EXAMPLE_ID?oc=5</link>
  <pubDate>Sun, 16 Aug 2026 22:03:06 GMT</pubDate>
  <description>&lt;a href="https://news.google.com/rss/articles/EXAMPLE_ID?oc=5"&gt;title&lt;/a&gt;&amp;nbsp;&lt;font color="#6f6f6f"&gt;三立新聞&lt;/font&gt;</description>
  <source url="https://inews.setn.com">三立新聞</source>
</item>
</channel></rss>
""".encode("utf-8")


class FetchSetnNewsRssTests(unittest.TestCase):
    def test_build_query_url_restricts_to_site_and_lookback(self) -> None:
        url = build_query_url("台股", lookback_days=3)
        self.assertIn("site%3Asetn.com", url)
        self.assertIn("when%3A3d", url)
        self.assertIn("hl=zh-TW", url)

    def test_parse_rss_strips_source_suffix_and_leaves_snippet_empty(self) -> None:
        rows = parse_rss(SAMPLE_RSS)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["date"], "2026-08-16")
        self.assertEqual(row["source"], "三立新聞")
        self.assertEqual(row["category"], "setn_google_news_rss")
        self.assertNotIn("三立新聞", row["title"])  # " - 三立新聞" suffix stripped
        self.assertTrue(row["title"].startswith("【台股盤前】"))
        self.assertEqual(row["snippet"], "")
        self.assertEqual(row["url"], "https://news.google.com/rss/articles/EXAMPLE_ID?oc=5")

    def test_parse_rss_skips_items_missing_title_or_link(self) -> None:
        empty = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        rows = parse_rss(empty)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
