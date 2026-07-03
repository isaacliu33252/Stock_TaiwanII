#!/usr/bin/env python3
"""Fetch and store TAIFEX TXO options data; compute PCR and OI-based features."""

from __future__ import annotations

import argparse
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
DEFAULT_CONTRACT = "TXO"

CREATE_TAIFEX_OPTIONS_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS taifex_options_daily (
    dt DATE NOT NULL,
    contract TEXT NOT NULL,
    contract_month TEXT NOT NULL,
    strike_price DOUBLE NOT NULL DEFAULT 0.0,
    call_put TEXT NOT NULL,
    trading_session TEXT NOT NULL,
    open DOUBLE NOT NULL DEFAULT 0.0,
    high DOUBLE NOT NULL DEFAULT 0.0,
    low DOUBLE NOT NULL DEFAULT 0.0,
    close DOUBLE NOT NULL DEFAULT 0.0,
    volume DOUBLE NOT NULL DEFAULT 0.0,
    settlement_price DOUBLE NOT NULL DEFAULT 0.0,
    open_interest DOUBLE NOT NULL DEFAULT 0.0,
    best_bid DOUBLE NOT NULL DEFAULT 0.0,
    best_ask DOUBLE NOT NULL DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'taifex_openapi_daily_market_report_opt',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt, contract, contract_month, strike_price, call_put, trading_session)
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_taifex_opt_dt ON taifex_options_daily(dt)",
    "CREATE INDEX IF NOT EXISTS idx_taifex_opt_contract ON taifex_options_daily(contract, dt)",
]

HISTORICAL_COLUMNS = {
    "交易日期": "Date",
    "契約": "Contract",
    "到期月份(週別)": "ContractMonth(Week)",
    "履約價": "StrikePrice",
    "買賣權": "CallPut",
    "開盤價": "Open",
    "最高價": "High",
    "最低價": "Low",
    "收盤價": "Close",
    "成交量": "Volume",
    "結算價": "SettlementPrice",
    "未沖銷契約數": "OpenInterest",
    "最後最佳買價": "BestBid",
    "最後最佳賣價": "BestAsk",
    "交易時段": "TradingSession",
}


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def ensure_schema() -> None:
    con = _conn()
    try:
        con.execute(CREATE_TAIFEX_OPTIONS_DAILY_SQL)
        for stmt in INDEX_SQL:
            con.execute(stmt)
    finally:
        con.close()


def _to_float(value: object) -> float:
    text = str(value if value is not None else "").strip().replace(",", "")
    if text in {"", "-", "NULL", "null", "None"}:
        return 0.0
    if text.endswith("%"):
        try:
            return float(text[:-1]) / 100.0
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
            "Referer": f"{TAIFEX_WEB_BASE}/optDailyMarketView",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _fetch_openapi(path: str) -> list[dict[str, Any]]:
    url = f"{OPENAPI_BASE}/{path.lstrip('/')}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected TAIFEX payload for {path}: {type(payload).__name__}")
    return [dict(row) for row in payload]


def _normalize_rows(rows: list[dict[str, Any]], contract: str, source: str) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("Contract", "")).upper().strip() != contract.upper():
            continue
        out.append(
            {
                "dt": _parse_date(row.get("Date")),
                "contract": str(row.get("Contract", "")).upper().strip(),
                "contract_month": str(row.get("ContractMonth(Week)", "")).strip(),
                "strike_price": _to_float(row.get("StrikePrice")),
                "call_put": str(row.get("CallPut", "")).strip(),
                "trading_session": str(row.get("TradingSession", "")).strip() or "一般",
                "open": _to_float(row.get("Open")),
                "high": _to_float(row.get("High")),
                "low": _to_float(row.get("Low")),
                "close": _to_float(row.get("Close")),
                "volume": _to_float(row.get("Volume")),
                "settlement_price": _to_float(row.get("SettlementPrice")),
                "open_interest": _to_float(row.get("OpenInterest")),
                "best_bid": _to_float(row.get("BestBid")),
                "best_ask": _to_float(row.get("BestAsk")),
                "source": source,
            }
        )
    return pd.DataFrame(out)


def _read_taifex_csv(raw: bytes) -> pd.DataFrame:
    for encoding in ("big5", "cp950", "utf-8-sig"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding, index_col=False, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(raw), index_col=False, low_memory=False)


def normalize_historical_csv(raw: bytes, contract: str) -> pd.DataFrame:
    frame = _read_taifex_csv(raw)
    frame = frame.rename(
        columns={key: value for key, value in HISTORICAL_COLUMNS.items() if key in frame.columns}
    )
    records = frame.to_dict(orient="records")
    return _normalize_rows(records, contract, "taifex_opt_data_down")


def upsert_options(rows: pd.DataFrame) -> int:
    if rows.empty:
        return 0
    ensure_schema()
    con = _conn()
    try:
        con.register("incoming_opt", rows)
        con.execute(
            """
            DELETE FROM taifex_options_daily
            USING incoming_opt
            WHERE taifex_options_daily.dt = incoming_opt.dt
              AND taifex_options_daily.contract = incoming_opt.contract
              AND taifex_options_daily.contract_month = incoming_opt.contract_month
              AND taifex_options_daily.strike_price = incoming_opt.strike_price
              AND taifex_options_daily.call_put = incoming_opt.call_put
              AND taifex_options_daily.trading_session = incoming_opt.trading_session
            """
        )
        con.execute(
            """
            INSERT INTO taifex_options_daily (
                dt, contract, contract_month, strike_price, call_put, trading_session,
                open, high, low, close, volume, settlement_price, open_interest,
                best_bid, best_ask, source
            )
            SELECT
                dt, contract, contract_month, strike_price, call_put, trading_session,
                open, high, low, close, volume, settlement_price, open_interest,
                best_bid, best_ask, source
            FROM incoming_opt
            """
        )
        con.unregister("incoming_opt")
    finally:
        con.close()
    return int(len(rows))


def refresh_latest(contract: str = DEFAULT_CONTRACT) -> dict[str, Any]:
    rows_api = _fetch_openapi("/DailyMarketReportOpt")
    df = _normalize_rows(rows_api, contract, "taifex_openapi_daily_market_report_opt")
    written = upsert_options(df)
    dates = sorted({str(d) for d in df["dt"].unique()}) if not df.empty else []
    return {"rows_written": written, "dates": dates, "contract": contract}


def refresh_history_years(
    years: list[int],
    contract: str = DEFAULT_CONTRACT,
    pause_seconds: float = 1.0,
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    total_rows = 0
    for year in years:
        raw = _request_bytes(
            f"{TAIFEX_WEB_BASE}/optDataDown",
            {"down_type": "2", "his_year": str(year)},
        )
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            print(f"  [WARN] {year}: not a zip file, skipping")
            continue
        year_rows = 0
        dates: list[date] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                normalized = normalize_historical_csv(archive.read(name), contract)
                year_rows += upsert_options(normalized)
                if not normalized.empty:
                    dates.extend(normalized["dt"].tolist())
        total_rows += year_rows
        summaries.append(
            {
                "year": year,
                "rows_written": year_rows,
                "min_date": str(min(dates)) if dates else None,
                "max_date": str(max(dates)) if dates else None,
            }
        )
        print(f"  {year}: {year_rows} rows ({min(dates) if dates else '-'} ~ {max(dates) if dates else '-'})")
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    return {"years": summaries, "total_rows_written": total_rows, "contract": contract}


def query_txo_features(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Return daily TXO PCR features ready for NCF merging."""
    ensure_schema()
    where = ["contract = 'TXO'", "trading_session = '一般'"]
    params: list[Any] = []
    if start:
        where.append("dt >= ?")
        params.append(pd.Timestamp(start).date())
    if end:
        where.append("dt <= ?")
        params.append(pd.Timestamp(end).date())

    sql = f"""
        WITH raw AS (
            SELECT
                dt,
                SUM(CASE WHEN call_put = '賣權' THEN volume  ELSE 0 END) AS put_vol,
                SUM(CASE WHEN call_put = '買權' THEN volume  ELSE 0 END) AS call_vol,
                SUM(CASE WHEN call_put = '賣權' THEN open_interest ELSE 0 END) AS put_oi,
                SUM(CASE WHEN call_put = '買權' THEN open_interest ELSE 0 END) AS call_oi,
                SUM(volume) AS total_vol
            FROM taifex_options_daily
            WHERE {' AND '.join(where)}
            GROUP BY dt
        )
        SELECT
            dt,
            CASE WHEN call_vol > 0 THEN put_vol / call_vol ELSE NULL END AS txo_pcr_volume,
            CASE WHEN call_oi  > 0 THEN put_oi  / call_oi  ELSE NULL END AS txo_pcr_oi,
            put_vol,
            call_vol,
            put_oi,
            call_oi,
            total_vol AS txo_total_volume
        FROM raw
        ORDER BY dt
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(sql, params).fetchdf()
    finally:
        con.close()

    if df.empty:
        return df

    df = df.sort_values("dt").reset_index(drop=True)

    # Rolling z-scores (5d, 20d)
    for col in ("txo_pcr_volume", "txo_pcr_oi"):
        for window in (5, 20):
            mu = df[col].rolling(window, min_periods=max(3, window // 2)).mean()
            sigma = df[col].rolling(window, min_periods=max(3, window // 2)).std()
            df[f"{col}_{window}d_zscore"] = ((df[col] - mu) / sigma.replace(0, float("nan"))).fillna(0.0)

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--refresh-latest", action="store_true")
    parser.add_argument("--refresh-history", action="store_true")
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--query-features", action="store_true")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.refresh_latest:
        result = refresh_latest(args.contract)
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        print(text)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        return

    if args.refresh_history:
        years = list(range(args.start_year, args.end_year + 1))
        print(f"Downloading TXO {args.contract} history: {years[0]}-{years[-1]}")
        result = refresh_history_years(years, args.contract, pause_seconds=args.pause_seconds)
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        print(text)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        return

    if args.query_features:
        df = query_txo_features(args.start_date, args.end_date)
        if args.output:
            df.to_csv(args.output, index=False, encoding="utf-8-sig")
        print(df.to_string(index=False))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
