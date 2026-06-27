#!/usr/bin/env python3
"""Regression checks for the 4-ETF shared market-regime feature pipeline."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .portfolio_data_loader import _read_relaxed_cache
    from .train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026 import (
        ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS,
        ETFPortfolioEnv,
        TICKERS,
        _align_panel,
        env_kwargs_from_result_payload,
        get_active_derived_features,
    )
except ImportError:
    from portfolio_data_loader import _read_relaxed_cache
    from train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026 import (
        ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS,
        ETFPortfolioEnv,
        TICKERS,
        _align_panel,
        env_kwargs_from_result_payload,
        get_active_derived_features,
    )


def _make_stock_frame(dates: pd.DatetimeIndex, ticker_index: int) -> pd.DataFrame:
    base_price = 50.0 + ticker_index * 7.5
    trend = np.linspace(0.0, 35.0 + ticker_index * 2.0, len(dates))
    close = base_price + trend
    sector_corr = np.linspace(0.15 + 0.08 * ticker_index, 0.75 + 0.04 * ticker_index, len(dates))

    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.998,
            "high": close * 1.002,
            "low": close * 0.996,
            "close": close,
            "volume": 1_000_000 + np.arange(len(dates)) * (1_500 + 200 * ticker_index),
            "dividends": np.where(np.arange(len(dates)) % 63 == 0, 0.3 + ticker_index * 0.05, 0.0),
            "close_ma120_ratio": np.linspace(-0.08, 0.10, len(dates)),
            "close_ma240_ratio": np.linspace(-0.12, 0.08, len(dates)),
            "ma60_ma240_ratio": np.linspace(-0.05, 0.07, len(dates)),
            "momentum_21": np.linspace(-0.02, 0.06, len(dates)),
            "momentum_63": np.linspace(-0.06, 0.18, len(dates)),
            "momentum_126": np.linspace(-0.10, 0.28, len(dates)),
            "momentum_252": np.linspace(-0.15, 0.42, len(dates)),
            "rolling_mdd_63": np.linspace(-0.18, -0.01, len(dates)),
            "sector_correlation": sector_corr,
            "twse_index_return": np.linspace(-0.6, 0.9, len(dates)),
            "twse_index_volume_change": np.sin(np.linspace(0.0, 6.0, len(dates))),
            "market_volatility": np.linspace(-0.4, 1.2, len(dates)),
            "dji_return_1d_lag1": np.linspace(-0.5, 0.5, len(dates)),
            "dji_return_5d_lag1": np.linspace(-0.8, 0.9, len(dates)),
            "dji_volatility_20d_lag1": np.linspace(-0.3, 1.1, len(dates)),
            "dji_ma60_ratio_lag1": np.linspace(-0.15, 0.20, len(dates)),
            "dji_drawdown_60d_lag1": np.linspace(-0.22, -0.01, len(dates)),
        }
    )


class MarketRegimeFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.date_range("2023-01-02", periods=320, freq="B")
        self.stock_data = {
            ticker: _make_stock_frame(dates, idx)
            for idx, ticker in enumerate(TICKERS)
        }

    def test_align_panel_generates_market_regime_features(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")

        self.assertIn("twse_index_return", panel.columns)
        self.assertIn("0050.TW_sector_correlation", panel.columns)
        self.assertIn("0050_vs_high_dividend_corr_gap", panel.columns)

        for col in ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS:
            self.assertIn(col, panel.columns)
            self.assertTrue(np.isfinite(panel[col]).all(), msg=f"{col} contains non-finite values")

        self.assertTrue((panel["market_stress_score"] >= 0.0).all())
        self.assertTrue((panel["market_stress_score"] <= 3.0).all())
        self.assertTrue((panel["market_trend_score"].abs() <= 3.0).all())
        self.assertTrue((panel["cross_market_momentum_gap"].abs() <= 3.0).all())

    def test_legacy_payload_keeps_legacy_feature_set(self) -> None:
        payload = {
            "constraints": {
                "turnover_penalty": 0.08,
                "min_rebalance_days": 60,
                "min_weight": 0.05,
                "max_weight": 0.70,
            },
            "feature_config": {
                "rsi_features_enabled": False,
            },
        }
        env_kwargs = env_kwargs_from_result_payload(payload)
        self.assertEqual(
            env_kwargs["active_derived_features"],
            get_active_derived_features(use_rsi_features=False, use_market_regime_features=False),
        )

    def test_relaxed_cache_accepts_late_listing_when_allowed(self) -> None:
        late_dates = pd.date_range("2020-07-10", periods=80, freq="B")
        late_df = pd.DataFrame(
            {
                "date": late_dates,
                "open": np.linspace(10.0, 12.0, len(late_dates)),
                "high": np.linspace(10.2, 12.2, len(late_dates)),
                "low": np.linspace(9.8, 11.8, len(late_dates)),
                "close": np.linspace(10.0, 12.0, len(late_dates)),
                "volume": np.full(len(late_dates), 1000, dtype=int),
            }
        )

        with TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "late_listing.parquet"
            late_df.to_parquet(cache_path, index=False)

            rejected = _read_relaxed_cache(
                cache_path,
                start_date="2020-01-01",
                end_date="2020-10-31",
                required_columns=["date", "open", "high", "low", "close", "volume"],
                min_rows=50,
                allow_late_start=False,
            )
            accepted = _read_relaxed_cache(
                cache_path,
                start_date="2020-01-01",
                end_date="2020-10-31",
                required_columns=["date", "open", "high", "low", "close", "volume"],
                min_rows=50,
                allow_late_start=True,
            )

        self.assertIsNone(rejected)
        self.assertIsNotNone(accepted)
        assert accepted is not None
        self.assertEqual(pd.Timestamp("2020-07-10"), pd.Timestamp(accepted["date"].min()))

    def test_defensive_cash_actions_reserve_cash(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")
        env = ETFPortfolioEnv(panel, min_weight=0.05, max_weight=0.70)
        moderate_cash = env._target_weights(10)
        deep_cash = env._target_weights(11)

        self.assertLess(float(moderate_cash.sum()), 1.0)
        self.assertLess(float(deep_cash.sum()), float(moderate_cash.sum()))
        self.assertGreaterEqual(float(deep_cash.sum()), 0.20)

    def test_market_stress_guardrail_overrides_risk_on_action(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")
        panel["market_stress_score"] = 1.35
        panel["market_trend_score"] = -0.45
        env = ETFPortfolioEnv(panel, stress_confirm_days=1, min_weight=0.05, max_weight=0.70)
        env.weights = env._target_weights(2)
        decision = env.plan_action(2)

        self.assertEqual(decision["candidate_source"], "market_stress")
        self.assertEqual(decision["reason"], "market_stress_deep_risk_off")
        self.assertGreaterEqual(float(decision["effective_target_cash_weight"]), 0.45)

    def test_market_stress_can_bypass_normal_cooldown(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")
        panel["market_stress_score"] = 1.35
        panel["market_trend_score"] = -0.45
        env = ETFPortfolioEnv(
            panel,
            min_rebalance_days=60,
            stress_rebalance_cooldown_days=0,
            stress_confirm_days=1,
            min_weight=0.05,
            max_weight=0.70,
        )
        env.step_idx = 10
        env.last_rebalance_idx = 5
        env.weights = env._target_weights(2)
        decision = env.plan_action(2)

        self.assertGreater(decision["cooldown_remaining"], 0)
        self.assertEqual(decision["stress_cooldown_remaining"], 0)
        self.assertTrue(decision["can_trade_now"])
        self.assertEqual(decision["execution_source"], "market_stress")

    def test_market_stress_requires_confirmation_and_tier_change(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")
        panel["market_stress_score"] = 1.35
        panel["market_trend_score"] = -0.45
        env = ETFPortfolioEnv(
            panel,
            min_rebalance_days=60,
            stress_rebalance_cooldown_days=0,
            stress_confirm_days=3,
            min_weight=0.05,
            max_weight=0.70,
        )
        env.step_idx = 1
        env.weights = env._target_weights(2)
        early = env.plan_action(2)
        self.assertTrue(early["can_trade_now"])
        self.assertEqual(early["stress_guardrail"]["reason"], "stress_wait_confirm_2d")
        self.assertTrue(early["stress_risk_budget"]["applied"])
        self.assertEqual(early["candidate_source"], "stress_budget")
        self.assertEqual(early["execution_source"], "stress_budget")
        self.assertGreaterEqual(float(early["effective_target_cash_weight"]), 0.30)

        env.step_idx = 5
        env.weights = env._target_weights(11)
        same_tier = env.plan_action(2)
        self.assertFalse(same_tier["can_trade_now"])
        self.assertEqual(same_tier["stress_guardrail"]["reason"], "stress_same_cash_tier")
        self.assertEqual(same_tier["execution_source"], "hold")

    def test_stress_risk_budget_caps_0050_before_full_risk_off(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")
        panel["market_stress_score"] = 0.19
        panel["market_trend_score"] = -0.02
        panel["0050_trend_score"] = 0.0
        panel["0050_drawdown_risk"] = 0.10
        env = ETFPortfolioEnv(panel, min_weight=0.05, max_weight=0.70)
        env.weights = env._target_weights(1)
        decision = env.plan_action(2)

        self.assertEqual(decision["execution_source"], "ppo_action")
        self.assertTrue(decision["stress_risk_budget"]["applied"])
        self.assertEqual(decision["stress_risk_budget"]["budget_level"], "caution")
        self.assertLessEqual(float(decision["effective_target_weights"]["0050.TW"]), 0.55)
        self.assertGreaterEqual(float(decision["effective_target_cash_weight"]), 0.08)

    def test_benchmark_shortfall_penalty_reduces_reward_when_lagging_0050(self) -> None:
        panel = _align_panel(self.stock_data, "2023-01-02", "2024-03-29")
        base_env = ETFPortfolioEnv(
            panel,
            benchmark_shortfall_penalty_weight=0.0,
            benchmark_shortfall_stress_scale=0.0,
        )
        penalty_env = ETFPortfolioEnv(
            panel,
            benchmark_shortfall_penalty_weight=0.10,
            benchmark_shortfall_stress_scale=0.0,
        )

        base_env.reset()
        penalty_env.reset()
        _, base_reward, _, _, _ = base_env.step(0)
        _, penalty_reward, _, _, penalty_info = penalty_env.step(0)

        self.assertLess(penalty_reward, base_reward)
        self.assertGreater(penalty_info["benchmark_penalty"]["penalty"], 0.0)
        self.assertLess(penalty_info["benchmark_penalty"]["bh_0050_relative"], 0.0)


if __name__ == "__main__":
    unittest.main()
