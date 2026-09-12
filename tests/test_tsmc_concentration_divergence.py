"""Unit tests for group_a_plus/integrations/tsmc_concentration_divergence.py's
pure functions. top5_breadth_snapshot() needs the real DB (individual-stock
price history) and is exercised via the real end-to-end runs recorded in
docs/TSMC_CONCENTRATION_DIVERGENCE_GROUPA_PLUS_20260809.md rather than here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.tsmc_concentration_divergence import (
    classify_narrow_lead,
    concentration_divergence,
    ex_tsmc_return,
    tsmc_contribution_to_0050,
)


class TestExTsmcReturn:
    def test_matches_daily_signal_formula(self):
        # ret_0050=0.05, ret_2330=0.10, weight=0.5831
        # ex = (0.05 - 0.5831*0.10) / (1-0.5831)
        result = ex_tsmc_return(0.05, 0.10, tsmc_weight=0.5831)
        expected = (0.05 - 0.5831 * 0.10) / (1.0 - 0.5831)
        assert result == pytest.approx(expected)

    def test_zero_when_tsmc_and_0050_move_identically(self):
        # if the whole basket moves like TSMC, ex-TSMC should also equal that move
        result = ex_tsmc_return(0.03, 0.03, tsmc_weight=0.5831)
        assert result == pytest.approx(0.03)

    def test_none_at_weight_one(self):
        assert ex_tsmc_return(0.05, 0.10, tsmc_weight=1.0) is None


class TestTsmcContribution:
    def test_scales_by_weight(self):
        assert tsmc_contribution_to_0050(0.10, tsmc_weight=0.5831) == pytest.approx(0.05831)

    def test_negative_return_negative_contribution(self):
        assert tsmc_contribution_to_0050(-0.10, tsmc_weight=0.5831) == pytest.approx(-0.05831)


class TestConcentrationDivergence:
    def test_zero_when_no_divergence(self):
        # TSMC and the rest of the basket move identically -> zero divergence
        result = concentration_divergence(0.03, 0.03, tsmc_weight=0.5831)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_positive_when_tsmc_outruns_basket(self):
        # TSMC up 10%, 0050 (blended) only up 2% -> ex-TSMC basket is weak,
        # divergence should be strongly positive (TSMC minus the weak rest)
        result = concentration_divergence(0.10, 0.02, tsmc_weight=0.5831)
        assert result > 0.05

    def test_negative_when_basket_outruns_tsmc(self):
        # TSMC flat, 0050 up strongly -> the rest of the basket is doing the
        # work, divergence should be negative
        result = concentration_divergence(0.0, 0.05, tsmc_weight=0.5831)
        assert result < 0.0


class TestClassifyNarrowLead:
    def test_true_when_tsmc_up_basket_down_and_gap_wide(self):
        # ret_2330=0.05 (>0), ret_ex_tsmc=-0.01 (<=0), gap vs 0050 (0.02) = 0.03 > 0.01
        assert classify_narrow_lead(0.05, 0.02, -0.01) is True

    def test_false_when_ex_tsmc_also_positive(self):
        assert classify_narrow_lead(0.05, 0.04, 0.02) is False

    def test_false_when_tsmc_itself_not_positive(self):
        assert classify_narrow_lead(-0.01, -0.02, -0.03) is False

    def test_false_when_gap_too_narrow(self):
        # TSMC 0.03, 0050 0.028 -> gap only 0.002, below the 0.01 threshold
        assert classify_narrow_lead(0.03, 0.028, -0.005) is False

    def test_false_on_missing_inputs(self):
        assert classify_narrow_lead(None, 0.02, -0.01) is False
        assert classify_narrow_lead(0.05, None, -0.01) is False
        assert classify_narrow_lead(0.05, 0.02, None) is False
