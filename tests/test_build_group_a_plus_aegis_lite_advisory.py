from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "build_group_a_plus_aegis_lite_advisory.py"
    spec = importlib.util.spec_from_file_location("_aegis_lite_advisory", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prices() -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-01", periods=90)
    trend = np.linspace(0.0, 0.18, len(idx))
    noisy_bad = np.array([0.03 * (-1) ** i for i in range(len(idx))]).cumsum()
    return pd.DataFrame(
        {
            "0050.TW": 100.0 * (1.0 + trend),
            "00631L.TW": 30.0 * (1.0 + trend * 0.4 + noisy_bad * 0.02),
            "00632R.TW": 10.0 * (1.0 - trend * 0.2),
            "00679B.TWO": 25.0 * (1.0 + np.linspace(0.0, 0.01, len(idx))),
        },
        index=idx,
    )


def test_vam_gate_rejects_00631l_when_vam_lags_0050() -> None:
    module = _load_module()
    vam = module.calculate_vam(_prices(), as_of="latest", lookback_days=63)

    gate = module.build_vam_gate(vam, max_00631l_to_0050_vol_ratio=2.25)

    assert gate["allow_00631l_add"] is False
    assert "00631L_vam_below_0050" in gate["reasons"]


def test_sortino_reference_weights_stay_near_active_weights() -> None:
    module = _load_module()
    base = {
        "0050.TW": 0.53,
        "00631L.TW": 0.07,
        "00632R.TW": 0.0,
        "00679B.TWO": 0.0,
        "cash": 0.40,
    }

    report = module.sortino_reference_weights(
        _prices(),
        base,
        as_of="latest",
        lookback_days=63,
        max_abs_deviation=0.15,
        max_single_asset_weight=0.85,
        turnover_penalty=0.02,
    )

    assert report["status"] in {"available", "fallback_to_active_weights"}
    assert abs(sum(report["reference_weights"].values()) - 1.0) < 1e-9
    for asset, delta in report["weight_delta"].items():
        assert abs(delta) <= 0.1500001 or asset == "cash"


def test_build_advisory_is_research_only() -> None:
    module = _load_module()
    base = {
        "0050.TW": 0.53,
        "00631L.TW": 0.07,
        "00632R.TW": 0.0,
        "00679B.TWO": 0.0,
        "cash": 0.40,
    }

    report = module.build_advisory(
        prices=_prices(),
        base_weights=base,
        signal={"strategy_id": "unit_strategy"},
        signal_path=Path("signal.json"),
        as_of="latest",
        vam_lookback_days=63,
        sortino_lookback_days=63,
        max_00631l_to_0050_vol_ratio=2.25,
        max_abs_deviation=0.15,
        max_single_asset_weight=0.85,
        turnover_penalty=0.02,
    )

    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["changes_golden1_0531"] is False
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["promotion_ready"] is False
