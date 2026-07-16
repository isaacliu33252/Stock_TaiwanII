from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.integrations.foundation_volatility_shadow import (
    build_foundation_vol_shadow_frame,
    latest_foundation_vol_snapshot,
    recovery_quality_from_snapshot,
)


def _synthetic_ohlc(n: int = 760, seed: int = 17) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-02", periods=n)
    returns = rng.normal(0.0002, 0.012, size=n)
    close = 100.0 * np.cumprod(1.0 + returns)
    open_ = close * (1.0 + rng.normal(0.0, 0.002, size=n))
    intraday_range = np.abs(rng.normal(0.007, 0.003, size=n)) + 1e-4
    high = np.maximum(open_, close) * (1.0 + intraday_range)
    low = np.minimum(open_, close) * (1.0 - intraday_range)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=dates)


def test_foundation_vol_shadow_frame_has_context_and_ensemble_columns() -> None:
    frame = build_foundation_vol_shadow_frame(
        _synthetic_ohlc(),
        context_lengths=(64, 128),
        horizons=(5, 10),
    )

    assert "har_rv_ctx64_h5_variance" in frame.columns
    assert "har_rv_ctx128_h10_variance" in frame.columns
    assert "ensemble_h5_variance" in frame.columns
    assert "ensemble_h10_uncertainty_ratio" in frame.columns
    assert frame["ensemble_h10_variance"].dropna().gt(0).all()


def test_latest_foundation_vol_snapshot_and_recovery_quality() -> None:
    frame = build_foundation_vol_shadow_frame(
        _synthetic_ohlc(),
        context_lengths=(64, 128),
        horizons=(10,),
    )
    snapshot = latest_foundation_vol_snapshot(frame)

    assert snapshot["status"] == "available"
    assert snapshot["schema_version"] == 1
    assert "10" in snapshot["horizons"]

    decision = recovery_quality_from_snapshot(
        snapshot,
        horizon=10,
        max_percentile=1.0,
        max_uncertainty_ratio=10.0,
    )
    assert decision["allow_recovery_boost"] is True


def test_recovery_quality_blocks_missing_snapshot() -> None:
    decision = recovery_quality_from_snapshot({"status": "unavailable"}, horizon=10)
    assert decision["allow_recovery_boost"] is False
