from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_systemic_bubble_srr_overlap import (
    build_overlap_report,
    build_systemic_daily_frame,
    write_overlap,
)


def _write_fixture_db(db_path: Path, dates: pd.DatetimeIndex) -> None:
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE ohlcv (
              ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE,
              close DOUBLE, volume BIGINT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE external_market_ohlcv (
              provider VARCHAR, ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE,
              low DOUBLE, close DOUBLE, volume BIGINT
            )
            """
        )
        rows = []
        for i, dt in enumerate(dates):
            bubble = 1.006 if 130 <= i <= 210 else 1.001
            shock = 0.95 if 211 <= i <= 220 else 1.0
            base_0050 = 100.0 * (1.001**i) * (bubble ** max(0, min(i, 210) - 129)) * shock
            close_map = {
                "0050.TW": base_0050,
                "00631L.TW": 50.0 * (base_0050 / 100.0) ** 1.8,
                "00632R.TW": 20.0 * (100.0 / base_0050) ** 0.9,
            }
            for ticker, close in close_map.items():
                volume = 1_000_000 + (i * 1000)
                if ticker == "00631L.TW" and 180 <= i <= 220:
                    volume *= 4
                rows.append((ticker, str(dt.date()), close, close, close, close, volume))
            conn.execute(
                "INSERT INTO external_market_ohlcv VALUES ('yfinance', '2330.TW', ?, ?, ?, ?, ?, ?)",
                [str(dt.date()), base_0050 * 8.0, base_0050 * 8.0, base_0050 * 8.0, base_0050 * 8.0, 5000],
            )
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


def _write_srr_frame(path: Path, dates: pd.DatetimeIndex) -> None:
    rows = []
    for i, dt in enumerate(dates[-80:]):
        event = 35 <= i <= 48
        rows.append(
            {
                "date": str(dt.date()),
                "no_add_active": i in {33, 34, 35, 36},
                "forward_ret_00631l_h5": -0.05 if event else 0.01,
                "forward_ret_0050_h5": -0.02 if event else 0.005,
                "forward_rel_00631l_vs_0050_h5": -0.03 if event else 0.005,
                "forward_mdd_00631l_h5": -0.09 if event else -0.01,
                "no_add_label_h5": event,
                "forward_ret_00631l_h10": -0.08 if event else 0.015,
                "forward_ret_0050_h10": -0.03 if event else 0.007,
                "forward_rel_00631l_vs_0050_h10": -0.05 if event else 0.008,
                "forward_mdd_00631l_h10": -0.12 if event else -0.012,
                "no_add_label_h10": event,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_systemic_daily_frame_has_daily_states() -> None:
    dates = pd.bdate_range("2025-01-01", periods=260)
    base = 100.0 * np.cumprod(np.full(len(dates), 1.001))
    close = pd.DataFrame(
        {
            "0050.TW": base,
            "00631L.TW": 50.0 * (base / 100.0) ** 1.7,
            "00632R.TW": 20.0 * (100.0 / base) ** 0.8,
            "2330.TW": base * 8.0,
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            "0050.TW": np.full(len(dates), 1_000_000.0),
            "00631L.TW": np.linspace(1_000_000.0, 2_000_000.0, len(dates)),
            "00632R.TW": np.full(len(dates), 800_000.0),
            "2330.TW": np.full(len(dates), 30_000_000.0),
        },
        index=dates,
    )
    frame = build_systemic_daily_frame(pd.concat({"close": close, "volume": volume}, axis=1))

    assert "systemic_score" in frame.columns
    assert "overall_state" in frame.columns
    assert frame["date"].is_monotonic_increasing
    assert set(frame["overall_state"]).issubset({"research_watch", "blocked_for_leverage_add"})


def test_build_overlap_report_keeps_systemic_research_only(tmp_path: Path) -> None:
    dates = pd.bdate_range("2025-01-01", periods=260)
    db_path = tmp_path / "stock_data.db"
    srr_frame = tmp_path / "srr.csv"
    _write_fixture_db(db_path, dates)
    _write_srr_frame(srr_frame, dates)

    report, frame = build_overlap_report(
        db_path=db_path,
        srr_frame_path=srr_frame,
        as_of=str(dates[-1].date()),
        start=str(dates[0].date()),
    )

    assert report["report_type"] == "group_a_plus_systemic_bubble_srr_overlap"
    assert report["status"] == "blocked"
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["allow_00631l_add"] is False
    assert "systemic_watch_or_worse" in report["summary"]
    assert "systemic_time_watch_and_coupling_elevated" in report["summary"]
    assert report["candidate_improvement"]["signal"] == "systemic_time_watch_and_coupling_elevated"
    assert "union_srr_or_systemic_watch" in report["summary"]
    assert "systemic_bubble_overlap_research_only" in report["blocking_reasons"]
    assert "systemic_systemic_score" in frame.columns


def test_write_overlap_writes_report_frame_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "systemic_bubble_srr_overlap.json"
    history = tmp_path / "history"
    report = {
        "as_of": "2026-07-20",
        "actual_overlap_end": "2026-07-16",
        "report_type": "group_a_plus_systemic_bubble_srr_overlap",
    }
    frame = pd.DataFrame({"x": [1]})

    write_overlap(report, frame, output, history)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["frame_output"].endswith("systemic_bubble_srr_overlap_frame.csv")
    assert output.with_name("systemic_bubble_srr_overlap_frame.csv").exists()
    assert (history / "systemic_bubble_srr_overlap_20260720.json").exists()
