from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_sin_lite_crash_window_backtest import build_backtest, write_backtest


def _write_fixture_db(db_path: Path) -> None:
    dates = pd.bdate_range("2020-01-01", periods=180)
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "0056.TW", "00679B.TWO", "00713.TW", "2330.TW", "2454.TW"]
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
            [(ticker, ticker, "stock", "sector", "industry", "fixture", True) for ticker in tickers],
        )
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        conn.execute("CREATE TABLE external_market_ohlcv (provider VARCHAR, ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = []
        for i, dt in enumerate(dates):
            shock = -0.03 if 65 <= i <= 82 else 0.001
            for j, ticker in enumerate(tickers):
                close = 100.0 * (1.0 + 0.002 * i + shock * (1.0 + j * 0.03))
                rows.append((ticker, str(dt.date()), close))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def test_sin_lite_crash_backtest_stays_research_only(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _write_fixture_db(db_path)

    payload = build_backtest(
        db_path=db_path,
        as_of="2020-09-30",
        windows=[{"name": "fixture_crash", "start": "2020-03-01", "end": "2020-04-30", "type": "crash_window"}],
        lookback=60,
        min_history=30,
        min_tickers=6,
        edge_threshold=0.2,
    )

    assert payload["report_type"] == "group_a_plus_sin_lite_crash_window_backtest"
    assert payload["status"] == "blocked"
    assert payload["decision"]["promotion_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["windows"][0]["status"] == "available"
    assert payload["aggregate"]["stress_window_days"] > 0
    assert payload["aggregate"]["stress_window_watch_or_worse_rate"] is not None
    assert "sin_lite_proxy_not_paper_equivalent" in payload["blocking_reasons"]


def test_write_backtest_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sin_lite_backtest.json"
    history = tmp_path / "history"
    payload = {
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
        "report_type": "group_a_plus_sin_lite_crash_window_backtest",
    }

    write_backtest(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert json.loads((history / "sin_lite_crash_window_backtest_20260720.json").read_text(encoding="utf-8")) == payload
