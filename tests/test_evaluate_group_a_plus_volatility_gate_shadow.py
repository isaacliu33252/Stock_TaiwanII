from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import (
    _cap_00631l_add,
    _confirmed_high_vol_mask,
    _regime_with_vol_gate,
    _regime_with_confirmed_high_vol_gate,
    _scaled_00631l_to_0050,
)


def test_scaled_00631l_to_0050_preserves_total_weight() -> None:
    weights = _scaled_00631l_to_0050(
        {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
        0.5,
    )

    assert weights["00631L.TW"] == pytest.approx(0.10)
    assert weights["0050.TW"] == pytest.approx(0.70)
    assert weights["cash"] == pytest.approx(0.20)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_cap_00631l_add_moves_only_excess_add_to_0050() -> None:
    target, capped, capped_weight = _cap_00631l_add(
        {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
        {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
    )

    assert capped is True
    assert capped_weight == pytest.approx(0.10)
    assert target["00631L.TW"] == pytest.approx(0.10)
    assert target["0050.TW"] == pytest.approx(0.70)
    assert target["cash"] == pytest.approx(0.20)


def test_cap_00631l_add_allows_reduction() -> None:
    target, capped, capped_weight = _cap_00631l_add(
        {"0050.TW": 0.80, "00631L.TW": 0.05, "cash": 0.15},
        {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
    )

    assert capped is False
    assert capped_weight == 0.0
    assert target["00631L.TW"] == pytest.approx(0.05)


def test_regime_with_vol_gate_only_changes_golden1_high_vol_in_high_only_mode() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    regimes = pd.Series(
        ["golden1", "group_a_plus_defensive", "golden1", "ncf_late_bull_hedge"],
        index=idx,
    )
    gate_frame = pd.DataFrame(
        {
            "volatility_gate": [
                "high_vol_defensive",
                "high_vol_defensive",
                "neutral_vol",
                "high_vol_defensive",
            ]
        },
        index=idx,
    )

    out = _regime_with_vol_gate(regimes, gate_frame, mode="high_only")

    assert out.iloc[0] == "golden1_vol_gate_high"
    assert out.iloc[1] == "group_a_plus_defensive"
    assert out.iloc[2] == "golden1"
    assert out.iloc[3] == "ncf_late_bull_hedge"


def test_regime_with_vol_gate_maps_neutral_only_in_tiered_mode() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    regimes = pd.Series(["golden1", "golden1", "golden1"], index=idx)
    gate_frame = pd.DataFrame(
        {"volatility_gate": ["low_vol_participation", "neutral_vol", "high_vol_defensive"]},
        index=idx,
    )

    out = _regime_with_vol_gate(regimes, gate_frame, mode="tiered")

    assert out.iloc[0] == "golden1"
    assert out.iloc[1] == "golden1_vol_gate_neutral"
    assert out.iloc[2] == "golden1_vol_gate_high"


def test_confirmed_high_vol_requires_risk_and_ncf_confirmation() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    regimes = pd.Series(["golden1", "golden1", "golden1", "group_a_plus_defensive"], index=idx)
    gate_frame = pd.DataFrame(
        {"volatility_gate": ["high_vol_defensive", "high_vol_defensive", "high_vol_defensive", "high_vol_defensive"]},
        index=idx,
    )
    frame = pd.DataFrame({"total_risk_score": [6, 5, 7, 9]}, index=idx)
    panel = pd.DataFrame(
        {
            "prob_up_h20": [0.40, 0.40, 0.80, 0.20],
            "prob_fwd_mdd_gt5_h20": [0.20, 0.20, 0.60, 0.90],
        },
        index=idx,
    )

    mask = _confirmed_high_vol_mask(regimes, gate_frame, frame, panel)
    out = _regime_with_confirmed_high_vol_gate(regimes, gate_frame, frame, panel)

    assert mask.tolist() == [True, False, True, False]
    assert out.iloc[0] == "golden1_vol_gate_high_confirmed"
    assert out.iloc[1] == "golden1"
    assert out.iloc[2] == "golden1_vol_gate_high_confirmed"
    assert out.iloc[3] == "group_a_plus_defensive"
