from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.evaluate_ncf_panel_coverage import audit_panel_coverage


def _write_panel(path: Path, dates: list[str], *, live_tail: bool = False) -> Path:
    frame = pd.DataFrame({"date": dates, "ensemble_prob_up": [0.5] * len(dates)})
    if live_tail:
        frame["is_live"] = [False] * (len(dates) - 1) + [True]
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _write_db(path: Path, ticker: str, latest: str) -> Path:
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE)")
        con.execute("INSERT INTO ohlcv VALUES (?, ?)", [ticker, latest])
    finally:
        con.close()
    return path


def test_panel_coverage_passes_when_panel_reaches_latest_ohlcv(tmp_path: Path) -> None:
    db = _write_db(tmp_path / "stock.duckdb", "00631L.TW", "2026-07-02")
    panel = _write_panel(tmp_path / "panel.csv", ["2026-07-01", "2026-07-02"], live_tail=True)

    report = audit_panel_coverage([(panel, "00631L.TW")], db_path=db)

    assert report["overall_status"] == "pass"
    assert report["panels"][0]["status"] == "pass"
    assert report["panels"][0]["live_tail_rows"] == 1


def test_panel_coverage_warns_when_gap_is_label_limited(tmp_path: Path) -> None:
    db = _write_db(tmp_path / "stock.duckdb", "2330.TW", "2026-07-02")
    panel = _write_panel(tmp_path / "panel.csv", ["2026-06-03"])

    report = audit_panel_coverage([(panel, "2330.TW")], db_path=db, max_labeled_gap_bdays=21)

    assert report["overall_status"] == "warn"
    assert report["panels"][0]["status"] == "warn"
    assert report["panels"][0]["business_day_gap_to_latest"] <= 21


def test_panel_coverage_fails_when_gap_exceeds_label_horizon(tmp_path: Path) -> None:
    db = _write_db(tmp_path / "stock.duckdb", "2330.TW", "2026-07-31")
    panel = _write_panel(tmp_path / "panel.csv", ["2026-06-03"])

    report = audit_panel_coverage([(panel, "2330.TW")], db_path=db, max_labeled_gap_bdays=20)

    assert report["overall_status"] == "fail"
    assert report["panels"][0]["status"] == "fail"


def test_panel_coverage_supports_external_market_ohlcv_source(tmp_path: Path) -> None:
    db = tmp_path / "stock.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute("CREATE TABLE external_market_ohlcv (provider VARCHAR, ticker VARCHAR, dt DATE)")
        con.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '2330.TW', '2026-07-02')")
    finally:
        con.close()
    panel = _write_panel(tmp_path / "panel.csv", ["2026-07-02"])

    report = audit_panel_coverage(
        [(panel, "2330.TW", "external_market_ohlcv", "yfinance")],
        db_path=db,
    )

    assert report["overall_status"] == "pass"
    assert report["panels"][0]["source"] == "external_market_ohlcv"
    assert report["panels"][0]["latest_ohlcv_date"] == "2026-07-02"
