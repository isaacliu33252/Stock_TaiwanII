from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_00631l_multisource_crash_risk import (
    FAMILY_STRESS_CONDITIONS,
    _stress_veto_fraction,
    evaluate_family_condition,
    family_condition_flags_for_row,
)


def test_evaluate_family_condition_handles_ge_le_and_missing_values() -> None:
    assert evaluate_family_condition(1.5, ">=", 1.0) is True
    assert evaluate_family_condition(0.5, ">=", 1.0) is False
    assert evaluate_family_condition(-1.5, "<=", -1.0) is True
    assert evaluate_family_condition(-0.5, "<=", -1.0) is False
    assert evaluate_family_condition(None, ">=", 1.0) is False
    assert evaluate_family_condition(float("nan"), ">=", 1.0) is False


def test_family_condition_flags_for_row_matches_thresholds() -> None:
    row = pd.Series(
        {
            "txo_pcr_volume_z20": 1.2,
            "txo_pcr_oi_z20": 0.5,
            "txo_foreign_put_call_net_oi_chg5_z60": np.nan,
        }
    )
    flags = family_condition_flags_for_row(row, "options_tail")

    assert flags == {
        "txo_pcr_volume_z20_ge_1": True,
        "txo_pcr_oi_z20_ge_1": False,
        "txo_foreign_put_call_net_oi_chg5_z60_ge_1": False,
    }


def test_stress_veto_fraction_requires_two_of_three_families() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    columns = {name for family in FAMILY_STRESS_CONDITIONS.values() for (name, _cmp, _thr) in family.values()}
    features = pd.DataFrame(0.0, index=idx, columns=sorted(columns))

    # Row 0: no family active.
    # Row 1: options + liquidity active (2 of 3) -> veto.
    features.loc[idx[1], "txo_pcr_volume_z20"] = 2.0
    features.loc[idx[1], "market_margin_forced_repay_z60"] = 2.0
    # Row 2: only options active (1 of 3) -> no veto.
    features.loc[idx[2], "txo_pcr_volume_z20"] = 2.0

    veto = _stress_veto_fraction(features)

    assert veto.loc[idx[0]] == 0.0
    assert veto.loc[idx[1]] == 1.0
    assert veto.loc[idx[2]] == 0.0


def test_family_stress_conditions_cover_expected_names() -> None:
    assert set(FAMILY_STRESS_CONDITIONS) == {"options_tail", "liquidity_forced_selling", "cross_market_shock"}
    assert len(FAMILY_STRESS_CONDITIONS["options_tail"]) == 3
    assert len(FAMILY_STRESS_CONDITIONS["liquidity_forced_selling"]) == 3
    assert len(FAMILY_STRESS_CONDITIONS["cross_market_shock"]) == 18
