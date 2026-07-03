from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_stock_rnn_relative_window_shadow.py"
    spec = importlib.util.spec_from_file_location("_test_stock_rnn_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _panel(rows: int = 70) -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "prob_up_h20": [0.35 + (i % 10) * 0.03 for i in range(rows)],
            "forward_gain_h20": [0.01 if i % 3 else -0.01 for i in range(rows)],
        },
        index=idx,
    )


def _prices(rows: int = 70) -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "0050.TW": [100.0 + i for i in range(rows)],
            "00631L.TW": [50.0 + i * 0.8 for i in range(rows)],
            "00632R.TW": [20.0 - i * 0.05 for i in range(rows)],
            "00679B.TWO": [30.0 + (i % 5) * 0.1 for i in range(rows)],
        },
        index=idx,
    )


def _ohlcv(rows: int = 70) -> dict[str, pd.DataFrame]:
    close = _prices(rows)
    return {
        "open": close * 0.995,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": close * 1000.0,
    }


def test_build_relative_window_features_uses_window_normalization() -> None:
    module = _load_module()
    features, target = module.build_relative_window_features(_panel(40), _prices(40), lookback=5)

    assert "0050.TW_rel_00" in features.columns
    assert "0050.TW_rel_04" in features.columns
    assert features.iloc[0]["0050.TW_rel_00"] == pytest.approx(0.0)
    assert features.iloc[0]["0050.TW_rel_04"] == pytest.approx(4.0 / 100.0)
    assert len(features) == len(target)


def test_build_ohlcv_relative_window_features_adds_volume_and_range() -> None:
    module = _load_module()
    features, target = module.build_ohlcv_relative_window_features(_panel(40), _ohlcv(40), lookback=5)

    assert "0050.TW_close_rel_00" in features.columns
    assert "0050.TW_range_rel_04" in features.columns
    assert "0050.TW_volume_rel_04" in features.columns
    assert "0050.TW_gap_abs_max" in features.columns
    assert features.iloc[0]["0050.TW_close_rel_00"] == pytest.approx(0.0)
    assert len(features) == len(target)


def test_evaluate_models_reports_research_decision() -> None:
    module = _load_module()
    features, target = module.build_relative_window_features(_panel(90), _prices(90), lookback=5)

    result = module.evaluate_models(features, target, n_splits=3, gap=2)

    assert "baseline" in result["aggregate"]
    assert "relative_window_logistic" in result["aggregate"]
    assert "relative_window_hgb" in result["aggregate"]
    assert result["aggregate"]["promotion_decision"] in {
        "research_only",
        "candidate_for_deeper_ablation",
    }


def test_evaluate_models_can_include_baseline_feature() -> None:
    module = _load_module()
    features, target = module.build_relative_window_features(_panel(90), _prices(90), lookback=5)

    result = module.evaluate_models(features, target, n_splits=3, gap=2, include_baseline_feature=True)

    assert result["aggregate"]["baseline"]["included_in_shadow_models"] is True
    assert "relative_window_hgb" in result["aggregate"]


def test_build_relative_window_features_rejects_short_lookback() -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="lookback"):
        module.build_relative_window_features(_panel(), _prices(), lookback=1)


def test_build_ohlcv_relative_window_features_rejects_missing_field() -> None:
    module = _load_module()
    data = _ohlcv()
    data.pop("volume")

    with pytest.raises(ValueError, match="volume"):
        module.build_ohlcv_relative_window_features(_panel(), data, lookback=5)
