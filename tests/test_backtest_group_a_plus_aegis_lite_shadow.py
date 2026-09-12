from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "backtest_group_a_plus_aegis_lite_shadow.py"
    spec = importlib.util.spec_from_file_location("_aegis_lite_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prices() -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-02", periods=160)
    choppy_decay = 1.0 - np.linspace(0.0, 0.10, len(idx)) + 0.03 * np.sin(np.arange(len(idx)) * 0.9)
    return pd.DataFrame(
        {
            "0050.TW": 100.0 * (1.0 + np.linspace(0.0, 0.30, len(idx))),
            "00631L.TW": 30.0 * choppy_decay,
            "00632R.TW": 10.0 * (1.0 - np.linspace(0.0, 0.08, len(idx))),
            "00679B.TWO": 25.0 * (1.0 + np.linspace(0.0, 0.02, len(idx))),
        },
        index=idx,
    )


def _baseline_weights(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "0050.TW": 0.53,
            "00631L.TW": 0.10,
            "00632R.TW": 0.0,
            "00679B.TWO": 0.0,
            "cash": 0.37,
            "execution_regime": "golden1",
        },
        index=index,
    )


def test_build_shadow_weights_can_block_00631l() -> None:
    module = _load_module()
    prices = _prices()
    baseline = _baseline_weights(prices.index)

    shadow, meta = module.build_shadow_weights(
        prices,
        baseline,
        vam_lookback_days=63,
        sortino_lookback_days=63,
        max_00631l_to_0050_vol_ratio=2.25,
        max_abs_deviation=0.15,
        max_single_asset_weight=0.85,
        turnover_penalty=0.02,
        sortino_reopt_frequency="monthly",
    )

    assert len(shadow) > 0
    assert meta["vam_block_days"] > 0
    assert float(shadow["00631L.TW"].max()) <= 0.25
    assert np.allclose(shadow[["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash"]].sum(axis=1), 1.0)


def test_simulate_weight_curve_reports_costs_and_values() -> None:
    module = _load_module()
    prices = _prices()
    weights = _baseline_weights(prices.index).drop(columns=["execution_regime"])

    curve, execution = module.simulate_weight_curve(prices, weights, initial_value=1_000_000.0)

    assert len(curve) == len(prices)
    assert curve.iloc[0] > 0
    assert execution["rebalance_count"] >= 1
    assert execution["transaction_cost"] >= 0


def test_backtest_report_is_research_only() -> None:
    module = _load_module()
    prices = _prices()
    baseline = _baseline_weights(prices.index)
    shadow = baseline.drop(columns=["execution_regime"]).copy()
    shadow["00631L.TW"] = 0.0
    shadow["0050.TW"] = shadow["0050.TW"] + 0.10

    report, curves = module.build_backtest_report(
        prices=prices,
        baseline_weights=baseline,
        shadow_weights=shadow,
        shadow_metadata={"vam_block_days": 1, "sortino_updates": 1, "event_count": 1, "events_sample": []},
        initial_value=1_000_000.0,
        latest_report={"active_strategy_id": "unit_latest"},
        params={"unit": True},
    )

    assert not curves.empty
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["changes_golden1_0531"] is False
    assert report["decision"]["creates_orders"] is False
