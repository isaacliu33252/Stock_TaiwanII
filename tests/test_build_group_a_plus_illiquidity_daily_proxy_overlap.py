from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_illiquidity_daily_proxy_overlap import build_overlap, write_overlap


def _make_db(path: Path) -> None:
    with duckdb.connect(str(path)) as conn:
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
                dt = str(date(2026, 1, 1) + timedelta(days=day))
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


def _make_srr_frame(path: Path) -> None:
    dates = pd.date_range("2026-03-01", "2026-04-05", freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "systemic_fragility_score": [0.8 if i in {15, 16} else 0.2 for i in range(len(dates))],
            "no_add_active": [i in {15, 20} for i in range(len(dates))],
            "graph_density": [0.7 if i in {15, 16} else 0.4 for i in range(len(dates))],
            "forward_ret_00631l_h5": [-0.04] * len(dates),
            "forward_rel_00631l_vs_0050_h5": [-0.02] * len(dates),
            "forward_mdd_00631l_h5": [-0.06] * len(dates),
            "no_add_label_h5": [True] * len(dates),
            "forward_ret_00631l_h10": [-0.05] * len(dates),
            "forward_rel_00631l_vs_0050_h10": [-0.02] * len(dates),
            "forward_mdd_00631l_h10": [-0.07] * len(dates),
            "no_add_label_h10": [True] * len(dates),
        }
    )
    frame.to_csv(path, index=False)


def test_build_overlap_keeps_proxy_research_only(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    srr = tmp_path / "srr.csv"
    crash = tmp_path / "crash.json"
    _make_db(db)
    _make_srr_frame(srr)
    crash.write_text(
        json.dumps(
            {
                "as_of": "2026-04-05",
                "watch_level": "watch",
                "alert_active": False,
                "category_score": 1,
            }
        ),
        encoding="utf-8",
    )

    report, frame = build_overlap(db_path=db, srr_frame_path=srr, crash_alert_path=crash, as_of="2026-04-05")

    assert report["report_type"] == "group_a_plus_illiquidity_daily_proxy_overlap"
    assert report["status"] == "blocked"
    assert report["decision"]["promotion_allowed"] is False
    assert report["decision"]["allow_00631l_add"] is False
    assert report["rows"] == len(frame)
    assert "illiquidity_elevated_vs_srr_no_add" in report["overlap"]
    assert report["latest_alignment"]["crash_risk_alert_watch_level"] == "watch"
    assert "daily_ohlcv_proxy_not_paper_equivalent" in report["blocking_reasons"]


def test_write_overlap_writes_report_frame_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "overlap.json"
    history = tmp_path / "history"
    frame = pd.DataFrame({"x": [1]}, index=pd.to_datetime(["2026-07-17"]))
    report = {
        "as_of": "2026-07-20",
        "actual_overlap_end": "2026-07-16",
        "report_type": "group_a_plus_illiquidity_daily_proxy_overlap",
    }

    write_overlap(report, frame, output, history)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["report_type"] == "group_a_plus_illiquidity_daily_proxy_overlap"
    assert (tmp_path / "latest" / "overlap_frame.csv").exists()
    history_file = history / "illiquidity_daily_proxy_overlap_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8"))["actual_overlap_end"] == "2026-07-16"
