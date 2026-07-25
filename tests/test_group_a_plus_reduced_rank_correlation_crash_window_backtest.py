from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_reduced_rank_correlation_crash_window_backtest import (
    build_backtest,
    write_backtest,
)


def _write_fixture_db(db_path: Path) -> None:
    dates = pd.bdate_range("2020-01-01", periods=180)
    tickers = [f"T{i:02d}.TW" for i in range(12)]
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = []
        for i, dt in enumerate(dates):
            stress = -0.04 if 65 <= i <= 90 else 0.001
            for j, ticker in enumerate(tickers):
                common = i * 0.1
                cross = stress * (j + 1) * 5.0
                rows.append((ticker, str(dt.date()), 100.0 + common + j + cross))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def test_reduced_rank_crash_window_backtest_stays_research_only(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _write_fixture_db(db_path)

    payload = build_backtest(
        db_path=db_path,
        as_of="2020-09-30",
        windows=[{"name": "fixture_stress", "start": "2020-03-15", "end": "2020-05-15", "type": "stress_window"}],
        window=20,
        min_history=40,
        min_tickers=10,
        baseline_lookback=60,
    )

    assert payload["report_type"] == "group_a_plus_reduced_rank_correlation_crash_window_backtest"
    assert payload["status"] == "blocked"
    assert payload["decision"]["promotion_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
    assert payload["windows"][0]["status"] == "available"
    assert payload["aggregate"]["stress_window_days"] > 0
    assert payload["aggregate"]["stress_window_watch_or_worse_rate"] is not None
    assert "reduced_rank_proxy_not_paper_equivalent" in payload["blocking_reasons"]


def test_write_backtest_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "backtest.json"
    history = tmp_path / "history"
    payload = {
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
        "report_type": "group_a_plus_reduced_rank_correlation_crash_window_backtest",
    }

    write_backtest(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    history_file = history / "reduced_rank_correlation_crash_window_backtest_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == payload
