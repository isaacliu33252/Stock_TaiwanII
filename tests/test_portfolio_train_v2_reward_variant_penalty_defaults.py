from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from portfolio_train_v2 import EnhancedStockTrainer


def _make_df(n: int = 30) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n)
    closes = np.full(n, 100.0)
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": np.full(n, 1000),
        }
    )


class TestRewardVariantPenaltyDefaults(unittest.TestCase):
    """2026-08-06 minimal comparison found reward_variant="alpha" collapses
    to a never-trade policy because turnover_penalty=0.01 (calibrated for
    v3's amplified reward scale) swamps AlphaRewardFunction's much smaller
    raw log-return scale. Fix: default to 0 penalty for the alpha variant,
    keep the original 0.01/20/0.02 defaults for v3 (backward compatible),
    and let explicit arguments override either way."""

    def test_v3_default_matches_original_hardcoded_values(self) -> None:
        trainer = EnhancedStockTrainer(ticker="TEST", df=_make_df(), enable_risk_manager=False)
        self.assertEqual(trainer.reward_variant, "v3")
        self.assertEqual(trainer.turnover_penalty, 0.01)
        self.assertEqual(trainer.min_hold_days, 20)
        self.assertEqual(trainer.short_hold_penalty, 0.02)

    def test_alpha_variant_defaults_to_zero_penalty(self) -> None:
        trainer = EnhancedStockTrainer(
            ticker="TEST", df=_make_df(), enable_risk_manager=False, reward_variant="alpha"
        )
        self.assertEqual(trainer.turnover_penalty, 0.0)
        self.assertEqual(trainer.min_hold_days, 0)
        self.assertEqual(trainer.short_hold_penalty, 0.0)

    def test_explicit_override_wins_for_v3(self) -> None:
        trainer = EnhancedStockTrainer(
            ticker="TEST", df=_make_df(), enable_risk_manager=False,
            reward_variant="v3", turnover_penalty=0.005,
        )
        self.assertEqual(trainer.turnover_penalty, 0.005)

    def test_explicit_override_wins_for_alpha(self) -> None:
        trainer = EnhancedStockTrainer(
            ticker="TEST", df=_make_df(), enable_risk_manager=False,
            reward_variant="alpha", turnover_penalty=0.003, min_hold_days=5, short_hold_penalty=0.001,
        )
        self.assertEqual(trainer.turnover_penalty, 0.003)
        self.assertEqual(trainer.min_hold_days, 5)
        self.assertEqual(trainer.short_hold_penalty, 0.001)

    def test_create_env_passes_resolved_penalties_through(self) -> None:
        trainer = EnhancedStockTrainer(
            ticker="TEST", df=_make_df(), enable_risk_manager=False, reward_variant="alpha"
        )
        with patch("environments.taiwan_stock_env.TaiwanStockTradingEnv") as mock_env_cls:
            trainer.create_env()
        _, kwargs = mock_env_cls.call_args
        self.assertEqual(kwargs["turnover_penalty"], 0.0)
        self.assertEqual(kwargs["min_hold_days"], 0)
        self.assertEqual(kwargs["short_hold_penalty"], 0.0)

    def test_backtest_env_also_uses_resolved_penalties_not_hardcoded_v3_values(self) -> None:
        trainer = EnhancedStockTrainer(
            ticker="TEST", df=_make_df(), enable_risk_manager=False, reward_variant="alpha"
        )
        trainer.model = MagicMock()
        trainer.model.predict.return_value = (0, None)  # always HOLD

        with patch("environments.taiwan_stock_env.TaiwanStockTradingEnv") as mock_env_cls:
            mock_env = mock_env_cls.return_value
            mock_env.reset.return_value = ([0.0], {})
            mock_env.step.return_value = ([0.0], 0.0, True, False, {"portfolio_value": 1_000_000.0})
            mock_env.balance = 1_000_000.0
            mock_env.position = 0
            mock_env.commission_rate = 0.001425
            mock_env.tax_rate = 0.003
            mock_env.trade_history = []
            trainer.backtest(df_test=_make_df())

        _, kwargs = mock_env_cls.call_args
        self.assertEqual(kwargs["turnover_penalty"], 0.0)
        self.assertEqual(kwargs["min_hold_days"], 0)
        self.assertEqual(kwargs["short_hold_penalty"], 0.0)


if __name__ == "__main__":
    unittest.main()
