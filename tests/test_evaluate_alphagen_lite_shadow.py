from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_alphagen_lite_shadow.py"
    spec = importlib.util.spec_from_file_location("_test_alphagen_lite_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _leaves(rows: int = 80) -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=rows, freq="B")
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "prob_up_h20": 0.5 + 0.05 * np.sin(np.arange(rows) / 5.0),
            "h20_prob_up": 0.5 + 0.05 * np.cos(np.arange(rows) / 5.0),
            "confidence": 0.6 + 0.02 * rng.standard_normal(rows),
            "prob_fwd_mdd_gt5_h20": 0.3 + 0.02 * rng.standard_normal(rows),
            "prob_fwd_gain_gt5_h20": 0.35 + 0.02 * rng.standard_normal(rows),
            "tail_reward_risk_score_h20": rng.standard_normal(rows) * 0.1,
            "close_0050.TW": 100.0 + np.cumsum(rng.standard_normal(rows) * 0.5),
            "close_00631L.TW": 50.0 + np.cumsum(rng.standard_normal(rows) * 0.8),
            "close_00632R.TW": 20.0 - np.cumsum(rng.standard_normal(rows) * 0.1),
            "close_00679B.TWO": 30.0 + 0.05 * rng.standard_normal(rows),
            "volume_0050.TW": 1_000_000 + rng.standard_normal(rows) * 10_000,
            "volume_00631L.TW": 500_000 + rng.standard_normal(rows) * 5_000,
            "volume_00632R.TW": 400_000 + rng.standard_normal(rows) * 5_000,
            "volume_00679B.TWO": 200_000 + rng.standard_normal(rows) * 2_000,
        },
        index=idx,
    )


def test_generate_candidates_covers_all_leaves_and_operators() -> None:
    module = _load_module()
    leaves = _leaves(60)

    candidates = module.generate_candidates(leaves)

    assert "raw__prob_up_h20" in candidates.columns
    assert "delta5__close_0050.TW" in candidates.columns
    assert "mean_bias20__close_00631L.TW" in candidates.columns
    assert "corr10__0050.TW_x_00631L.TW" in candidates.columns
    assert len(candidates) == len(leaves)


def test_greedy_pool_select_respects_capacity_and_diversity() -> None:
    module = _load_module()
    idx = pd.date_range("2026-01-02", periods=120, freq="B")
    rng = np.random.default_rng(1)
    target = pd.Series(rng.standard_normal(120), index=idx)
    signal = target * 2.0 + rng.standard_normal(120) * 0.1
    features = pd.DataFrame(
        {
            "raw__strong_signal": signal,
            "raw__near_duplicate": signal + rng.standard_normal(120) * 0.05,
            "raw__pure_noise_1": rng.standard_normal(120),
            "raw__pure_noise_2": rng.standard_normal(120),
        },
        index=idx,
    )

    selected, weights, means, stds = module.greedy_pool_select(
        features, target, capacity=3, ic_lower_bound=0.05, mutual_ic_threshold=0.7
    )

    assert "raw__strong_signal" in selected
    assert "raw__near_duplicate" not in selected
    assert len(selected) <= 3
    assert len(weights) == len(selected)


def test_evaluate_reports_research_decision() -> None:
    module = _load_module()
    idx = pd.date_range("2026-01-02", periods=150, freq="B")
    rng = np.random.default_rng(7)
    target = pd.Series(rng.standard_normal(150) * 0.02, index=idx)
    features = pd.DataFrame(
        {
            "raw__prob_up_h20": 0.5 + target * 3.0 + rng.standard_normal(150) * 0.05,
            "raw__noise_a": rng.standard_normal(150),
            "raw__noise_b": rng.standard_normal(150),
        },
        index=idx,
    )

    result = module.evaluate(
        features,
        target,
        n_splits=3,
        gap=2,
        capacity=2,
        ic_lower_bound=0.05,
        mutual_ic_threshold=0.7,
    )

    assert "baseline" in result["aggregate"]
    assert "alphagen_lite_pool" in result["aggregate"]
    assert result["aggregate"]["promotion_decision"] in {
        "research_only",
        "candidate_for_deeper_ablation",
    }
    assert len(result["folds"]) == 3


def test_ic_helpers_handle_constant_series() -> None:
    module = _load_module()
    idx = pd.date_range("2026-01-02", periods=20, freq="B")
    constant = pd.Series([1.0] * 20, index=idx)
    varying = pd.Series(range(20), index=idx, dtype=float)

    assert module._ic(constant, varying) is None
    assert module._rank_ic(constant, varying) is None
