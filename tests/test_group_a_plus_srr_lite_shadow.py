from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.integrations.srr_lite_shadow import build_srr_lite_shadow_from_prices


def _price_frame(*, correlated_tail: bool) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-01", periods=90)
    rng = np.random.default_rng(42)
    base = rng.normal(0.0005, 0.006, len(idx))
    data: dict[str, np.ndarray] = {}
    symbols = ["0050.TW", "00631L.TW", "2330.TW", "SOXX", "TSM", "00679B.TWO"]
    for i, symbol in enumerate(symbols):
        noise = rng.normal(0.0, 0.006 + i * 0.0005, len(idx))
        ret = 0.25 * base + 0.75 * noise
        if correlated_tail:
            ret[-10:] = base[-10:] * (1.0 + i * 0.02) + rng.normal(0.0, 0.0004, 10)
        data[symbol] = 100.0 * np.cumprod(1.0 + ret)
    return pd.DataFrame(data, index=idx)


def test_srr_lite_flags_high_correlation_fragility() -> None:
    snapshot = build_srr_lite_shadow_from_prices(_price_frame(correlated_tail=True))

    assert snapshot["status"] == "available"
    assert snapshot["fragility_level"] in {"elevated", "high"}
    assert snapshot["systemic_fragility_score"] >= 0.55
    assert snapshot["metrics"]["graph_density"] > 0.5
    assert snapshot["allow_crash_watch_auto_weight_change"] is False
    assert "crash_watch_active" in snapshot
    assert snapshot["allow_auto_weight_change"] is False


def test_srr_lite_stays_shadow_only_when_correlation_is_low() -> None:
    snapshot = build_srr_lite_shadow_from_prices(_price_frame(correlated_tail=False))

    assert snapshot["status"] == "available"
    assert snapshot["no_add_active"] is False
    assert snapshot["crash_watch_active"] is False
    assert snapshot["recommended_action"] == "none"
    assert snapshot["crash_watch_recommended_action"] == "none"
    assert snapshot["allow_00631l_add_reference"] is True
