"""Unit tests for evaluate_adaptive_window_hit_rate_comparison.py's
_hit_rate() helper. build_report() is integration-level (needs the real DB)
and is exercised by the real end-to-end run recorded in
docs/ADAPTIVE_LOOKBACK_NARROW_LEAD_GROUPA_PLUS_20260809.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_adaptive_window_hit_rate_comparison import _hit_rate


class TestHitRate:
    def test_perfect_agreement_is_100pct(self):
        pred = np.array([1.0, -1.0, 1.0, -1.0, 1.0])
        truth = np.array([0.5, -0.5, 0.5, -0.5, 0.5])
        result = _hit_rate(pred, truth, valid_start=0)
        assert result["hit_rate"] == pytest.approx(1.0)
        assert result["n"] == 5

    def test_perfect_disagreement_is_0pct(self):
        pred = np.array([1.0, -1.0, 1.0, -1.0])
        truth = np.array([-0.5, 0.5, -0.5, 0.5])
        result = _hit_rate(pred, truth, valid_start=0)
        assert result["hit_rate"] == pytest.approx(0.0)

    def test_zero_predictions_excluded(self):
        # a zero prediction (no signal that day) should not count toward n
        pred = np.array([1.0, 0.0, -1.0])
        truth = np.array([0.5, 0.5, -0.5])
        result = _hit_rate(pred, truth, valid_start=0)
        assert result["n"] == 2

    def test_empty_returns_none_hit_rate(self):
        result = _hit_rate(np.array([]), np.array([]), valid_start=0)
        assert result["n"] == 0
        assert result["hit_rate"] is None

    def test_valid_start_trims_warmup(self):
        pred = np.array([1.0, 1.0, -1.0, -1.0])
        truth = np.array([-0.5, -0.5, -0.5, -0.5])  # first two are "wrong" warmup rows
        result = _hit_rate(pred, truth, valid_start=2)
        assert result["n"] == 2
        assert result["hit_rate"] == pytest.approx(1.0)

    def test_significance_flag_at_extreme_hit_rate(self):
        rng_pred = np.array([1.0] * 60 + [-1.0] * 40)
        rng_truth = np.array([0.5] * 60 + [-0.5] * 40)
        result = _hit_rate(rng_pred, rng_truth, valid_start=0)
        assert result["hit_rate"] == pytest.approx(1.0)
        assert result["significant_at_5pct"] is True
