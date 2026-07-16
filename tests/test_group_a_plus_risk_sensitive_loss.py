from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.risk_sensitive_loss import (
    diebold_mariano_test,
    qlike_loss,
    risk_sensitive_loss,
    routing_regret_frame,
    summarize_routing_diagnostics,
    underprediction_loss,
)


def test_qlike_loss_is_zero_when_forecast_matches_realized() -> None:
    realized = pd.Series([0.01, 0.04])
    forecast = pd.Series([0.01, 0.04])

    loss = qlike_loss(realized, forecast)

    assert loss.tolist() == pytest.approx([0.0, 0.0])


def test_underprediction_loss_only_penalizes_low_forecasts() -> None:
    realized = pd.Series([0.04, 0.04])
    forecast = pd.Series([0.02, 0.08])

    loss = underprediction_loss(realized, forecast)

    assert loss.iloc[0] == pytest.approx(0.25)
    assert loss.iloc[1] == pytest.approx(0.0)


def test_risk_sensitive_loss_adds_underprediction_penalty() -> None:
    realized = pd.Series([0.04])
    forecast = pd.Series([0.02])

    combined = risk_sensitive_loss(realized, forecast, underprediction_weight=2.0)

    assert combined.iloc[0] == pytest.approx(qlike_loss(realized, forecast).iloc[0] + 2.0 * 0.25)


def test_routing_regret_frame_selects_oracle_and_miss_best() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    selected = pd.Series(["low", "high", "neutral"], index=idx)
    losses = pd.DataFrame(
        {
            "low": [1.0, 2.0, 3.0],
            "high": [2.0, 1.0, 2.0],
            "neutral": [3.0, 4.0, 1.0],
        },
        index=idx,
    )

    regret = routing_regret_frame(selected_route=selected, candidate_losses=losses)

    assert regret["best_route"].tolist() == ["low", "high", "neutral"]
    assert regret["selected_regret"].tolist() == pytest.approx([0.0, 0.0, 0.0])
    assert regret["miss_best"].tolist() == [False, False, False]


def test_diebold_mariano_no_systematic_difference_is_not_significant() -> None:
    idx = pd.date_range("2026-01-01", periods=200, freq="B")
    rng = np.random.default_rng(0)
    base = np.abs(rng.normal(0.2, 0.05, size=200))
    loss_a = pd.Series(base + rng.normal(0.0, 0.001, size=200), index=idx)
    loss_b = pd.Series(base + rng.normal(0.0, 0.001, size=200), index=idx)

    result = diebold_mariano_test(loss_a, loss_b, h=5)

    assert result["status"] == "ok"
    assert result["p_value"] > 0.05
    assert result["significant_at_5pct"] is False


def test_diebold_mariano_detects_clear_systematic_difference() -> None:
    idx = pd.date_range("2026-01-01", periods=300, freq="B")
    rng = np.random.default_rng(1)
    noise = rng.normal(0.0, 0.01, size=300)
    loss_a = pd.Series(0.10 + noise, index=idx)  # consistently lower loss
    loss_b = pd.Series(0.20 + noise, index=idx)  # consistently higher loss

    result = diebold_mariano_test(loss_a, loss_b, h=1)

    assert result["status"] == "ok"
    assert result["a_more_accurate"] is True
    assert result["p_value"] < 0.01
    assert result["significant_at_5pct"] is True


def test_diebold_mariano_insufficient_data_reports_status() -> None:
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    loss_a = pd.Series([0.1, 0.2, 0.15, 0.18, 0.12], index=idx)
    loss_b = pd.Series([0.2, 0.1, 0.25, 0.08, 0.22], index=idx)

    result = diebold_mariano_test(loss_a, loss_b, h=5)

    assert result["status"] == "insufficient_data"


def test_diebold_mariano_ignores_misaligned_nan_rows() -> None:
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    rng = np.random.default_rng(2)
    loss_a = pd.Series(rng.normal(0.1, 0.01, size=60), index=idx)
    loss_b = pd.Series(rng.normal(0.1, 0.01, size=60), index=idx)
    loss_a.iloc[:20] = float("nan")

    result = diebold_mariano_test(loss_a, loss_b, h=5)

    assert result["status"] == "ok"
    assert result["n"] == 40


def test_summarize_routing_diagnostics_reports_miss_best_rate() -> None:
    idx = pd.date_range("2026-01-01", periods=2, freq="B")
    regret = pd.DataFrame(
        {
            "selected_route": ["low", "high"],
            "selected_loss": [1.0, 3.0],
            "best_route": ["low", "neutral"],
            "best_loss": [1.0, 2.0],
            "selected_regret": [0.0, 1.0],
            "miss_best": [False, True],
        },
        index=idx,
    )

    summary = summarize_routing_diagnostics(regret)

    assert summary["evaluated_count"] == 2
    assert summary["miss_best_rate"] == pytest.approx(0.5)
    assert summary["mean_selected_regret"] == pytest.approx(0.5)
