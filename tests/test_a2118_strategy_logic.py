from __future__ import annotations

import pandas as pd
import pytest

from group_a_plus.runners.a2118 import (
    GOLDEN_LEVERAGE_CAP_REGIME,
    NCF_LB_REGIME,
    _apply_golden_leverage_cap_overlay,
    _apply_late_bull_overlay,
    _golden_leverage_cap_weights,
    _golden_rebound_recapture_weights,
    _late_bull_hedge_weights,
    _recovery_boost_weights,
)


def _assert_weights(result: dict[str, float], expected: dict[str, float]) -> None:
    for ticker, weight in expected.items():
        assert result[ticker] == pytest.approx(weight)
    assert sum(result.values()) == pytest.approx(1.0)


def test_late_bull_hedge_weights_halve_00631l_into_0050_and_normalize() -> None:
    base = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}

    result = _late_bull_hedge_weights(base)

    _assert_weights(result, {"0050.TW": 0.60, "00631L.TW": 0.10, "cash": 0.30})


def test_late_bull_hedge_weights_respect_intensity_bounds() -> None:
    base = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}

    _assert_weights(_late_bull_hedge_weights(base, intensity=-1.0), base)
    _assert_weights(_late_bull_hedge_weights(base, intensity=2.0), {"0050.TW": 0.60, "00631L.TW": 0.10, "cash": 0.30})


def test_rebound_and_recovery_boost_weights_move_0050_into_00631l() -> None:
    base = {"0050.TW": 0.60, "00631L.TW": 0.10, "cash": 0.30}

    rebound = _golden_rebound_recapture_weights(base, boost_fraction=0.25)
    recovery = _recovery_boost_weights(base, boost_fraction=0.50)

    _assert_weights(rebound, {"0050.TW": 0.45, "00631L.TW": 0.25, "cash": 0.30})
    _assert_weights(recovery, {"0050.TW": 0.30, "00631L.TW": 0.40, "cash": 0.30})


def test_golden_leverage_cap_weights_cap_00631l_and_move_excess_to_0050() -> None:
    base = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}

    result = _golden_leverage_cap_weights(base, max_00631l_weight=0.15)

    _assert_weights(result, {"0050.TW": 0.55, "00631L.TW": 0.15, "cash": 0.30})


def test_late_bull_overlay_changes_only_triggering_golden1_days() -> None:
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    regime = pd.Series(["golden1", "golden1", "group_a_plus_defensive"], index=idx)
    ma_gap = pd.Series([0.12, 0.09, 0.20], index=idx)
    panel = pd.DataFrame(
        {
            "prob_up_h20": [0.40, 0.40, 0.20],
            "confidence": [0.60, 0.60, 0.90],
            "prob_up_h5": [0.30, 0.30, 0.30],
        },
        index=idx,
    )

    modified, info = _apply_late_bull_overlay(
        regime,
        panel,
        ma_gap,
        ma_gap_min=0.10,
        h20_max=0.45,
        conf_min=0.55,
    )

    assert modified.tolist() == [NCF_LB_REGIME, "golden1", "group_a_plus_defensive"]
    assert info["late_bull_trigger_days"] == 1
    assert info["late_bull_trigger_events"][0]["date"] == "2026-01-02"


def test_late_bull_overlay_reports_missing_panel_columns_without_changing_regime() -> None:
    idx = pd.to_datetime(["2026-01-02"])
    regime = pd.Series(["golden1"], index=idx)
    panel = pd.DataFrame({"prob_up_h20": [0.20]}, index=idx)

    modified, info = _apply_late_bull_overlay(regime, panel, pd.Series([0.20], index=idx))

    assert modified.tolist() == ["golden1"]
    assert info["late_bull_trigger_days"] == 0
    assert info["skipped_reason"] == "missing_required_panel_columns"
    assert info["missing_columns"] == ["confidence"]


def test_golden_leverage_cap_overlay_requires_tail_vol_and_drawdown() -> None:
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    regime = pd.Series(["golden1", "golden1", "group_a_plus_recovery"], index=idx)
    frame = pd.DataFrame(
        {
            "tail_risk_score": [1, 1, 5],
            "realized_vol_ratio_20_60": [1.30, 1.10, 2.00],
            "drawdown": [-0.09, -0.09, -0.20],
        },
        index=idx,
    )

    modified, info = _apply_golden_leverage_cap_overlay(
        regime,
        frame,
        tail_risk_score_min=1,
        realized_vol_ratio_min=1.25,
        drawdown_max=-0.08,
    )

    assert modified.tolist() == [GOLDEN_LEVERAGE_CAP_REGIME, "golden1", "group_a_plus_recovery"]
    assert info["golden_leverage_cap_days"] == 1
    assert info["golden_leverage_cap_events"][0]["date"] == "2026-01-02"
