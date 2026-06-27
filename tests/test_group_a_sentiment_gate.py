#!/usr/bin/env python3
"""Regression checks for Group A sentiment-driven risk gating."""

from __future__ import annotations

import unittest

import pandas as pd

from train_dual_group_2024_2026 import FEATURE_COLUMNS, LLM_SENTIMENT_COLUMNS, PortfolioEnv


GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _make_group_a_panel(
    *,
    llm_sentiment_score: float,
    llm_sentiment_confidence: float,
    llm_risk_off_score: float,
    llm_news_intensity: float,
) -> pd.DataFrame:
    dates = pd.date_range("2026-05-18", periods=4, freq="B")
    rows: list[dict[str, float | str]] = []
    close_bases = {"0050.TW": 100.0, "00631L.TW": 48.0, "00632R.TW": 18.0}

    for idx, date in enumerate(dates):
        row: dict[str, float | str] = {
            "date": date,
            "llm_sentiment_score": llm_sentiment_score,
            "llm_sentiment_confidence": llm_sentiment_confidence,
            "llm_risk_off_score": llm_risk_off_score,
            "llm_news_intensity": llm_news_intensity,
        }
        for ticker in GROUP_A_TICKERS:
            close = close_bases[ticker] * (1.0 + 0.01 * idx)
            row[f"{ticker}_open"] = close * 0.998
            row[f"{ticker}_close"] = close
            for feature in FEATURE_COLUMNS:
                if feature == "close_ma120_ratio":
                    row[f"{ticker}_{feature}"] = 1.02
                elif feature == "close_ma240_ratio":
                    row[f"{ticker}_{feature}"] = 1.01
                elif feature == "ma60_ma240_ratio":
                    row[f"{ticker}_{feature}"] = 1.005
                elif feature == "rolling_mdd_63":
                    row[f"{ticker}_{feature}"] = -0.03
                else:
                    row[f"{ticker}_{feature}"] = 0.02
        rows.append(row)
    return pd.DataFrame(rows)


class GroupASentimentGateTests(unittest.TestCase):
    @unittest.skip("Sentiment gate not integrated into A21.11 active strategy")
    def test_positive_sentiment_boosts_leverage_weight(self) -> None:
        panel = _make_group_a_panel(
            llm_sentiment_score=0.85,
            llm_sentiment_confidence=0.85,
            llm_risk_off_score=0.05,
            llm_news_intensity=2.5,
        )
        env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            shared_feature_cols=list(LLM_SENTIMENT_COLUMNS),
            profile_name="default",
            leverage_cap=0.30,
            inverse_cap=0.30,
            sentiment_gate_enabled=True,
            sentiment_positive_threshold=0.20,
            sentiment_positive_max_risk_off_score=0.10,
            sentiment_positive_leverage_boost=0.05,
        )

        decision = env.plan_action(1)

        self.assertEqual(decision["candidate_source"], "llm_sentiment")
        self.assertEqual(decision["candidate_reason"], "llm_sentiment_positive")
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["0050.TW"]), 0.80, places=6)
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["00631L.TW"]), 0.20, places=6)
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["00632R.TW"]), 0.0, places=6)
        self.assertAlmostEqual(
            float(decision["risk_gate"]["positive_leverage_boost"]),
            0.05,
            places=6,
        )

    def test_risk_off_sentiment_zeroes_leverage(self) -> None:
        panel = _make_group_a_panel(
            llm_sentiment_score=-0.20,
            llm_sentiment_confidence=0.80,
            llm_risk_off_score=0.25,
            llm_news_intensity=2.2,
        )
        env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            shared_feature_cols=list(LLM_SENTIMENT_COLUMNS),
            profile_name="default",
            leverage_cap=0.30,
            inverse_cap=0.30,
            sentiment_gate_enabled=True,
        )

        decision = env.plan_action(2)

        self.assertEqual(decision["candidate_source"], "llm_sentiment")
        self.assertEqual(decision["candidate_reason"], "llm_sentiment_risk_off")
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["0050.TW"]), 1.0, places=6)
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["00631L.TW"]), 0.0, places=6)
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["00632R.TW"]), 0.0, places=6)

    def test_severe_sentiment_can_hold_inverse_outside_m_state(self) -> None:
        panel = _make_group_a_panel(
            llm_sentiment_score=-0.95,
            llm_sentiment_confidence=0.90,
            llm_risk_off_score=0.90,
            llm_news_intensity=4.5,
        )
        env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            shared_feature_cols=list(LLM_SENTIMENT_COLUMNS),
            profile_name="default",
            leverage_cap=0.30,
            inverse_cap=0.30,
            sentiment_gate_enabled=True,
            inverse_m_state_only=True,
        )

        decision = env.plan_action(1)

        self.assertEqual(decision["candidate_source"], "llm_sentiment")
        self.assertEqual(decision["candidate_reason"], "llm_sentiment_severe")
        self.assertAlmostEqual(float(decision["candidate_target_weights"]["00631L.TW"]), 0.0, places=6)
        self.assertGreaterEqual(float(decision["candidate_target_weights"]["00632R.TW"]), 0.299)
        self.assertTrue(bool(decision["inverse_rule"]["override_active"]))


if __name__ == "__main__":
    unittest.main()
