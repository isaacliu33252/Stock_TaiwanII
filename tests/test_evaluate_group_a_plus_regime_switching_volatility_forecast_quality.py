from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_regime_switching_volatility_forecast_quality import _metrics


def test_metrics_reports_improvement_against_benchmark() -> None:
    idx = pd.bdate_range("2026-01-02", periods=60)
    actual = pd.Series(np.linspace(0.0001, 0.0002, len(idx)), index=idx)
    forecast = actual * 1.02
    benchmark = actual * 1.30
    result = _metrics(actual, forecast, benchmark)

    assert result["status"] == "available"
    assert result["n"] == 60
    assert result["qlike_improvement_pct"] > 0.0
    assert result["mse_improvement_pct"] > 0.0
    assert result["win_rate_vs_benchmark"] > 0.5


def test_metrics_blocks_insufficient_data() -> None:
    idx = pd.bdate_range("2026-01-02", periods=10)
    actual = pd.Series(np.linspace(0.0001, 0.0002, len(idx)), index=idx)
    result = _metrics(actual, actual, actual)
    assert result["status"] == "insufficient_data"
    assert result["n"] == 10

