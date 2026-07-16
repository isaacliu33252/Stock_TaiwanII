from __future__ import annotations

import json

import pandas as pd

from group_a_plus.integrations.trough_override_eligibility_shadow import (
    append_shadow_log_row,
    build_shadow_log_row,
)


def _fixture_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, dict]:
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
    compounding_regime = pd.Series(["TRANSITIONAL", "TRANSITIONAL", "TRANSITIONAL"], index=idx)
    report = {"base_weights": {"cash": {"cash": 1.0}, "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2}}}
    return prices, frame, trough, gate, compounding_regime, report


def test_build_shadow_log_row_reports_todays_eligibility() -> None:
    prices, frame, trough, gate, compounding_regime, report = _fixture_inputs()
    # Today (last row) is NOT the eligible middle day -- expect eligible=False.
    row = build_shadow_log_row(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        compounding_regime=compounding_regime,
        report=report,
    )

    assert row["status"] == "available"
    assert row["date"] == str(prices.index[-1].date())
    assert row["eligible"] is False
    assert row["trigger_source"] is None
    assert row["trough_state"] == "NO_TROUGH"


def test_build_shadow_log_row_detects_eligible_middle_day_when_it_is_latest() -> None:
    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 60.0],
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
    compounding_regime = pd.Series(["TRANSITIONAL", "TRANSITIONAL"], index=idx)
    report = {"base_weights": {"cash": {"cash": 1.0}, "golden1": {"0050.TW": 0.8, "00631L.TW": 0.2}}}

    row = build_shadow_log_row(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate,
        compounding_regime=compounding_regime,
        report=report,
    )

    assert row["eligible"] is True
    assert row["trigger_source"] == "trough"
    assert row["override_00631l_buy_weight"] > 0.0


def test_build_shadow_log_row_empty_prices_is_unavailable() -> None:
    row = build_shadow_log_row(
        prices=pd.DataFrame(),
        frame=pd.DataFrame(),
        trough_state=pd.DataFrame({"state": []}),
        gate_frame=pd.DataFrame({"volatility_gate": []}),
        compounding_regime=pd.Series(dtype=str),
        report={},
    )

    assert row["status"] == "unavailable"
    assert row["reason"] == "empty_prices"


def test_append_shadow_log_row_dedupes_by_date(tmp_path) -> None:
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "available", "date": "2026-07-15", "eligible": False}

    assert append_shadow_log_row(row, log_path) is True
    assert append_shadow_log_row(row, log_path) is False

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2026-07-15"
