from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.backtest_group_a_plus_letf_liquidity_feedback_watch_shadow import build_report, write_report


def _db(path: Path) -> Path:
    con = duckdb.connect(str(path))
    con.execute(
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
    for day in range(90):
        date = str((pd.Timestamp("2026-01-01") + pd.offsets.BDay(day)).date())
        shock = day == 70
        for ticker, multiplier in (("0050.TW", 1.0), ("00631L.TW", 2.0), ("00632R.TW", 0.1)):
            close = (100.0 + day * 0.1) * multiplier
            high = close * (1.08 if shock else 1.01)
            low = close * (0.90 if shock else 0.99)
            volume = 5_000_000 if shock else 1_000_000
            if shock and ticker == "00631L.TW":
                close *= 0.9
            con.execute("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", [ticker, date, close, high, low, close, volume])
    con.close()
    return path


def test_build_letf_liquidity_feedback_report_from_db(tmp_path: Path) -> None:
    report = build_report(
        db_path=_db(tmp_path / "stock.db"),
        as_of="2026-05-15",
        start="2026-01-01",
        range_threshold=0.03,
        volume_z_min=1.0,
        dislocation_z_min=1.0,
        min_trigger_count=1,
    )

    assert report["as_of"] == "2026-05-15"
    assert report["input_coverage"]["trigger_count"] >= 1
    assert report["decision"]["creates_orders"] is False


def test_write_letf_liquidity_feedback_report_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "report.json"
    history = tmp_path / "history"
    report = {"as_of": "2026-08-07", "decision": {"target_weight_change_allowed": False}}

    write_report(report, output_path=output, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "letf_liquidity_feedback_watch_shadow_backtest_20260807.json").exists()
