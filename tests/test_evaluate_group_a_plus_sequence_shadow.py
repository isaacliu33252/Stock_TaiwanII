from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_group_a_plus_sequence_shadow.py"
    spec = importlib.util.spec_from_file_location("_test_sequence_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _panel(rows: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=rows, freq="B")
    base = pd.Series(range(rows), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "prob_up_h1": 0.45 + (base % 7) * 0.01,
            "prob_up_h5": 0.46 + (base % 5) * 0.01,
            "prob_up_h20": 0.35 + (base % 11) * 0.02,
            "ensemble_prob_up": 0.40 + (base % 9) * 0.015,
            "prob_magnitude": 0.05 + (base % 3) * 0.02,
            "prob_fwd_mdd_gt5_h20": 0.60 - (base % 6) * 0.01,
            "prob_fwd_gain_gt5_h20": 0.30 + (base % 6) * 0.01,
            "tail_reward_risk_score_h20": -0.30 + (base % 8) * 0.03,
            "confidence": 0.10 + (base % 10) * 0.03,
            "forward_gain_h20": [0.01 if i % 3 else -0.01 for i in range(rows)],
            "is_live": False,
        },
        index=idx,
    )


def test_build_sequence_features_adds_lagged_columns() -> None:
    module = _load_module()
    features, target = module.build_sequence_features(_panel())

    assert "prob_up_h20_lag1" in features.columns
    assert "prob_up_h20_roll5_mean" in features.columns
    assert "h1_minus_h20" in features.columns
    assert len(features) == len(target)
    assert set(target.unique()) == {0, 1}


def test_evaluate_shadow_models_reports_baseline_and_models() -> None:
    module = _load_module()
    features, target = module.build_sequence_features(_panel(70))

    result = module.evaluate_shadow_models(features, target, n_splits=3, gap=2)

    assert "baseline" in result["aggregate"]
    assert "lagged_logistic" in result["aggregate"]
    assert "lagged_hgb" in result["aggregate"]
    assert result["aggregate"]["promotion_decision"] in {
        "research_only",
        "candidate_for_deeper_ablation",
    }


def test_build_sequence_features_rejects_missing_label() -> None:
    module = _load_module()
    frame = _panel().drop(columns=["forward_gain_h20"])

    with pytest.raises(ValueError, match="forward_gain_h20"):
        module.build_sequence_features(frame)
