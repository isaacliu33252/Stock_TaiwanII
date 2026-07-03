#!/usr/bin/env python3
"""Tests for local FinBERT-style daily sentiment feature conversion."""

from __future__ import annotations

import unittest

import pandas as pd

from build_finbert_sentiment_features import (
    OUTPUT_COLUMNS,
    build_finbert_daily_features,
    resolve_finbert_text_columns,
    score_text_finbert_proxy,
)


class BuildFinbertSentimentFeaturesTests(unittest.TestCase):
    def test_score_text_finbert_proxy_matches_finbert_shape(self) -> None:
        positive = score_text_finbert_proxy("台股強勢反彈 買盤回升 成長樂觀")
        negative = score_text_finbert_proxy("市場暴跌 賣壓升溫 通膨風險衝擊")

        self.assertGreater(positive["finbert_sentiment_score"], 0.0)
        self.assertLess(negative["finbert_sentiment_score"], 0.0)
        self.assertGreater(positive["finbert_positive_ratio"], positive["finbert_negative_ratio"])
        self.assertGreater(negative["finbert_negative_ratio"], negative["finbert_positive_ratio"])
        for payload in (positive, negative):
            total = (
                payload["finbert_positive_ratio"]
                + payload["finbert_negative_ratio"]
                + payload["finbert_neutral_ratio"]
            )
            self.assertAlmostEqual(total, 1.0, places=6)
            self.assertGreaterEqual(payload["finbert_confidence"], 0.0)
            self.assertLessEqual(payload["finbert_confidence"], 1.0)

    def test_build_finbert_daily_features_uses_title_and_snippet(self) -> None:
        table = pd.DataFrame(
            [
                {
                    "date": "2026-06-24",
                    "title": "0050 強勢反彈",
                    "description": "",
                    "snippet": "買盤回升 市場樂觀 成長",
                },
                {
                    "date": "2026-06-25",
                    "title": "台股賣壓升溫",
                    "description": "",
                    "snippet": "通膨風險 衝擊市場 暴跌",
                },
                {
                    "published_at": "2026-06-25 09:30:00+08:00",
                    "title": "電子股下跌",
                    "description": "",
                    "snippet": "疲軟 下行 賣壓",
                },
            ]
        )

        self.assertEqual(resolve_finbert_text_columns(table), ["title", "snippet"])
        daily = build_finbert_daily_features(table)

        self.assertEqual(list(daily.columns), OUTPUT_COLUMNS)
        self.assertEqual(list(daily["date"]), ["2026-06-24", "2026-06-25"])
        self.assertEqual(
            set(daily["finbert_scoring_mode"]),
            {"rule_based_finbert_proxy"},
        )
        first = daily[daily["date"] == "2026-06-24"].iloc[0]
        second = daily[daily["date"] == "2026-06-25"].iloc[0]
        self.assertGreater(first["finbert_sentiment_score"], 0.0)
        self.assertLess(second["finbert_sentiment_score"], 0.0)
        self.assertEqual(float(second["finbert_record_count"]), 2.0)
        self.assertGreater(second["finbert_news_intensity"], 0.0)


if __name__ == "__main__":
    unittest.main()
