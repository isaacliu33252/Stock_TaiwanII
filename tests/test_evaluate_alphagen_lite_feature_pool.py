from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_alphagen_lite_feature_pool.py"
    spec = importlib.util.spec_from_file_location("_test_alphagen_lite_feature_pool", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pruning_recommendation_marks_never_selected_features_as_prune_candidates() -> None:
    module = _load_module()
    folds = [
        {
            "consensus_d_features_selected_by_full_pool": [],
            "full_pool_test_ic": 0.10,
            "pre_pruned_pool_test_ic": 0.10,
        },
        {
            "consensus_d_features_selected_by_full_pool": ["above_ma20"],
            "full_pool_test_ic": 0.25,
            "pre_pruned_pool_test_ic": 0.05,
        },
    ]

    recommendation = module.build_pruning_recommendation(
        folds,
        ["volume_ratio_5", "above_ma20"],
    )

    assert recommendation["status"] == "research_only"
    assert recommendation["active_allocation_impact"] == "none"
    assert recommendation["feature_actions"]["volume_ratio_5"]["action"] == "prune_candidate"
    assert recommendation["feature_actions"]["above_ma20"]["action"] == "monitor"
    assert "above_ma20" in recommendation["monitor_features"]


def test_evaluate_pool_vs_manual_pruning_includes_research_only_recommendation() -> None:
    module = _load_module()
    idx = pd.date_range("2024-01-02", periods=120, freq="B")
    rng = np.random.default_rng(11)
    base = pd.Series(np.sin(np.arange(120) / 6.0), index=idx)
    target = base + pd.Series(rng.standard_normal(120) * 0.05, index=idx)
    features = pd.DataFrame(
        {
            "strong_signal": target + rng.standard_normal(120) * 0.02,
            "above_ma20": target + rng.standard_normal(120) * 0.03,
            "volume_ratio_5": rng.standard_normal(120),
            "n225_x_twii_ret": rng.standard_normal(120),
            "noise": rng.standard_normal(120),
        },
        index=idx,
    )

    report = module.evaluate_pool_vs_manual_pruning(
        features,
        target,
        n_splits=3,
        gap=2,
        capacity=3,
        ic_lower_bound=0.03,
        mutual_ic_threshold=0.95,
    )

    assert "pruning_recommendation" in report
    assert report["pruning_recommendation"]["active_allocation_impact"] == "none"
    assert set(report["aggregate"]["consensus_d_features_checked"]) == {
        "above_ma20",
        "volume_ratio_5",
        "n225_x_twii_ret",
    }
    assert len(report["folds"]) == 3
