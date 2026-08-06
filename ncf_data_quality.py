"""Data quality helpers for NCF daily JSON outputs and pre-training gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


def _max_date(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> str | None:
    try:
        value = con.execute(sql, params or []).fetchone()[0]
    except Exception:
        return None
    if value is None:
        return None
    return str(pd.Timestamp(value).date())


def _days_lag(reference_date: str | None, source_date: str | None) -> int | None:
    if not reference_date or not source_date:
        return None
    return int((pd.Timestamp(reference_date) - pd.Timestamp(source_date)).days)


def _external_market_ticker_dates(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    try:
        rows = con.execute(
            """
            SELECT ticker, MAX(dt) AS max_dt
            FROM external_market_ohlcv
            WHERE provider='yfinance'
            GROUP BY ticker
            ORDER BY ticker
            """
        ).fetchall()
    except Exception:
        return {}
    return {str(ticker): str(pd.Timestamp(max_dt).date()) for ticker, max_dt in rows if max_dt is not None}


def _table_columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str] | None:
    try:
        rows = con.execute(f"PRAGMA table_info('{table}')").fetchall()
    except Exception:
        return None
    return {str(row[1]) for row in rows}


def _query_dates(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any],
) -> list[pd.Timestamp]:
    rows = con.execute(sql, params).fetchall()
    return [pd.Timestamp(row[0]) for row in rows if row[0] is not None]


def _price_dates(con: duckdb.DuckDBPyConnection, ticker: str, start: str | None = None) -> tuple[str, list[pd.Timestamp]]:
    params: list[Any] = [ticker]
    where = "ticker=?"
    if start:
        where += " AND dt>=?"
        params.append(start)
    local_dates = _query_dates(
        con,
        f"SELECT DISTINCT dt FROM ohlcv WHERE {where} ORDER BY dt",
        params,
    )
    if local_dates:
        return "ohlcv", local_dates

    external_params: list[Any] = ["yfinance", ticker]
    external_where = "provider=? AND ticker=?"
    if start:
        external_where += " AND dt>=?"
        external_params.append(start)
    external_dates = _query_dates(
        con,
        f"SELECT DISTINCT dt FROM external_market_ohlcv WHERE {external_where} ORDER BY dt",
        external_params,
    )
    if external_dates:
        return "external_market_ohlcv:yfinance", external_dates
    return "missing", []


def _date_gap_report(dates: list[pd.Timestamp], *, max_gap_days: int) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    for prev, curr in zip(dates, dates[1:]):
        days = int((curr - prev).days)
        if days > max_gap_days:
            gaps.append(
                {
                    "from": str(prev.date()),
                    "to": str(curr.date()),
                    "calendar_days": days,
                }
            )
    return {
        "max_allowed_calendar_gap_days": int(max_gap_days),
        "gap_count": len(gaps),
        "gaps": gaps,
    }


REQUIRED_SCHEMA: dict[str, set[str]] = {
    "ohlcv": {"ticker", "dt"},
    "institutional_data": {"ticker", "dt"},
    "margin_data": {"ticker", "dt"},
    "market_margin_data": {"dt"},
    "taifex_futures_daily": {"contract", "dt"},
    "taifex_futures_institutional": {"contract_code", "dt"},
    "shareholding_distribution": {"stock_id", "dt"},
    "external_market_ohlcv": {"provider", "ticker", "dt"},
}


def ncf_data_freshness(db_path: Path, ticker: str, last_close_date: str) -> dict[str, Any]:
    """Return source freshness metadata for an NCF signal.

    Dates are compared against the OHLCV close date actually used by the model,
    not wall-clock today. This avoids marking a signal stale when Yahoo has a
    partial latest row with NaN close that is intentionally ignored by DuckDB.
    """
    ticker_id = ticker.split(".")[0]
    with duckdb.connect(str(db_path), read_only=True) as con:
        external_market_dates = _external_market_ticker_dates(con)
        sources = {
            "ohlcv": _max_date(con, "SELECT MAX(dt) FROM ohlcv WHERE ticker=?", [ticker]),
            "institutional": _max_date(con, "SELECT MAX(dt) FROM institutional_data WHERE ticker=?", [ticker]),
            "margin": _max_date(con, "SELECT MAX(dt) FROM margin_data WHERE ticker=?", [ticker]),
            "market_margin": _max_date(con, "SELECT MAX(dt) FROM market_margin_data"),
            "taifex_futures": _max_date(
                con,
                "SELECT MAX(dt) FROM taifex_futures_daily WHERE contract='TX'",
            ),
            "taifex_institutional": _max_date(
                con,
                "SELECT MAX(dt) FROM taifex_futures_institutional WHERE contract_code IN ('臺股期貨', '台股期貨', 'TX')",
            ),
            "tdcc_shareholding": _max_date(
                con,
                "SELECT MAX(dt) FROM shareholding_distribution WHERE stock_id=?",
                [ticker_id],
            ),
            # Worst-case (earliest) "latest date" across all tracked external
            # tickers (^VIX, ^TWII, ^GSPC, ^IRX, ^TNX, GC=F, etc.) -- catches
            # any single straggling ticker rather than averaging it away.
            # Previously this table wasn't monitored at all: the daily
            # pipeline could silently run on stale VIX/US-market data with
            # `status: "ok"` (see [[project_group_a_plus_fable5_audit_20260702]] H1).
            "external_market_ohlcv": _max_date(
                con,
                """
                SELECT MIN(max_dt) FROM (
                    SELECT ticker, MAX(dt) AS max_dt
                    FROM external_market_ohlcv
                    WHERE provider='yfinance'
                    GROUP BY ticker
                )
                """,
            ),
        }

    lag_days = {name: _days_lag(last_close_date, date) for name, date in sources.items()}
    source_details = {
        "external_market_ohlcv": {
            "ticker_dates": external_market_dates,
            "ticker_lag_days_vs_reference": {
                ext_ticker: _days_lag(last_close_date, ext_date)
                for ext_ticker, ext_date in external_market_dates.items()
            },
        }
    }
    missing = [name for name, date in sources.items() if date is None]
    stale = [
        name
        for name, lag in lag_days.items()
        if lag is not None and lag > (14 if name == "tdcc_shareholding" else 3)
    ]
    ahead = [name for name, lag in lag_days.items() if lag is not None and lag < 0]
    status = "ok"
    if missing:
        status = "degraded_missing"
    elif stale:
        status = "degraded_stale"

    return {
        "reference_last_close_date": str(pd.Timestamp(last_close_date).date()),
        "sources": sources,
        "source_details": source_details,
        "lag_days_vs_reference": lag_days,
        "missing_sources": missing,
        "stale_sources": stale,
        "sources_ahead_of_ohlcv": ahead,
        "status": status,
    }


def validate_ncf_training_data(
    db_path: Path,
    *,
    tickers: list[str],
    train_start: str | None = None,
    reference_date: str | None = None,
    max_ohlcv_gap_days: int = 14,
    fail_on_degraded_freshness: bool = False,
) -> dict[str, Any]:
    """Validate NCF training data before model training.

    This is intentionally database-level and model-agnostic. It verifies the
    schema contract needed by the NCF feature builders and checks for large
    calendar gaps in each target ticker's OHLCV history. Freshness checks are
    included in the report and can be promoted to blocking via
    ``fail_on_degraded_freshness``.
    """
    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    ticker_reports: dict[str, Any] = {}

    with duckdb.connect(str(db_path), read_only=True) as con:
        for table, required_columns in REQUIRED_SCHEMA.items():
            columns = _table_columns(con, table)
            if columns is None:
                missing_tables.append(table)
                continue
            missing = sorted(required_columns - columns)
            if missing:
                missing_columns[table] = missing

        for ticker in tickers:
            price_source, dates = _price_dates(con, ticker, train_start)
            ticker_report: dict[str, Any] = {
                "price_source": price_source,
                "ohlcv_rows": len(dates),
                "first_ohlcv_date": str(dates[0].date()) if dates else None,
                "last_ohlcv_date": str(dates[-1].date()) if dates else None,
                "ohlcv_gaps": _date_gap_report(dates, max_gap_days=max_ohlcv_gap_days),
            }
            ref = reference_date if reference_date and reference_date != "latest" else ticker_report["last_ohlcv_date"]
            if ref and price_source == "ohlcv":
                ticker_report["freshness"] = ncf_data_freshness(db_path, ticker, str(ref))
            elif ref:
                ticker_report["freshness"] = {
                    "status": "ok",
                    "reference_last_close_date": str(pd.Timestamp(ref).date()),
                    "sources": {price_source: ticker_report["last_ohlcv_date"]},
                    "reason": "external_price_source_freshness_reported_by_price_dates",
                }
            else:
                ticker_report["freshness"] = {
                    "status": "degraded_missing",
                    "reason": "missing_ohlcv_reference_date",
                }
            ticker_reports[ticker] = ticker_report

    blocking_reasons: list[str] = []
    if missing_tables:
        blocking_reasons.append("missing_tables")
    if missing_columns:
        blocking_reasons.append("missing_columns")
    for ticker, report in ticker_reports.items():
        if report["ohlcv_rows"] == 0:
            blocking_reasons.append(f"missing_price_history:{ticker}")
        if report["ohlcv_gaps"]["gap_count"] > 0:
            blocking_reasons.append(f"ohlcv_calendar_gap:{ticker}")
        freshness = report["freshness"]
        if fail_on_degraded_freshness and freshness.get("status") != "ok":
            blocking_reasons.append(f"degraded_freshness:{ticker}:{freshness.get('status')}")

    status = "ok" if not blocking_reasons else "failed"
    return {
        "schema_version": 1,
        "status": status,
        "db_path": str(db_path),
        "tickers": tickers,
        "train_start": train_start,
        "reference_date": reference_date,
        "max_ohlcv_gap_days": int(max_ohlcv_gap_days),
        "fail_on_degraded_freshness": bool(fail_on_degraded_freshness),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "ticker_reports": ticker_reports,
        "blocking_reasons": blocking_reasons,
    }


def _parse_tickers(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NCF data before training.")
    parser.add_argument("--db", default="FinRL/data/stock_data.db")
    parser.add_argument("--tickers", default="00631L.TW,00632R.TW,2330.TW")
    parser.add_argument("--train-start", default=None)
    parser.add_argument("--reference-date", default="latest")
    parser.add_argument("--max-ohlcv-gap-days", type=int, default=14)
    parser.add_argument("--fail-on-degraded-freshness", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = validate_ncf_training_data(
        Path(args.db),
        tickers=_parse_tickers(args.tickers),
        train_start=args.train_start,
        reference_date=args.reference_date,
        max_ohlcv_gap_days=args.max_ohlcv_gap_days,
        fail_on_degraded_freshness=args.fail_on_degraded_freshness,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
