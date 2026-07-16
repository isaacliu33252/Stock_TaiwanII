from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.evaluate.evaluate_cross_market_directed_graph_shadow import (
    _metrics_by_condition,
    _metrics_by_year,
    _threshold_metrics,
    add_composite_source_features,
    align_source_returns_to_taiwan_dates,
    build_target_outcomes,
    select_directed_edges,
)


def test_source_alignment_uses_strictly_prior_source_close() -> None:
    source = pd.DataFrame(
        {"TSM": [100.0, 110.0, 121.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
    )
    target_dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])

    features = align_source_returns_to_taiwan_dates(source, pd.DatetimeIndex(target_dates), windows=(1,))

    assert np.isnan(features.loc[pd.Timestamp("2026-01-02"), "src_TSM_ret1d"])
    assert features.loc[pd.Timestamp("2026-01-05"), "src_TSM_ret1d"] == pytest.approx(0.10)
    assert features.loc[pd.Timestamp("2026-01-06"), "src_TSM_ret1d"] == pytest.approx(0.10)


def test_edge_selection_marks_stable_directed_predictor() -> None:
    dates = pd.bdate_range("2025-01-02", periods=320)
    x = pd.Series(np.sin(np.arange(320) / 7.0) * 0.02, index=dates)
    y = x * 1.5
    features = pd.DataFrame({"src_TSM_ret1d": x}, index=dates)
    outcomes = pd.DataFrame({"target_00631L.TW_ret1d_fwd": y}, index=dates)

    edges, selected = select_directed_edges(
        features,
        outcomes,
        window=80,
        step=20,
        tstat_threshold=2.0,
        min_windows=3,
        stability_threshold=0.50,
    )

    assert not edges.empty
    assert bool(edges.iloc[0]["stable"]) is True
    assert selected == [{"feature": "src_TSM_ret1d"}]


def test_composite_features_add_semiconductor_basket_and_spreads() -> None:
    features = pd.DataFrame(
        {
            "src_TSM_ret1d": [0.01],
            "src_SOXX_ret1d": [0.02],
            "src_NVDA_ret1d": [0.03],
            "src_QQQ_ret1d": [0.015],
        },
        index=[pd.Timestamp("2026-01-02")],
    )

    out = add_composite_source_features(features)

    assert out.loc[pd.Timestamp("2026-01-02"), "src_US_SEMI_BASKET_ret1d"] == pytest.approx(0.02)
    assert out.loc[pd.Timestamp("2026-01-02"), "src_SOXX_minus_QQQ_ret1d"] == pytest.approx(0.005)
    assert out.loc[pd.Timestamp("2026-01-02"), "src_TSM_minus_SOXX_ret1d"] == pytest.approx(-0.01)


def test_build_target_outcomes_creates_reenter_and_no_add_labels() -> None:
    dates = pd.bdate_range("2026-01-02", periods=8)
    target = pd.DataFrame(
        {
            "0050.TW": [100, 100, 100, 100, 100, 101, 102, 103],
            "00631L.TW": [100, 100, 100, 100, 100, 108, 110, 112],
        },
        index=dates,
        dtype=float,
    )

    outcomes = build_target_outcomes(target, horizon=5)

    assert outcomes.loc[dates[0], "label_REENTER"] == 1.0
    assert outcomes.loc[dates[0], "label_NO_ADD"] == 0.0
    assert np.isnan(outcomes.loc[dates[-1], "label_REENTER"])
    assert np.isnan(outcomes.loc[dates[-1], "label_NO_ADD"])
    assert "condition_0050_5d_le_minus2pct" in outcomes.columns
    assert "condition_00631l_5d_le_minus4pct" in outcomes.columns


def test_threshold_metrics_report_precision_and_recall() -> None:
    metrics = _threshold_metrics(
        pd.Series([1, 0, 1, 0]),
        np.asarray([0.70, 0.65, 0.40, 0.20]),
        thresholds=(0.60,),
    )

    assert metrics == [
        {
            "threshold": 0.6,
            "alerts": 2,
            "true_positives": 1,
            "false_positives": 1,
            "false_negatives": 1,
            "precision": 0.5,
            "recall": 0.5,
            "false_positive_rate": 0.5,
        }
    ]


def test_metrics_by_year_splits_oos_predictions() -> None:
    metrics = _metrics_by_year(
        ["2020-03-02", "2020-03-03", "2021-01-04", "2021-01-05"],
        {"REENTER": [1, 0, 1, 0], "NO_ADD": [0, 1, 0, 1]},
        {"REENTER": [0.8, 0.2, 0.7, 0.3], "NO_ADD": [0.1, 0.9, 0.2, 0.8]},
    )

    assert metrics["2020"]["REENTER"]["rows"] == 2
    assert metrics["2021"]["NO_ADD"]["rows"] == 2
    assert metrics["2020"]["NO_ADD"]["auc"] == 1.0


def test_metrics_by_condition_filters_triggered_rows() -> None:
    metrics = _metrics_by_condition(
        ["2020-03-02", "2020-03-03", "2020-03-04", "2020-03-05"],
        {"condition_0050_5d_le_minus2pct": [1, 0, 1, 0]},
        {"REENTER": [1, 0, 0, 1], "NO_ADD": [1, 0, 1, 0]},
        {"REENTER": [0.6, 0.4, 0.3, 0.7], "NO_ADD": [0.8, 0.2, 0.7, 0.1]},
    )

    condition = metrics["condition_0050_5d_le_minus2pct"]
    assert condition["condition_rows"] == 2
    assert condition["NO_ADD"]["positive_rate"] == 1.0
    assert condition["NO_ADD"]["threshold_metrics"][0]["precision"] == 1.0
