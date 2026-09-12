from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from group_a_plus.integrations.triadic_stress_index import (
    _asymmetric_memory,
    compute_network_metrics,
    latest_tsi_snapshot,
    rolling_tsi_frame,
)


def _synthetic_prices(n: int = 160, seed: int = 10788) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-02", periods=n)
    calm = rng.normal(0.0002, 0.006, size=(n // 2, 6))
    common = rng.normal(-0.0008, 0.018, size=(n - n // 2, 1))
    idio = rng.normal(0.0, 0.004, size=(n - n // 2, 6))
    stressed = common + idio
    returns = np.vstack([calm, stressed])
    return pd.DataFrame(100.0 * np.cumprod(1.0 + returns, axis=0), index=idx, columns=[f"T{i}" for i in range(6)])


def test_compute_network_metrics_has_attribution_and_positive_tsi() -> None:
    prices = _synthetic_prices()
    returns = prices.pct_change().tail(20)
    metrics = compute_network_metrics(returns, min_observations=12)
    assert metrics.tsi > 0.0
    assert metrics.n_assets == 6
    assert set(metrics.node_triangle) == set(prices.columns)
    assert set(metrics.node_degree) == set(prices.columns)


def test_rolling_tsi_rises_in_synthetic_common_factor_stress() -> None:
    prices = _synthetic_prices()
    frame, _ = rolling_tsi_frame(prices, window_days=20, min_observations=12)
    early = frame["tsi"].iloc[:30].median()
    late = frame["tsi"].iloc[-30:].median()
    assert late > early
    assert frame["tsi_memory"].iloc[-1] > frame["tsi_memory"].iloc[30]


def test_asymmetric_memory_rises_faster_than_it_falls() -> None:
    series = pd.Series([0.0, 10.0, 0.0])
    memory = _asymmetric_memory(series, alpha_up=0.6, alpha_down=0.08)
    assert memory.iloc[1] == 6.0
    assert memory.iloc[2] == pytest.approx(5.52)


def test_latest_snapshot_is_shadow_only_no_allocation_fields() -> None:
    snapshot = latest_tsi_snapshot(_synthetic_prices(), as_of="2025-08-15")
    assert snapshot["status"] == "available"
    assert snapshot["policy"] == "shadow_only_no_weight_change"
    assert snapshot["production_effect"] == "none"
    assert snapshot["outputs_target_weights"] is False
    assert snapshot["outputs_execution_regime"] is False
    assert "target_weights" not in snapshot
    assert "execution_regime" not in snapshot
    assert snapshot["top_attribution"]
