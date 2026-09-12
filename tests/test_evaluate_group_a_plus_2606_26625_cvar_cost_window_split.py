from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_2606_26625_cvar_cost_window_split import (
    _simulate_monthly_rebalanced,
    _variants,
)


def test_variants_move_removed_exposure_to_cash() -> None:
    latest = {
        "0050.TW": 0.47,
        "00631L.TW": 0.10,
        "00632R.TW": 0.16,
        "00679B.TWO": 0.0,
        "cash": 0.27,
    }

    variants = _variants(latest)

    assert variants["no_00631l_to_cash"]["00631L.TW"] == 0.0
    assert variants["no_00631l_to_cash"]["cash"] == 0.37
    assert variants["no_00632r_to_cash"]["00632R.TW"] == 0.0
    assert variants["no_00632r_to_cash"]["cash"] == pytest.approx(0.43)
    assert variants["no_letf_to_cash"]["00631L.TW"] == 0.0
    assert variants["no_letf_to_cash"]["00632R.TW"] == 0.0


def test_monthly_rebalanced_simulation_charges_rebalance_cost() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="D")
    returns = pd.DataFrame(
        {
            "0050.TW": [0.10, -0.02, 0.03, 0.00],
            "00631L.TW": [0.20, -0.04, 0.06, 0.00],
            "00632R.TW": [-0.10, 0.02, -0.03, 0.00],
            "00679B.TWO": [0.00, 0.00, 0.00, 0.00],
        },
        index=index,
    )

    simulated, turnover = _simulate_monthly_rebalanced(
        returns,
        {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
        rebalance_every=2,
        cost_bps=10.0,
    )

    assert len(simulated) == 4
    assert turnover.iloc[0] == 0.0
    assert turnover.iloc[2] > 0.0
    assert simulated.iloc[2] < 0.5 * 0.03 + 0.2 * 0.06
