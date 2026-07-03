from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_ncf_advisory_policy.py"
    spec = importlib.util.spec_from_file_location("_test_evaluate_ncf_advisory_policy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _advisory() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    return pd.DataFrame(
        {
            "market_direction": ["UP", "DOWN", "DOWN", "UP"],
            "agreement_score": [0.80, 0.90, 0.40, 0.80],
            "conflict_flag": [False, False, True, False],
        },
        index=idx,
    )


def test_policy_exposure_uses_rule_before_execution_lag() -> None:
    module = _load_module()
    exposure = module.policy_exposure(_advisory(), "high_agreement_bearish_reduce_20")

    assert exposure.tolist() == [1.0, 0.8, 1.0, 1.0]


def test_simulate_policy_uses_prior_day_advisory_for_today_exposure() -> None:
    module = _load_module()
    prices = pd.DataFrame(
        {"0050.TW": [100.0, 90.0, 81.0, 89.1]},
        index=_advisory().index,
    )

    values, detail, result = module.simulate_policy(
        _advisory(),
        prices,
        "bearish_reduce_20",
        initial_value=100.0,
    )

    assert detail["0050_exposure"].tolist() == [1.0, 1.0, 0.8, 0.8]
    assert values.iloc[-1] > 100.0 * (89.1 / 100.0)
    assert result["turnover_proxy"] == pytest.approx(0.2)


def test_evaluate_policies_adds_baseline_deltas() -> None:
    module = _load_module()
    prices = pd.DataFrame(
        {"0050.TW": [100.0, 90.0, 81.0, 89.1]},
        index=_advisory().index,
    )

    results, _ = module.evaluate_policies(
        _advisory(),
        prices,
        ["baseline_0050", "bearish_reduce_20"],
        initial_value=100.0,
    )

    assert "delta_total_return_vs_baseline" in results["bearish_reduce_20"]
    assert results["bearish_reduce_20"]["avg_0050_exposure"] < results["baseline_0050"]["avg_0050_exposure"]
