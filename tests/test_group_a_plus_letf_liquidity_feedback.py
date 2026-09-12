from __future__ import annotations

import pandas as pd

from group_a_plus.integrations.letf_liquidity_feedback import build_letf_liquidity_feedback_backtest


def _ohlcv() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=90, freq="B")
    rows = []
    for i, dt in enumerate(dates):
        base_0050 = 100.0 + i * 0.05
        shock = i == 70
        for ticker, multiplier in (("0050.TW", 1.0), ("00631L.TW", 2.0), ("00632R.TW", 0.1)):
            close = base_0050 * multiplier
            high = close * 1.01
            low = close * 0.99
            volume = 1_000_000
            if shock:
                high = close * 1.08
                low = close * 0.90
                volume = 5_000_000
                if ticker == "00631L.TW":
                    close *= 0.90
            rows.append(
                {
                    "ticker": ticker,
                    "dt": dt,
                    "open": close,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
    return pd.DataFrame(rows)


def test_letf_liquidity_feedback_backtest_flags_shadow_events() -> None:
    report = build_letf_liquidity_feedback_backtest(
        ohlcv=_ohlcv(),
        as_of="2026-05-15",
        start="2026-01-01",
        range_threshold=0.03,
        volume_z_min=1.0,
        dislocation_z_min=1.0,
        min_trigger_count=1,
    )

    assert report["input_coverage"]["trigger_count"] >= 1
    assert report["summary"]["ready_for_manual_review"] is True
    assert report["event_metrics"]["00631L.TW"]["fwd_return_1d"]["n"] >= 1
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["guarded_candidate_allowed"] is False


def test_letf_liquidity_feedback_backtest_reports_no_events() -> None:
    report = build_letf_liquidity_feedback_backtest(
        ohlcv=_ohlcv(),
        as_of="2026-03-01",
        start="2026-01-01",
        range_threshold=0.50,
        volume_z_min=10.0,
        dislocation_z_min=10.0,
        min_trigger_count=1,
    )

    assert report["input_coverage"]["trigger_count"] == 0
    assert report["summary"]["recommendation"] == "needs_more_trigger_history"
    assert report["decision"]["creates_orders"] is False
