from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.integrations.network_volatility_spillover_shadow import (
    build_log_realized_variance_panel,
    build_spillover_network_frame,
    latest_spillover_snapshot,
    spillover_recovery_boost_gate,
)


def test_build_log_realized_variance_panel_from_long_ohlcv() -> None:
    idx = pd.date_range("2026-01-01", periods=10, freq="B")
    rows = []
    for ticker, offset in [("0050.TW", 0.0), ("00631L.TW", 1.0)]:
        for i, dt in enumerate(idx):
            close = 100 + offset + i
            rows.append(
                {
                    "dt": dt,
                    "ticker": ticker,
                    "open": close * 0.99,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                }
            )
    panel = build_log_realized_variance_panel(pd.DataFrame(rows), tickers=("0050.TW", "00631L.TW"))

    assert panel.shape == (10, 2)
    assert np.isfinite(panel.to_numpy()).all()


def test_spillover_frame_and_gate_block_high_crisis_regime() -> None:
    idx = pd.date_range("2025-01-01", periods=360, freq="B")
    shock = np.sin(np.arange(len(idx)) / 7.0)
    log_rv = pd.DataFrame(
        {
            "0050.TW": shock + np.linspace(0, 2, len(idx)),
            "00631L.TW": np.roll(shock, 1) + np.linspace(0, 2, len(idx)),
            "00632R.TW": -0.5 * np.roll(shock, 1),
            "00679B.TWO": 0.1 * np.cos(np.arange(len(idx)) / 11.0),
        },
        index=idx,
    )

    frame = build_spillover_network_frame(log_rv, window=60, min_periods=30, edge_threshold=0.10)
    snapshot = latest_spillover_snapshot(frame)
    gate = spillover_recovery_boost_gate(
        {
            **snapshot,
            "systemic_percentile_252d": 0.95,
            "target_in_percentile_252d": 0.95,
            "crisis_regime": True,
        }
    )

    assert "spillover_systemic_score" in frame.columns
    assert snapshot["status"] == "available"
    assert snapshot["edge_density"] >= 0.0
    assert gate["allow_recovery_boost"] is False
    assert gate["reason"] == "spillover_blocked"


def test_spillover_gate_allows_normal_regime() -> None:
    gate = spillover_recovery_boost_gate(
        {
            "status": "available",
            "systemic_percentile_252d": 0.4,
            "target_in_percentile_252d": 0.5,
            "crisis_regime": False,
        }
    )

    assert gate["allow_recovery_boost"] is True
    assert gate["reason"] == "spillover_ok"
