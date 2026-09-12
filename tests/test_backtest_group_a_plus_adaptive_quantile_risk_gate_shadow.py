from __future__ import annotations

import pandas as pd

from scripts.evaluate.backtest_group_a_plus_adaptive_quantile_risk_gate_shadow import (
    DEFAULT_TICKERS,
    evaluate,
)


def _signal(date: str, weights: dict, **overrides):
    payload = {
        "actual_data_date": date,
        "business_stale_days": 2,
        "calendar_stale_days": 2,
        "execution_allowed": False,
        "target_weights": weights,
        "ncf_live_overlay": {"status": "stale"},
        "signal_alignment": {
            "alignment": "mixed",
            "divergent_sources": [],
            "leverage_suitability": {"tier": 1},
        },
        "tail_conformal": {"state": "TAIL_RISK_NORMAL", "allow_00631l_add": True},
        "garch_regime_shadow": {"volatility_gate": {"high_vol_gate": False}},
    }
    payload.update(overrides)
    return payload


def test_backtest_caps_leverage_when_gate_is_pessimistic() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    close = pd.DataFrame(
        {
            "0050.TW": [100.0, 99.0, 100.0],
            "00631L.TW": [100.0, 94.0, 95.0],
            "00632R.TW": [10.0, 10.3, 10.2],
            "00679B.TWO": [25.0, 25.0, 25.0],
        },
        index=dates,
    )
    signals = [
        _signal(
            "2026-01-02",
            {"0050.TW": 0.5, "00631L.TW": 0.2, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.3},
        ),
        _signal(
            "2026-01-05",
            {"0050.TW": 0.5, "00631L.TW": 0.2, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.3},
        ),
    ]

    result = evaluate(signals, close, tickers=DEFAULT_TICKERS, min_samples=1)

    assert result["status"] == "ok"
    assert result["gate_activity"]["cap_00631l_days"] == 2
    assert result["gate_activity"]["raise_cash_floor_days"] == 0
    assert result["rows"][0]["gated_00631l_weight"] == 0.0
    assert result["rows"][0]["gated_cash_weight"] >= 0.45
    assert result["gated_metrics"]["worst_day"] > result["raw_metrics"]["worst_day"]
    assert result["decision"]["target_weight_change_allowed"] is False


def test_backtest_reports_insufficient_signal_snapshots() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    close = pd.DataFrame(
        {
            "0050.TW": [100.0, 101.0],
            "00631L.TW": [100.0, 102.0],
            "00632R.TW": [10.0, 9.9],
            "00679B.TWO": [25.0, 25.0],
        },
        index=dates,
    )
    signals = [
        _signal(
            "2026-01-02",
            {"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.7},
            execution_allowed=True,
            business_stale_days=0,
            ncf_live_overlay={"status": "applied"},
        )
    ]

    result = evaluate(signals, close, tickers=DEFAULT_TICKERS, min_samples=3)

    assert result["status"] == "insufficient_signal_snapshots"
    assert result["sample"]["return_rows"] == 1
    assert result["decision"]["promotion_decision"] == "do_not_promote"
