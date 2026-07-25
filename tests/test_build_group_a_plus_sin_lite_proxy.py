from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_sin_lite_proxy import build_proxy, write_proxy


def _write_fixture_db(db_path: Path) -> None:
    dates = pd.bdate_range("2026-01-01", periods=110)
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "0056.TW", "00679B.TWO", "00713.TW"]
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE ticker_metadata (
                ticker VARCHAR,
                canonical_ticker VARCHAR,
                asset_type VARCHAR,
                sector VARCHAR,
                industry VARCHAR,
                group_a_plus_role VARCHAR,
                included_in_sin_lite BOOLEAN
            )
            """
        )
        conn.executemany(
            "INSERT INTO ticker_metadata VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("0050.TW", "0050.TW", "equity_etf", "broad_market", "large_cap", "core", True),
                ("00631L.TW", "00631L.TW", "leveraged_equity_etf", "leveraged", "large_cap", "leverage", True),
                ("00632R.TW", "00632R.TW", "inverse_equity_etf", "inverse", "large_cap", "inverse", True),
                ("0056.TW", "0056.TW", "equity_etf", "dividend", "high_dividend", "income", True),
                ("00679B.TWO", "00679B.TWO", "bond_etf", "duration", "treasury", "bond", True),
                ("00713.TW", "00713.TW", "equity_etf", "defensive", "low_vol", "defensive", True),
                ("2330.TW", "2330.TW", "stock", "semiconductors", "foundry", "anchor", True),
                ("wf", "wf", "test_artifact", "excluded", "excluded", "excluded", False),
            ],
        )
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        conn.execute("CREATE TABLE external_market_ohlcv (provider VARCHAR, ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = []
        ext_rows = []
        for i, dt in enumerate(dates):
            base = 100.0 + i * 0.2
            for j, ticker in enumerate(tickers):
                sign = -1.0 if ticker == "00632R.TW" else 1.0
                rows.append((ticker, str(dt.date()), base * (1.0 + sign * j * 0.002)))
            ext_rows.append(("yfinance", "2330.TW", str(dt.date()), base * 1.1))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)
        conn.executemany("INSERT INTO external_market_ohlcv VALUES (?, ?, ?, ?)", ext_rows)


def test_build_proxy_uses_metadata_and_external_2330_without_live_permission(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _write_fixture_db(db_path)

    payload = build_proxy(db_path=db_path, as_of="2026-06-30", lookback=100, min_history=80, edge_threshold=0.2)

    assert payload["report_type"] == "group_a_plus_sin_lite_proxy"
    assert payload["method"]["paper_equivalent"] is False
    assert payload["decision"]["sin_lite_available_for_shadow_review"] is True
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["auto_rebalance_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert "2330.TW" in payload["coverage"]["usable_tickers"]
    assert "wf" not in payload["coverage"]["usable_tickers"]
    assert payload["coverage"]["usable_ticker_count"] >= 6
    assert payload["latest"]["sin_lite_score"] is not None
    assert "sin_lite_proxy_not_validated_for_live_weight_change" in payload["blocking_reasons"]


def test_write_proxy_writes_latest_and_history(tmp_path: Path) -> None:
    payload = {"as_of": "2026-07-20", "actual_data_end": "2026-07-17"}
    output = tmp_path / "latest" / "sin_lite_proxy.json"
    history = tmp_path / "history"

    write_proxy(payload, output, history)

    assert output.exists()
    assert (history / "sin_lite_proxy_20260720.json").exists()
