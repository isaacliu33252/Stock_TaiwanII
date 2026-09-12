"""Unit tests for scripts/evaluate/build_group_a_plus_golden1_crash_window_protection_review.py's
pure functions -- no DB/network access, synthetic data only."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts" / "evaluate"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_group_a_plus_golden1_crash_window_protection_review import (  # noqa: E402
    _window_stats,
    detect_drawdown_episodes,
)


def _flat_then_crash_then_recover(n_flat=100, n_crash=20, n_recover=100, crash_depth=0.15):
    dates = pd.bdate_range("2020-01-01", periods=n_flat + n_crash + n_recover)
    flat = np.full(n_flat, 100.0)
    crash = np.linspace(100.0, 100.0 * (1.0 - crash_depth), n_crash)
    recover = np.linspace(crash[-1], 100.0, n_recover)
    prices = np.concatenate([flat, crash, recover])
    return pd.Series(prices, index=dates)


def test_window_stats_computes_return_and_max_drawdown():
    values = pd.Series([100.0, 110.0, 90.0, 95.0])

    stats = _window_stats(values)

    assert stats["n"] == 4
    assert stats["return"] == pytest.approx((95.0 / 100.0) - 1.0)
    # peak 110 -> trough 90 within the window
    assert stats["max_drawdown"] == pytest.approx((90.0 / 110.0) - 1.0)


def test_window_stats_returns_none_for_too_few_rows():
    assert _window_stats(pd.Series([100.0, 101.0])) is None


def test_detect_drawdown_episodes_finds_the_single_crash():
    close = _flat_then_crash_then_recover(crash_depth=0.15)

    episodes = detect_drawdown_episodes(close, threshold=-0.08, min_gap_days=20)

    assert len(episodes) == 1
    label, peak, trough = episodes[0]
    peak_ts, trough_ts = pd.Timestamp(peak), pd.Timestamp(trough)
    assert peak_ts < trough_ts
    # trough should fall within the crash leg, not the flat or recovery legs
    crash_start = close.index[100]
    crash_end = close.index[120]
    assert crash_start <= trough_ts <= crash_end


def test_detect_drawdown_episodes_ignores_shallow_dips():
    close = _flat_then_crash_then_recover(crash_depth=0.03)

    episodes = detect_drawdown_episodes(close, threshold=-0.08, min_gap_days=20)

    assert episodes == []


def test_detect_drawdown_episodes_merges_nearby_legs():
    dates = pd.bdate_range("2020-01-01", periods=80)
    prices = np.full(80, 100.0)
    prices[10:20] = np.linspace(100.0, 85.0, 10)  # first leg down
    prices[20:25] = np.linspace(85.0, 95.0, 5)  # brief partial bounce (still not a new high)
    prices[25:35] = np.linspace(95.0, 80.0, 10)  # second leg down, close in time to the first
    prices[35:] = np.linspace(80.0, 100.0, 45)
    close = pd.Series(prices, index=dates)

    episodes = detect_drawdown_episodes(close, threshold=-0.08, min_gap_days=20)

    assert len(episodes) == 1
