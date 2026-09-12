"""Unit tests for evaluate_adaptive_lookback_narrow_lead_shadow.py's pure
logic. evaluate_window()/build_report() are integration-level (need the
real DB / a2118 backtest) and are exercised by the real end-to-end run
recorded in docs/ADAPTIVE_LOOKBACK_NARROW_LEAD_GROUPA_PLUS_20260809.md.
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

from scripts.evaluate.evaluate_adaptive_lookback_narrow_lead_shadow import (
    _apply_add_0050_instead_from_trigger,
    _divergence_series_for_window,
    select_adaptive_window,
)


def _price_series(values: list[float], start: str = "2026-01-01") -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


class TestDivergenceSeriesForWindow:
    def test_zero_divergence_when_tsmc_and_0050_move_identically(self):
        close_2330 = _price_series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
        close_0050 = close_2330.copy()
        div, ret2330 = _divergence_series_for_window(close_2330, close_0050, window=5, tsmc_weight=0.5831)
        assert div.dropna().abs().max() < 1e-9

    def test_positive_divergence_when_tsmc_outruns_basket(self):
        close_2330 = _price_series([100.0 * (1.05**i) for i in range(10)])
        close_0050 = _price_series([100.0 * (1.01**i) for i in range(10)])
        div, ret2330 = _divergence_series_for_window(close_2330, close_0050, window=5, tsmc_weight=0.5831)
        assert div.dropna().iloc[-1] > 0.0
        assert ret2330.dropna().iloc[-1] > 0.0


class TestSelectAdaptiveWindow:
    def test_returns_valid_window_for_every_date(self):
        n = 400
        rng = np.random.default_rng(42)
        close_2330 = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=pd.date_range("2024-01-01", periods=n))
        close_0050 = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=close_2330.index)
        close_631l = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.02, n)), index=close_2330.index)
        chosen, div, ret2330 = select_adaptive_window(
            close_2330, close_631l, close_0050, close_2330.index,
            candidate_windows=(20, 40, 60), eval_lookback=30,
        )
        assert len(chosen) == n
        assert set(chosen.unique()).issubset({20, 40, 60})
        assert len(div) == n
        assert len(ret2330) == n

    def test_uses_default_window_before_enough_history(self):
        n = 50
        rng = np.random.default_rng(1)
        close_2330 = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=pd.date_range("2024-01-01", periods=n))
        close_0050 = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=close_2330.index)
        close_631l = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.02, n)), index=close_2330.index)
        chosen, _div, _ret = select_adaptive_window(
            close_2330, close_631l, close_0050, close_2330.index,
            candidate_windows=(20, 40, 60), eval_lookback=30,
        )
        # not enough history yet (eval_lookback=30, min_valid=10) -> default (middle) window
        assert chosen.iloc[0] == 40


class TestApplyAdd0050InsteadFromTrigger:
    def test_redirects_increment_only_on_triggered_increasing_days(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        targets = pd.DataFrame(
            {
                "0050.TW": [0.5, 0.5, 0.4, 0.4],
                "00631L.TW": [0.0, 0.1, 0.2, 0.2],
                "00632R.TW": [0.0, 0.0, 0.0, 0.0],
                "00679B.TWO": [0.0, 0.0, 0.0, 0.0],
                "cash": [0.5, 0.4, 0.4, 0.4],
            },
            index=dates,
        )
        trigger = pd.Series([False, True, True, False], index=dates)
        adjusted, meta = _apply_add_0050_instead_from_trigger(targets, trigger)
        # day1: 00631L increases 0.0->0.1 and triggered -> redirected to 0050
        assert adjusted.loc[dates[1], "00631L.TW"] == pytest.approx(0.0)
        assert adjusted.loc[dates[1], "0050.TW"] == pytest.approx(0.6)
        # day2: 00631L increases again (0.0 [held] -> 0.2) and triggered -> redirected again
        assert adjusted.loc[dates[2], "00631L.TW"] == pytest.approx(0.0)
        assert meta["event_count"] == 2

    def test_no_redirect_when_not_triggered(self):
        dates = pd.date_range("2026-01-01", periods=3, freq="D")
        targets = pd.DataFrame(
            {
                "0050.TW": [0.5, 0.5, 0.5],
                "00631L.TW": [0.0, 0.2, 0.2],
                "00632R.TW": [0.0, 0.0, 0.0],
                "00679B.TWO": [0.0, 0.0, 0.0],
                "cash": [0.5, 0.3, 0.3],
            },
            index=dates,
        )
        trigger = pd.Series([False, False, False], index=dates)
        adjusted, meta = _apply_add_0050_instead_from_trigger(targets, trigger)
        pd.testing.assert_frame_equal(adjusted, targets)
        assert meta["event_count"] == 0
