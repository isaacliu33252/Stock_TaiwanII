from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "build_ncf_advisory_panel.py"
    spec = importlib.util.spec_from_file_location("_test_build_ncf_advisory_panel", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _panel(prob_h1: float, prob_h5: float, prob_h20: float) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])
    return pd.DataFrame(
        {
            "prob_up_h1": [prob_h1] * 3,
            "prob_up_h5": [prob_h5] * 3,
            "prob_up_h20": [prob_h20] * 3,
            "ensemble_prob_up": [(prob_h1 + prob_h5 + prob_h20) / 3.0] * 3,
            "confidence": [0.8] * 3,
        },
        index=idx,
    )


def test_build_advisory_panel_detects_consistent_market_up() -> None:
    module = _load_module()
    panel_l = _panel(0.65, 0.70, 0.68)
    panel_r = _panel(0.35, 0.30, 0.32)

    out = module.build_advisory_panel(panel_l, panel_r)

    assert list(out["market_direction"].unique()) == ["UP"]
    assert out["conflict_flag"].eq(False).all()
    assert out["agreement_score"].min() > 0.6


def test_build_advisory_panel_detects_conflict() -> None:
    module = _load_module()
    panel_l = _panel(0.70, 0.70, 0.70)
    panel_r = _panel(0.70, 0.70, 0.70)

    out = module.build_advisory_panel(panel_l, panel_r)

    assert out["conflict_flag"].eq(True).all()
    assert out["agreement_score"].max() < 0.5


def test_add_forward_returns_uses_trading_day_shift() -> None:
    module = _load_module()
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])
    advisory = pd.DataFrame({"market_direction": ["UP", "DOWN", "UP"]}, index=idx)
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 110.0, 121.0],
            "00631L.TW": [50.0, 55.0, 66.0],
        },
        index=idx,
    )

    out = module.add_forward_returns(advisory, prices, horizons=(1,))

    assert round(float(out.loc[idx[0], "fwd_0050.TW_ret_1d"]), 6) == 0.10
    assert round(float(out.loc[idx[1], "fwd_00631L.TW_ret_1d"]), 6) == 0.20
