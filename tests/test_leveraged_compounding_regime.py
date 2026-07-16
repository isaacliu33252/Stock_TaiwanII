from __future__ import annotations

import pandas as pd

from group_a_plus.integrations.leveraged_compounding_regime import (
    MEAN_REVERTING,
    TRANSITIONAL,
    TREND_PERSISTENT,
    build_compounding_features,
    classify_compounding_regime,
)


def test_classifies_trend_persistent_when_sequence_features_align() -> None:
    idx = pd.date_range("2026-01-01", periods=2)
    features = pd.DataFrame(
        {
            "rolling_AR1_5d": [0.10, 0.20],
            "rolling_AR1_20d": [0.08, 0.12],
            "variance_ratio": [1.05, 1.10],
            "trend_persistence": [0.65, 0.70],
            "reversal_speed": [0.30, 0.35],
            "positive_return_streak": [3.0, 4.0],
            "negative_return_streak": [0.0, 0.0],
            "drawdown_recovery_ratio": [0.10, 0.20],
            "00631L_vs_0050_relative_momentum": [0.02, 0.03],
        },
        index=idx,
    )

    out = classify_compounding_regime(features)

    assert out.iloc[-1]["compounding_regime"] == TREND_PERSISTENT
    assert out.iloc[-1]["recommended_policy"] == "do_not_reduce_00631l_for_high_volatility_alone"


def test_classifies_mean_reverting_when_reversal_features_align() -> None:
    idx = pd.date_range("2026-01-01", periods=2)
    features = pd.DataFrame(
        {
            "rolling_AR1_5d": [-0.10, -0.20],
            "rolling_AR1_20d": [-0.08, -0.12],
            "variance_ratio": [0.90, 0.80],
            "trend_persistence": [0.52, 0.50],
            "reversal_speed": [0.60, 0.70],
            "positive_return_streak": [1.0, 0.0],
            "negative_return_streak": [0.0, 1.0],
            "drawdown_recovery_ratio": [0.80, 0.90],
            "00631L_vs_0050_relative_momentum": [-0.01, -0.02],
        },
        index=idx,
    )

    out = classify_compounding_regime(features)

    assert out.iloc[-1]["compounding_regime"] == MEAN_REVERTING
    assert out.iloc[-1]["recommended_policy"] == "prohibit_new_leverage_or_reduce_rebalance_frequency"


def test_defaults_to_transitional_when_scores_are_mixed() -> None:
    idx = pd.date_range("2026-01-01", periods=1)
    features = pd.DataFrame(
        {
            "rolling_AR1_5d": [0.01],
            "rolling_AR1_20d": [0.00],
            "variance_ratio": [1.00],
            "trend_persistence": [0.56],
            "reversal_speed": [0.50],
            "positive_return_streak": [1.0],
            "negative_return_streak": [1.0],
            "drawdown_recovery_ratio": [0.30],
            "00631L_vs_0050_relative_momentum": [0.00],
        },
        index=idx,
    )

    out = classify_compounding_regime(features)

    assert out.iloc[-1]["compounding_regime"] == TRANSITIONAL
    assert out.iloc[-1]["recommended_policy"] == "maintain_a2118_no_active_overlay"


def test_build_compounding_features_includes_rolling_ce_and_vol_persistence() -> None:
    idx = pd.date_range("2026-01-01", periods=130, freq="B")
    price_0050 = pd.Series([100.0 + i * 0.1 for i in range(len(idx))], index=idx)
    price_00631l = pd.Series([50.0 + i * 0.12 for i in range(len(idx))], index=idx)

    features = build_compounding_features(price_00631l, price_0050)

    assert "compounding_effect_20d" in features
    assert "compounding_effect_60d" in features
    assert "compounding_effect_120d" in features
    assert "volatility_persistence_ratio" in features
    assert features["compounding_effect_120d"].notna().any()
