from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

from scripts.evaluate.evaluate_group_a_plus_systemic_bubble_time_at_risk_review import build_review, write_report, _load_panel


def test_build_review_is_research_only() -> None:
    dates = pd.date_range("2020-01-01", periods=380, freq="B")
    base = 100.0 * np.cumprod(np.full(len(dates), 1.0008))
    close = pd.DataFrame(
        {
            "0050.TW": base,
            "00631L.TW": 50.0 * np.cumprod(np.full(len(dates), 1.0014)),
            "00632R.TW": 20.0 * np.cumprod(np.full(len(dates), 0.9992)),
            "2330.TW": base * 8.0,
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            "0050.TW": np.full(len(dates), 1_000_000.0),
            "00631L.TW": np.full(len(dates), 2_000_000.0),
            "00632R.TW": np.full(len(dates), 900_000.0),
            "2330.TW": np.full(len(dates), 30_000_000.0),
        },
        index=dates,
    )
    panel = pd.concat({"close": close, "volume": volume}, axis=1)

    report = build_review(panel)

    assert report["report_type"] == "group_a_plus_systemic_bubble_time_at_risk_review"
    assert report["decision"]["allow_00631l_add"] is False
    assert report["decision"]["promote_to_live"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert "time_at_risk_state" in report["states"]
    assert "etf_coupling_score" in report["latest"]


def test_write_report_writes_output_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    latest = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "x",
        "latest": {"date": "2026-07-17"},
        "decision": {"allow_00631l_add": False},
    }

    write_report(report, output, latest, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert json.loads(latest.read_text(encoding="utf-8")) == report
    assert json.loads((history / "20260717.json").read_text(encoding="utf-8")) == report


def test_load_panel_uses_external_market_ohlcv_for_2330(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE ohlcv (
              ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE,
              close DOUBLE, volume BIGINT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE external_market_ohlcv (
              provider VARCHAR, ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE,
              low DOUBLE, close DOUBLE, volume BIGINT
            )
            """
        )
        dates = pd.date_range("2026-01-01", periods=80, freq="B")
        for idx, dt in enumerate(dates):
            for ticker, close in {
                "0050.TW": 100.0 + idx,
                "00631L.TW": 50.0 + idx * 2.0,
                "00632R.TW": 20.0 - idx * 0.05,
            }.items():
                con.execute(
                    "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [ticker, str(dt.date()), close, close, close, close, 1000],
                )
            con.execute(
                "INSERT INTO external_market_ohlcv VALUES ('yfinance', '2330.TW', ?, ?, ?, ?, ?, ?)",
                [str(dt.date()), 800.0 + idx, 800.0 + idx, 800.0 + idx, 800.0 + idx, 5000],
            )
    finally:
        con.close()

    panel = _load_panel(db_path, ("0050.TW", "00631L.TW", "00632R.TW", "2330.TW"), "2026-01-01", "2026-04-30")

    assert ("close", "2330.TW") in panel.columns
    assert panel[("close", "2330.TW")].notna().any()
