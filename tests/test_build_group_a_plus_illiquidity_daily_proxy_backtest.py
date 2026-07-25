from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_illiquidity_daily_proxy_backtest import build_backtest, write_backtest


def test_build_backtest_keeps_daily_proxy_research_only(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    with duckdb.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE ohlcv (
                ticker VARCHAR,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        rows = []
        for ticker in ("0050.TW", "00631L.TW", "00632R.TW"):
            price = 100.0
            for day in range(95):
                dt = str(date(2020, 1, 1) + timedelta(days=day))
                if day == 75:
                    open_ = price
                    high = price * 1.02
                    low = price * 0.88
                    close = price * 0.90
                    volume = 5000
                    price = close
                else:
                    price *= 1.001
                    open_ = price
                    high = price * 1.01
                    low = price * 0.99
                    close = price
                    volume = 1000 + day
                rows.append((ticker, dt, open_, high, low, close, volume))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    backtest = build_backtest(
        db_path=db,
        as_of="2020-03-31",
        windows=[
            {
                "name": "fixture_2020_crash",
                "start": "2020-03-01",
                "end": "2020-03-31",
                "type": "crash_window",
            }
        ],
    )

    assert backtest["report_type"] == "group_a_plus_illiquidity_daily_proxy_backtest"
    assert backtest["status"] == "blocked"
    assert backtest["decision"]["promotion_allowed"] is False
    assert backtest["decision"]["allow_00631l_add"] is False
    assert backtest["aggregate"]["stress_window_days"] > 0
    assert backtest["aggregate"]["stress_window_elevated_or_worse_rate"] is not None
    assert backtest["windows"][0]["status"] == "available"
    assert backtest["windows"][0]["elevated_or_worse_days"] >= 1
    assert "daily_ohlcv_proxy_not_paper_equivalent" in backtest["blocking_reasons"]


def test_write_backtest_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "backtest.json"
    history = tmp_path / "history"
    payload = {
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
        "report_type": "group_a_plus_illiquidity_daily_proxy_backtest",
    }

    write_backtest(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    history_file = history / "illiquidity_daily_proxy_backtest_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == payload
