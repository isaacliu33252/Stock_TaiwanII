#!/usr/bin/env python3
"""Tests for Liberty Times market-news filtering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from filter_ltn_market_news import read_records, score_market_relevance


class FilterLtnMarketNewsTests(unittest.TestCase):
    def test_finance_category_passes(self) -> None:
        record = {
            "date": "2024-01-01",
            "source": "自由時報",
            "title": "台股盤前》AI 題材續強",
            "url": "https://example.com/a",
            "category": "財經",
            "snippet": "台股與電子股今天受矚目。",
        }
        include, debug = score_market_relevance(record)
        self.assertTrue(include)
        self.assertGreaterEqual(debug["score"], 3)

    def test_politics_without_market_terms_fails(self) -> None:
        record = {
            "date": "2024-01-01",
            "source": "自由時報",
            "title": "某政治人物出席活動",
            "url": "https://example.com/b",
            "category": "政治",
            "snippet": "地方行程與致詞內容。",
        }
        include, _ = score_market_relevance(record)
        self.assertFalse(include)

    def test_international_with_macro_terms_passes(self) -> None:
        record = {
            "date": "2024-01-01",
            "source": "自由時報",
            "title": "聯準會降息預期升溫",
            "url": "https://example.com/c",
            "category": "國際",
            "snippet": "市場關注 Fed 與美債殖利率走勢。",
        }
        include, debug = score_market_relevance(record)
        self.assertTrue(include)
        self.assertIn("macro_policy", debug["keyword_hits"])

    def test_read_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "merged.jsonl"
            path.write_text(
                '{"date":"2024-01-01","source":"自由時報","title":"A","url":"https://example.com","category":"財經","snippet":"B"}\n',
                encoding="utf-8",
            )
            records = read_records(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["category"], "財經")


if __name__ == "__main__":
    unittest.main()
