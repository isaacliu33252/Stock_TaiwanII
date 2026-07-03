from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_lightgbm_advisory_backtest.py"
    spec = importlib.util.spec_from_file_location("_test_lightgbm_advisory_backtest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    return pd.DataFrame({"execution_regime": ["golden1", "golden1", "golden1", "group_a_plus_defensive"]}, index=idx)


def _weights() -> dict[str, dict[str, float]]:
    return {
        "golden1": {"0050.TW": 0.7, "00631L.TW": 0.1, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.2},
        "group_a_plus_defensive": {
            "0050.TW": 0.4,
            "00631L.TW": 0.0,
            "00632R.TW": 0.0,
            "00679B.TWO": 0.3,
            "cash": 0.3,
        },
    }


class LightGbmAdvisoryBacktestTests(unittest.TestCase):
    def test_advisory_weight_frame_uses_prior_day_oos_probability(self) -> None:
        module = _load_module()
        probs = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
                "oos_prob_up": [0.20, 0.90, 0.20],
            }
        )

        out = module.advisory_weight_frame(
            _frame(),
            _weights(),
            probs,
            down_threshold=0.45,
            trim_fraction=0.5,
        )

        self.assertEqual(0.0, out.loc[pd.Timestamp("2026-01-02"), "trim_fraction_applied"])
        self.assertEqual(0.5, out.loc[pd.Timestamp("2026-01-05"), "trim_fraction_applied"])
        self.assertAlmostEqual(0.05, out.loc[pd.Timestamp("2026-01-05"), "weight_00631L.TW"])
        self.assertAlmostEqual(0.25, out.loc[pd.Timestamp("2026-01-05"), "weight_cash"])
        self.assertEqual(0.0, out.loc[pd.Timestamp("2026-01-06"), "trim_fraction_applied"])
        self.assertEqual(0.0, out.loc[pd.Timestamp("2026-01-07"), "trim_fraction_applied"])

    def test_dynamic_weight_curve_rebalances_when_weights_change(self) -> None:
        module = _load_module()
        frame = _frame()
        weights = pd.DataFrame(index=frame.index)
        weights["weight_0050.TW"] = [0.7, 0.7, 0.65, 0.4]
        weights["weight_00631L.TW"] = [0.1, 0.1, 0.05, 0.0]
        weights["weight_00632R.TW"] = 0.0
        weights["weight_00679B.TWO"] = [0.0, 0.0, 0.0, 0.3]
        weights["weight_cash"] = [0.2, 0.2, 0.3, 0.3]
        prices = pd.DataFrame(
            {
                "0050.TW": [100.0, 101.0, 99.0, 100.0],
                "00631L.TW": [50.0, 51.0, 49.0, 50.0],
                "00632R.TW": [10.0, 10.0, 10.0, 10.0],
                "00679B.TWO": [20.0, 20.1, 20.2, 20.3],
            },
            index=frame.index,
        )

        curve, execution = module.simulate_dynamic_weight_curve(
            prices,
            weights,
            initial_value=1000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            equity_etf_sell_tax=0.0,
        )

        self.assertEqual(len(frame), len(curve))
        self.assertEqual(3, execution["rebalance_count"])
        self.assertGreater(curve.iloc[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
