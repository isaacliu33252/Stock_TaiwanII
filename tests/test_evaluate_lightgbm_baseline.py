from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_lightgbm_baseline.py"
    spec = importlib.util.spec_from_file_location("_test_lightgbm_baseline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _panel(rows: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02", periods=rows, freq="B")
    x = np.linspace(-1.0, 1.0, rows)
    return pd.DataFrame(
        {
            "date": idx,
            "prob_up_h20": np.clip(0.5 + 0.2 * x, 0.01, 0.99),
            "prob_up_h5": np.clip(0.5 + 0.1 * np.sin(np.arange(rows)), 0.01, 0.99),
            "confidence": 0.4 + (np.arange(rows) % 10) * 0.03,
            "tail_reward_risk_score_h20": -0.2 + x * 0.1,
            "forward_gain_h20": np.where((np.arange(rows) % 5) < 3, 0.01, -0.01),
            "forward_mdd_h20": -0.05,
            "is_live": False,
        }
    )


class LightGbmBaselineTests(unittest.TestCase):
    def test_evaluate_lightgbm_baseline_uses_purged_folds(self) -> None:
        module = _load_module()

        result = module.evaluate_lightgbm_baseline(
            _panel(),
            n_splits=3,
            test_size=20,
            purge=5,
            min_train_size=30,
        )

        self.assertIn("aggregate", result)
        self.assertEqual(3, len(result["folds"]))
        for fold in result["folds"]:
            self.assertEqual(5, fold["purge_rows"])
            self.assertIn("model_brier", fold)
            self.assertIn("baseline_brier", fold)
        self.assertIn(result["promotion_decision"], {"research_only", "candidate_for_deeper_ablation"})

    def test_feature_builder_excludes_forward_labels(self) -> None:
        module = _load_module()

        features = module._feature_frame(_panel(), "forward_gain_h20")

        self.assertIn("prob_up_h20", features.columns)
        self.assertNotIn("forward_mdd_h20", features.columns)
        self.assertNotIn("forward_gain_h20", features.columns)

    def test_attach_fourier_price_features_from_duckdb(self) -> None:
        module = _load_module()
        panel = _panel(90)
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                rows = [
                    ("00631L.TW", str(row.date()), float(30.0 + i * 0.1 + np.sin(i / 3.0)))
                    for i, row in enumerate(panel["date"])
                ]
                con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)
            finally:
                con.close()

            out = module.attach_fourier_price_features(
                panel,
                db_path=db_path,
                ticker="00631L.TW",
                windows=(16,),
            )

        cols = [col for col in out.columns if col.startswith("fft_00631L_TW_16d_")]
        self.assertTrue(cols)
        self.assertIn("fft_00631L_TW_16d_spectral_entropy", out.columns)

    def test_attach_cross_asset_relation_features_from_duckdb(self) -> None:
        module = _load_module()
        panel = _panel(90)
        import tempfile

        tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                rows = []
                for i, row in enumerate(panel["date"]):
                    for j, ticker in enumerate(tickers):
                        rows.append((ticker, str(row.date()), float(20 + j * 10 + i * (0.05 + j * 0.01))))
                con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)
            finally:
                con.close()

            out = module.attach_cross_asset_relation_features(
                panel,
                db_path=db_path,
                windows=(5,),
            )

        self.assertIn("rel_5d_lev_base_corr", out.columns)
        self.assertIn("rel_5d_inverse_conflict", out.columns)


if __name__ == "__main__":
    unittest.main()
