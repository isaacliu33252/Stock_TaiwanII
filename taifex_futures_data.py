#!/usr/bin/env python3
"""Fetch and store TAIFEX futures data used as Group A market-risk features."""

from __future__ import annotations

import argparse
import calendar
import io
import json
import math
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
OPENAPI_BASE = "https://openapi.taifex.com.tw/v1"
TAIFEX_WEB_BASE = "https://www.taifex.com.tw/cht/3"
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "data" / "taifex"
DEFAULT_CONTRACTS = ["TX"]
HISTORICAL_SOURCE = "taifex_fut_data_down"

CREATE_TAIFEX_FUTURES_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS taifex_futures_daily (
    dt DATE NOT NULL,
    contract TEXT NOT NULL,
    contract_month TEXT NOT NULL,
    trading_session TEXT NOT NULL,
    open DOUBLE NOT NULL DEFAULT 0.0,
    high DOUBLE NOT NULL DEFAULT 0.0,
    low DOUBLE NOT NULL DEFAULT 0.0,
    last DOUBLE NOT NULL DEFAULT 0.0,
    change DOUBLE NOT NULL DEFAULT 0.0,
    pct_change DOUBLE NOT NULL DEFAULT 0.0,
    volume DOUBLE NOT NULL DEFAULT 0.0,
    settlement_price DOUBLE NOT NULL DEFAULT 0.0,
    open_interest DOUBLE NOT NULL DEFAULT 0.0,
    best_bid DOUBLE NOT NULL DEFAULT 0.0,
    best_ask DOUBLE NOT NULL DEFAULT 0.0,
    historical_high DOUBLE NOT NULL DEFAULT 0.0,
    historical_low DOUBLE NOT NULL DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'taifex_openapi_daily_market_report_fut',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt, contract, contract_month, trading_session)
);
"""

CREATE_TAIFEX_FUTURES_INSTITUTIONAL_SQL = """
CREATE TABLE IF NOT EXISTS taifex_futures_institutional (
    dt DATE NOT NULL,
    contract_code TEXT NOT NULL,
    institution TEXT NOT NULL,
    trading_volume_long DOUBLE NOT NULL DEFAULT 0.0,
    trading_value_long_thousands DOUBLE NOT NULL DEFAULT 0.0,
    trading_volume_short DOUBLE NOT NULL DEFAULT 0.0,
    trading_value_short_thousands DOUBLE NOT NULL DEFAULT 0.0,
    trading_volume_net DOUBLE NOT NULL DEFAULT 0.0,
    trading_value_net_thousands DOUBLE NOT NULL DEFAULT 0.0,
    open_interest_long DOUBLE NOT NULL DEFAULT 0.0,
    open_interest_value_long_thousands DOUBLE NOT NULL DEFAULT 0.0,
    open_interest_short DOUBLE NOT NULL DEFAULT 0.0,
    open_interest_value_short_thousands DOUBLE NOT NULL DEFAULT 0.0,
    open_interest_net DOUBLE NOT NULL DEFAULT 0.0,
    open_interest_value_net_thousands DOUBLE NOT NULL DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'taifex_openapi_major_institutional_futures_date',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt, contract_code, institution)
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_taifex_futures_daily_dt ON taifex_futures_daily(dt)",
    "CREATE INDEX IF NOT EXISTS idx_taifex_futures_daily_contract ON taifex_futures_daily(contract, dt)",
    "CREATE INDEX IF NOT EXISTS idx_taifex_futures_inst_dt ON taifex_futures_institutional(dt)",
    "CREATE INDEX IF NOT EXISTS idx_taifex_futures_inst_contract ON taifex_futures_institutional(contract_code, dt)",
]


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def ensure_schema() -> None:
    con = _conn()
    try:
        con.execute(CREATE_TAIFEX_FUTURES_DAILY_SQL)
        con.execute(CREATE_TAIFEX_FUTURES_INSTITUTIONAL_SQL)
        for stmt in INDEX_SQL:
            con.execute(stmt)
    finally:
        con.close()


def _to_float(value: object) -> float:
    text = str(value if value is not None else "").strip().replace(",", "")
    if text in {"", "-", "NULL", "null", "None"}:
        return 0.0
    if text.endswith("%"):
        text = text[:-1]
        try:
            return float(text) / 100.0
        except ValueError:
            return 0.0
    try:
        out = float(text)
    except ValueError:
        return 0.0
    if math.isnan(out) or math.isinf(out):
        return 0.0
    return out


def _parse_date(value: object) -> date:
    text = str(value).strip()
    if "/" in text:
        return pd.to_datetime(text, format="%Y/%m/%d").date()
    return pd.to_datetime(text, format="%Y%m%d").date()


def _request_bytes(url: str, data: dict[str, str] | None = None) -> bytes:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Accept": "application/zip,text/csv,text/plain,*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{TAIFEX_WEB_BASE}/futDailyMarketView",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch_openapi(path: str) -> list[dict[str, Any]]:
    url = f"{OPENAPI_BASE}/{path.lstrip('/')}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected TAIFEX payload for {path}: {type(payload).__name__}")
    return [dict(row) for row in payload]


def normalize_daily_rows(rows: list[dict[str, Any]], contracts: list[str]) -> pd.DataFrame:
    wanted = {contract.upper().strip() for contract in contracts}
    out: list[dict[str, Any]] = []
    for row in rows:
        contract = str(row.get("Contract", "")).upper().strip()
        if contract not in wanted:
            continue
        out.append(
            {
                "dt": _parse_date(row.get("Date")),
                "contract": contract,
                "contract_month": str(row.get("ContractMonth(Week)", "")).strip(),
                "trading_session": str(row.get("TradingSession", "")).strip() or "一般",
                "open": _to_float(row.get("Open")),
                "high": _to_float(row.get("High")),
                "low": _to_float(row.get("Low")),
                "last": _to_float(row.get("Last")),
                "change": _to_float(row.get("Change")),
                "pct_change": _to_float(row.get("%")),
                "volume": _to_float(row.get("Volume")),
                "settlement_price": _to_float(row.get("SettlementPrice")),
                "open_interest": _to_float(row.get("OpenInterest")),
                "best_bid": _to_float(row.get("BestBid")),
                "best_ask": _to_float(row.get("BestAsk")),
                "historical_high": _to_float(row.get("HistoricalHigh")),
                "historical_low": _to_float(row.get("HistoricalLow")),
                "source": "taifex_openapi_daily_market_report_fut",
            }
        )
    return pd.DataFrame(out)


HISTORICAL_DAILY_COLUMNS = {
    "交易日期": "Date",
    "契約": "Contract",
    "到期月份(週別)": "ContractMonth(Week)",
    "開盤價": "Open",
    "最高價": "High",
    "最低價": "Low",
    "收盤價": "Last",
    "漲跌價": "Change",
    "漲跌%": "%",
    "成交量": "Volume",
    "結算價": "SettlementPrice",
    "未沖銷契約數": "OpenInterest",
    "最後最佳買價": "BestBid",
    "最後最佳賣價": "BestAsk",
    "歷史最高價": "HistoricalHigh",
    "歷史最低價": "HistoricalLow",
    "交易時段": "TradingSession",
}


def _read_taifex_csv(raw: bytes) -> pd.DataFrame:
    for encoding in ("big5", "cp950", "utf-8-sig"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding, index_col=False, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(raw), index_col=False, low_memory=False)


def normalize_historical_daily_csv(raw: bytes, contracts: list[str]) -> pd.DataFrame:
    frame = _read_taifex_csv(raw)
    frame = frame.rename(columns={key: value for key, value in HISTORICAL_DAILY_COLUMNS.items() if key in frame.columns})
    records = frame.to_dict(orient="records")
    normalized = normalize_daily_rows(records, contracts)
    if not normalized.empty:
        normalized["source"] = HISTORICAL_SOURCE
    return normalized


def fetch_yearly_futures_zip(year: int) -> bytes:
    return _request_bytes(
        f"{TAIFEX_WEB_BASE}/futDataDown",
        {"down_type": "2", "his_year": str(year)},
    )


def fetch_daily_futures_csv(start_date: date, end_date: date, contract: str) -> bytes:
    return _request_bytes(
        f"{TAIFEX_WEB_BASE}/futDataDown",
        {
            "down_type": "1",
            "queryStartDate": start_date.strftime("%Y/%m/%d"),
            "queryEndDate": end_date.strftime("%Y/%m/%d"),
            "commodity_id": contract,
            "commodity_id2": "",
        },
    )


def _iter_month_ranges(start_date: date, end_date: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start_date
    while cursor <= end_date:
        month_last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, month_last_day)
        stop = min(month_end, end_date)
        ranges.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return ranges


def refresh_history_years(
    years: list[int],
    contracts: list[str],
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    pause_seconds: float = 0.25,
) -> dict[str, Any]:
    yearly_dir = archive_dir / "futures_yearly"
    yearly_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    total_rows = 0
    for year in years:
        raw = fetch_yearly_futures_zip(year)
        zip_path = yearly_dir / f"{year}_fut.zip"
        zip_path.write_bytes(raw)
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            raise RuntimeError(f"TAIFEX yearly download for {year} is not a zip file")

        year_rows = 0
        dates: list[date] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                normalized = normalize_historical_daily_csv(archive.read(name), contracts)
                year_rows += upsert_daily(normalized)
                if not normalized.empty:
                    dates.extend(normalized["dt"].tolist())
        total_rows += year_rows
        summaries.append(
            {
                "year": year,
                "archive": str(zip_path),
                "rows_written": year_rows,
                "min_date": min(dates) if dates else None,
                "max_date": max(dates) if dates else None,
            }
        )
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    return {"years": summaries, "daily_rows_written": total_rows, "contracts": contracts}


def refresh_history_range(
    start_date: date,
    end_date: date,
    contracts: list[str],
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    pause_seconds: float = 0.25,
) -> dict[str, Any]:
    range_dir = archive_dir / "futures_daily_ranges"
    range_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    total_rows = 0
    for start, stop in _iter_month_ranges(start_date, end_date):
        rows_written = 0
        dates: list[date] = []
        for contract in contracts:
            raw = fetch_daily_futures_csv(start, stop, contract)
            csv_path = range_dir / f"{contract}_{start:%Y%m%d}_{stop:%Y%m%d}.csv"
            csv_path.write_bytes(raw)
            normalized = normalize_historical_daily_csv(raw, [contract])
            rows_written += upsert_daily(normalized)
            if not normalized.empty:
                dates.extend(normalized["dt"].tolist())
            if pause_seconds > 0:
                time.sleep(pause_seconds)
        total_rows += rows_written
        summaries.append(
            {
                "start_date": start,
                "end_date": stop,
                "rows_written": rows_written,
                "min_date": min(dates) if dates else None,
                "max_date": max(dates) if dates else None,
            }
        )
    return {"ranges": summaries, "daily_rows_written": total_rows, "contracts": contracts}


def normalize_institutional_rows(rows: list[dict[str, Any]], contract_names: list[str]) -> pd.DataFrame:
    wanted = set(contract_names)
    out: list[dict[str, Any]] = []
    for row in rows:
        contract_code = str(row.get("ContractCode", "")).strip()
        if contract_code not in wanted:
            continue
        out.append(
            {
                "dt": _parse_date(row.get("Date")),
                "contract_code": contract_code,
                "institution": str(row.get("Item", "")).strip(),
                "trading_volume_long": _to_float(row.get("TradingVolume(Long)")),
                "trading_value_long_thousands": _to_float(row.get("TradingValue(Long)(Thousands)")),
                "trading_volume_short": _to_float(row.get("TradingVolume(Short)")),
                "trading_value_short_thousands": _to_float(row.get("TradingValue(Short)(Thousands)")),
                "trading_volume_net": _to_float(row.get("TradingVolume(Net)")),
                "trading_value_net_thousands": _to_float(row.get("TradingValue(Net)(Thousands)")),
                "open_interest_long": _to_float(row.get("OpenInterest(Long)")),
                "open_interest_value_long_thousands": _to_float(
                    row.get("ContractValueofOpenInterest(Long)(Thousands)")
                ),
                "open_interest_short": _to_float(row.get("OpenInterest(Short)")),
                "open_interest_value_short_thousands": _to_float(
                    row.get("ContractValueofOpenInterest(Short)(Thousands)")
                ),
                "open_interest_net": _to_float(row.get("OpenInterest(Net)")),
                "open_interest_value_net_thousands": _to_float(
                    row.get("ContractValueofOpenInterest(Net)(Thousands)")
                ),
                "source": "taifex_openapi_major_institutional_futures_date",
            }
        )
    return pd.DataFrame(out)


def upsert_daily(rows: pd.DataFrame) -> int:
    if rows.empty:
        return 0
    ensure_schema()
    con = _conn()
    try:
        con.register("incoming_taifex_daily", rows)
        con.execute(
            """
            DELETE FROM taifex_futures_daily
            USING incoming_taifex_daily
            WHERE taifex_futures_daily.dt = incoming_taifex_daily.dt
              AND taifex_futures_daily.contract = incoming_taifex_daily.contract
              AND taifex_futures_daily.contract_month = incoming_taifex_daily.contract_month
              AND taifex_futures_daily.trading_session = incoming_taifex_daily.trading_session
            """
        )
        con.execute(
            """
            INSERT INTO taifex_futures_daily (
                dt, contract, contract_month, trading_session, open, high, low, last,
                change, pct_change, volume, settlement_price, open_interest, best_bid,
                best_ask, historical_high, historical_low, source
            )
            SELECT
                dt, contract, contract_month, trading_session, open, high, low, last,
                change, pct_change, volume, settlement_price, open_interest, best_bid,
                best_ask, historical_high, historical_low, source
            FROM incoming_taifex_daily
            """
        )
        con.unregister("incoming_taifex_daily")
    finally:
        con.close()
    return int(len(rows))


def upsert_institutional(rows: pd.DataFrame) -> int:
    if rows.empty:
        return 0
    ensure_schema()
    con = _conn()
    try:
        con.register("incoming_taifex_inst", rows)
        con.execute(
            """
            DELETE FROM taifex_futures_institutional
            USING incoming_taifex_inst
            WHERE taifex_futures_institutional.dt = incoming_taifex_inst.dt
              AND taifex_futures_institutional.contract_code = incoming_taifex_inst.contract_code
              AND taifex_futures_institutional.institution = incoming_taifex_inst.institution
            """
        )
        con.execute(
            """
            INSERT INTO taifex_futures_institutional (
                dt, contract_code, institution, trading_volume_long,
                trading_value_long_thousands, trading_volume_short,
                trading_value_short_thousands, trading_volume_net,
                trading_value_net_thousands, open_interest_long,
                open_interest_value_long_thousands, open_interest_short,
                open_interest_value_short_thousands, open_interest_net,
                open_interest_value_net_thousands, source
            )
            SELECT
                dt, contract_code, institution, trading_volume_long,
                trading_value_long_thousands, trading_volume_short,
                trading_value_short_thousands, trading_volume_net,
                trading_value_net_thousands, open_interest_long,
                open_interest_value_long_thousands, open_interest_short,
                open_interest_value_short_thousands, open_interest_net,
                open_interest_value_net_thousands, source
            FROM incoming_taifex_inst
            """
        )
        con.unregister("incoming_taifex_inst")
    finally:
        con.close()
    return int(len(rows))


def query_taifex_futures_features(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    ensure_schema()
    where = ["d.contract = 'TX'"]
    params: list[Any] = []
    if start:
        where.append("d.dt >= ?")
        params.append(pd.Timestamp(start).date())
    if end:
        where.append("d.dt <= ?")
        params.append(pd.Timestamp(end).date())
    sql = f"""
        WITH tx_main AS (
            SELECT *
            FROM taifex_futures_daily d
            WHERE {' AND '.join(where)}
              AND d.contract_month <> ''
              AND d.contract_month NOT LIKE '%/%'
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY d.dt, d.trading_session
                ORDER BY d.contract_month ASC
            ) = 1
        ),
        pivoted AS (
            SELECT
                dt,
                MAX(CASE WHEN trading_session = '一般' THEN last ELSE NULL END) AS tx_regular_last,
                MAX(CASE WHEN trading_session = '一般' THEN settlement_price ELSE NULL END) AS tx_regular_settlement,
                MAX(CASE WHEN trading_session = '一般' THEN open_interest ELSE NULL END) AS tx_regular_open_interest,
                MAX(CASE WHEN trading_session = '一般' THEN volume ELSE NULL END) AS tx_regular_volume,
                MAX(CASE WHEN trading_session = '盤後' THEN last ELSE NULL END) AS tx_after_hours_last,
                MAX(CASE WHEN trading_session = '盤後' THEN volume ELSE NULL END) AS tx_after_hours_volume
            FROM tx_main
            GROUP BY dt
        ),
        inst AS (
            SELECT
                dt,
                MAX(CASE WHEN institution = '外資及陸資' THEN trading_volume_net ELSE NULL END) AS tx_fini_trading_volume_net,
                MAX(CASE WHEN institution = '外資及陸資' THEN open_interest_net ELSE NULL END) AS tx_fini_open_interest_net,
                MAX(CASE WHEN institution = '投信' THEN open_interest_net ELSE NULL END) AS tx_trust_open_interest_net,
                MAX(CASE WHEN institution = '自營商' THEN open_interest_net ELSE NULL END) AS tx_dealer_open_interest_net
            FROM taifex_futures_institutional
            WHERE contract_code = '臺股期貨'
            GROUP BY dt
        )
        SELECT
            p.dt,
            COALESCE(p.tx_regular_last, 0.0) AS tx_regular_last,
            COALESCE(p.tx_regular_settlement, 0.0) AS tx_regular_settlement,
            COALESCE(p.tx_regular_open_interest, 0.0) AS tx_regular_open_interest,
            COALESCE(p.tx_regular_volume, 0.0) AS tx_regular_volume,
            COALESCE(p.tx_after_hours_last, 0.0) AS tx_after_hours_last,
            COALESCE(p.tx_after_hours_volume, 0.0) AS tx_after_hours_volume,
            COALESCE(p.tx_after_hours_last - NULLIF(p.tx_regular_last, 0.0), 0.0) AS tx_after_hours_basis,
            COALESCE((p.tx_after_hours_last / NULLIF(p.tx_regular_last, 0.0)) - 1.0, 0.0) AS tx_after_hours_return,
            COALESCE(i.tx_fini_trading_volume_net, 0.0) AS tx_fini_trading_volume_net,
            COALESCE(i.tx_fini_open_interest_net, 0.0) AS tx_fini_open_interest_net,
            COALESCE(i.tx_trust_open_interest_net, 0.0) AS tx_trust_open_interest_net,
            COALESCE(i.tx_dealer_open_interest_net, 0.0) AS tx_dealer_open_interest_net
        FROM pivoted p
        LEFT JOIN inst i USING (dt)
        ORDER BY p.dt
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def refresh_latest(contracts: list[str]) -> dict[str, Any]:
    daily = normalize_daily_rows(fetch_openapi("/DailyMarketReportFut"), contracts)
    inst = normalize_institutional_rows(
        fetch_openapi("/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"),
        ["臺股期貨"],
    )
    daily_rows = upsert_daily(daily)
    institutional_rows = upsert_institutional(inst)
    dates = sorted({str(value) for value in daily.get("dt", [])} | {str(value) for value in inst.get("dt", [])})
    return {
        "daily_rows_written": daily_rows,
        "institutional_rows_written": institutional_rows,
        "dates": dates,
        "contracts": contracts,
        "features": query_taifex_futures_features(dates[0], dates[-1]).to_dict(orient="records") if dates else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", default=",".join(DEFAULT_CONTRACTS))
    parser.add_argument("--refresh-latest", action="store_true")
    parser.add_argument("--refresh-history", action="store_true")
    parser.add_argument("--refresh-range", action="store_true")
    parser.add_argument("--query-features", action="store_true")
    parser.add_argument("--start-year", type=int, default=1998)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR))
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    parser.add_argument("--output")
    args = parser.parse_args()

    contracts = [item.strip().upper() for item in str(args.contracts).split(",") if item.strip()]
    if args.refresh_history:
        years = list(range(int(args.start_year), int(args.end_year) + 1))
        result = refresh_history_years(
            years,
            contracts,
            archive_dir=Path(args.archive_dir),
            pause_seconds=float(args.pause_seconds),
        )
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        print(text)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return
    if args.refresh_range:
        if not args.start_date or not args.end_date:
            raise SystemExit("--refresh-range requires --start-date and --end-date")
        result = refresh_history_range(
            pd.Timestamp(args.start_date).date(),
            pd.Timestamp(args.end_date).date(),
            contracts,
            archive_dir=Path(args.archive_dir),
            pause_seconds=float(args.pause_seconds),
        )
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        print(text)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return
    if args.refresh_latest:
        result = refresh_latest(contracts)
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        print(text)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return
    if args.query_features:
        features = query_taifex_futures_features(args.start_date, args.end_date)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            features.to_csv(path, index=False, encoding="utf-8-sig")
        print(features.to_string(index=False))
        return
    parser.print_help()


if __name__ == "__main__":
    main()
