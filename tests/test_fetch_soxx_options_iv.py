from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_00631l_multisource_crash_risk import _load_cross_market_features
from scripts.fetch.fetch_soxx_options_iv import build_soxx_iv_snapshot, write_snapshot


@dataclass
class FakeOptionChain:
    calls: pd.DataFrame
    puts: pd.DataFrame


class FakeTicker:
    options = ["2026-08-14", "2026-09-18"]
    fast_info = {"last_price": 100.0}

    def history(self, *args, **kwargs) -> pd.DataFrame:
        return pd.DataFrame({"Close": [100.0]})

    def option_chain(self, expiry: str) -> FakeOptionChain:
        calls = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "impliedVolatility": [0.28, 0.30, 0.33],
                "volume": [10, 20, 30],
                "openInterest": [100, 200, 300],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "impliedVolatility": [0.36, 0.32, 0.31],
                "volume": [40, 50, 60],
                "openInterest": [400, 500, 600],
            }
        )
        return FakeOptionChain(calls=calls, puts=puts)


def test_build_soxx_iv_snapshot_uses_nearest_30d_expiry() -> None:
    snapshot = build_soxx_iv_snapshot(
        ticker_obj=FakeTicker(),
        snapshot_date="2026-07-12",
        target_dte=30,
    )

    assert snapshot["underlying"] == "SOXX"
    assert snapshot["expiry"].isoformat() == "2026-08-14"
    assert snapshot["dte"] == 33
    assert snapshot["atm_iv"] == 0.31
    assert round(snapshot["put_call_iv_skew"], 6) == 0.03
    assert snapshot["put_call_volume_ratio"] == 2.5


class FakeTickerWithBadNearZeroIV(FakeTicker):
    def option_chain(self, expiry: str) -> FakeOptionChain:
        calls = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "impliedVolatility": [0.28, 0.001, 0.33],
                "volume": [10, 20, 30],
                "openInterest": [100, 200, 300],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "impliedVolatility": [0.36, 0.002, 0.31],
                "volume": [40, 50, 60],
                "openInterest": [400, 500, 600],
            }
        )
        return FakeOptionChain(calls=calls, puts=puts)


def test_build_soxx_iv_snapshot_ignores_near_zero_placeholder_iv() -> None:
    snapshot = build_soxx_iv_snapshot(
        ticker_obj=FakeTickerWithBadNearZeroIV(),
        snapshot_date="2026-07-12",
        target_dte=30,
    )

    assert snapshot["atm_call_iv"] == 0.28
    assert snapshot["atm_put_iv"] == 0.36
    assert snapshot["atm_iv"] == 0.32
    assert snapshot["atm_iv"] >= 0.05


def test_external_options_iv_features_feed_cross_market_alert(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE external_market_ohlcv (
                provider TEXT,
                ticker TEXT,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                source TEXT,
                fetched_at TIMESTAMP
            )
            """
        )
        dates = pd.date_range("2026-01-01", periods=80, freq="D")
        rows = []
        for i, dt in enumerate(dates):
            rows.append(("yfinance", "SOXX", dt.date(), 100 + i, 100 + i, 100 + i, 100 + i, 1000, "test", None))
            rows.append(("yfinance", "^VIX", dt.date(), 20 + i * 0.05, 20 + i * 0.05, 20 + i * 0.05, 20 + i * 0.05, 0, "test", None))
        con.executemany("INSERT INTO external_market_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        con.close()

    for i, dt in enumerate(pd.date_range("2026-01-01", periods=80, freq="D")):
        write_snapshot(
            db_path,
            {
                "provider": "yfinance",
                "underlying": "SOXX",
                "dt": dt.date(),
                "spot": 100.0 + i,
                "expiry": (dt + pd.Timedelta(days=30)).date(),
                "dte": 30,
                "atm_iv": 0.20 + i * 0.002,
                "atm_call_iv": 0.20 + i * 0.002,
                "atm_put_iv": 0.21 + i * 0.002,
                "otm_put_iv_95": 0.24 + i * 0.002,
                "otm_call_iv_105": 0.20 + i * 0.001,
                "put_call_iv_skew": 0.04 + i * 0.001,
                "put_call_volume_ratio": 1.0 + i * 0.01,
                "put_call_oi_ratio": 1.2 + i * 0.01,
                "contract_count": 100,
                "source": "test",
                "fetched_at": pd.Timestamp("2026-07-12"),
            },
        )

    features = _load_cross_market_features(db_path, dates)
    last = features.iloc[-1]

    assert pd.notna(last["soxx_atm_iv30_z252"])
    assert pd.notna(last["soxx_iv_rank_252"])
    assert pd.notna(last["soxx_iv_minus_rv20_z252"])
    assert pd.notna(last["soxx_put_call_iv_skew_z252"])
