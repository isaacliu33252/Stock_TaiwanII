from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_stock_ranking_walkforward.py"
    spec = importlib.util.spec_from_file_location("_test_stock_ranking_wf", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ohlcv(days: int = 180) -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=days, freq="B")
    rows = []
    tickers = ["0050.TW", "2330.TW", "2317.TW", "2454.TW"]
    for j, ticker in enumerate(tickers):
        base = 50.0 + j * 20.0
        for i, dt in enumerate(dates):
            trend = i * (0.03 + j * 0.01)
            wave = np.sin(i / 7.0 + j) * 0.6
            close = base + trend + wave
            rows.append(
                {
                    "ticker": ticker,
                    "date": dt,
                    "open": close * 0.998,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": int(1000 + i * 3 + j * 100),
                    "dividends": 0.0,
                }
            )
    return pd.DataFrame(rows)


class StockRankingWalkForwardTests(unittest.TestCase):
    def test_build_feature_panel_adds_market_industry_and_sentiment_features(self) -> None:
        module = _load_module()
        industry = pd.DataFrame(
            {"ticker": ["2330.TW", "2317.TW", "2454.TW"], "industry": ["semi", "electronics", "semi"]}
        )
        sentiment = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-02", periods=180, freq="B"),
                "llm_sentiment_score": np.linspace(-0.2, 0.2, 180),
                "llm_sentiment_confidence": 0.7,
                "llm_risk_off_score": 0.1,
                "llm_news_intensity": 1.0,
            }
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sentiment_path = Path(tmp) / "sentiment.csv"
            sentiment.to_csv(sentiment_path, index=False)
            panel = module.build_feature_panel(
                _ohlcv(),
                horizon=1,
                industry_map=industry,
                llm_sentiment_path=sentiment_path,
            )

        self.assertIn("market_ret_1d", panel.columns)
        self.assertIn("industry_relative_ret_5d", panel.columns)
        self.assertIn("llm_sentiment_score_lag1", panel.columns)
        self.assertIn("cs_rank_ret_20d", panel.columns)
        self.assertTrue(panel["target_return"].notna().all())

    def test_walkforward_ranking_uses_purged_date_folds_and_outputs_selections(self) -> None:
        module = _load_module()
        panel = module.build_feature_panel(_ohlcv(220), horizon=3)

        report, selections, curve = module.run_walkforward_ranking(
            panel,
            horizon=3,
            top_k=2,
            n_splits=2,
            test_size=20,
            purge=3,
            min_train_dates=80,
            rebalance_every=3,
        )

        self.assertEqual(2, len(report["folds"]))
        for fold in report["folds"]:
            self.assertGreaterEqual(fold["train_dates"], 80)
        self.assertFalse(selections.empty)
        self.assertFalse(curve.empty)
        self.assertIn("topk_metrics", report["aggregate"])
        self.assertIn("equal_weight_universe_metrics", report["aggregate"])

    def test_parse_tickers_normalises_plain_twse_codes(self) -> None:
        module = _load_module()

        self.assertEqual(["2330.TW", "2317.TW", "0050.TW"], module.parse_tickers("2330,2317.TW,0050"))


if __name__ == "__main__":
    unittest.main()
