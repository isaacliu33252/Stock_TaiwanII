from __future__ import annotations

import pandas as pd

# Codex 2026-08-14: regression tests for the research-only dual-regime
# defensive cash-floor shadow. No live strategy promotion is implied.
from scripts.evaluate.sweep_group_a_plus_dual_regime_defensive_cash_floor import (
    DualCashFloorVariant,
    _dual_masks,
    _with_dual_regime,
)


def _variant() -> DualCashFloorVariant:
    return DualCashFloorVariant(
        name="case",
        crash_cash_floor=0.55,
        slow_cash_floor=0.40,
        crash_ma_gap_max=-0.05,
        crash_drawdown_max=-0.05,
        crash_total_risk_min=4,
        crash_tail_risk_min=1,
        slow_ma_gap_max=0.0,
        slow_drawdown_max=-0.08,
        slow_total_risk_min=6,
        slow_tail_risk_min=1,
        slow_vol_ratio_min=0.8,
    )


def test_dual_masks_prioritize_crash_over_slow() -> None:
    index = pd.date_range("2026-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "execution_regime": [
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "golden1",
            ],
            "ma_gap": [-0.06, -0.01, 0.01, -0.10],
            "exit_momentum": [-0.01, -0.01, -0.01, -0.01],
            "drawdown": [-0.09, -0.09, -0.09, -0.30],
            "total_risk_score": [7, 7, 7, 7],
            "tail_risk_score": [2, 0, 0, 2],
            "realized_vol_ratio_20_60": [1.0, 0.9, 0.7, 1.0],
        },
        index=index,
    )

    crash, slow = _dual_masks(frame, _variant())

    assert crash.tolist() == [True, False, False, False]
    assert slow.tolist() == [False, True, False, False]


def test_slow_mask_requires_vol_ratio_floor() -> None:
    index = pd.date_range("2026-01-01", periods=2)
    frame = pd.DataFrame(
        {
            "execution_regime": ["group_a_plus_defensive", "group_a_plus_defensive"],
            "ma_gap": [-0.01, -0.01],
            "exit_momentum": [-0.01, -0.01],
            "drawdown": [-0.09, -0.09],
            "total_risk_score": [7, 7],
            "tail_risk_score": [0, 0],
            "realized_vol_ratio_20_60": [0.79, 0.80],
        },
        index=index,
    )

    crash, slow = _dual_masks(frame, _variant())

    assert crash.tolist() == [False, False]
    assert slow.tolist() == [False, True]


def test_with_dual_regime_uses_separate_shadow_regimes() -> None:
    index = pd.date_range("2026-01-01", periods=3)
    frame = pd.DataFrame(
        {
            "execution_regime": ["group_a_plus_defensive", "group_a_plus_defensive", "golden1"],
            "ma_gap": [-0.06, -0.01, -0.10],
            "exit_momentum": [-0.01, -0.01, -0.01],
            "drawdown": [-0.09, -0.09, -0.30],
            "total_risk_score": [7, 7, 7],
            "tail_risk_score": [2, 0, 2],
            "realized_vol_ratio_20_60": [1.0, 0.9, 1.0],
        },
        index=index,
    )

    regimes, activity = _with_dual_regime(frame, _variant())

    assert regimes.tolist() == [
        "shadow_dual_cash_floor_crash_case",
        "shadow_dual_cash_floor_slow_case",
        "golden1",
    ]
    assert activity == {"crash_active_days": 1, "slow_active_days": 1, "total_active_days": 2}
    assert frame["execution_regime"].tolist() == ["group_a_plus_defensive", "group_a_plus_defensive", "golden1"]
