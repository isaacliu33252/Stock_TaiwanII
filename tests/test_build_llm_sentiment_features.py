#!/usr/bin/env python3
"""Tests for raw-news to daily sentiment feature conversion."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from build_llm_sentiment_features import OUTPUT_COLUMNS, prepare_llm_sentiment_path


class BuildLlmSentimentFeaturesTests(unittest.TestCase):
    def test_prepare_llm_sentiment_path_builds_from_news_directory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            news_dir = root / "news"
            nested_dir = news_dir / "nested"
            news_dir.mkdir()
            nested_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "date": "2026-05-18",
                        "title": "0050 強勢反彈",
                        "description": "市場樂觀看待台股成長與回升。",
                    }
                ]
            ).to_csv(news_dir / "news_1.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "pub_date": "2026-05-19 08:30:00+08:00",
                        "title": "通膨風險升溫",
                        "description": "市場擔心波動與風險。",
                    }
                ]
            ).to_json(
                nested_dir / "news_2.jsonl",
                orient="records",
                lines=True,
                force_ascii=False,
            )

            output_path = root / "daily_sentiment.csv"
            resolved_path, info = prepare_llm_sentiment_path(news_dir, output_path=output_path)

            self.assertEqual(resolved_path, output_path)
            self.assertTrue(output_path.exists())
            self.assertTrue(bool(info.get("generated")))
            self.assertEqual(info.get("mode"), "rule_based")
            self.assertEqual(info.get("text_columns"), ["title", "description"])

            daily = pd.read_csv(output_path)
            self.assertEqual(list(daily.columns), OUTPUT_COLUMNS)
            self.assertEqual(len(daily), 2)
            self.assertEqual(set(daily["date"]), {"2026-05-18", "2026-05-19"})

    def test_prepare_llm_sentiment_path_keeps_pre_scored_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "scored.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2026-05-18",
                        "llm_sentiment_score": 0.2,
                        "llm_sentiment_confidence": 0.8,
                        "llm_risk_off_score": 0.1,
                        "llm_news_intensity": 1.0,
                    }
                ]
            ).to_csv(source, index=False)

            resolved_path, info = prepare_llm_sentiment_path(source)

            self.assertEqual(resolved_path, source)
            self.assertFalse(bool(info.get("generated")))
            self.assertEqual(info.get("mode"), "pre_scored")
            self.assertEqual(info.get("path"), str(source))


if __name__ == "__main__":
    unittest.main()
