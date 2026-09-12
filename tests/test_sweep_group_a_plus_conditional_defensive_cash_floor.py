from __future__ import annotations

import pandas as pd

# Codex 2026-08-14: regression tests for the research-only conditional cash
# floor shadow. These tests intentionally do not authorize live target writes.
from scripts.evaluate.sweep_group_a_plus_conditional_defensive_cash_floor import (
    CashFloorVariant,
    _activation_mask,
    _raise_cash_floor,
    _with_variant_regime,
)


def test_raise_cash_floor_reduces_risky_weights_pro_rata() -> None:
    adjusted = _raise_cash_floor(
        {"0050.TW": 0.4, "00631L.TW": 0.1, "00679B.TWO": 0.2, "cash": 0.3},
        0.45,
    )

    assert adjusted["cash"] == 0.45
    assert round(adjusted["0050.TW"] / adjusted["00631L.TW"], 6) == 4.0
    assert round(sum(adjusted.values()), 6) == 1.0


def test_activation_mask_requires_defensive_and_weak_trend() -> None:
    index = pd.date_range("2026-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "execution_regime": [
                "golden1",
                "group_a_plus_defensive",
                "group_a_plus_defensive",
                "group_a_plus_defensive",
            ],
            "ma_gap": [-0.05, -0.03, 0.01, -0.03],
            "exit_momentum": [-0.01, -0.01, -0.01, 0.01],
            "drawdown": [-0.12, -0.02, -0.12, -0.12],
            "total_risk_score": [8, 7, 7, 7],
            "tail_risk_score": [2, 0, 0, 0],
        },
        index=index,
    )
    variant = CashFloorVariant("case", 0.45, -0.02, 0.0, -0.05, 6, 1)

    mask = _activation_mask(frame, variant)

    assert mask.tolist() == [False, True, False, False]


def test_with_variant_regime_adds_shadow_regime_without_mutating_base() -> None:
    index = pd.date_range("2026-01-01", periods=3)
    frame = pd.DataFrame(
        {
            "execution_regime": ["group_a_plus_defensive", "group_a_plus_defensive", "golden1"],
            "ma_gap": [-0.03, 0.01, -0.03],
            "exit_momentum": [-0.01, -0.01, -0.01],
            "drawdown": [-0.08, -0.08, -0.08],
            "total_risk_score": [7, 7, 7],
            "tail_risk_score": [0, 0, 0],
        },
        index=index,
    )
    variant = CashFloorVariant("case", 0.45, -0.02, 0.0, -0.05, 6, 1)

    regimes, active_days, transitions = _with_variant_regime(frame, variant)

    assert active_days == 1
    assert regimes.tolist() == ["shadow_defensive_cash_floor_case", "group_a_plus_defensive", "golden1"]
    assert frame["execution_regime"].tolist() == ["group_a_plus_defensive", "group_a_plus_defensive", "golden1"]
    assert transitions == [
        {"date": "2026-01-01", "action": "enter"},
        {"date": "2026-01-02", "action": "exit"},
    ]
