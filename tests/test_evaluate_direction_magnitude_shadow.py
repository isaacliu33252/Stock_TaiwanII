from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_direction_magnitude_shadow.py"
    spec = importlib.util.spec_from_file_location("_test_direction_magnitude_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _panel(rows: int = 90) -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=rows, freq="B")
    returns = []
    for i in range(rows):
        sign = 1.0 if i % 4 in {1, 2} else -1.0
        returns.append(sign * (0.004 + (i % 7) * 0.001))
    return pd.DataFrame(
        {
            "prob_up_h20": [0.35 + (i % 10) * 0.03 for i in range(rows)],
            "forward_gain_h20": returns,
        },
        index=idx,
    )


def _ohlcv(rows: int = 90) -> dict[str, pd.DataFrame]:
    idx = pd.date_range("2026-01-02", periods=rows, freq="B")
    base = pd.DataFrame(
        {
            "0050.TW": [100.0 + i * 0.4 for i in range(rows)],
            "00631L.TW": [50.0 + i * 0.5 for i in range(rows)],
            "00632R.TW": [20.0 - i * 0.03 for i in range(rows)],
            "00679B.TWO": [30.0 + (i % 5) * 0.1 for i in range(rows)],
        },
        index=idx,
    )
    return {
        "open": base * 0.995,
        "high": base * 1.01,
        "low": base * 0.99,
        "close": base,
        "volume": base * 1000.0,
    }


def test_build_direction_magnitude_dataset_returns_aligned_targets() -> None:
    module = _load_module()

    features, direction, magnitude, signed_return = module.build_direction_magnitude_dataset(
        _panel(50),
        _ohlcv(50),
        lookback=5,
    )

    assert len(features) == len(direction) == len(magnitude) == len(signed_return)
    assert "prob_up_h20" in features.columns
    assert set(direction.unique()).issubset({0, 1})
    assert (magnitude >= 0.0).all()
    assert (magnitude == signed_return.abs()).all()


def test_clip_by_train_percentile_caps_large_magnitude() -> None:
    module = _load_module()
    clipped = module._clip_by_train_percentile(
        values=[-1.0, 0.02, 0.50],
        train_magnitude=pd.Series([0.01, 0.02, 0.03, 0.04]),
        percentile=75,
    )

    assert clipped[0] == pytest.approx(0.0)
    assert clipped[1] == pytest.approx(0.02)
    assert clipped[2] <= 0.04


def test_evaluate_direction_magnitude_models_reports_shadow_decision() -> None:
    module = _load_module()
    features, direction, magnitude, signed_return = module.build_direction_magnitude_dataset(
        _panel(100),
        _ohlcv(100),
        lookback=5,
    )

    result = module.evaluate_direction_magnitude_models(
        features,
        direction,
        magnitude,
        signed_return,
        n_splits=3,
        gap=2,
        magnitude_clip_percentile=90,
    )

    aggregate = result["aggregate"]
    assert aggregate["baseline"]["feature"] == "prob_up_h20"
    assert aggregate["direction_model"]["model"] == "hist_gradient_boosting_classifier"
    assert aggregate["magnitude_model"]["model"] == "gradient_boosting_regressor_huber"
    assert aggregate["active_allocation_impact"] == "none"
    assert aggregate["promotion_decision"] in {"research_only", "candidate_for_deeper_ablation"}
    assert "signed_return_residual_p10" in aggregate["combined_signed_return"]
