from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from group_a_plus.integrations.cross_asset_relation import (
    build_cross_asset_relation_features,
    cross_asset_relation_feature_columns,
)


class CrossAssetRelationTests(unittest.TestCase):
    def test_build_relation_features(self) -> None:
        idx = pd.date_range("2026-01-02", periods=80, freq="B")
        base = 100 + np.linspace(0, 10, len(idx))
        prices = pd.DataFrame(
            {
                "0050.TW": base,
                "00631L.TW": base * 1.1 + np.sin(np.arange(len(idx))),
                "00632R.TW": 20 - np.linspace(0, 2, len(idx)),
                "00679B.TWO": 30 + np.cos(np.arange(len(idx)) / 4),
            },
            index=idx,
        )

        features = build_cross_asset_relation_features(prices, windows=(5, 20))

        for col in cross_asset_relation_feature_columns(windows=(5, 20)):
            self.assertIn(col, features.columns)
        self.assertTrue(np.isfinite(features.to_numpy()).all())
        self.assertGreater(features["rel_20d_lev_beta_to_base"].abs().sum(), 0.0)

    def test_missing_required_price_column_raises(self) -> None:
        prices = pd.DataFrame({"0050.TW": [1.0, 2.0]})

        with self.assertRaisesRegex(ValueError, "missing price columns"):
            build_cross_asset_relation_features(prices)


if __name__ == "__main__":
    unittest.main()
