"""Tests for the GatedLinear-lite drawdown forecast pure-logging daily shadow accumulator."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from group_a_plus.integrations.gatedlinear_drawdown_forecast_shadow_log import (
    H,
    L,
    append_shadow_log_row,
    fit_and_forecast,
)


def _synthetic_drawdown(n=400, seed=0) -> pd.Series:
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=0.0003, scale=0.01, size=n)
    close = 100.0 * np.cumprod(1 + rets)
    close = pd.Series(close, index=pd.date_range("2023-01-02", periods=n, freq="B"))
    running_max = close.cummax()
    return close / running_max - 1


def test_fit_and_forecast_available_with_enough_history():
    drawdown = _synthetic_drawdown(n=400)

    row = fit_and_forecast(drawdown)

    assert row["status"] == "available"
    assert row["horizon_trading_days"] == H
    assert row["date"] == str(drawdown.index[-1].date())
    assert row["current_drawdown"] == drawdown.iloc[-1]
    assert isinstance(row["predicted_drawdown_h20"], float)
    assert set(row["gate_weights"]) == {"trend", "diff", "phase"}
    assert row["n_train_pairs"] > 0


def test_fit_and_forecast_unavailable_with_insufficient_history():
    drawdown = _synthetic_drawdown(n=L + H)  # far below the min_required floor

    row = fit_and_forecast(drawdown)

    assert row["status"] == "unavailable"
    assert "insufficient_history" in row["reason"]


def test_append_shadow_log_row_dedupes_by_date(tmp_path):
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "available", "date": "2026-08-14", "predicted_drawdown_h20": -0.05}

    assert append_shadow_log_row(row, log_path) is True
    assert append_shadow_log_row(row, log_path) is False

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2026-08-14"


def test_append_shadow_log_row_skips_unavailable_rows(tmp_path):
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "unavailable", "reason": "insufficient_history"}

    assert append_shadow_log_row(row, log_path) is False
    assert not log_path.exists()
