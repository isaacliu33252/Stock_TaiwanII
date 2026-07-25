from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.fetch.backfill_group_a_plus_ticker_metadata import backfill_metadata


def test_backfill_metadata_creates_static_mapping_without_changing_ohlcv(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    output = tmp_path / "ticker_metadata_backfill_report.json"
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        conn.execute("CREATE TABLE external_market_ohlcv (provider VARCHAR, ticker VARCHAR, dt DATE, close DOUBLE)")
        conn.executemany(
            "INSERT INTO ohlcv VALUES (?, ?, ?)",
            [
                ("0050.TW", "2026-07-17", 100.0),
                ("00631L.TW", "2026-07-17", 200.0),
                ("wf", "2024-10-07", 1.0),
            ],
        )
        conn.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '2330.TW', '2026-07-17', 1100.0)")

    report = backfill_metadata(db_path=db_path, output_path=output, history_dir=None)

    assert report["decision"]["metadata_backfilled"] is True
    assert report["decision"]["price_data_changed"] is False
    assert report["ohlcv_tickers_missing_metadata"] == []
    assert "2330.TW" in report["metadata_tickers_without_ohlcv"]
    assert "2330.TW" in report["external_market_tickers_with_metadata"]
    assert output.exists()

    with duckdb.connect(str(db_path), read_only=True) as conn:
        ohlcv_count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        wf_row = conn.execute(
            """
            SELECT included_in_sin_lite, exclusion_reason
            FROM ticker_metadata
            WHERE ticker = 'wf'
            """
        ).fetchone()
        leverage_row = conn.execute(
            """
            SELECT asset_type, is_leveraged_etf, group_a_plus_role
            FROM ticker_metadata
            WHERE ticker = '00631L.TW'
            """
        ).fetchone()

    assert ohlcv_count == 3
    assert wf_row == (False, "non_ticker_walk_forward_artifact")
    assert leverage_row == ("leveraged_equity_etf", True, "leverage_leg")
    assert json.loads(output.read_text(encoding="utf-8"))["table"] == "ticker_metadata"
