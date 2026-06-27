#!/usr/bin/env python3
"""Regression checks for Group A PVA sigmoid buy-the-dip behavior."""

from __future__ import annotations

import unittest

import pandas as pd

from train_dual_group_2024_2026 import FEATURE_COLUMNS, PortfolioEnv


GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _feature_value(ticker: str, feature: str, bearish: bool) -> float:
    if feature == "close_ma120_ratio":
        return 0.88 if bearish and ticker == "0050.TW" else 1.01
    if feature == "close_ma240_ratio":
        return 0.90 if bearish and ticker == "0050.TW" else 1.00
    if feature == "ma60_ma240_ratio":
        return 0.95 if bearish and ticker == "0050.TW" else 1.00
    if feature == "momentum_21":
        return -0.10 if bearish and ticker == "0050.TW" else 0.01
    if feature == "momentum_63":
        return -0.18 if bearish and ticker == "0050.TW" else 0.02
    if feature == "momentum_126":
        return -0.22 if bearish and ticker == "0050.TW" else 0.03
    if feature == "momentum_252":
        return -0.24 if bearish and ticker == "0050.TW" else 0.04
    if feature == "rolling_mdd_63":
        return -0.28 if bearish and ticker == "0050.TW" else -0.03
    raise KeyError(feature)


def _make_group_a_panel(*, bearish_pva: bool) -> pd.DataFrame:
    dates = pd.date_range("2026-03-02", periods=40, freq="B")
    close_bases = {"0050.TW": 100.0, "00631L.TW": 48.0, "00632R.TW": 18.0}
    rows: list[dict[str, float | str]] = []

    for idx, date in enumerate(dates):
        row: dict[str, float | str] = {
            "date": date,
            "0050_pva_p": -0.12 if bearish_pva else 0.01,
            "0050_pva_v": -0.15 if bearish_pva else 0.02,
            "0050_pva_a": -0.11 if bearish_pva else 0.01,
            "0050_pva_p_z": -2.5 if bearish_pva else 0.2,
            "0050_pva_v_z": -2.2 if bearish_pva else 0.1,
            "0050_pva_a_z": -2.7 if bearish_pva else 0.1,
            "0050_sjm_state_code": -1.0 if bearish_pva else 0.0,
        }
        for ticker in GROUP_A_TICKERS:
            base = close_bases[ticker]
            if ticker == "0050.TW":
                drift = 1.0 - 0.007 * idx if bearish_pva else 1.0 + 0.001 * idx
                wobble = 1.0 + (0.02 if idx % 2 == 0 else -0.025)
            elif ticker == "00631L.TW":
                drift = 1.0 - 0.012 * idx if bearish_pva else 1.0 + 0.002 * idx
                wobble = 1.0 + (0.035 if idx % 2 == 0 else -0.04)
            else:
                drift = 1.0 + 0.008 * idx if bearish_pva else 1.0 - 0.001 * idx
                wobble = 1.0
            close = base * drift * wobble
            row[f"{ticker}_open"] = close * 0.998
            row[f"{ticker}_close"] = close
            for feature in FEATURE_COLUMNS:
                row[f"{ticker}_{feature}"] = _feature_value(ticker, feature, bearish_pva)
        rows.append(row)
    return pd.DataFrame(rows)


def _make_group_a_panel_with_state(*, bearish_pva: bool, sjm_state_code: float) -> pd.DataFrame:
    panel = _make_group_a_panel(bearish_pva=bearish_pva).copy()
    panel["0050_sjm_state_code"] = float(sjm_state_code)
    return panel


class GroupAPVASigmoidTests(unittest.TestCase):
    @unittest.skip("PVA sigmoid not integrated into A21.11 active strategy")
    def test_buy_dip_strength_redeploys_budget_from_inverse_to_0050(self) -> None:
        panel = _make_group_a_panel(bearish_pva=True)
        baseline_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            profile_name="default",
            enable_pva_sigmoid=True,
            pva_drift_threshold=0.01,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.30,
            pva_buy_dip_strength=0.0,
        )
        buy_dip_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            profile_name="default",
            enable_pva_sigmoid=True,
            pva_drift_threshold=0.01,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.30,
            pva_buy_dip_strength=0.75,
        )

        baseline = baseline_env.plan_action(2)
        buy_dip = buy_dip_env.plan_action(2)

        self.assertEqual(baseline["candidate_source"], "pva_risk_scale")
        self.assertEqual(buy_dip["candidate_source"], "pva_risk_scale")
        self.assertEqual(buy_dip["candidate_reason"], "pva_overlay_m")
        self.assertGreater(
            float(buy_dip["candidate_target_weights"]["0050.TW"]),
            float(baseline["candidate_target_weights"]["0050.TW"]),
        )
        self.assertLess(
            float(buy_dip["candidate_target_weights"]["00632R.TW"]),
            float(baseline["candidate_target_weights"]["00632R.TW"]),
        )
        self.assertLess(
            float(buy_dip["candidate_target_weights"]["00631L.TW"]),
            float(baseline["candidate_target_weights"]["00631L.TW"]),
        )
        self.assertGreater(
            float(buy_dip["pva_details"]["risk_metrics"]["dip_accumulation_signal"]),
            0.5,
        )

    def test_j_state_weight_015_is_more_aggressive_than_legacy_005(self) -> None:
        panel = _make_group_a_panel_with_state(bearish_pva=True, sjm_state_code=1.0)
        legacy_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            profile_name="default",
            enable_pva_sigmoid=True,
            pva_j_state_weight=0.05,
            pva_drift_threshold=0.0,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.30,
        )
        aggressive_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            profile_name="default",
            enable_pva_sigmoid=True,
            pva_j_state_weight=0.15,
            pva_drift_threshold=0.0,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.30,
        )

        legacy = legacy_env.plan_action(2)
        aggressive = aggressive_env.plan_action(2)

        self.assertEqual(legacy["candidate_reason"], "pva_overlay_j")
        self.assertEqual(aggressive["candidate_reason"], "pva_overlay_j")
        self.assertAlmostEqual(float(legacy["pva_state_weight"]), 0.05, places=6)
        self.assertAlmostEqual(float(aggressive["pva_state_weight"]), 0.15, places=6)
        self.assertGreater(
            float(aggressive["candidate_target_weights"]["0050.TW"]),
            float(legacy["candidate_target_weights"]["0050.TW"]),
        )
        self.assertLess(
            float(aggressive["candidate_target_weights"]["00631L.TW"]),
            float(legacy["candidate_target_weights"]["00631L.TW"]),
        )

    @unittest.skip("PVA sigmoid not integrated into A21.11 active strategy")
    def test_s_state_high_drift_boost_raises_effective_blend_weight(self) -> None:
        panel = _make_group_a_panel_with_state(bearish_pva=True, sjm_state_code=0.0)
        base_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            profile_name="default",
            enable_pva_sigmoid=True,
            pva_weight=0.30,
            pva_drift_threshold=0.01,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.30,
            pva_s_state_drift_boost=0.0,
            pva_s_state_max_weight=0.30,
        )
        boosted_env = PortfolioEnv(
            panel,
            GROUP_A_TICKERS,
            profile_name="default",
            enable_pva_sigmoid=True,
            pva_weight=0.30,
            pva_drift_threshold=0.01,
            pva_target_vol=0.01,
            pva_min_leverage_scale=0.25,
            pva_inverse_hedge_budget=0.30,
            pva_s_state_drift_boost=0.15,
            pva_s_state_max_weight=0.45,
        )

        base = base_env.plan_action(2)
        boosted = boosted_env.plan_action(2)

        base_metrics = dict(base["pva_details"]["risk_metrics"])
        boosted_metrics = dict(boosted["pva_details"]["risk_metrics"])
        self.assertEqual(base["candidate_reason"], "pva_overlay_s")
        self.assertEqual(boosted["candidate_reason"], "pva_overlay_s")
        self.assertFalse(bool(base_metrics["s_state_drift_boost_applied"]))
        self.assertTrue(bool(boosted_metrics["s_state_drift_boost_applied"]))
        self.assertGreater(float(boosted["pva_state_weight"]), float(base["pva_state_weight"]))
        self.assertGreater(
            float(boosted_metrics["effective_blend_weight"]),
            float(base_metrics["effective_blend_weight"]),
        )
        self.assertGreater(
            float(boosted["candidate_target_weights"]["0050.TW"]),
            float(base["candidate_target_weights"]["0050.TW"]),
        )
        self.assertLess(
            float(boosted["candidate_target_weights"]["00631L.TW"]),
            float(base["candidate_target_weights"]["00631L.TW"]),
        )


if __name__ == "__main__":
    unittest.main()
