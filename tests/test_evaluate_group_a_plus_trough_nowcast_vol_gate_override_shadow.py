from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow import simulate_override_policy


def _fixture_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0, 100.0],
            "00631L.TW": [50.0, 50.0, 60.0],
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
    gate = pd.DataFrame({"volatility_gate": ["neutral_vol", "high_vol_defensive", "neutral_vol"]}, index=idx)
    report = {"base_weights": {"cash": {"cash": 1.0}, "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2}}}
    return prices, frame, trough, gate, report


def test_override_only_fires_for_partial_high_vol_00631l_buy_attempt() -> None:
    prices, frame, trough, gate, report = _fixture_inputs()

    out = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
        override_fraction=0.25,
    )

    assert out["override_eligible_days"] == 1
    assert out["override_events"][0]["override_00631l_buy_weight"] > 0.0


def test_no_override_records_eligible_event_without_buy_weight() -> None:
    prices, frame, trough, gate, report = _fixture_inputs()

    out = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
        override_fraction=0.0,
    )

    assert out["override_eligible_days"] == 1
    assert out["override_events"][0]["override_00631l_buy_weight"] == 0.0


def test_confirmation_mode_filters_first_partial_day() -> None:
    prices, frame, trough, gate, report = _fixture_inputs()

    second_partial = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
        override_fraction=0.25,
        confirmation_mode="second_partial",
    )
    no_lower_low = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
        override_fraction=0.25,
        confirmation_mode="no_lower_low_3d",
    )

    assert second_partial["override_eligible_days"] == 0
    assert no_lower_low["override_eligible_days"] == 1
    assert no_lower_low["override_events"][0]["no_fresh_0050_lower_low_3d"] is True


def test_default_eligibility_mode_ignores_compounding_trend_persistent_signal() -> None:
    prices, frame, trough, gate, report = _fixture_inputs()
    # Day 3 (index 2) has no trough signal but is flagged TREND_PERSISTENT and
    # high-vol; the default (trough-only) eligibility mode must not fire on it.
    gate = pd.DataFrame({"volatility_gate": ["neutral_vol", "high_vol_defensive", "high_vol_defensive"]}, index=trough.index)
    compounding_regime = pd.Series(["TRANSITIONAL", "TRANSITIONAL", "TREND_PERSISTENT"], index=trough.index)

    out = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
        override_fraction=0.25,
        eligibility_mode="trough_partial_reentry_only",
        compounding_regime=compounding_regime,
    )

    assert out["override_eligible_days"] == 1
    assert out["override_events"][0]["trigger_source"] == "trough"


def test_union_eligibility_mode_also_fires_on_compounding_trend_persistent() -> None:
    prices, frame, trough, gate, report = _fixture_inputs()
    gate = pd.DataFrame({"volatility_gate": ["neutral_vol", "high_vol_defensive", "high_vol_defensive"]}, index=trough.index)
    compounding_regime = pd.Series(["TRANSITIONAL", "TRANSITIONAL", "TREND_PERSISTENT"], index=trough.index)

    out = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        report=report,
        initial_value=100_000.0,
        override_fraction=0.25,
        eligibility_mode="trough_or_compounding_trend_persistent",
        compounding_regime=compounding_regime,
    )

    assert out["override_eligible_days"] == 2
    triggers = {event["date"]: event["trigger_source"] for event in out["override_events"]}
    assert triggers[str(trough.index[1].date())] == "trough"
    assert triggers[str(trough.index[2].date())] == "compounding_trend_persistent"


def test_unknown_eligibility_mode_raises() -> None:
    prices, frame, trough, gate, report = _fixture_inputs()

    try:
        simulate_override_policy(
            prices=prices,
            frame=frame,
            trough_state=trough,
            gate_frame=gate,
            report=report,
            initial_value=100_000.0,
            override_fraction=0.25,
            eligibility_mode="not_a_real_mode",
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
