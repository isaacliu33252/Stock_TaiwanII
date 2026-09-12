from __future__ import annotations

import numpy as np
import pytest

from scripts.evaluate.evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound import (
    solve_min_cvar_weights,
)


def test_solver_prefers_low_vol_asset_when_return_floor_is_low() -> None:
    rng = np.random.default_rng(0)
    n = 500
    low_vol = rng.normal(0.0002, 0.002, n)
    high_vol = rng.normal(0.0004, 0.02, n)
    scenarios = np.column_stack([low_vol, high_vol])

    solved = solve_min_cvar_weights(scenarios, alpha=0.95, min_mean_return=float(low_vol.mean()))

    assert solved["feasible"] is True
    weights = solved["weights"]
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert weights[0] > weights[1]


def test_solver_shifts_toward_high_return_asset_when_floor_is_high() -> None:
    # Deterministic scenarios (no sampling noise): asset 0 has a fixed small
    # positive return every day; asset 1 alternates a large gain/loss but has
    # a strictly higher mean. A return floor above asset 0's mean is only
    # reachable by allocating to asset 1.
    n = 500
    low_vol = np.full(n, 0.0002)
    high_vol = np.where(np.arange(n) % 2 == 0, 0.02, -0.015)
    scenarios = np.column_stack([low_vol, high_vol])
    assert high_vol.mean() > low_vol.mean()
    floor = 0.9 * high_vol.mean() + 0.1 * low_vol.mean()

    solved = solve_min_cvar_weights(scenarios, alpha=0.95, min_mean_return=floor)

    assert solved["feasible"] is True
    weights = solved["weights"]
    assert weights[1] > weights[0]


def test_solver_infeasible_when_return_floor_unreachable() -> None:
    rng = np.random.default_rng(2)
    n = 200
    asset = rng.normal(0.0001, 0.001, n)
    scenarios = np.column_stack([asset])

    solved = solve_min_cvar_weights(scenarios, alpha=0.95, min_mean_return=1.0)

    assert solved["feasible"] is False
