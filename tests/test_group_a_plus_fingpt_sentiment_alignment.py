#!/usr/bin/env python3
"""Regression checks for the FinGPT-inspired GroupA+ sentiment overlay."""

from __future__ import annotations

import unittest

import pandas as pd

from backtest_group_a_plus_fingpt_sentiment_alignment import _build_features


class FinGPTSentimentAlignmentTests(unittest.TestCase):
    def test_news_is_lagged_until_next_calendar_day(self) -> None:
        records = [
            {
                "date": "2026-01-05",
                "source": "ltn",
                "title": "台股面臨戰爭與流動性風險",
                "summary": "外資賣壓升高",
                "category": "財經",
                "url": "https://example.test/1",
            }
        ]
        index = pd.DatetimeIndex(["2026-01-05", "2026-01-06"])

        features, coverage = _build_features(records, index)

        self.assertEqual(coverage["source_count"], 1)
        self.assertEqual(float(features.loc["2026-01-05", "news_count_7d"]), 0.0)
        self.assertEqual(float(features.loc["2026-01-06", "news_count_7d"]), 1.0)
        self.assertGreater(float(features.loc["2026-01-06", "fingpt_risk_score"]), 0.0)

    def test_weekend_news_is_available_on_monday(self) -> None:
        records = [
            {
                "date": "2026-01-10",
                "source": "ltn",
                "title": "半導體出口管制衝擊台股",
                "summary": "晶片禁令風險升高",
                "category": "財經",
                "url": "https://example.test/2",
            }
        ]
        index = pd.DatetimeIndex(["2026-01-09", "2026-01-12"])

        features, _coverage = _build_features(records, index)

        self.assertEqual(float(features.loc["2026-01-09", "news_count_7d"]), 0.0)
        self.assertEqual(float(features.loc["2026-01-12", "news_count_7d"]), 1.0)


if __name__ == "__main__":
    unittest.main()
