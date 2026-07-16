from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment import simulate_buy_attempt_alignment


def test_partial_reentry_allows_fast_buy_attempt_when_guards_clear() -> None:
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 105.0],
            "00631L.TW": [50.0, 50.0, 58.0],
            "00632R.TW": [10.0, 10.0, 10.0],
            "00679B.TWO": [25.0, 25.0, 25.0],
        },
        index=idx,
    )
    frame = pd.DataFrame(
        {
            "execution_regime": ["cash", "golden1", "golden1"],
            "total_risk_score": [0, 0, 0],
            "tail_risk_score": [0, 0, 0],
            "drawdown": [0.0, 0.0, 0.0],
        },
        index=idx,
    )
    trough = pd.DataFrame({"state": ["NO_TROUGH", "PARTIAL_REENTRY", "NO_TROUGH"]}, index=idx)
    gate = pd.DataFrame({"volatility_gate": ["neutral_vol", "neutral_vol", "neutral_vol"]}, index=idx)
    report = {"base_weights": {"cash": {"cash": 1.0}, "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2}}}

    out = simulate_buy_attempt_alignment(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
    )

    assert out["partial_reentry_buy_attempt_days"] == 1
    assert out["allowed_fast_reentry_days"] == 1
    assert out["events"][0]["buy_fraction"] == 0.7


def test_high_vol_blocks_partial_00631l_fast_buy() -> None:
    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 50.0],
            "00632R.TW": [10.0, 10.0],
            "00679B.TWO": [25.0, 25.0],
        },
        index=idx,
    )
    frame = pd.DataFrame(
        {
            "execution_regime": ["cash", "golden1"],
            "total_risk_score": [0, 0],
            "tail_risk_score": [0, 0],
            "drawdown": [0.0, 0.0],
        },
        index=idx,
    )
    trough = pd.DataFrame({"state": ["NO_TROUGH", "PARTIAL_REENTRY"]}, index=idx)
    gate = pd.DataFrame({"volatility_gate": ["neutral_vol", "high_vol_defensive"]}, index=idx)
    report = {"base_weights": {"cash": {"cash": 1.0}, "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2}}}

    out = simulate_buy_attempt_alignment(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
    )

    assert out["partial_reentry_buy_attempt_days"] == 1
    assert out["allowed_fast_reentry_days"] == 0
    assert out["blocked_by_volatility_gate"] == 1
