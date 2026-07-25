from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_reduced_rank_confirmation_overlap_backtest import (
    build_backtest,
    write_backtest,
)


def _write_fixture_db(db_path: Path) -> None:
    dates = pd.bdate_range("2020-01-01", periods=180)
    tickers = [f"T{i:02d}.TW" for i in range(12)]
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
        rows = []
        for i, dt in enumerate(dates):
            stress = -0.04 if 65 <= i <= 90 else 0.001
            for j, ticker in enumerate(tickers):
                rows.append((ticker, str(dt.date()), 100.0 + i * 0.1 + j + stress * (j + 1) * 5.0))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def test_confirmation_overlap_backtest_stays_research_only(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _write_fixture_db(db_path)

    payload, frame = build_backtest(
        db_path=db_path,
        as_of="2020-09-30",
        start="2020-01-01",
        windows=[{"name": "fixture_stress", "start": "2020-03-15", "end": "2020-05-15", "type": "stress_window"}],
    )

    assert payload["report_type"] == "group_a_plus_reduced_rank_confirmation_overlap_backtest"
    assert payload["status"] == "blocked"
    assert not frame.empty
    assert "reduced_watch_or_worse" in payload["summary"]
    assert "confirmed_reduced_rank" in payload["summary"]
    assert payload["decision"]["confirmation_gate_promotable"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
    assert "confirmation_overlap_research_only" in payload["blocking_reasons"]


def test_write_backtest_writes_latest_history_and_frame(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "overlap.json"
    history = tmp_path / "history"
    payload = {
        "as_of": "2026-07-20",
        "actual_data_end": "2026-07-17",
        "report_type": "group_a_plus_reduced_rank_confirmation_overlap_backtest",
    }
    frame = pd.DataFrame({"x": [1]}, index=[pd.Timestamp("2026-07-17")])

    write_backtest(payload, frame, output, history)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["report_type"] == payload["report_type"]
    assert Path(loaded["frame_output"]).exists()
    history_file = history / "reduced_rank_confirmation_overlap_backtest_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8"))["report_type"] == payload["report_type"]
