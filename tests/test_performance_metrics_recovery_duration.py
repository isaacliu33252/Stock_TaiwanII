from __future__ import annotations

import numpy as np

from backtesting.performance_metrics import calculate_recovery_duration


def test_recovery_duration_counts_days_from_trough_to_new_high() -> None:
    # peak=110 at idx1, trough=90 at idx3, recovers to >=110 at idx6 -> 3 days after trough
    equity = np.array([100.0, 110.0, 100.0, 90.0, 95.0, 105.0, 110.0, 112.0])

    assert calculate_recovery_duration(equity) == 3


def test_recovery_duration_returns_none_when_never_recovered() -> None:
    equity = np.array([100.0, 110.0, 90.0, 95.0, 100.0])

    assert calculate_recovery_duration(equity) is None


def test_recovery_duration_zero_when_no_drawdown() -> None:
    equity = np.array([100.0, 101.0, 102.0, 103.0])

    assert calculate_recovery_duration(equity) == 0


def test_recovery_duration_handles_short_series() -> None:
    assert calculate_recovery_duration(np.array([100.0])) is None
    assert calculate_recovery_duration(np.array([])) is None
