from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_group_a_plus_monte_carlo_stress.py"
    spec = importlib.util.spec_from_file_location("_test_monte_carlo_stress", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_target_weights_from_signal_adds_missing_cash() -> None:
    module = _load_module()
    weights = module.target_weights_from_signal(
        {
            "target_weights": {
                "0050.TW": 0.70,
                "00631L.TW": 0.10,
                "00632R.TW": 0.0,
                "00679B.TWO": 0.0,
            }
        }
    )

    assert weights["cash"] == pytest.approx(0.20)


def test_portfolio_daily_returns_uses_latest_weights() -> None:
    module = _load_module()
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 101.0, 99.99],
            "00631L.TW": [50.0, 51.0, 49.98],
            "00632R.TW": [10.0, 9.9, 10.0],
            "00679B.TWO": [30.0, 30.0, 30.0],
        },
        index=idx,
    )

    returns = module.portfolio_daily_returns(prices, {"0050.TW": 0.7, "00631L.TW": 0.1, "cash": 0.2})

    assert returns.iloc[0] == pytest.approx(0.009)
    assert returns.iloc[1] == pytest.approx(-0.009)


def test_simulate_monte_carlo_is_reproducible() -> None:
    module = _load_module()
    daily = pd.Series([0.01, -0.02, 0.005, 0.0])

    first = module.simulate_monte_carlo(daily, initial_value=100.0, horizon_days=5, n_paths=1000, seed=7)
    second = module.simulate_monte_carlo(daily, initial_value=100.0, horizon_days=5, n_paths=1000, seed=7)

    assert first["terminal_value"]["median"] == pytest.approx(second["terminal_value"]["median"])
    assert 0.0 <= first["path_return"]["prob_loss"] <= 1.0
