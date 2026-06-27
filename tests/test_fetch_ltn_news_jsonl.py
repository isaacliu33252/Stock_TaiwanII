#!/usr/bin/env python3
"""Tests for Liberty Times public search result export helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

from fetch_ltn_news_jsonl import (
    build_prompt_template,
    build_search_url,
    deduplicate_records,
    extract_records_from_html,
    parse_cli_date,
    parse_cli_month,
    month_date_range,
)


SAMPLE_HTML = """
<html>
  <body>
    <ul class="list boxTitle">
      <li>
        <a href="https://health.ltn.com.tw/article/breakingnews/4568540" class="tit">第一則新聞標題</a>
        <div class="meta">
          <i class="immtag chan7">健康</i>
          <span class="time">2024/01/31</span>
        </div>
        <p>第一則摘要內容。</p>
      </li>
      <li>
        <a href="https://ec.ltn.com.tw/article/breakingnews/1234567" class="tit">第二則新聞標題</a>
        <div class="meta">
          <i class="immtag chan3">財經</i>
          <span class="time">2024/01/30</span>
        </div>
        <p>第二則摘要內容。</p>
      </li>
    </ul>
  </body>
</html>
"""


class FetchLtnNewsJsonlTests(unittest.TestCase):
    def test_parse_cli_date_accepts_multiple_formats(self) -> None:
        self.assertEqual(parse_cli_date("2024-01-31"), "2024-01-31")
        self.assertEqual(parse_cli_date("2024/01/31"), "2024-01-31")
        self.assertEqual(parse_cli_date("20240131"), "2024-01-31")

    def test_parse_cli_month_accepts_multiple_formats(self) -> None:
        self.assertEqual(parse_cli_month("2024-02"), (2024, 2))
        self.assertEqual(parse_cli_month("2024/02"), (2024, 2))
        self.assertEqual(parse_cli_month("202402"), (2024, 2))

    def test_month_date_range(self) -> None:
        self.assertEqual(month_date_range("2024-02"), ("2024-02-01", "2024-02-29"))
        self.assertEqual(month_date_range("2020-02"), ("2020-02-01", "2020-02-29"))

    def test_build_search_url(self) -> None:
        url = build_search_url(
            keyword="主流",
            start_date="2024-01-01",
            end_date="2024-01-31",
            news_type="all",
            page=2,
        )
        self.assertIn("keyword=%E4%B8%BB%E6%B5%81", url)
        self.assertIn("start_time=20240101", url)
        self.assertIn("end_time=20240131", url)
        self.assertIn("page=2", url)

    def test_extract_records_from_html(self) -> None:
        records = extract_records_from_html(SAMPLE_HTML)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["source"], "自由時報")
        self.assertEqual(records[0]["date"], "2024-01-31")
        self.assertEqual(records[0]["category"], "健康")
        self.assertEqual(records[0]["snippet"], "第一則摘要內容。")
        self.assertEqual(records[1]["title"], "第二則新聞標題")

    def test_deduplicate_records(self) -> None:
        records = extract_records_from_html(SAMPLE_HTML)
        deduped = deduplicate_records(records + [records[0]])
        self.assertEqual(len(deduped), 2)

    def test_extract_records_from_html_accepts_relative_date(self) -> None:
        html = """
        <ul class="list boxTitle">
          <li>
            <a href="https://news.ltn.com.tw/news/world/breakingnews/9999999" class="tit">即時新聞</a>
            <i class="immtag chan1">國際</i>
            <span class="time">21分鐘前</span>
            <p>即時摘要。</p>
          </li>
        </ul>
        """
        records = extract_records_from_html(html, fallback_date="2026-05-20")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["date"], "2026-05-20")

    def test_build_prompt_template(self) -> None:
        prompt = build_prompt_template(
            keyword="主流",
            start_date="2024-01-01",
            end_date="2024-01-31",
            jsonl_path=Path("/tmp/ltn.jsonl"),
            record_count=12,
        )
        self.assertIn("只能使用每行 JSON 內既有欄位", prompt)
        self.assertIn("不可要求額外抓取全文", prompt)
        self.assertIn("record_count: 12", prompt)


if __name__ == "__main__":
    unittest.main()
