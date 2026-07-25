from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.sweep_group_a_plus_sin_lite_params import run_sweep, write_sweep


def _write_fixture_db(db_path: Path) -> None:
    dates = pd.bdate_range("2020-01-01", periods=120)
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
            [(ticker, ticker, "stock", "sector", "industry", "fixture", True) for ticker in tickers],
        )
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        conn.execute("CREATE TABLE external_market_ohlcv (provider VARCHAR, ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = []
        for i, dt in enumerate(dates):
            stress = -0.02 if 45 <= i <= 55 else 0.001
            for j, ticker in enumerate(tickers):
                rows.append((ticker, str(dt.date()), 100.0 + i * 0.1 + stress * 100.0 * (j + 1)))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def test_run_sweep_keeps_candidates_research_only(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _write_fixture_db(db_path)

    payload = run_sweep(
        db_path=db_path,
        as_of="2020-06-30",
        lookbacks=[40, 60],
        min_histories=[30],
        min_tickers_values=[4],
        edge_thresholds=[0.2, 0.4],
    )

    assert payload["report_type"] == "group_a_plus_sin_lite_param_sweep"
    assert payload["grid"]["candidate_count"] == 4
    assert payload["best_candidate"]["params"]["lookback"] in {40, 60}
    assert payload["decision"]["promotion_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert "sin_lite_sweep_research_only" in payload["blocking_reasons"]


def test_write_sweep_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sweep.json"
    history = tmp_path / "history"
    payload = {"as_of": "2026-07-20", "report_type": "group_a_plus_sin_lite_param_sweep"}

    write_sweep(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert json.loads((history / "sin_lite_param_sweep_20260720.json").read_text(encoding="utf-8")) == payload
