"""Unit tests for evaluate_cross_market_lead_lag_relative_return_shadow.py's
pure functions. walk_forward_relative_return_model()/build_report() are
integration-level (need the real DB) and are exercised by the real
end-to-end run recorded in
docs/CROSS_MARKET_LEAD_LAG_RELATIVE_RETURN_GROUPA_PLUS_20260809.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_cross_market_lead_lag_relative_return_shadow import (
    _directional_accuracy,
    _r2,
    build_relative_return_targets,
)


class TestBuildRelativeReturnTargets:
    def test_00631l_relative_target_is_return_spread(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        target_close = pd.DataFrame(
            {
                "00631L.TW": [100.0, 110.0, 121.0, 121.0],
                "0050.TW": [50.0, 51.0, 51.0, 51.0],
            },
            index=dates,
        )
        out = build_relative_return_targets(target_close)
        # day0->day1: 00631L +10%, 0050 +2% -> relative = +8%
        assert out["target_rel_00631l_vs_0050_ret1d_fwd"].iloc[0] == pytest.approx(0.08)

    def test_2330_relative_target_uses_ex_tsmc_formula(self):
        dates = pd.date_range("2026-01-01", periods=3, freq="D")
        target_close = pd.DataFrame(
            {
                "2330.TW": [100.0, 100.0, 100.0],  # flat -> 0% fwd return
                "0050.TW": [50.0, 51.0, 51.0],  # +2% fwd return on day0
            },
            index=dates,
        )
        w = 0.5831
        out = build_relative_return_targets(target_close, tsmc_weight=w)
        fwd_2330 = 0.0
        fwd_0050 = 0.02
        fwd_ex_tsmc = (fwd_0050 - w * fwd_2330) / (1.0 - w)
        expected = fwd_2330 - fwd_ex_tsmc
        assert out["target_rel_2330_vs_0050_ex_tsmc_ret1d_fwd"].iloc[0] == pytest.approx(expected)

    def test_missing_columns_produce_empty_frame(self):
        target_close = pd.DataFrame({"2330.TW": [100.0, 101.0]}, index=pd.date_range("2026-01-01", periods=2))
        out = build_relative_return_targets(target_close)
        assert out.empty or out.shape[1] == 0


class TestR2:
    def test_perfect_prediction_is_one(self):
        y = np.array([0.01, -0.02, 0.03, -0.01])
        assert _r2(y, y) == pytest.approx(1.0)

    def test_mean_prediction_is_zero(self):
        y = np.array([0.01, -0.02, 0.03, -0.01])
        pred = np.full_like(y, y.mean())
        assert _r2(y, pred) == pytest.approx(0.0, abs=1e-9)

    def test_worse_than_mean_is_negative(self):
        y = np.array([0.01, -0.02, 0.03, -0.01])
        pred = -y * 5.0
        assert _r2(y, pred) < 0.0


class TestDirectionalAccuracy:
    def test_all_correct_signs(self):
        y = np.array([0.01, -0.02, 0.03])
        pred = np.array([0.001, -0.5, 2.0])
        assert _directional_accuracy(y, pred) == pytest.approx(1.0)

    def test_all_wrong_signs(self):
        y = np.array([0.01, -0.02, 0.03])
        pred = np.array([-0.001, 0.5, -2.0])
        assert _directional_accuracy(y, pred) == pytest.approx(0.0)

    def test_ignores_zero_actuals(self):
        y = np.array([0.0, 0.0])
        pred = np.array([1.0, -1.0])
        assert _directional_accuracy(y, pred) is None
