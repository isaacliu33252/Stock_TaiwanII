from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.integrations.riccati_mv_shadow import MeanVarianceSpec
from scripts.evaluate.evaluate_group_a_plus_riccati_mv_risk_budget_shadow import (
    apply_riccati_mv_caps_to_targets,
    build_confirmation_series,
)


def test_apply_riccati_mv_caps_moves_only_leverage_and_inverse_excess_to_cash() -> None:
    idx = pd.bdate_range("2025-01-02", periods=220)
    r = np.r_[np.full(110, 0.001), np.full(110, -0.001)]
    prices = pd.DataFrame(
        {
            "0050.TW": 100.0 * np.cumprod(1.0 + r),
            "00631L.TW": 80.0 * np.cumprod(1.0 + 2.0 * r),
            "00632R.TW": 20.0 * np.cumprod(1.0 - r),
            "00679B.TWO": np.linspace(30.0, 31.0, len(idx)),
        },
        index=idx,
    )
    target = pd.DataFrame(
        {
            "0050.TW": 0.45,
            "00631L.TW": 0.20,
            "00632R.TW": 0.20,
            "00679B.TWO": 0.0,
            "cash": 0.15,
        },
        index=idx,
    )

    guarded, events = apply_riccati_mv_caps_to_targets(
        prices,
        target,
        spec=MeanVarianceSpec(lookback_days=80, min_observations=40, grid_step=0.05, min_cash=0.20),
    )

    assert not guarded.empty
    assert (guarded[["00631L.TW", "00632R.TW"]] <= target[["00631L.TW", "00632R.TW"]] + 1e-12).all().all()
    assert (guarded["0050.TW"] <= target["0050.TW"] + 1e-12).all()
    assert (guarded["cash"] >= target["cash"] - 1e-12).all()
    assert np.allclose(guarded[["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash"]].sum(axis=1), 1.0)
    assert events


def test_confirmation_gate_can_disable_caps() -> None:
    idx = pd.bdate_range("2025-01-02", periods=180)
    prices = pd.DataFrame(
        {
            "0050.TW": np.linspace(100.0, 105.0, len(idx)),
            "00631L.TW": np.linspace(80.0, 92.0, len(idx)),
            "00632R.TW": np.linspace(20.0, 18.0, len(idx)),
            "00679B.TWO": np.linspace(30.0, 30.5, len(idx)),
        },
        index=idx,
    )
    target = pd.DataFrame(
        {"0050.TW": 0.45, "00631L.TW": 0.20, "00632R.TW": 0.20, "00679B.TWO": 0.0, "cash": 0.15},
        index=idx,
    )
    confirmation = pd.Series(False, index=idx)

    guarded, events = apply_riccati_mv_caps_to_targets(
        prices,
        target,
        spec=MeanVarianceSpec(lookback_days=60, min_observations=30, grid_step=0.10, min_cash=0.20),
        confirmation=confirmation,
    )

    assert events == []
    pd.testing.assert_frame_equal(guarded[target.columns], target)


def test_current_policy_re_evaluation_records_second_pass() -> None:
    idx = pd.bdate_range("2025-01-02", periods=220)
    r = np.r_[np.full(110, 0.001), np.full(110, -0.001)]
    prices = pd.DataFrame(
        {
            "0050.TW": 100.0 * np.cumprod(1.0 + r),
            "00631L.TW": 80.0 * np.cumprod(1.0 + 2.0 * r),
            "00632R.TW": 20.0 * np.cumprod(1.0 - r),
            "00679B.TWO": np.linspace(30.0, 31.0, len(idx)),
        },
        index=idx,
    )
    target = pd.DataFrame(
        {
            "0050.TW": 0.45,
            "00631L.TW": 0.20,
            "00632R.TW": 0.20,
            "00679B.TWO": 0.0,
            "cash": 0.15,
        },
        index=idx,
    )

    guarded, events = apply_riccati_mv_caps_to_targets(
        prices,
        target,
        spec=MeanVarianceSpec(lookback_days=80, min_observations=40, grid_step=0.05, min_cash=0.20),
        re_evaluate_current_policy=True,
    )

    assert events
    assert "current_policy_re_evaluation" in events[-1]
    assert (guarded[["00631L.TW", "00632R.TW"]] <= target[["00631L.TW", "00632R.TW"]] + 1e-12).all().all()
    assert np.allclose(guarded[["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash"]].sum(axis=1), 1.0)


def test_cap_beta_damps_applied_cap() -> None:
    idx = pd.bdate_range("2025-01-02", periods=220)
    r = np.r_[np.full(110, 0.001), np.full(110, -0.001)]
    prices = pd.DataFrame(
        {
            "0050.TW": 100.0 * np.cumprod(1.0 + r),
            "00631L.TW": 80.0 * np.cumprod(1.0 + 2.0 * r),
            "00632R.TW": 20.0 * np.cumprod(1.0 - r),
            "00679B.TWO": np.linspace(30.0, 31.0, len(idx)),
        },
        index=idx,
    )
    target = pd.DataFrame(
        {
            "0050.TW": 0.45,
            "00631L.TW": 0.20,
            "00632R.TW": 0.20,
            "00679B.TWO": 0.0,
            "cash": 0.15,
        },
        index=idx,
    )

    full, _ = apply_riccati_mv_caps_to_targets(
        prices,
        target,
        spec=MeanVarianceSpec(lookback_days=80, min_observations=40, grid_step=0.05, min_cash=0.20),
        cap_tickers=("00631L.TW",),
        cap_beta=1.0,
    )
    half, events = apply_riccati_mv_caps_to_targets(
        prices,
        target,
        spec=MeanVarianceSpec(lookback_days=80, min_observations=40, grid_step=0.05, min_cash=0.20),
        cap_tickers=("00631L.TW",),
        cap_beta=0.5,
    )

    changed = full["00631L.TW"] < target["00631L.TW"]
    assert changed.any()
    first_changed = changed[changed].index[0]
    assert full.loc[first_changed, "00631L.TW"] < half.loc[first_changed, "00631L.TW"] < target.loc[first_changed, "00631L.TW"]
    assert events[-1]["cap_beta"] == 0.5


def test_build_confirmation_series_modes() -> None:
    idx = pd.bdate_range("2026-01-02", periods=3)
    frame = pd.DataFrame(
        {
            "total_risk_score_lookback_max": [2, 5, 6],
            "tail_risk_score": [0, 1, 0],
            "drawdown": [-0.02, -0.09, -0.04],
            "realized_vol_ratio_20_60": [1.0, 1.1, 1.3],
        },
        index=idx,
    )

    total = build_confirmation_series(frame, mode="total_risk", total_risk_min=5, tail_risk_min=1, drawdown_max=-0.08, vol_ratio_min=1.15)
    tail = build_confirmation_series(frame, mode="tail_or_drawdown", total_risk_min=5, tail_risk_min=1, drawdown_max=-0.08, vol_ratio_min=1.15)
    tail_only = build_confirmation_series(frame, mode="tail_only", total_risk_min=5, tail_risk_min=1, drawdown_max=-0.08, vol_ratio_min=1.15)
    strict = build_confirmation_series(frame, mode="tail_drawdown_vol", total_risk_min=5, tail_risk_min=1, drawdown_max=-0.08, vol_ratio_min=1.15)

    assert total.tolist() == [False, True, True]
    assert tail.tolist() == [False, True, False]
    assert tail_only.tolist() == [False, True, False]
    assert strict.tolist() == [False, True, False]
