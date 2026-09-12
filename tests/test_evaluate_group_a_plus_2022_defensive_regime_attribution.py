from __future__ import annotations

import pandas as pd

# Codex 2026-08-14: attribution-only tests. These helpers must not imply live
# strategy promotion or target-weight writes.
from scripts.evaluate.evaluate_group_a_plus_2022_defensive_regime_attribution import (
    _defensive_variants,
    _episode_rows,
    _move_weight,
    _regime_variants,
)


def test_move_weight_transfers_source_to_destination() -> None:
    weights = _move_weight({"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3}, "00679B.TWO", "cash")

    assert weights["00679B.TWO"] == 0.0
    assert weights["cash"] == 0.6
    assert round(sum(weights.values()), 6) == 1.0


def test_defensive_variants_include_bond_isolation_cases() -> None:
    base = {
        "golden1": {"0050.TW": 0.5, "cash": 0.5},
        "group_a_plus_defensive": {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3},
        "group_a_plus_recovery": {"0050.TW": 0.7, "00631L.TW": 0.1, "cash": 0.2},
        "group_a_plus_recovery_00631l_boost": {"0050.TW": 0.7, "00631L.TW": 0.1, "cash": 0.2},
    }

    variants = _defensive_variants(base)

    assert variants["defensive_bond_to_cash"]["group_a_plus_defensive"]["cash"] == 0.6
    assert variants["defensive_bond_to_0050"]["group_a_plus_defensive"]["0050.TW"] == 0.7
    assert variants["recovery_replaced_by_defensive"]["group_a_plus_recovery"]["00679B.TWO"] == 0.3


def test_regime_variants_replace_only_target_regimes() -> None:
    index = pd.date_range("2026-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "execution_regime": [
                "golden1",
                "group_a_plus_defensive",
                "group_a_plus_recovery",
                "golden1",
            ]
        },
        index=index,
    )

    variants = _regime_variants(frame)

    assert variants["defensive_to_golden1"].tolist() == ["golden1", "golden1", "group_a_plus_recovery", "golden1"]
    assert variants["recovery_to_defensive_regime"].tolist() == [
        "golden1",
        "group_a_plus_defensive",
        "group_a_plus_defensive",
        "golden1",
    ]
    assert frame["execution_regime"].tolist()[1] == "group_a_plus_defensive"


def test_episode_rows_summarize_contiguous_non_golden_periods() -> None:
    index = pd.date_range("2026-01-01", periods=5)
    frame = pd.DataFrame(
        {
            "execution_regime": [
                "golden1",
                "group_a_plus_defensive",
                "group_a_plus_recovery",
                "golden1",
                "group_a_plus_defensive",
            ],
            "portfolio_value": [100.0, 100.0, 110.0, 120.0, 115.0],
            "drawdown": [0.0, -0.1, -0.05, 0.0, -0.2],
            "ma_gap": [0.1, -0.1, -0.02, 0.1, -0.2],
            "total_risk_score": [1, 6, 3, 1, 7],
            "tail_risk_score": [0, 1, 0, 0, 2],
        },
        index=index,
    )
    prices = pd.DataFrame(
        {
            "0050.TW": [10.0, 10.0, 11.0, 12.0, 12.0],
            "00631L.TW": [10.0] * 5,
            "00632R.TW": [10.0] * 5,
            "00679B.TWO": [10.0, 10.0, 9.0, 9.0, 8.0],
        },
        index=index,
    )

    rows = _episode_rows(frame, prices)

    assert len(rows) == 2
    assert rows[0]["start"] == "2026-01-02"
    assert rows[0]["end"] == "2026-01-03"
    assert round(rows[0]["portfolio_return"], 6) == 0.1
    assert round(rows[0]["ticker_total_returns"]["00679B.TWO"], 6) == -0.1
