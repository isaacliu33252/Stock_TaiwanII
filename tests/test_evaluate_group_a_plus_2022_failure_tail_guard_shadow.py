from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_group_a_plus_2022_failure_and_tail_guard_shadow.py"
    spec = importlib.util.spec_from_file_location("_tail_guard_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame() -> pd.DataFrame:
    idx = pd.bdate_range("2022-01-03", periods=6)
    return pd.DataFrame(
        {
            "portfolio_value": [100.0, 98.0, 95.0, 97.0, 94.0, 96.0],
            "execution_regime": ["golden1", "golden1", "group_a_plus_defensive", "golden1", "golden1", "golden1"],
            "tail_risk_score": [0, 1, 1, 0, 2, 0],
            "total_risk_score": [0, 2, 3, 0, 4, 0],
            "drawdown": [0.0, -0.02, -0.05, -0.03, -0.08, -0.04],
            "ma_gap": [0.02, -0.01, -0.04, 0.01, -0.05, 0.0],
            "return_0050_1d": [0.0, -0.02, -0.03, 0.02, -0.04, 0.01],
            "realized_vol_ratio_20_60": [1.0, 1.1, 1.2, 1.0, 1.5, 1.0],
        },
        index=idx,
    )


def test_tail_guard_proxy_only_changes_golden1_tail_days() -> None:
    module = _load_module()
    guarded, events = module._apply_tail_guard_proxy(_frame(), tail_risk_score_min=1)

    assert guarded.iloc[0] == "golden1"
    assert guarded.iloc[1] == "golden1__tail_no_00631l_add_proxy"
    assert guarded.iloc[2] == "group_a_plus_defensive"
    assert guarded.iloc[4] == "golden1__tail_no_00631l_add_proxy"
    assert len(events) == 2


def test_top_loss_days_include_regime_and_risk_context() -> None:
    module = _load_module()
    losses = module._top_loss_days(_frame(), top_n=2)

    assert len(losses) == 2
    assert losses[0]["portfolio_return"] < 0
    assert "execution_regime" in losses[0]
    assert "tail_risk_score" in losses[0]


def test_zero_00631l_to_0050_preserves_total_weight() -> None:
    module = _load_module()
    weights = module._zero_00631l_to_0050({"0050.TW": 0.5, "00631L.TW": 0.1, "cash": 0.4})

    assert weights["00631L.TW"] == 0.0
    assert weights["0050.TW"] == 0.6
    assert abs(sum(weights.values()) - 1.0) < 1e-12
