"""Unit tests for evaluate_adaptive_review_interval_shadow.py's pure logic.
evaluate_window()/build_report() are integration-level (need the real DB /
a2118 backtest) and are exercised by the real end-to-end run recorded in
docs/ADAPTIVE_REVIEW_INTERVAL_GROUPA_PLUS_20260809.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_adaptive_review_interval_shadow import (
    classify_review_interval,
    simulate_adaptive_review,
)


def _row(**kw) -> pd.Series:
    base = {"execution_regime": "golden1", "ma_gap": 0.05, "drawdown": -0.01, "tail_risk_score": 0.0}
    base.update(kw)
    return pd.Series(base)


class TestClassifyReviewInterval:
    def test_recovery_regime_always_daily(self):
        interval, label = classify_review_interval(_row(execution_regime="group_a_plus_recovery"))
        assert interval == 1
        assert label == "crash_or_recovery"

    def test_deep_drawdown_forces_daily_even_in_golden1(self):
        # drawdown within crash_dd_buffer (0.03) of the -0.11 dd_threshold
        interval, label = classify_review_interval(_row(execution_regime="golden1", drawdown=-0.09))
        assert interval == 1
        assert label == "crash_or_recovery"

    def test_high_tail_risk_score_forces_daily(self):
        interval, label = classify_review_interval(_row(execution_regime="golden1", tail_risk_score=6))
        assert interval == 1
        assert label == "crash_or_recovery"

    def test_stable_golden1_gets_3_day_review(self):
        interval, label = classify_review_interval(
            _row(execution_regime="golden1", ma_gap=0.05, drawdown=-0.01, tail_risk_score=0)
        )
        assert interval == 3
        assert label == "stable_golden1"

    def test_golden1_near_defensive_threshold_stays_daily(self):
        # ma_gap close to ENTRY_MA_GAP (-0.003), not comfortably above it
        interval, label = classify_review_interval(
            _row(execution_regime="golden1", ma_gap=0.0, drawdown=-0.01, tail_risk_score=0)
        )
        assert interval == 1
        assert label == "golden1_near_threshold"

    def test_stable_defensive_far_from_reentry_gets_5_day_review(self):
        # ma_gap well below EXIT_MA_GAP (0.010) minus buffer (0.02) -> -0.05 or lower
        interval, label = classify_review_interval(
            _row(execution_regime="group_a_plus_defensive", ma_gap=-0.05, drawdown=-0.02, tail_risk_score=0)
        )
        assert interval == 5
        assert label == "stable_defensive_far_from_threshold"

    def test_defensive_near_reentry_threshold_stays_daily(self):
        interval, label = classify_review_interval(
            _row(execution_regime="group_a_plus_defensive", ma_gap=0.005, drawdown=-0.02, tail_risk_score=0)
        )
        assert interval == 1
        assert label == "defensive_near_threshold"

    def test_unknown_regime_conservative_default(self):
        interval, label = classify_review_interval(_row(execution_regime="ncf_late_bull_hedge"))
        assert interval == 1
        assert label == "other_regime_conservative_default"


class TestSimulateAdaptiveReview:
    def test_freezes_weights_between_reviews(self):
        dates = pd.date_range("2026-01-01", periods=6, freq="D")
        frame = pd.DataFrame(
            {
                "execution_regime": ["golden1"] * 6,
                "ma_gap": [0.05] * 6,
                "drawdown": [-0.01] * 6,
                "tail_risk_score": [0.0] * 6,
            },
            index=dates,
        )
        targets = pd.DataFrame(
            {
                "0050.TW": [0.3, 0.3, 0.3, 0.5, 0.5, 0.5],
                "00631L.TW": [0.0] * 6,
                "00632R.TW": [0.0] * 6,
                "00679B.TWO": [0.0] * 6,
                "cash": [0.7, 0.7, 0.7, 0.5, 0.5, 0.5],
            },
            index=dates,
        )
        adjusted, log = simulate_adaptive_review(frame, targets)
        # stable golden1 -> 3-day review: reviews on day0 and day3
        assert adjusted.loc[dates[0], "0050.TW"] == pytest.approx(0.3)
        assert adjusted.loc[dates[1], "0050.TW"] == pytest.approx(0.3)  # frozen, even though baseline changed
        assert adjusted.loc[dates[2], "0050.TW"] == pytest.approx(0.3)  # still frozen
        assert adjusted.loc[dates[3], "0050.TW"] == pytest.approx(0.5)  # re-reviewed, picks up new target
        assert len(log) == 2

    def test_crash_regime_reviews_every_day(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        frame = pd.DataFrame(
            {
                "execution_regime": ["group_a_plus_recovery"] * 4,
                "ma_gap": [0.05] * 4,
                "drawdown": [-0.01] * 4,
                "tail_risk_score": [0.0] * 4,
            },
            index=dates,
        )
        targets = pd.DataFrame(
            {
                "0050.TW": [0.3, 0.4, 0.5, 0.6],
                "00631L.TW": [0.0] * 4,
                "00632R.TW": [0.0] * 4,
                "00679B.TWO": [0.0] * 4,
                "cash": [0.7, 0.6, 0.5, 0.4],
            },
            index=dates,
        )
        adjusted, log = simulate_adaptive_review(frame, targets)
        pd.testing.assert_frame_equal(adjusted, targets)
        assert len(log) == 4
