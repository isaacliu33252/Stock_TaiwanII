from __future__ import annotations

import pandas as pd
import pytest

from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_shadow import (
    _forward_max_drawdown,
    _forward_return,
    simulate_staging_policy,
    summarize_forward_returns,
)


def test_forward_return_uses_trading_rows() -> None:
    close = pd.Series([100.0, 110.0, 121.0], index=pd.date_range("2026-01-02", periods=3, freq="B"))

    out = _forward_return(close, 2)

    assert out.iloc[0] == pytest.approx(0.21)
    assert pd.isna(out.iloc[1])


def test_forward_max_drawdown_measures_path_after_event() -> None:
    close = pd.Series([100.0, 98.0, 93.0, 104.0], index=pd.date_range("2026-01-02", periods=4, freq="B"))

    out = _forward_max_drawdown(close, 3)

    assert out.iloc[0] == pytest.approx(-0.07)


def test_summarize_forward_returns_counts_false_full_reentry() -> None:
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    state_frame = pd.DataFrame(
        {"state": ["FULL_REENTRY", "NO_TROUGH", "PARTIAL_REENTRY", "NO_TROUGH", "NO_TROUGH"]},
        index=idx,
    )
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 99.0, 101.0, 102.0, 103.0],
            "00631L.TW": [100.0, 92.0, 96.0, 97.0, 98.0],
        },
        index=idx,
    )

    summary = summarize_forward_returns(
        state_frame,
        prices,
        horizons=(1,),
        false_reentry_horizon=3,
        false_reentry_drawdown_threshold=-0.03,
    )

    assert summary["by_state"]["FULL_REENTRY"]["days"] == 1
    assert summary["false_reentry_event_count"] == 1
    assert summary["false_reentry_events"][0]["state"] == "FULL_REENTRY"


def test_staging_policy_accelerates_full_reentry_buy() -> None:
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 110.0, 120.0],
            "00631L.TW": [50.0, 60.0, 70.0],
            "00632R.TW": [10.0, 10.0, 10.0],
            "00679B.TWO": [25.0, 25.0, 25.0],
        },
        index=idx,
    )
    regimes = pd.Series(["cash", "golden1", "golden1"], index=idx)
    report = {
        "base_weights": {
            "cash": {"cash": 1.0},
            "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2, "cash": 0.0},
        }
    }
    no_trough = pd.DataFrame({"state": ["NO_TROUGH", "NO_TROUGH", "NO_TROUGH"]}, index=idx)
    full_reentry = pd.DataFrame({"state": ["NO_TROUGH", "FULL_REENTRY", "NO_TROUGH"]}, index=idx)

    baseline = simulate_staging_policy(prices, regimes, no_trough, report, initial_value=100_000.0)
    accelerated = simulate_staging_policy(prices, regimes, full_reentry, report, initial_value=100_000.0)

    assert accelerated["execution"]["accelerated_event_count"] == 1
    assert accelerated["metrics"]["final_value"] > baseline["metrics"]["final_value"]
