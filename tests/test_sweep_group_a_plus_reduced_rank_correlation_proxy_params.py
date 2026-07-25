from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.sweep_group_a_plus_reduced_rank_correlation_proxy_params import run_sweep, write_sweep


def _write_fixture_db(db_path: Path) -> None:
    dates = pd.bdate_range("2026-01-01", periods=100)
    tickers = [f"T{i:02d}.TW" for i in range(12)]
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        rows = []
        for i, dt in enumerate(dates):
            for j, ticker in enumerate(tickers):
                common = 0.2 * i
                idiosyncratic = ((i + j) % 7) * 0.03
                rows.append((ticker, str(dt.date()), 100.0 + common + j + idiosyncratic))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def test_run_sweep_keeps_reduced_rank_proxy_research_only(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    _write_fixture_db(db_path)

    payload = run_sweep(
        db_path=db_path,
        as_of="2026-05-31",
        windows=[20, 30],
        min_histories=[40],
        analysis_lookbacks=[80],
        min_tickers_values=[10],
    )

    assert payload["report_type"] == "group_a_plus_reduced_rank_correlation_proxy_param_sweep"
    assert payload["status"] == "blocked"
    assert payload["grid"]["candidate_count"] == 2
    assert payload["decision"]["promotion_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
    assert "reduced_rank_proxy_sweep_research_only" in payload["blocking_reasons"]


def test_write_sweep_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sweep.json"
    history = tmp_path / "history"
    payload = {
        "as_of": "2026-07-20",
        "report_type": "group_a_plus_reduced_rank_correlation_proxy_param_sweep",
    }

    write_sweep(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    history_file = history / "reduced_rank_correlation_proxy_param_sweep_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == payload
