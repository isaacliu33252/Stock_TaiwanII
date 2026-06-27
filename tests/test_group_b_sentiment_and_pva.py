#!/usr/bin/env python3
"""Regression checks for Group B sentiment gating and PVA scaling."""

from __future__ import annotations

import unittest

import pandas as pd

from train_dual_group_2024_2026 import (
    FEATURE_COLUMNS,
    GROUP_B_ACTION_SCHEMA_CORE6_CASH20_V1,
    LLM_SENTIMENT_COLUMNS,
    PortfolioEnv,
)


GROUP_B_TICKERS = [
    "0056.TW",
    "00646.TW",
    "00679B.TWO",
    "00713.TW",
    "00751B.TWO",
    "00878.TW",
]
GROUP_B_RISK = {"0056.TW", "00646.TW", "00713.TW", "00878.TW"}
GROUP_B_DEFENSIVE = {"00679B.TWO", "00751B.TWO"}


def _feature_value(ticker: str, feature: str, bearish: bool) -> float:
    is_risk = ticker in GROUP_B_RISK
    if feature == "close_ma120_ratio":
        return 0.92 if bearish and is_risk else 1.01
    if feature == "close_ma240_ratio":
        return 0.90 if bearish and is_risk else 1.00
    if feature == "ma60_ma240_ratio":
        return 0.96 if bearish and is_risk else 1.00
    if feature == "momentum_21":
        return -0.08 if bearish and is_risk else 0.01
    if feature == "momentum_63":
        return -0.14 if bearish and is_risk else 0.02
    if feature == "momentum_126":
        return -0.18 if bearish and is_risk else 0.03
    if feature == "momentum_252":
        return -0.20 if bearish and is_risk else 0.04
    if feature == "rolling_mdd_63":
        return -0.22 if bearish and is_risk else -0.03
    raise KeyError(feature)


def _make_group_b_panel(
    *,
    llm_sentiment_score: float,
    llm_sentiment_confidence: float,
    llm_risk_off_score: float,
    llm_news_intensity: float,
    bearish_pva: bool,
) -> pd.DataFrame:
    dates = pd.date_range("2026-03-02", periods=40, freq="B")
    close_bases = {
        "0056.TW": 42.0,
        "00646.TW": 68.0,
        "00679B.TWO": 27.0,
        "00713.TW": 54.0,
        "00751B.TWO": 31.0,
        "00878.TW": 27.0,
    }
    rows: list[dict[str, float | str]] = []

    for idx, date in enumerate(dates):
        row: dict[str, float | str] = {
            "date": date,
            "llm_sentiment_score": llm_sentiment_score,
            "llm_sentiment_confidence": llm_sentiment_confidence,
            "llm_risk_off_score": llm_risk_off_score,
            "llm_news_intensity": llm_news_intensity,
            "group_b_pva_p": -0.10 if bearish_pva else 0.01,
            "group_b_pva_v": -0.12 if bearish_pva else 0.02,
            "group_b_pva_a": -0.09 if bearish_pva else 0.01,
            "group_b_pva_p_z": -2.4 if bearish_pva else 0.2,
            "group_b_pva_v_z": -2.3 if bearish_pva else 0.1,
            "group_b_pva_a_z": -2.6 if bearish_pva else 0.1,
            "group_b_sjm_state_code": -1.0 if bearish_pva else 0.0,
        }
        for ticker in GROUP_B_TICKERS:
            base = close_bases[ticker]
            if ticker in GROUP_B_RISK:
                drift = 1.0 - 0.006 * idx
                wobble = 1.0 + (0.03 if idx % 2 == 0 else -0.02)
            else:
                drift = 1.0 + 0.0015 * idx
                wobble = 1.0
            close = base * drift * wobble
            row[f"{ticker}_open"] = close * 0.998
            row[f"{ticker}_close"] = close
            for feature in FEATURE_COLUMNS:
                row[f"{ticker}_{feature}"] = _feature_value(ticker, feature, bearish_pva)
        rows.append(row)
    return pd.DataFrame(rows)


class GroupBOverlayTests(unittest.TestCase):
    def test_severe_llm_sentiment_rotates_to_defensive_plus_cash(self) -> None:
        panel = _make_group_b_panel(
            llm_sentiment_score=-0.95,
            llm_sentiment_confidence=0.90,
            llm_risk_off_score=0.95,
            llm_news_intensity=4.2,
            bearish_pva=False,
        )
        env = PortfolioEnv(
            panel,
            GROUP_B_TICKERS,
            shared_feature_cols=list(LLM_SENTIMENT_COLUMNS),
            profile_name="group_b_balanced",
            group_b_action_schema=GROUP_B_ACTION_SCHEMA_CORE6_CASH20_V1,
            sentiment_gate_enabled=True,
        )

        decision = env.plan_action(2)
        defensive_weight = float(
            decision["candidate_target_weights"]["00679B.TWO"]
            + decision["candidate_target_weights"]["00751B.TWO"]
        )

        self.assertEqual(decision["candidate_source"], "llm_sentiment")
        self.assertEqual(decision["candidate_reason"], "llm_sentiment_severe")
        self.assertGreaterEqual(float(decision["candidate_target_cash_weight"]), 0.29)
        self.assertGreaterEqual(defensive_weight, 0.66)

    def test_group_b_pva_overlay_scales_down_risk_budget(self) -> None:
        panel = _make_group_b_panel(
            llm_sentiment_score=0.0,
            llm_sentiment_confidence=0.0,
            llm_risk_off_score=0.0,
            llm_news_intensity=0.0,
            bearish_pva=True,
        )
        env = PortfolioEnv(
            panel,
            GROUP_B_TICKERS,
            profile_name="group_b_balanced",
            group_b_action_schema=GROUP_B_ACTION_SCHEMA_CORE6_CASH20_V1,
            enable_pva_sigmoid=True,
            pva_drift_threshold=0.01,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.20,
        )

        decision = env.plan_action(2)
        risk_tickers = ["0056.TW", "00646.TW", "00713.TW", "00878.TW"]
        defensive_tickers = ["00679B.TWO", "00751B.TWO"]
        base_risk = sum(float(decision["base_target_weights"][ticker]) for ticker in risk_tickers)
        candidate_risk = sum(float(decision["candidate_target_weights"][ticker]) for ticker in risk_tickers)
        base_defensive = sum(float(decision["base_target_weights"][ticker]) for ticker in defensive_tickers)
        candidate_defensive = sum(float(decision["candidate_target_weights"][ticker]) for ticker in defensive_tickers)

        self.assertEqual(decision["candidate_source"], "pva_risk_scale")
        self.assertEqual(decision["candidate_reason"], "pva_overlay_m")
        self.assertLess(candidate_risk, base_risk)
        self.assertGreater(candidate_defensive, base_defensive)
        self.assertGreater(float(decision["candidate_target_cash_weight"]), 0.0)


if __name__ == "__main__":
    unittest.main()
