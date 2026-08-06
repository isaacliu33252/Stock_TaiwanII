from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from ncf_data_quality import ncf_data_freshness, validate_ncf_training_data
from scripts.misc.ncf_00631l import reconcile_latest_panel_row


def test_ncf_data_freshness_reports_lags_and_ahead_sources(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE institutional_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE margin_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE market_margin_data (dt DATE)")
    con.execute("CREATE TABLE taifex_futures_daily (contract TEXT, dt DATE)")
    con.execute("CREATE TABLE taifex_futures_institutional (contract_code TEXT, dt DATE)")
    con.execute("CREATE TABLE shareholding_distribution (stock_id TEXT, dt DATE)")
    con.execute(
        "CREATE TABLE external_market_ohlcv (provider TEXT, ticker TEXT, dt DATE)"
    )
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-06-25')")
    con.execute("INSERT INTO institutional_data VALUES ('00631L.TW', '2026-06-26')")
    con.execute("INSERT INTO margin_data VALUES ('00631L.TW', '2026-06-24')")
    con.execute("INSERT INTO market_margin_data VALUES ('2026-06-26')")
    con.execute("INSERT INTO taifex_futures_daily VALUES ('TX', '2026-06-26')")
    con.execute("INSERT INTO taifex_futures_institutional VALUES ('臺股期貨', '2026-06-26')")
    con.execute("INSERT INTO shareholding_distribution VALUES ('00631L', '2026-06-18')")
    con.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '^VIX', '2026-06-25')")
    con.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '^TWII', '2026-06-24')")
    con.close()

    result = ncf_data_freshness(db, "00631L.TW", "2026-06-25")

    assert result["status"] == "ok"
    assert result["lag_days_vs_reference"]["margin"] == 1
    assert result["lag_days_vs_reference"]["tdcc_shareholding"] == 7
    # Worst-case ticker (^TWII, 1 day behind ^VIX) determines the reported date.
    assert result["sources"]["external_market_ohlcv"] == "2026-06-24"
    assert result["source_details"]["external_market_ohlcv"]["ticker_dates"] == {
        "^TWII": "2026-06-24",
        "^VIX": "2026-06-25",
    }
    assert result["source_details"]["external_market_ohlcv"]["ticker_lag_days_vs_reference"]["^TWII"] == 1
    assert "institutional" in result["sources_ahead_of_ohlcv"]
    assert "tdcc_shareholding" not in result["stale_sources"]


def test_ncf_data_freshness_flags_stale_external_market_data(tmp_path: Path) -> None:
    """H1 regression: external_market_ohlcv (VIX/US-market yfinance cache) must
    be monitored -- previously this table wasn't checked at all, so the daily
    pipeline could run on stale VIX/US-market data with status "ok"."""
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE institutional_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE margin_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE market_margin_data (dt DATE)")
    con.execute("CREATE TABLE taifex_futures_daily (contract TEXT, dt DATE)")
    con.execute("CREATE TABLE taifex_futures_institutional (contract_code TEXT, dt DATE)")
    con.execute("CREATE TABLE shareholding_distribution (stock_id TEXT, dt DATE)")
    con.execute(
        "CREATE TABLE external_market_ohlcv (provider TEXT, ticker TEXT, dt DATE)"
    )
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-07-02')")
    con.execute("INSERT INTO institutional_data VALUES ('00631L.TW', '2026-07-02')")
    con.execute("INSERT INTO margin_data VALUES ('00631L.TW', '2026-07-02')")
    con.execute("INSERT INTO market_margin_data VALUES ('2026-07-02')")
    con.execute("INSERT INTO taifex_futures_daily VALUES ('TX', '2026-07-02')")
    con.execute("INSERT INTO taifex_futures_institutional VALUES ('臺股期貨', '2026-07-02')")
    con.execute("INSERT INTO shareholding_distribution VALUES ('00631L', '2026-06-25')")
    # ^VIX fresh, but ^TNX stuck 6 calendar days behind -- the worst-case
    # ticker should drive the reported freshness, not an average.
    con.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '^VIX', '2026-07-02')")
    con.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '^TNX', '2026-06-26')")
    con.close()

    result = ncf_data_freshness(db, "00631L.TW", "2026-07-02")

    assert result["sources"]["external_market_ohlcv"] == "2026-06-26"
    assert result["lag_days_vs_reference"]["external_market_ohlcv"] == 6
    assert result["source_details"]["external_market_ohlcv"]["ticker_lag_days_vs_reference"] == {
        "^TNX": 6,
        "^VIX": 0,
    }
    assert "external_market_ohlcv" in result["stale_sources"]
    assert result["status"] == "degraded_stale"


def test_ncf_data_freshness_external_market_ignores_non_yfinance_provider(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE institutional_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE margin_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE market_margin_data (dt DATE)")
    con.execute("CREATE TABLE taifex_futures_daily (contract TEXT, dt DATE)")
    con.execute("CREATE TABLE taifex_futures_institutional (contract_code TEXT, dt DATE)")
    con.execute("CREATE TABLE shareholding_distribution (stock_id TEXT, dt DATE)")
    con.execute("CREATE TABLE external_market_ohlcv (provider TEXT, ticker TEXT, dt DATE)")
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-07-02')")
    con.execute("INSERT INTO institutional_data VALUES ('00631L.TW', '2026-07-02')")
    con.execute("INSERT INTO margin_data VALUES ('00631L.TW', '2026-07-02')")
    con.execute("INSERT INTO market_margin_data VALUES ('2026-07-02')")
    con.execute("INSERT INTO taifex_futures_daily VALUES ('TX', '2026-07-02')")
    con.execute("INSERT INTO taifex_futures_institutional VALUES ('臺股期貨', '2026-07-02')")
    con.execute("INSERT INTO shareholding_distribution VALUES ('00631L', '2026-06-25')")
    con.execute("INSERT INTO external_market_ohlcv VALUES ('manual', '^VIX', '2026-01-01')")
    con.execute("INSERT INTO external_market_ohlcv VALUES ('yfinance', '^VIX', '2026-07-02')")
    con.close()

    result = ncf_data_freshness(db, "00631L.TW", "2026-07-02")

    assert result["status"] == "ok"
    assert result["sources"]["external_market_ohlcv"] == "2026-07-02"
    assert result["source_details"]["external_market_ohlcv"]["ticker_dates"] == {"^VIX": "2026-07-02"}


def test_ncf_data_freshness_flags_missing_source(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    for ddl in [
        "CREATE TABLE ohlcv (ticker TEXT, dt DATE)",
        "CREATE TABLE institutional_data (ticker TEXT, dt DATE)",
        "CREATE TABLE margin_data (ticker TEXT, dt DATE)",
        "CREATE TABLE market_margin_data (dt DATE)",
        "CREATE TABLE taifex_futures_daily (contract TEXT, dt DATE)",
        "CREATE TABLE taifex_futures_institutional (contract_code TEXT, dt DATE)",
        "CREATE TABLE shareholding_distribution (stock_id TEXT, dt DATE)",
    ]:
        con.execute(ddl)
    con.execute("INSERT INTO ohlcv VALUES ('00632R.TW', '2026-06-25')")
    con.close()

    result = ncf_data_freshness(db, "00632R.TW", "2026-06-25")

    assert result["status"] == "degraded_missing"
    assert "institutional" in result["missing_sources"]


def test_validate_ncf_training_data_blocks_schema_and_ohlcv_gaps(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE)")
    # Missing required ticker column.
    con.execute("CREATE TABLE institutional_data (dt DATE)")
    con.execute("CREATE TABLE margin_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE market_margin_data (dt DATE)")
    con.execute("CREATE TABLE taifex_futures_daily (contract TEXT, dt DATE)")
    con.execute("CREATE TABLE taifex_futures_institutional (contract_code TEXT, dt DATE)")
    con.execute("CREATE TABLE shareholding_distribution (stock_id TEXT, dt DATE)")
    con.execute("CREATE TABLE external_market_ohlcv (provider TEXT, ticker TEXT, dt DATE)")
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-07-01')")
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-07-25')")
    con.close()

    result = validate_ncf_training_data(
        db,
        tickers=["00631L.TW"],
        max_ohlcv_gap_days=14,
    )

    assert result["status"] == "failed"
    assert result["missing_columns"] == {"institutional_data": ["ticker"]}
    assert "ohlcv_calendar_gap:00631L.TW" in result["blocking_reasons"]
    assert result["ticker_reports"]["00631L.TW"]["ohlcv_gaps"]["gaps"] == [
        {"from": "2026-07-01", "to": "2026-07-25", "calendar_days": 24}
    ]


def test_validate_ncf_training_data_passes_clean_minimal_schema(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE institutional_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE margin_data (ticker TEXT, dt DATE)")
    con.execute("CREATE TABLE market_margin_data (dt DATE)")
    con.execute("CREATE TABLE taifex_futures_daily (contract TEXT, dt DATE)")
    con.execute("CREATE TABLE taifex_futures_institutional (contract_code TEXT, dt DATE)")
    con.execute("CREATE TABLE shareholding_distribution (stock_id TEXT, dt DATE)")
    con.execute("CREATE TABLE external_market_ohlcv (provider TEXT, ticker TEXT, dt DATE)")
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-07-01')")
    con.execute("INSERT INTO ohlcv VALUES ('00631L.TW', '2026-07-02')")
    con.close()

    result = validate_ncf_training_data(
        db,
        tickers=["00631L.TW"],
        max_ohlcv_gap_days=14,
        fail_on_degraded_freshness=False,
    )

    assert result["status"] == "ok"
    assert result["blocking_reasons"] == []


def test_reconcile_latest_panel_row_aligns_json_horizon_payload(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-06-29",
                "prob_up_h1": 0.60,
                "prob_up_h5": 0.57,
                "prob_up_h20": 0.42,
                "ensemble_prob_up": 0.51,
                "direction": "UP",
                "prob_magnitude": 0.02,
                "h20_prob_up": 0.42,
                "h20_direction": "DOWN",
                "confidence": 0.02,
                "is_live": True,
            }
        ]
    ).to_csv(panel_path, index=False)
    payload = {
        "last_close_date": "2026-06-29",
        "horizons": {
            "1": {"classification": {"probability_up": 0.4669}},
            "5": {"classification": {"probability_up": 0.3576}},
            "20": {"classification": {"probability_up": 0.2703}},
        },
        "horizon_ensemble": {
            # H2 (2026-07-02 Fable 5 audit, Option A): reconcile now uses
            # these *_panel_aligned fields (same expanding-AUC weighting as
            # the panel itself), not combined_probability_up/confidence
            # (a differently-weighted, differently-scaled JSON-only metric
            # that used to leak into the panel's prob_magnitude/confidence
            # columns on reconciliation).
            "combined_probability_up": 0.3419,
            "direction": "DOWN",
            "confidence": 0.6621,
            "ensemble_prob_up_panel_aligned": 0.28,
            "prob_magnitude_panel_aligned": 0.44,
        },
    }

    result = reconcile_latest_panel_row(panel_path, payload)
    frame = pd.read_csv(panel_path)

    assert result["status"] == "updated"
    assert frame.loc[0, "prob_up_h1"] == 0.4669
    assert frame.loc[0, "prob_up_h5"] == 0.3576
    assert frame.loc[0, "prob_up_h20"] == 0.2703
    assert frame.loc[0, "h20_prob_up"] == 0.2703
    assert frame.loc[0, "h20_direction"] == "DOWN"
    assert frame.loc[0, "ensemble_prob_up"] == 0.28
    assert frame.loc[0, "direction"] == "DOWN"
    assert frame.loc[0, "prob_magnitude"] == 0.44
    assert frame.loc[0, "confidence"] == 0.44


def test_reconcile_latest_panel_row_skips_alignment_when_field_absent(tmp_path: Path) -> None:
    """Backward compatibility: JSON payloads generated before the
    *_panel_aligned fields existed must not have prob_magnitude/confidence
    overwritten with a stale/absent value -- direction/prob_up_h* still
    update from the fields that were always present."""
    panel_path = tmp_path / "panel.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-06-29",
                "prob_up_h1": 0.60,
                "ensemble_prob_up": 0.51,
                "direction": "UP",
                "prob_magnitude": 0.02,
                "confidence": 0.02,
            }
        ]
    ).to_csv(panel_path, index=False)
    payload = {
        "last_close_date": "2026-06-29",
        "horizons": {"1": {"classification": {"probability_up": 0.70}}},
        "horizon_ensemble": {"combined_probability_up": 0.40, "direction": "DOWN"},
    }

    result = reconcile_latest_panel_row(panel_path, payload)
    frame = pd.read_csv(panel_path)

    assert result["status"] == "updated"
    assert frame.loc[0, "prob_up_h1"] == 0.70
    assert frame.loc[0, "direction"] == "DOWN"
    assert frame.loc[0, "ensemble_prob_up"] == 0.51
    assert frame.loc[0, "prob_magnitude"] == 0.02
    assert frame.loc[0, "confidence"] == 0.02
