from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_sin_lite_srr_overlap import build_overlap_report, write_overlap


def _write_fixture_db(db_path: Path, dates: pd.DatetimeIndex) -> None:
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "0056.TW", "00679B.TWO", "00713.TW", "2330.TW"]
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
            stress = -0.02 if 45 <= i <= 58 else 0.001
            for j, ticker in enumerate(tickers):
                close = 100.0 + i * 0.1 + stress * 100.0 * (j + 1)
                rows.append((ticker, str(dt.date()), close))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", rows)


def _write_srr_frame(path: Path, dates: pd.DatetimeIndex) -> None:
    rows = []
    for i, dt in enumerate(dates[-40:]):
        rows.append(
            {
                "date": str(dt.date()),
                "no_add_active": i in {5, 6},
                "forward_ret_00631l_h5": -0.04 if 5 <= i <= 12 else 0.01,
                "forward_ret_0050_h5": -0.01 if 5 <= i <= 12 else 0.005,
                "forward_rel_00631l_vs_0050_h5": -0.03 if 5 <= i <= 12 else 0.005,
                "forward_mdd_00631l_h5": -0.08 if 5 <= i <= 12 else -0.01,
                "no_add_label_h5": 5 <= i <= 12,
                "forward_ret_00631l_h10": -0.05 if 5 <= i <= 12 else 0.015,
                "forward_ret_0050_h10": -0.01 if 5 <= i <= 12 else 0.007,
                "forward_rel_00631l_vs_0050_h10": -0.04 if 5 <= i <= 12 else 0.008,
                "forward_mdd_00631l_h10": -0.09 if 5 <= i <= 12 else -0.012,
                "no_add_label_h10": 5 <= i <= 12,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_overlap_report_keeps_sin_lite_research_only(tmp_path: Path) -> None:
    dates = pd.bdate_range("2020-01-01", periods=110)
    db_path = tmp_path / "stock_data.db"
    srr_frame = tmp_path / "srr.csv"
    param_sweep = tmp_path / "sweep.json"
    _write_fixture_db(db_path, dates)
    _write_srr_frame(srr_frame, dates)
    param_sweep.write_text(
        json.dumps({"best_candidate": {"params": {"lookback": 40, "min_history": 25, "edge_threshold": 0.2}}}),
        encoding="utf-8",
    )

    report, frame = build_overlap_report(
        db_path=db_path,
        srr_frame_path=srr_frame,
        param_sweep_path=param_sweep,
        as_of=str(dates[-1].date()),
    )

    assert report["report_type"] == "group_a_plus_sin_lite_srr_overlap"
    assert report["status"] == "blocked"
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["allow_00631l_add"] is False
    assert report["systemic_bubble_overlap"]["status"] == "not_available"
    assert "srr_no_add_active" in report["summary"]
    assert "union_srr_or_sin_tuned_watch" in report["summary"]
    assert "sin_tuned_watch_without_srr" in report["summary"]
    assert "sin_lite_overlap_research_only" in report["blocking_reasons"]
    assert "sin_tuned_watch" in frame.columns


def test_write_overlap_writes_latest_frame_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "overlap.json"
    frame_output = tmp_path / "latest" / "overlap.csv"
    history = tmp_path / "history"
    report = {"as_of": "2026-07-20", "report_type": "group_a_plus_sin_lite_srr_overlap"}
    frame = pd.DataFrame({"x": [1]})

    write_overlap(report, frame, output, frame_output, history)

    assert json.loads(output.read_text(encoding="utf-8"))["frame_output"] == str(frame_output)
    assert frame_output.exists()
    assert (history / "sin_lite_srr_overlap_20260720.json").exists()
