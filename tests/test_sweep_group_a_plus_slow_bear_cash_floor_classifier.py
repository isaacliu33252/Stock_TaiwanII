from __future__ import annotations

import pandas as pd

# Codex 2026-08-14: regression tests for the research-only slow-bear classifier
# shadow. These tests do not authorize live target writes.
from scripts.evaluate.sweep_group_a_plus_slow_bear_cash_floor_classifier import (
    SlowBearVariant,
    _defensive_age,
    _ret20,
    _slow_bear_mask,
    _with_classifier_regime,
)


def _variant() -> SlowBearVariant:
    return SlowBearVariant(
        name="case",
        crash_cash_floor=0.55,
        slow_cash_floor=0.45,
        def_age_min=2,
        ma_gap_max=0.0,
        drawdown_max=-0.05,
        ret20_max=0.02,
        ma_gap_neg_window=3,
        ma_gap_neg_ratio_min=0.6,
        risk_lookback=2,
        total_risk_min=4,
    )


def test_defensive_age_resets_outside_defensive() -> None:
    regime = pd.Series(["golden1", "group_a_plus_defensive", "group_a_plus_defensive", "golden1"])

    assert _defensive_age(regime).tolist() == [0, 1, 2, 0]


def test_ret20_uses_compounded_daily_returns() -> None:
    index = pd.date_range("2026-01-01", periods=6)
    frame = pd.DataFrame({"return_0050_1d": [0.01] * 6}, index=index)

    result = _ret20(frame)

    assert round(float(result.iloc[-1]), 6) == round((1.01**6) - 1.0, 6)


def test_slow_bear_mask_requires_age_recovery_failure_and_risk() -> None:
    index = pd.date_range("2026-01-01", periods=5)
    frame = pd.DataFrame(
        {
            "execution_regime": [
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "golden1",
            ],
            "ma_gap": [-0.01, -0.01, -0.01, -0.06, -0.01],
            "exit_momentum": [-0.01, -0.01, -0.01, -0.01, -0.01],
            "drawdown": [-0.06, -0.06, -0.06, -0.08, -0.20],
            "return_0050_1d": [-0.005, -0.005, -0.005, -0.005, -0.005],
            "total_risk_score": [3, 4, 4, 4, 9],
            "tail_risk_score": [0, 0, 0, 1, 2],
        },
        index=index,
    )

    crash, slow = _slow_bear_mask(frame, _variant())

    assert crash.tolist() == [False, False, False, True, False]
    assert slow.tolist() == [False, True, True, False, False]


def test_with_classifier_regime_keeps_shadow_labels_separate() -> None:
    index = pd.date_range("2026-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "execution_regime": [
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "golden1",
            ],
            "ma_gap": [-0.01, -0.01, -0.06, -0.01],
            "exit_momentum": [-0.01, -0.01, -0.01, -0.01],
            "drawdown": [-0.06, -0.06, -0.08, -0.20],
            "return_0050_1d": [-0.005, -0.005, -0.005, -0.005],
            "total_risk_score": [4, 4, 4, 9],
            "tail_risk_score": [0, 0, 1, 2],
        },
        index=index,
    )

    regimes, activity = _with_classifier_regime(frame, _variant())

    assert regimes.tolist() == [
        "group_a_plus_defensive",
        "shadow_slow_bear_cash_floor_case",
        "shadow_slow_bear_crash_floor_case",
        "golden1",
    ]
    assert activity == {"crash_active_days": 1, "slow_active_days": 1, "total_active_days": 2}
