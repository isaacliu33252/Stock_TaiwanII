from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from group_a_plus.integrations.trough_nowcast import compute_trough_nowcast


def _write_minimal_ohlcv(db_path: Path) -> None:
    dates = pd.bdate_range("2026-01-01", "2026-07-10")
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)")
        for ticker in TICKERS:
            price = 100.0
            for i, dt in enumerate(dates):
                if dt >= pd.Timestamp("2026-07-03"):
                    price *= 1.02
                elif i > len(dates) - 30:
                    price *= 0.985
                else:
                    price *= 1.0005
                volume = 1000.0
                if pd.Timestamp("2026-07-02") <= dt <= pd.Timestamp("2026-07-07"):
                    volume = 3000.0
                if dt == pd.Timestamp("2026-07-10"):
                    volume = 1500.0
                con.execute(
                    "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [ticker, str(dt.date()), price, price, price, price, volume],
                )
        con.execute("CREATE TABLE external_market_ohlcv (ticker TEXT, dt DATE, close DOUBLE)")
        for ticker in ("SOXX", "TSM", "TWD=X", "2330.TW"):
            price = 100.0
            for dt in dates[-20:]:
                price *= 1.03 if dt >= pd.Timestamp("2026-07-06") and ticker != "TWD=X" else 0.99
                con.execute("INSERT INTO external_market_ohlcv VALUES (?, ?, ?)", [ticker, str(dt.date()), price])
    finally:
        con.close()


def test_trough_nowcast_requires_warning_context(tmp_path: Path) -> None:
    db_path = tmp_path / "market.duckdb"
    _write_minimal_ohlcv(db_path)

    result = compute_trough_nowcast(
        db_path=db_path,
        actual_date=pd.Timestamp("2026-07-10"),
        latest_features={"drawdown": -0.08, "total_risk_score": 3, "tail_risk_score": 0},
        ncf_live_overlay={},
        market_state={"state": "bull_trend", "risk_level": "risk_on"},
    )

    assert result["state"] == "NO_TROUGH"
    assert result["context_active"] is False


def test_trough_nowcast_warning_when_rebound_lacks_risk_unwind_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "market.duckdb"
    _write_minimal_ohlcv(db_path)

    result = compute_trough_nowcast(
        db_path=db_path,
        actual_date=pd.Timestamp("2026-07-10"),
        latest_features={"drawdown": -0.08, "total_risk_score": 9, "tail_risk_score": 2},
        ncf_live_overlay={"a2118_extreme_risk_warning": {"active": True}},
        market_state={"state": "crash_risk", "risk_level": "severe"},
    )

    assert result["state"] == "CAPITULATION_WARNING"
    assert result["context_active"] is True
    assert result["recommended_execution_staging_fraction"] is None
    assert result["capitulation_score"] >= 3
    assert result["reentry_confirmation_score"] >= 3
    assert result["full_reentry_checks"]["full_reentry_confirmed"] is False
    market_proxy = result["inputs"]["market_proxy"]
    assert market_proxy["latest_0050_close"] is not None
    assert market_proxy["prior_0050_3d_low"] is not None
    assert market_proxy["no_fresh_0050_lower_low_3d"] is True
