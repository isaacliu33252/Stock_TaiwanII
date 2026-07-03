from __future__ import annotations

import unittest

import pandas as pd

from group_a_plus.integrations.llm_sentiment_features import (
    attach_llm_sentiment_features,
    build_llm_sentiment_feature_frame,
)


class LlmSentimentFeatureTests(unittest.TestCase):
    def test_build_features_lags_same_day_sentiment(self) -> None:
        daily = pd.DataFrame(
            [
                {
                    "date": "2026-01-02",
                    "llm_sentiment_score": 0.8,
                    "llm_sentiment_confidence": 0.7,
                    "llm_risk_off_score": 0.1,
                    "llm_news_intensity": 2.0,
                },
                {
                    "date": "2026-01-05",
                    "llm_sentiment_score": -0.6,
                    "llm_sentiment_confidence": 0.9,
                    "llm_risk_off_score": 0.8,
                    "llm_news_intensity": 1.0,
                },
            ]
        )

        features = build_llm_sentiment_feature_frame(daily, windows=(2,), lag_days=1)

        self.assertAlmostEqual(0.0, features.loc[pd.Timestamp("2026-01-02"), "llm_sentiment_score_lag1"])
        self.assertAlmostEqual(0.8, features.loc[pd.Timestamp("2026-01-05"), "llm_sentiment_score_lag1"])

    def test_attach_features_left_joins_panel_dates(self) -> None:
        panel = pd.DataFrame({"date": pd.to_datetime(["2026-01-02", "2026-01-05"]), "x": [1.0, 2.0]})
        daily = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "llm_sentiment_score": [0.5, -0.5],
                "llm_sentiment_confidence": [0.8, 0.9],
                "llm_risk_off_score": [0.1, 0.7],
                "llm_news_intensity": [1.0, 3.0],
            }
        )

        out = attach_llm_sentiment_features(panel, daily, lag_days=1, windows=(2,))

        self.assertIn("llm_sentiment_2d", out.columns)
        self.assertAlmostEqual(0.0, out.loc[0, "llm_sentiment_score_lag1"])
        self.assertAlmostEqual(0.5, out.loc[1, "llm_sentiment_score_lag1"])


if __name__ == "__main__":
    unittest.main()
