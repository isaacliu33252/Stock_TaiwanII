from __future__ import annotations

import math

import numpy as np
import pandas as pd

from group_a_plus.integrations.tbrain_features import (
    add_tbrain_features,
    compute_weekly_close,
    direction_magnitude_gate,
    kdj_j_quantile_snapshot,
    latest_tbrain_snapshot,
    score_weighted_ensemble,
    squash_vector,
    tbrain_feature_columns,
    weekly_ma_bull_snapshot,
)


def _ohlcv(rows: int = 160) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = pd.Series(np.linspace(100.0, 140.0, rows), index=idx)
    return pd.DataFrame(
        {
            "open": close * 0.998,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.linspace(1_000_000.0, 1_600_000.0, rows),
        },
        index=idx,
    )


def test_squash_vector_matches_tbrain_transform() -> None:
    result = squash_vector([3.0, 4.0])

    np.testing.assert_allclose(result, np.array([15.0 / 26.0, 20.0 / 26.0]))


def test_add_tbrain_features_generates_location_and_kdj_columns() -> None:
    features = add_tbrain_features(_ohlcv())

    assert "tbrain_close_ma130_loc" in features.columns
    assert "tbrain_volume_ma65_loc" in features.columns
    assert "tbrain_kdj_k_9_3_3" in features.columns
    assert "tbrain_kdj_j_5_21_11" in features.columns
    assert math.isfinite(float(features["tbrain_close_ma130_loc"].iloc[-1]))


def test_tbrain_feature_columns_match_generated_core_columns() -> None:
    features = add_tbrain_features(_ohlcv())
    generated = set(features.columns)

    for col in tbrain_feature_columns():
        if "squash" not in col:
            assert col in generated


def test_score_weighted_ensemble_uses_validation_edge_weights() -> None:
    result = score_weighted_ensemble(
        {"rf": 0.60, "et": 0.40, "gb": 0.90},
        {"rf": 0.60, "et": 0.50, "gb": 0.70},
    )

    assert result["weights"]["gb"] > result["weights"]["rf"]
    assert result["weights"]["et"] == 0.0
    assert result["prediction"] > 0.75


def test_direction_magnitude_gate_requires_agreement_and_size() -> None:
    passed = direction_magnitude_gate(probability_up=0.58, predicted_return=0.006)
    failed = direction_magnitude_gate(probability_up=0.58, predicted_return=-0.006)

    assert passed["passed"] is True
    assert failed["passed"] is False
    assert failed["return_side"] == "DOWN"


def test_latest_tbrain_snapshot_is_compact_json_ready() -> None:
    snapshot = latest_tbrain_snapshot(_ohlcv())

    assert "tbrain_close_ma22_loc" in snapshot
    assert "tbrain_kdj_k_9_3_3" in snapshot
    assert all(isinstance(value, float) for value in snapshot.values())


def test_kdj_j_quantile_snapshot_returns_ordered_band_with_enough_history() -> None:
    result = kdj_j_quantile_snapshot(_ohlcv())

    assert result["tbrain_kdj_j_9_3_3_q_low"] is not None
    assert result["tbrain_kdj_j_9_3_3_q_high"] is not None
    assert result["tbrain_kdj_j_9_3_3_q_low"] <= result["tbrain_kdj_j_9_3_3_q_high"]


def test_kdj_j_quantile_snapshot_returns_none_with_insufficient_history() -> None:
    result = kdj_j_quantile_snapshot(_ohlcv(rows=5))

    assert result["tbrain_kdj_j_9_3_3_q_low"] is None
    assert result["tbrain_kdj_j_9_3_3_q_high"] is None


def test_compute_weekly_close_collapses_to_one_row_per_iso_week() -> None:
    weekly = compute_weekly_close(_ohlcv())

    assert len(weekly) < 160
    assert weekly.is_monotonic_increasing
    assert weekly.index.is_monotonic_increasing


def test_weekly_ma_bull_snapshot_detects_bull_alignment_on_uptrend() -> None:
    result = weekly_ma_bull_snapshot(_ohlcv())

    assert result["status"] == "available"
    assert result["bull_aligned"] is True
    assert result["bear_aligned"] is False
    assert result["ma_short"] > result["ma_mid"] > result["ma_long"]


def test_weekly_ma_bull_snapshot_flags_insufficient_history() -> None:
    result = weekly_ma_bull_snapshot(_ohlcv(rows=30))

    assert result["status"] == "insufficient_history"
