from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.run.build_00631l_crash_risk_alert import (
    RAW_FRESHNESS_SOURCES,
    _active_reason_lines,
    _as_of_advancement_blocking,
    _category_flags,
    _cross_market_raw_latest_date,
    _family_freshness,
    _history_path,
    _raw_sources_worst_case_date,
    _soxx_iv_health,
    _watch_level,
    write_crash_risk_alert,
)


def test_watch_level_by_score() -> None:
    assert _watch_level(0) == "none"
    assert _watch_level(1) == "watch"
    assert _watch_level(2) == "medium"
    assert _watch_level(3) == "high"


def test_category_flags_are_explainable() -> None:
    row = pd.Series(
        {
            "txo_foreign_put_call_net_oi_chg5_z60": 1.2,
            "market_margin_forced_repay_z60": 1.3,
            "vix_chg5_z60": 0.2,
        }
    )

    flags, details = _category_flags(row)

    assert flags == {
        "options_tail": True,
        "liquidity_forced_selling": True,
        "cross_market_shock": False,
    }
    assert details["options_tail"]["txo_foreign_put_call_net_oi_chg5_z60_ge_1"] is True
    assert details["liquidity_forced_selling"]["market_margin_forced_repay_z60_ge_1"] is True


def test_global_risk_off_conditions_trigger_cross_market_family() -> None:
    row = pd.Series(
        {
            "vix_level_z60": 1.2,
            "soxx_downside_vol20_z60": 1.4,
            "usdtwd_ret5_z60": 1.1,
        }
    )

    flags, details = _category_flags(row)

    assert flags["cross_market_shock"] is True
    assert details["cross_market_shock"]["vix_level_z60_ge_1"] is True
    assert details["cross_market_shock"]["soxx_downside_vol20_z60_ge_1"] is True
    assert details["cross_market_shock"]["usdtwd_ret5_z60_ge_1"] is True


def test_soxx_implied_vol_conditions_trigger_cross_market_family() -> None:
    row = pd.Series(
        {
            "soxx_iv_rank_252": 0.85,
            "soxx_iv_minus_rv20_z252": 1.3,
            "soxx_put_call_iv_skew_z252": 1.2,
        }
    )

    flags, details = _category_flags(row)

    assert flags["cross_market_shock"] is True
    assert details["cross_market_shock"]["soxx_iv_rank_252_ge_80pct"] is True
    assert details["cross_market_shock"]["soxx_iv_minus_rv20_z252_ge_1"] is True
    assert details["cross_market_shock"]["soxx_put_call_iv_skew_z252_ge_1"] is True


def test_soxx_raw_implied_vol_fallback_triggers_cross_market_family() -> None:
    row = pd.Series(
        {
            "soxx_atm_iv30_raw": 0.62,
            "soxx_put_call_volume_ratio_raw": 5.4,
            "soxx_put_call_oi_ratio_raw": 5.1,
        }
    )

    flags, details = _category_flags(row)

    assert flags["cross_market_shock"] is True
    assert details["cross_market_shock"]["soxx_atm_iv30_raw_ge_55pct"] is True
    assert details["cross_market_shock"]["soxx_put_call_volume_ratio_raw_ge_3"] is True
    assert details["cross_market_shock"]["soxx_put_call_oi_ratio_raw_ge_3"] is True


def test_soxx_iv_health_flags_bad_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE external_options_iv (
                provider TEXT,
                underlying TEXT,
                dt DATE,
                spot DOUBLE,
                expiry DATE,
                dte INTEGER,
                atm_iv DOUBLE,
                atm_call_iv DOUBLE,
                atm_put_iv DOUBLE,
                otm_put_iv_95 DOUBLE,
                otm_call_iv_105 DOUBLE,
                put_call_iv_skew DOUBLE,
                put_call_volume_ratio DOUBLE,
                put_call_oi_ratio DOUBLE,
                contract_count BIGINT,
                source TEXT,
                fetched_at TIMESTAMP
            )
            """
        )
        con.execute(
            """
            INSERT INTO external_options_iv VALUES
            ('yfinance', 'SOXX', '2026-07-10', 581.0, '2026-07-11', 1, 2.5,
             2.5, 2.5, 2.5, 2.5, 0.0, 25.0, 25.0, 5, 'test', '2026-07-12')
            """
        )
    finally:
        con.close()

    health = _soxx_iv_health(db_path, pd.Timestamp("2026-07-09"))

    assert health["status"] == "warning"
    assert "dte_outside_7_60" in health["warnings"]
    assert "atm_iv_outside_5pct_200pct" in health["warnings"]
    assert "low_contract_count" in health["warnings"]
    assert "no_snapshot_at_or_before_alert_as_of" in health["warnings"]


def _write_external_market_ohlcv(db_path: Path, rows: list[tuple[str, str, float]]) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "CREATE TABLE external_market_ohlcv (ticker TEXT, dt DATE, close DOUBLE)"
        )
        con.executemany(
            "INSERT INTO external_market_ohlcv VALUES (?, ?, ?)", rows
        )
    finally:
        con.close()


def test_cross_market_raw_latest_date_uses_worst_case_ticker(tmp_path: Path) -> None:
    # ^TWII (Taiwan calendar) is one day fresher than the US-calendar tickers.
    # Staleness must be judged by the stalest contributing ticker, not the
    # freshest one, otherwise a stuck US data feed goes unnoticed.
    db_path = tmp_path / "stock_data.db"
    _write_external_market_ohlcv(
        db_path,
        [
            ("^TWII", "2026-07-08", 20000.0),
            ("^VIX", "2026-07-07", 15.0),
            ("SOXX", "2026-07-07", 250.0),
            ("QQQ", "2026-07-07", 500.0),
            ("TSM", "2026-07-07", 200.0),
            ("TWD=X", "2026-07-07", 30.0),
        ],
    )

    latest = _cross_market_raw_latest_date(db_path, pd.Timestamp("2026-07-09"))

    assert latest == "2026-07-07"


def test_family_freshness_detects_stale_cross_market_despite_ffilled_features(tmp_path: Path) -> None:
    # Regression test: build_multisource_features forward-fills cross-market
    # closes before z-scoring, so the engineered feature columns can still be
    # non-null at as_of even when the underlying raw data stopped updating
    # two days earlier. _family_freshness must not be fooled by that ffill.
    db_path = tmp_path / "stock_data.db"
    _write_external_market_ohlcv(
        db_path,
        [
            ("^TWII", "2026-07-08", 20000.0),
            ("^VIX", "2026-07-07", 15.0),
            ("SOXX", "2026-07-07", 250.0),
            ("QQQ", "2026-07-07", 500.0),
            ("TSM", "2026-07-07", 200.0),
            ("TWD=X", "2026-07-07", 30.0),
        ],
    )

    index = pd.date_range("2026-07-01", "2026-07-09", freq="D")
    features = pd.DataFrame(index=index)
    # Simulate the ffill artifact: a non-null cross-market value on as_of
    # even though the raw source is two days stale.
    features["vix_level_z60"] = 0.5
    features["txo_pcr_volume_z20"] = 0.1
    features["market_margin_forced_repay_z60"] = 0.1

    freshness = _family_freshness(features, pd.Timestamp("2026-07-09"), db_path)

    assert freshness["families"]["cross_market_shock"]["latest_date_at_or_before_as_of"] == "2026-07-07"
    assert freshness["families"]["cross_market_shock"]["stale"] is True
    assert freshness["status"] == "degraded"


def test_raw_sources_worst_case_date_uses_stalest_table(tmp_path: Path) -> None:
    # options_tail mixes taifex_options_daily (TXO market-wide) with
    # derivative_institutional_data (foreign TXO/TX positioning). If one
    # table stops updating while the other keeps going, family freshness
    # must reflect the stalest table, not the freshest.
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "CREATE TABLE taifex_options_daily (contract TEXT, trading_session TEXT, dt DATE)"
        )
        con.execute(
            "INSERT INTO taifex_options_daily VALUES ('TXO', '一般', '2026-07-03')"
        )
        con.execute(
            "CREATE TABLE derivative_institutional_data (product_id TEXT, institutional_investors TEXT, dt DATE)"
        )
        con.execute(
            "INSERT INTO derivative_institutional_data VALUES ('TXO', '外資', '2026-07-09')"
        )
    finally:
        con.close()

    latest = _raw_sources_worst_case_date(db_path, RAW_FRESHNESS_SOURCES["options_tail"], pd.Timestamp("2026-07-09"))

    assert latest == "2026-07-03"


def test_family_freshness_detects_stale_options_tail_source_table(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "CREATE TABLE taifex_options_daily (contract TEXT, trading_session TEXT, dt DATE)"
        )
        con.execute(
            "INSERT INTO taifex_options_daily VALUES ('TXO', '一般', '2026-07-03')"
        )
        con.execute(
            "CREATE TABLE derivative_institutional_data (product_id TEXT, institutional_investors TEXT, dt DATE)"
        )
        con.execute(
            "INSERT INTO derivative_institutional_data VALUES ('TXO', '外資', '2026-07-09')"
        )
        con.execute("CREATE TABLE external_market_ohlcv (ticker TEXT, dt DATE, close DOUBLE)")
        for ticker in ("^VIX", "SOXX", "QQQ", "^TWII", "TSM", "TWD=X"):
            con.execute("INSERT INTO external_market_ohlcv VALUES (?, '2026-07-09', 1.0)", [ticker])
    finally:
        con.close()

    index = pd.date_range("2026-07-01", "2026-07-09", freq="D")
    features = pd.DataFrame(index=index)
    # Simulate the masking artifact: the engineered column fed by the fresher
    # table (derivative_institutional_data) is non-null on as_of, which would
    # otherwise hide that taifex_options_daily stopped updating on 2026-07-03.
    features["txo_foreign_put_call_net_oi_chg5_z60"] = 0.2
    features["market_margin_forced_repay_z60"] = 0.1
    features["securities_lending_0050_volume_z60"] = 0.1

    freshness = _family_freshness(features, pd.Timestamp("2026-07-09"), db_path)

    assert freshness["families"]["options_tail"]["latest_date_at_or_before_as_of"] == "2026-07-03"
    assert freshness["families"]["options_tail"]["stale"] is True
    assert freshness["status"] == "degraded"


def test_active_reason_lines_splits_cross_market_subfamilies() -> None:
    details = {
        "cross_market_shock": {
            "vix_level_z60_ge_1": True,
            "soxx_atm_iv30_raw_ge_55pct": True,
            "usdtwd_ret5_z60_ge_1": False,
        },
    }

    lines = _active_reason_lines(details)

    assert len(lines) == 2
    price_fx_line = next(line for line in lines if line.startswith("Cross-market price/FX"))
    iv_line = next(line for line in lines if line.startswith("Cross-market implied volatility"))
    assert "VIX level is elevated" in price_fx_line
    assert "SOXX 30-day ATM implied volatility is above 55%" in iv_line


def test_active_reason_lines_cross_market_single_subfamily_only() -> None:
    details = {
        "cross_market_shock": {"vix_level_z60_ge_1": True},
        "options_tail": {"txo_pcr_volume_z20_ge_1": True},
    }

    lines = _active_reason_lines(details)

    assert lines == [
        "Cross-market price/FX: VIX level is elevated",
        "Options tail demand: TXO market put/call volume ratio is elevated",
    ]


def test_as_of_advancement_blocking_identifies_missing_family() -> None:
    index = pd.date_range("2026-07-07", "2026-07-10", freq="D")
    features = pd.DataFrame(index=index)
    # options_tail and cross_market_shock have data through 07-10, but
    # liquidity_forced_selling stops updating after 07-09 -- it alone
    # should block 07-10 from becoming the resolved as_of.
    features["txo_pcr_volume_z20"] = [0.1, 0.2, 0.3, 0.4]
    features["vix_level_z60"] = [0.1, 0.2, 0.3, 0.4]
    features["market_margin_forced_repay_z60"] = [0.1, 0.2, 0.3, None]

    report = _as_of_advancement_blocking(features, pd.Timestamp("2026-07-09"))

    assert report["as_of"] == "2026-07-09"
    assert report["latest_available_feature_date"] == "2026-07-10"
    assert report["blocked_dates"] == [
        {"date": "2026-07-10", "missing_families": ["liquidity_forced_selling"]}
    ]


def test_as_of_advancement_blocking_no_candidates_past_as_of() -> None:
    index = pd.date_range("2026-07-07", "2026-07-09", freq="D")
    features = pd.DataFrame(index=index)
    features["txo_pcr_volume_z20"] = [0.1, 0.2, 0.3]

    report = _as_of_advancement_blocking(features, pd.Timestamp("2026-07-09"))

    assert report["blocked_dates"] == []


def test_write_crash_risk_alert_writes_latest_and_history(tmp_path: Path) -> None:
    payload = {
        "as_of": "2026-07-09",
        "category_score": 2,
        "alert_active": False,
    }
    latest = tmp_path / "latest" / "crash_risk_alert.json"
    history = tmp_path / "history"

    write_crash_risk_alert(payload, output_path=latest, history_dir=history)

    assert json.loads(latest.read_text())["as_of"] == "2026-07-09"
    assert json.loads(_history_path(history, pd.Timestamp("2026-07-09")).read_text())["category_score"] == 2
