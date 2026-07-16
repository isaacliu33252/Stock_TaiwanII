from __future__ import annotations

import json
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from scripts.report.build_ncf_2330_checklist import build_checklist


def _write_prices(con: duckdb.DuckDBPyConnection, table: str, ticker: str, dates, closes, provider="yfinance") -> None:
    rows = []
    for dt, close in zip(dates, closes):
        if table == "external_market_ohlcv":
            rows.append((provider, ticker, str(pd.Timestamp(dt).date()), close, close, close, close, 1000.0))
        else:
            rows.append((ticker, str(pd.Timestamp(dt).date()), close, close, close, close, 1000.0))
    if table == "external_market_ohlcv":
        con.executemany(
            "INSERT INTO external_market_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    else:
        con.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


def _make_fixture(tmp: Path) -> tuple[Path, Path, Path]:
    db_path = tmp / "stock_data.db"
    results_dir = tmp / "results"
    results_dir.mkdir()
    project_root = tmp
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE external_market_ohlcv "
        "(provider VARCHAR, ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)"
    )
    con.execute(
        "CREATE TABLE ohlcv "
        "(ticker VARCHAR, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)"
    )
    con.execute(
        "CREATE TABLE stock_per_data "
        "(ticker VARCHAR, dt DATE, dividend_yield DOUBLE, per DOUBLE, pbr DOUBLE, source VARCHAR, updated_at TIMESTAMP)"
    )
    dates = pd.bdate_range("2026-01-01", periods=140)
    tsmc = [100 + i * 0.8 for i in range(len(dates))]
    etf50 = [80 + i * 0.5 for i in range(len(dates))]
    tsm = [50 + i * 0.2 for i in range(len(dates))]
    fx = [31.0 - i * 0.001 for i in range(len(dates))]
    soxx = [200 + i * 0.7 for i in range(len(dates))]
    _write_prices(con, "external_market_ohlcv", "2330.TW", dates, tsmc)
    _write_prices(con, "external_market_ohlcv", "TSM", dates, tsm)
    _write_prices(con, "external_market_ohlcv", "TWD=X", dates, fx)
    _write_prices(con, "external_market_ohlcv", "SOXX", dates, soxx)
    _write_prices(con, "ohlcv", "0050.TW", dates, etf50, provider=None)
    con.execute(
        "INSERT INTO stock_per_data VALUES ('2330.TW', ?, 1.2, 18.5, 4.2, 'fixture', CURRENT_TIMESTAMP)",
        [str(dates[-1].date())],
    )
    con.close()

    months = pd.date_range("2025-01-01", periods=18, freq="MS")
    pd.DataFrame(
        {
            "date": months,
            "stock_id": ["2330"] * len(months),
            "revenue": [1000 + i * 25 for i in range(len(months))],
        }
    ).to_csv(results_dir / "finmind_2330_monthly_revenue_cache.csv", index=False)

    inst_rows = []
    for dt in dates[-8:]:
        inst_rows.append({"date": dt, "stock_id": "2330", "name": "Foreign_Investor", "buy": 2000, "sell": 1000})
        inst_rows.append({"date": dt, "stock_id": "2330", "name": "Investment_Trust", "buy": 500, "sell": 400})
        inst_rows.append({"date": dt, "stock_id": "2330", "name": "Dealer", "buy": 300, "sell": 250})
    pd.DataFrame(inst_rows).to_csv(results_dir / "finmind_2330_institutional_buysell_cache.csv", index=False)
    pd.DataFrame(
        {
            "date": dates[-8:],
            "stock_id": ["2330"] * 8,
            "ForeignInvestmentSharesRatio": [73.0 + i * 0.01 for i in range(8)],
        }
    ).to_csv(results_dir / "finmind_2330_shareholding_cache.csv", index=False)

    ncf_payload = {
        "ticker": "2330.TW",
        "last_close_date": str(dates[-1].date()),
        "tsmc_market_state": {"state": 1, "label_zh": "強勢領漲"},
        "horizons": {"20": {"classification": {"probability_up": 0.70}}},
        "forward_severe_drawdown_risk": {"available": True, "probability": 0.08},
    }
    (results_dir / "ncf_2330_fixture.json").write_text(json.dumps(ncf_payload), encoding="utf-8")
    return db_path, results_dir, project_root


def test_build_ncf_2330_checklist_schema_and_layers() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        db_path, results_dir, project_root = _make_fixture(Path(tmp_name))

        report = build_checklist(
            db_path=db_path,
            results_dir=results_dir,
            project_root=project_root,
            mode="daily",
        )

    assert report["report"] == "ncf_2330_checklist"
    assert report["policy"] == "diagnostic_only_no_weight_change"
    assert report["layers"]["valuation"]["status"] == "available_partial"
    assert report["layers"]["valuation"]["values"]["pe"] == 18.5
    assert report["layers"]["valuation"]["values"]["pb"] == 4.2
    assert report["layers"]["technical"]["status"] == "available"
    assert report["layers"]["chip"]["signal"] == "bullish"
    assert report["layers"]["ncf_2330"]["values"]["state"]["state"] == 1
    overlay = report["factor_quality_overlay"]
    assert overlay["status"] == "research_only"
    assert overlay["source"] == "evaluate_ncf_2330_checklist_factor_quality.py"
    assert "technical_extension" in overlay["components"]
    assert "valuation_heat" in overlay["components"]


def test_build_ncf_2330_checklist_marks_missing_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        db_path = tmp / "missing.db"
        results_dir = tmp / "results"
        results_dir.mkdir()

        report = build_checklist(db_path=db_path, results_dir=results_dir, project_root=tmp)

    assert report["layers"]["fundamental"]["status"] == "missing_source"
    assert report["layers"]["technical"]["status"] == "missing_source"
    assert report["layers"]["ncf_2330"]["status"] == "missing_source"
    assert report["factor_quality_overlay"]["status"] == "research_only"
