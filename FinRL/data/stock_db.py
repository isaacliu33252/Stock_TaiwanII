#!/usr/bin/env python3
"""
stock_db.py — Stock Database Maintenance CLI
=============================================

功能:
    --build       完整重建（先 DROP 再 INSERT）
    --rebuild      快速重建：只移除 wf 噪音 ticker，重新匯入
    --update       增量更新：比對 parquet 與 DB，只寫入新的 dt
    --add SYMBOL   新增股票（從網路下載寫入 DB）
    --add-margin   新增融資融券資料（從 TWSE / TPEX 下載寫入 DB）
    --query        查詢
    --validate     驗證資料完整性（缺交易日、價格異常）
    --stats        顯示 DB 狀態
    --dedup        移除DB重複記錄

用法:
    python3 stock_db.py --stats
    python3 stock_db.py --update
    python3 stock_db.py --add 2330.TW --start 2020-01-01
    python3 stock_db.py --validate
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import requests

# ─── Paths ────────────────────────────────────────────────────────────────────

FINRL_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = FINRL_ROOT / "data" / "stock_data.db"
CACHE_DIR = FINRL_ROOT / "data" / "cache"


# ─── Schema ───────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker       TEXT    NOT NULL,
    dt           DATE    NOT NULL,
    open         DOUBLE  NOT NULL,
    high         DOUBLE  NOT NULL,
    low          DOUBLE  NOT NULL,
    close        DOUBLE  NOT NULL,
    volume       BIGINT  NOT NULL,
    dividends    DOUBLE  DEFAULT 0.0,
    stock_splits DOUBLE  DEFAULT 0.0,
    source_file  TEXT    NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_INSTITUTIONAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS institutional_data (
    ticker                       TEXT    NOT NULL,
    dt                           DATE    NOT NULL,
    foreign_net_buy              DOUBLE  NOT NULL DEFAULT 0.0,
    investment_trust_net_buy     DOUBLE  NOT NULL DEFAULT 0.0,
    dealer_net_buy               DOUBLE  NOT NULL DEFAULT 0.0,
    institutional_total_net_buy  DOUBLE  NOT NULL DEFAULT 0.0,
    source                       TEXT    NOT NULL DEFAULT 'twse_t86',
    updated_at                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_MARGIN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS margin_data (
    ticker             TEXT    NOT NULL,
    dt                 DATE    NOT NULL,
    margin_buy         DOUBLE  NOT NULL DEFAULT 0.0,
    margin_sell        DOUBLE  NOT NULL DEFAULT 0.0,
    margin_repayment   DOUBLE  NOT NULL DEFAULT 0.0,
    margin_limit       DOUBLE  NOT NULL DEFAULT 0.0,
    margin_balance     DOUBLE  NOT NULL DEFAULT 0.0,
    margin_prev_balance DOUBLE NOT NULL DEFAULT 0.0,
    offset_loan_short  DOUBLE  NOT NULL DEFAULT 0.0,
    short_buy          DOUBLE  NOT NULL DEFAULT 0.0,
    short_sell         DOUBLE  NOT NULL DEFAULT 0.0,
    short_repayment    DOUBLE  NOT NULL DEFAULT 0.0,
    short_limit        DOUBLE  NOT NULL DEFAULT 0.0,
    short_balance      DOUBLE  NOT NULL DEFAULT 0.0,
    short_prev_balance DOUBLE  NOT NULL DEFAULT 0.0,
    source             TEXT    NOT NULL DEFAULT 'twse_mi_margn',
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_MARKET_MARGIN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_margin_data (
    dt                 DATE    NOT NULL,
    ticker_count       BIGINT  NOT NULL DEFAULT 0,
    margin_buy         DOUBLE  NOT NULL DEFAULT 0.0,
    margin_sell        DOUBLE  NOT NULL DEFAULT 0.0,
    margin_repayment   DOUBLE  NOT NULL DEFAULT 0.0,
    margin_limit       DOUBLE  NOT NULL DEFAULT 0.0,
    margin_balance     DOUBLE  NOT NULL DEFAULT 0.0,
    margin_prev_balance DOUBLE NOT NULL DEFAULT 0.0,
    offset_loan_short  DOUBLE  NOT NULL DEFAULT 0.0,
    short_buy          DOUBLE  NOT NULL DEFAULT 0.0,
    short_sell         DOUBLE  NOT NULL DEFAULT 0.0,
    short_repayment    DOUBLE  NOT NULL DEFAULT 0.0,
    short_limit        DOUBLE  NOT NULL DEFAULT 0.0,
    short_balance      DOUBLE  NOT NULL DEFAULT 0.0,
    short_prev_balance DOUBLE  NOT NULL DEFAULT 0.0,
    source             TEXT    NOT NULL DEFAULT 'twse_mi_margn_all',
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt)
);
"""

CREATE_SHAREHOLDING_DISTRIBUTION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shareholding_distribution (
    stock_id       TEXT    NOT NULL,
    dt             DATE    NOT NULL,
    holding_level  BIGINT  NOT NULL,
    people         BIGINT  NOT NULL DEFAULT 0,
    shares         BIGINT  NOT NULL DEFAULT 0,
    percent        DOUBLE  NOT NULL DEFAULT 0.0,
    source         TEXT    NOT NULL DEFAULT 'tdcc_openapi_1_5',
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_id, dt, holding_level)
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_ticker_dt ON ohlcv(ticker, dt)",
    "CREATE INDEX IF NOT EXISTS idx_dt ON ohlcv(dt)",
    "CREATE INDEX IF NOT EXISTS idx_updated ON ohlcv(updated_at)",
]

INSTITUTIONAL_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_inst_ticker_dt ON institutional_data(ticker, dt)",
    "CREATE INDEX IF NOT EXISTS idx_inst_dt ON institutional_data(dt)",
]

MARGIN_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_margin_ticker_dt ON margin_data(ticker, dt)",
    "CREATE INDEX IF NOT EXISTS idx_margin_dt ON margin_data(dt)",
]

MARKET_MARGIN_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_market_margin_dt ON market_margin_data(dt)",
]

SHAREHOLDING_DISTRIBUTION_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_shareholding_stock_dt ON shareholding_distribution(stock_id, dt)",
    "CREATE INDEX IF NOT EXISTS idx_shareholding_dt ON shareholding_distribution(dt)",
]

INSTITUTIONAL_COLUMNS = [
    "foreign_net_buy",
    "investment_trust_net_buy",
    "dealer_net_buy",
    "institutional_total_net_buy",
]

MARGIN_COLUMNS = [
    "margin_buy",
    "margin_sell",
    "margin_repayment",
    "margin_limit",
    "margin_balance",
    "margin_prev_balance",
    "offset_loan_short",
    "short_buy",
    "short_sell",
    "short_repayment",
    "short_limit",
    "short_balance",
    "short_prev_balance",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def _read_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


def _inclusive_history_end(value: str | date | datetime) -> str:
    """yfinance history() treats end as exclusive; move it forward one day."""
    return (pd.Timestamp(value).normalize() + timedelta(days=1)).strftime("%Y-%m-%d")


def _normalize_yf_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol.endswith((".TW", ".TWO")):
        return symbol
    return f"{symbol}.TW"


def _normalize_twse_institutional_ticker(symbol: str) -> str:
    symbol = str(symbol).upper().strip()
    if symbol.endswith((".TW", ".TWO")):
        return symbol
    return f"{symbol}.TW"


def _normalize_twse_margin_ticker(symbol: str) -> str:
    symbol = str(symbol).upper().strip()
    if symbol.endswith((".TW", ".TWO")):
        return symbol
    return f"{symbol}.TW"


def _normalize_tpex_ticker(symbol: str) -> str:
    symbol = str(symbol).upper().strip()
    if symbol.endswith(".TWO"):
        return symbol
    if symbol.endswith(".TW"):
        return f"{symbol[:-3]}.TWO"
    return f"{symbol}.TWO"


def _normalize_shareholding_stock_id(symbol: str) -> str:
    symbol = str(symbol).upper().strip()
    if symbol.endswith(".TWO"):
        return symbol[:-4]
    if symbol.endswith(".TW"):
        return symbol[:-3]
    return symbol


SHAREHOLDING_LEVEL_MAP = {
    "1-999": 1,
    "1,000-5,000": 2,
    "5,001-10,000": 3,
    "10,001-15,000": 4,
    "15,001-20,000": 5,
    "20,001-30,000": 6,
    "30,001-40,000": 7,
    "40,001-50,000": 8,
    "50,001-100,000": 9,
    "100,001-200,000": 10,
    "200,001-400,000": 11,
    "400,001-600,000": 12,
    "600,001-800,000": 13,
    "800,001-1,000,000": 14,
    "1,000,001以上": 15,
    "morethan1,000,001": 15,
    "差異數調整": 16,
    "差異數調整（說明4）": 16,
    "difference": 16,
    "合計": 17,
    "total": 17,
}


def _normalize_shareholding_level(value: object) -> int | None:
    raw = str(value).strip().replace(" ", "")
    numeric = pd.to_numeric(raw, errors="coerce")
    if not pd.isna(numeric):
        return int(numeric)
    return SHAREHOLDING_LEVEL_MAP.get(raw)


def _roc_date_string(trade_date: str | date | datetime) -> str:
    ts = pd.Timestamp(trade_date).normalize()
    return f"{ts.year - 1911:03d}/{ts.month:02d}/{ts.day:02d}"


def _decode_tpex_csv_bytes(content: bytes) -> str:
    for encoding in ("cp950", "big5hkscs", "big5", "utf-8-sig", "utf-8"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "代號" in text or "日期" in text or "資料日期" in text:
            return text
    return content.decode("cp950", errors="ignore")


def _extract_ticker(fname: str) -> str:
    """解析 parquet 檔名 → ticker"""
    base = fname.replace(".parquet", "")
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_", base)
    return base[: m.start()] if m else base.split("_")[0]


def _ensure_db() -> None:
    """確保資料庫和資料表存在"""
    conn = _conn()
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_INSTITUTIONAL_TABLE_SQL)
    conn.execute(CREATE_SHAREHOLDING_DISTRIBUTION_TABLE_SQL)
    _ensure_schema_compat(conn)
    _ensure_indexes(conn)
    conn.close()


def _ensure_schema_compat(conn: duckdb.DuckDBPyConnection) -> None:
    """Backfill columns added after older DBs were created."""
    cols = {
        str(row[1]): row
        for row in conn.execute("PRAGMA table_info('ohlcv')").fetchall()
    }
    if not cols:
        return

    alter_stmts: list[str] = []
    if "source_file" not in cols:
        alter_stmts.append("ALTER TABLE ohlcv ADD COLUMN source_file TEXT DEFAULT ''")
    if "updated_at" not in cols:
        alter_stmts.append("ALTER TABLE ohlcv ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    for stmt in alter_stmts:
        conn.execute(stmt)

    conn.execute(CREATE_INSTITUTIONAL_TABLE_SQL)
    conn.execute(CREATE_MARGIN_TABLE_SQL)
    conn.execute(CREATE_MARKET_MARGIN_TABLE_SQL)
    conn.execute(CREATE_SHAREHOLDING_DISTRIBUTION_TABLE_SQL)


def _ensure_indexes(conn: duckdb.DuckDBPyConnection) -> None:
    for stmt in INDEX_SQL:
        conn.execute(stmt)
    for stmt in INSTITUTIONAL_INDEX_SQL:
        conn.execute(stmt)
    for stmt in MARGIN_INDEX_SQL:
        conn.execute(stmt)
    for stmt in MARKET_MARGIN_INDEX_SQL:
        conn.execute(stmt)
    for stmt in SHAREHOLDING_DISTRIBUTION_INDEX_SQL:
        conn.execute(stmt)


def query_ohlcv(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Query OHLCV rows from DuckDB and return a pandas DataFrame."""
    ticker = str(ticker).upper().strip()
    if not ticker:
        return pd.DataFrame()

    sql = """
        SELECT
            ticker,
            dt,
            open,
            high,
            low,
            close,
            volume,
            dividends,
            stock_splits
        FROM ohlcv
        WHERE ticker = ?
    """
    params: list[object] = [ticker]
    if start_date:
        sql += " AND dt >= ?"
        params.append(str(start_date))
    if end_date:
        sql += " AND dt <= ?"
        params.append(str(end_date))
    sql += " ORDER BY dt"

    conn = _read_conn()
    try:
        df = conn.execute(sql, params).fetchdf()
    finally:
        conn.close()
    return df


def query_institutional_data(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Query institutional net-buy rows from DuckDB and return a pandas DataFrame."""
    ticker = _normalize_twse_institutional_ticker(ticker)
    if not ticker:
        return pd.DataFrame()

    conn = _read_conn()
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "institutional_data" not in tables:
            return pd.DataFrame()
        sql = """
            SELECT
                ticker,
                dt,
                foreign_net_buy,
                investment_trust_net_buy,
                dealer_net_buy,
                institutional_total_net_buy
            FROM institutional_data
            WHERE ticker = ?
        """
        params: list[object] = [ticker]
        if start_date:
            sql += " AND dt >= ?"
            params.append(str(start_date))
        if end_date:
            sql += " AND dt <= ?"
            params.append(str(end_date))
        sql += " ORDER BY dt"
        return conn.execute(sql, params).fetchdf()
    finally:
        conn.close()


def query_margin_data(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Query margin/short-sale rows from DuckDB and return a pandas DataFrame."""
    ticker = _normalize_twse_margin_ticker(ticker)
    if not ticker:
        return pd.DataFrame()

    conn = _read_conn()
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "margin_data" not in tables:
            return pd.DataFrame()
        sql = """
            SELECT
                ticker,
                dt,
                margin_buy,
                margin_sell,
                margin_repayment,
                margin_limit,
                margin_balance,
                margin_prev_balance,
                offset_loan_short,
                short_buy,
                short_sell,
                short_repayment,
                short_limit,
                short_balance,
                short_prev_balance
            FROM margin_data
            WHERE ticker = ?
        """
        params: list[object] = [ticker]
        if start_date:
            sql += " AND dt >= ?"
            params.append(str(start_date))
        if end_date:
            sql += " AND dt <= ?"
            params.append(str(end_date))
        sql += " ORDER BY dt"
        return conn.execute(sql, params).fetchdf()
    finally:
        conn.close()


def query_market_margin_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Query market-level TWSE margin/short-sale aggregates from DuckDB."""
    conn = _read_conn()
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "market_margin_data" not in tables:
            return pd.DataFrame()
        sql = """
            SELECT
                dt,
                ticker_count,
                margin_buy,
                margin_sell,
                margin_repayment,
                margin_limit,
                margin_balance,
                margin_prev_balance,
                offset_loan_short,
                short_buy,
                short_sell,
                short_repayment,
                short_limit,
                short_balance,
                short_prev_balance
            FROM market_margin_data
            WHERE 1 = 1
        """
        params: list[object] = []
        if start_date:
            sql += " AND dt >= ?"
            params.append(str(start_date))
        if end_date:
            sql += " AND dt <= ?"
            params.append(str(end_date))
        sql += " ORDER BY dt"
        return conn.execute(sql, params).fetchdf()
    finally:
        conn.close()


def query_shareholding_distribution(
    stock_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Query TDCC/FinMind shareholding-tier rows from DuckDB."""
    stock_id = _normalize_shareholding_stock_id(stock_id)
    if not stock_id:
        return pd.DataFrame()

    conn = _read_conn()
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "shareholding_distribution" not in tables:
            return pd.DataFrame()
        sql = """
            SELECT stock_id, dt, holding_level, people, shares, percent, source
            FROM shareholding_distribution
            WHERE stock_id = ?
        """
        params: list[object] = [stock_id]
        if start_date:
            sql += " AND dt >= ?"
            params.append(str(start_date))
        if end_date:
            sql += " AND dt <= ?"
            params.append(str(end_date))
        sql += " ORDER BY dt, holding_level"
        return conn.execute(sql, params).fetchdf()
    finally:
        conn.close()


def query_shareholding_features(
    stock_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Return weekly minority/major-holder features derived from TDCC tiers."""
    tiers = query_shareholding_distribution(stock_id, start_date, end_date)
    if tiers.empty:
        return pd.DataFrame()
    tiers = tiers.copy()
    tiers["minority_percent"] = tiers["percent"].where(tiers["holding_level"].between(1, 5), 0.0)
    tiers["major_percent"] = tiers["percent"].where(tiers["holding_level"].between(12, 15), 0.0)
    total_people = (
        tiers.loc[tiers["holding_level"] == 17, ["dt", "people"]]
        .drop_duplicates(subset=["dt"], keep="last")
        .rename(columns={"people": "total_people"})
    )
    features = (
        tiers.groupby("dt", as_index=False)[["minority_percent", "major_percent"]]
        .sum()
        .merge(total_people, on="dt", how="left")
        .sort_values("dt")
        .reset_index(drop=True)
    )
    features["total_people"] = pd.to_numeric(features["total_people"], errors="coerce").fillna(0).astype("int64")
    is_adjacent_week = pd.to_datetime(features["dt"]).diff().dt.days.le(10)
    features["minority_percent_change_1w"] = features["minority_percent"].diff().where(is_adjacent_week, 0.0)
    features["major_percent_change_1w"] = features["major_percent"].diff().where(is_adjacent_week, 0.0)
    features["total_people_change_1w"] = features["total_people"].diff().where(is_adjacent_week, 0).astype("int64")
    return features


def parse_shareholding_distribution_rows(
    payload: list[dict[str, object]] | dict[str, object],
    *,
    source: str = "tdcc_openapi_1_5",
) -> pd.DataFrame:
    """Normalize TDCC OpenAPI or FinMind TaiwanStockHoldingSharesPer rows."""
    if isinstance(payload, dict):
        raw_rows = payload.get("data", [])
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list) or not raw_rows:
        return pd.DataFrame()

    records: list[dict[str, object]] = []
    def numeric(value: object) -> object:
        return str(value).replace(",", "").strip() if isinstance(value, str) else value

    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        clean = {str(key).lstrip("\ufeff"): value for key, value in row.items()}
        stock_id = clean.get("證券代號", clean.get("stock_id", ""))
        raw_date = clean.get("資料日期", clean.get("date"))
        holding_level = clean.get("持股分級", clean.get("holding_level", clean.get("HoldingSharesLevel")))
        people = clean.get("人數", clean.get("people", 0))
        shares = clean.get("股數", clean.get("shares", clean.get("unit", 0)))
        percent = clean.get("占集保庫存數比例%", clean.get("percent", 0.0))
        if stock_id in (None, "") or raw_date in (None, "") or holding_level in (None, ""):
            continue
        normalized_level = _normalize_shareholding_level(holding_level)
        if normalized_level is None:
            continue
        records.append(
            {
                "stock_id": _normalize_shareholding_stock_id(str(stock_id)),
                "dt": pd.to_datetime(str(raw_date), errors="coerce"),
                "holding_level": normalized_level,
                "people": pd.to_numeric(numeric(people), errors="coerce"),
                "shares": pd.to_numeric(numeric(shares), errors="coerce"),
                "percent": pd.to_numeric(numeric(percent), errors="coerce"),
                "source": source,
            }
        )
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame.from_records(records)
    frame = frame.dropna(subset=["stock_id", "dt", "holding_level"])
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    frame["people"] = frame["people"].fillna(0).astype("int64")
    frame["shares"] = frame["shares"].fillna(0).astype("int64")
    frame["percent"] = frame["percent"].fillna(0.0).astype(float)
    return frame.drop_duplicates(subset=["stock_id", "dt", "holding_level"], keep="last").reset_index(drop=True)


def _pick_first_existing_column(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for name in candidates:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index, dtype=float)


def _normalize_header_text(value: str) -> str:
    return re.sub(r"[\s\u3000()（）,:：/\\-]", "", str(value).strip())


def _find_matching_column_name(
    columns: list[str] | pd.Index,
    *,
    exact: list[str] | None = None,
    contains_all: list[list[str]] | None = None,
) -> str | None:
    normalized = {str(column): _normalize_header_text(column) for column in columns}

    for candidate in exact or []:
        target = _normalize_header_text(candidate)
        for column, token in normalized.items():
            if token == target:
                return column

    for group in contains_all or []:
        target_tokens = [_normalize_header_text(token) for token in group]
        for column, token in normalized.items():
            if all(part in token for part in target_tokens):
                return column
    return None


def _pick_numeric_column(
    df: pd.DataFrame,
    *,
    exact: list[str] | None = None,
    contains_all: list[list[str]] | None = None,
) -> pd.Series:
    column = _find_matching_column_name(df.columns, exact=exact, contains_all=contains_all)
    if column is None:
        return pd.Series(0.0, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _parse_twse_t86_csv(text: str, trade_date: pd.Timestamp) -> pd.DataFrame:
    lines = [line for line in text.splitlines() if line.strip()]
    header_idx = None
    for idx, line in enumerate(lines):
        if "證券代號" in line and "投信" in line and "自營商" in line:
            header_idx = idx
            break
    if header_idx is None:
        return pd.DataFrame()

    csv_text = "\n".join(lines[header_idx:])
    reader = csv.reader(StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return pd.DataFrame()

    header = rows[0]
    data_rows = []
    for row in rows[1:]:
        if not row or len(row) != len(header):
            continue
        code = str(row[0]).replace("=", "").replace('"', "").strip().upper()
        if not re.fullmatch(r"[0-9A-Z]{4,7}", code):
            continue
        data_rows.append(row)
    if not data_rows:
        return pd.DataFrame()

    df = pd.DataFrame(data_rows, columns=header)
    df = df.dropna(how="all", axis=1)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.loc[:, [column for column in df.columns if column]]
    df = df.apply(
        lambda column: column.map(lambda value: value.replace(",", "").strip() if isinstance(value, str) else value)
    )
    codes = (
        df["證券代號"]
        .astype(str)
        .str.replace("=", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.upper()
    )

    foreign_core = _pick_first_existing_column(
        df,
        [
            "外陸資買賣超股數(不含外資自營商)",
            "外資買賣超股數",
            "外資及陸資買賣超股數",
        ],
    )
    foreign_prop = _pick_first_existing_column(df, ["外資自營商買賣超股數"])
    investment_trust = _pick_first_existing_column(df, ["投信買賣超股數"])
    dealer = _pick_first_existing_column(df, ["自營商買賣超股數"])
    institutional_total = _pick_first_existing_column(df, ["三大法人買賣超股數"])
    foreign_total = foreign_core + foreign_prop
    if (institutional_total.abs() < 1e-12).all():
        institutional_total = foreign_total + investment_trust + dealer

    out = pd.DataFrame(
        {
            "ticker": codes.map(_normalize_twse_institutional_ticker),
            "dt": pd.Timestamp(trade_date).date(),
            "foreign_net_buy": foreign_total.astype(float),
            "investment_trust_net_buy": investment_trust.astype(float),
            "dealer_net_buy": dealer.astype(float),
            "institutional_total_net_buy": institutional_total.astype(float),
            "source": "twse_t86",
        }
    )
    return out.drop_duplicates(subset=["ticker", "dt"], keep="last").reset_index(drop=True)


def _parse_tpex_csv_frame(text: str, required_markers: list[str]) -> pd.DataFrame:
    lines = [line for line in text.splitlines() if line.strip()]
    header_idx = None
    for idx, line in enumerate(lines):
        if all(marker in line for marker in required_markers):
            header_idx = idx
            break
    if header_idx is None:
        return pd.DataFrame()

    reader = csv.reader(StringIO("\n".join(lines[header_idx:])))
    rows = list(reader)
    if not rows:
        return pd.DataFrame()

    header = [str(column).strip() for column in rows[0]]
    data_rows: list[list[object]] = []
    for row in rows[1:]:
        if not row or len(row) != len(header):
            continue
        code = str(row[0]).replace("=", "").replace('"', "").strip().upper()
        if not re.fullmatch(r"[0-9A-Z]{4,7}", code):
            continue
        data_rows.append(row)
    if not data_rows:
        return pd.DataFrame()

    df = pd.DataFrame(data_rows, columns=header)
    df = df.dropna(how="all", axis=1)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.loc[:, [column for column in df.columns if column]]
    return df.apply(
        lambda column: column.map(lambda value: value.replace(",", "").strip() if isinstance(value, str) else value)
    )


def _parse_tpex_institutional_csv(text: str, trade_date: pd.Timestamp) -> pd.DataFrame:
    df = _parse_tpex_csv_frame(text, ["代號", "三大法人買賣超股數"])
    if df.empty:
        return pd.DataFrame()

    code_col = _find_matching_column_name(
        df.columns,
        exact=["代號", "證券代號", "股票代號"],
        contains_all=[["代號"]],
    )
    if code_col is None:
        return pd.DataFrame()

    codes = (
        df[code_col]
        .astype(str)
        .str.replace("=", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.upper()
    )
    valid_mask = codes.str.fullmatch(r"[0-9A-Z]{4,7}", na=False)
    if not valid_mask.any():
        return pd.DataFrame()
    df = df.loc[valid_mask].copy()
    codes = codes.loc[valid_mask]

    foreign_core = _pick_numeric_column(
        df,
        exact=[
            "外資及陸資(不含外資自營商)-買賣超股數",
            "外陸資(不含外資自營商)-買賣超股數",
        ],
        contains_all=[
            ["外資", "不含外資自營商", "買賣超股數"],
            ["外陸資", "不含外資自營商", "買賣超股數"],
        ],
    )
    foreign_prop = _pick_numeric_column(
        df,
        exact=["外資自營商-買賣超股數"],
        contains_all=[["外資自營商", "買賣超股數"]],
    )
    foreign_total_reported = _pick_numeric_column(
        df,
        exact=["外資及陸資-買賣超股數", "外陸資-買賣超股數"],
        contains_all=[["外資及陸資", "買賣超股數"], ["外陸資", "買賣超股數"]],
    )
    investment_trust = _pick_numeric_column(
        df,
        exact=["投信-買賣超股數"],
        contains_all=[["投信", "買賣超股數"]],
    )
    dealer = _pick_numeric_column(
        df,
        exact=["自營商-買賣超股數"],
        contains_all=[["自營商", "買賣超股數"]],
    )
    institutional_total = _pick_numeric_column(
        df,
        exact=["三大法人買賣超股數合計", "三大法人買賣超股數"],
        contains_all=[["三大法人", "買賣超股數"]],
    )
    foreign_total = foreign_total_reported.copy()
    if (foreign_total.abs() < 1e-12).all():
        foreign_total = foreign_core + foreign_prop
    if (institutional_total.abs() < 1e-12).all():
        institutional_total = foreign_total + investment_trust + dealer

    out = pd.DataFrame(
        {
            "ticker": codes.map(_normalize_tpex_ticker),
            "dt": pd.Timestamp(trade_date).date(),
            "foreign_net_buy": foreign_total.astype(float),
            "investment_trust_net_buy": investment_trust.astype(float),
            "dealer_net_buy": dealer.astype(float),
            "institutional_total_net_buy": institutional_total.astype(float),
            "source": "tpex_3itrade_hedge",
        }
    )
    return out.drop_duplicates(subset=["ticker", "dt"], keep="last").reset_index(drop=True)


def _parse_tpex_margin_csv(text: str, trade_date: pd.Timestamp) -> pd.DataFrame:
    df = _parse_tpex_csv_frame(text, ["代號", "前資餘"])
    if df.empty:
        return pd.DataFrame()

    code_col = _find_matching_column_name(
        df.columns,
        exact=["代號", "證券代號", "股票代號"],
        contains_all=[["代號"]],
    )
    if code_col is None:
        return pd.DataFrame()

    codes = (
        df[code_col]
        .astype(str)
        .str.replace("=", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.upper()
    )
    valid_mask = codes.str.fullmatch(r"[0-9A-Z]{4,7}", na=False)
    if not valid_mask.any():
        return pd.DataFrame()
    df = df.loc[valid_mask].copy()
    codes = codes.loc[valid_mask]

    out = pd.DataFrame(
        {
            "ticker": codes.map(_normalize_tpex_ticker),
            "dt": pd.Timestamp(trade_date).date(),
            "margin_buy": _pick_numeric_column(df, exact=["資買"]).astype(float),
            "margin_sell": _pick_numeric_column(df, exact=["資賣"]).astype(float),
            "margin_repayment": _pick_numeric_column(df, exact=["現償"]).astype(float),
            "margin_limit": _pick_numeric_column(df, exact=["資限額"]).astype(float),
            "margin_balance": _pick_numeric_column(df, exact=["資餘額", "資餘"]).astype(float),
            "margin_prev_balance": _pick_numeric_column(df, exact=["前資餘額(張)", "前資餘(張)", "前資餘"]).astype(float),
            "offset_loan_short": _pick_numeric_column(df, exact=["資券相抵(張)", "資券相抵", "資券互抵"]).astype(float),
            "short_buy": _pick_numeric_column(df, exact=["券買"]).astype(float),
            "short_sell": _pick_numeric_column(df, exact=["券賣"]).astype(float),
            "short_repayment": _pick_numeric_column(df, exact=["券償"]).astype(float),
            "short_limit": _pick_numeric_column(df, exact=["券限額"]).astype(float),
            "short_balance": _pick_numeric_column(df, exact=["券餘額", "券餘"]).astype(float),
            "short_prev_balance": _pick_numeric_column(df, exact=["前券餘額(張)", "券前餘額(張)", "券前餘", "前券餘"]).astype(float),
            "source": "tpex_margin_bal",
        }
    )
    return out.drop_duplicates(subset=["ticker", "dt"], keep="last").reset_index(drop=True)


def _extract_twse_table_from_json(
    payload: dict,
    *,
    required_tokens: list[str],
) -> tuple[str | None, list[str], list[list[object]]] | None:
    candidates: list[tuple[str | None, list[str], list[list[object]]]] = []

    if isinstance(payload.get("fields"), list) and isinstance(payload.get("data"), list):
        candidates.append((payload.get("title"), payload["fields"], payload["data"]))

    for table in payload.get("tables", []) or []:
        if isinstance(table, dict) and isinstance(table.get("fields"), list) and isinstance(table.get("data"), list):
            candidates.append((table.get("title"), table["fields"], table["data"]))

    normalized_required = [_normalize_header_text(token) for token in required_tokens]
    for title, fields, rows in candidates:
        normalized_title = _normalize_header_text(title or "")
        if normalized_title and all(token in normalized_title for token in normalized_required):
            return title, fields, rows
        normalized_fields = [_normalize_header_text(field) for field in fields]
        if all(any(token in field for field in normalized_fields) for token in normalized_required):
            return title, fields, rows
    return None


def _parse_twse_margin_frame(frame: pd.DataFrame, trade_date: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    df = frame.copy()
    df = df.dropna(how="all", axis=1)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.loc[:, [column for column in df.columns if column]]
    df = df.apply(
        lambda column: column.map(lambda value: value.replace(",", "").strip() if isinstance(value, str) else value)
    )

    code_col = _find_matching_column_name(
        df.columns,
        exact=["證券代號", "股票代號"],
        contains_all=[["證券", "代號"], ["股票", "代號"]],
    )
    if code_col is None:
        return pd.DataFrame()

    codes = (
        df[code_col]
        .astype(str)
        .str.replace("=", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.upper()
    )
    valid_mask = codes.str.fullmatch(r"[0-9A-Z]{4,7}", na=False)
    if not valid_mask.any():
        return pd.DataFrame()
    df = df.loc[valid_mask].copy()
    codes = codes.loc[valid_mask]

    out = pd.DataFrame(
        {
            "ticker": codes.map(_normalize_twse_margin_ticker),
            "dt": pd.Timestamp(trade_date).date(),
            "margin_buy": _pick_numeric_column(df, exact=["融資買進"], contains_all=[["融資", "買進"]]).astype(float),
            "margin_sell": _pick_numeric_column(df, exact=["融資賣出"], contains_all=[["融資", "賣出"]]).astype(float),
            "margin_repayment": _pick_numeric_column(
                df,
                exact=["融資現金償還", "融資償還"],
                contains_all=[["融資", "償還"]],
            ).astype(float),
            "margin_limit": _pick_numeric_column(df, exact=["融資限額"], contains_all=[["融資", "限額"]]).astype(float),
            "margin_balance": _pick_numeric_column(
                df,
                exact=["融資今日餘額"],
                contains_all=[["融資", "今日", "餘額"]],
            ).astype(float),
            "margin_prev_balance": _pick_numeric_column(
                df,
                exact=["融資前日餘額"],
                contains_all=[["融資", "前日", "餘額"]],
            ).astype(float),
            "offset_loan_short": _pick_numeric_column(
                df,
                exact=["資券相抵", "資券互抵"],
                contains_all=[["資券", "抵"]],
            ).astype(float),
            "short_buy": _pick_numeric_column(df, exact=["融券買進"], contains_all=[["融券", "買進"]]).astype(float),
            "short_sell": _pick_numeric_column(df, exact=["融券賣出"], contains_all=[["融券", "賣出"]]).astype(float),
            "short_repayment": _pick_numeric_column(
                df,
                exact=["融券現券償還", "融券償還"],
                contains_all=[["融券", "償還"]],
            ).astype(float),
            "short_limit": _pick_numeric_column(df, exact=["融券限額"], contains_all=[["融券", "限額"]]).astype(float),
            "short_balance": _pick_numeric_column(
                df,
                exact=["融券今日餘額"],
                contains_all=[["融券", "今日", "餘額"]],
            ).astype(float),
            "short_prev_balance": _pick_numeric_column(
                df,
                exact=["融券前日餘額"],
                contains_all=[["融券", "前日", "餘額"]],
            ).astype(float),
            "source": "twse_mi_margn",
        }
    )
    return out.drop_duplicates(subset=["ticker", "dt"], keep="last").reset_index(drop=True)


def _clean_twse_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace(",", "").replace("=", "").replace('"', "").strip()
    return str(value).strip()


def _coerce_twse_numeric(value: object) -> float:
    numeric = pd.to_numeric(_clean_twse_value(value), errors="coerce")
    if pd.isna(numeric):
        return 0.0
    return float(numeric)


def _parse_twse_margin_rows(
    fields: list[str],
    rows: list[list[object]],
    trade_date: pd.Timestamp,
) -> pd.DataFrame:
    normalized_fields = [_normalize_header_text(field) for field in fields]
    uses_summary_layout = (
        len(fields) >= 15
        and normalized_fields[:2] == [_normalize_header_text("代號"), _normalize_header_text("名稱")]
        and normalized_fields.count(_normalize_header_text("買進")) >= 2
        and normalized_fields.count(_normalize_header_text("今日餘額")) >= 2
    )
    if not uses_summary_layout:
        return _parse_twse_margin_frame(pd.DataFrame(rows, columns=fields), trade_date)

    records: list[dict[str, object]] = []
    for row in rows:
        if not row or len(row) < 15:
            continue
        code = _clean_twse_value(row[0]).upper()
        if not re.fullmatch(r"[0-9A-Z]{4,7}", code):
            continue
        records.append(
            {
                "ticker": _normalize_twse_margin_ticker(code),
                "dt": pd.Timestamp(trade_date).date(),
                "margin_buy": _coerce_twse_numeric(row[2]),
                "margin_sell": _coerce_twse_numeric(row[3]),
                "margin_repayment": _coerce_twse_numeric(row[4]),
                "margin_prev_balance": _coerce_twse_numeric(row[5]),
                "margin_balance": _coerce_twse_numeric(row[6]),
                "margin_limit": _coerce_twse_numeric(row[7]),
                "short_buy": _coerce_twse_numeric(row[8]),
                "short_sell": _coerce_twse_numeric(row[9]),
                "short_repayment": _coerce_twse_numeric(row[10]),
                "short_prev_balance": _coerce_twse_numeric(row[11]),
                "short_balance": _coerce_twse_numeric(row[12]),
                "short_limit": _coerce_twse_numeric(row[13]),
                "offset_loan_short": _coerce_twse_numeric(row[14]),
                "source": "twse_mi_margn",
            }
        )
    if not records:
        return pd.DataFrame()
    return pd.DataFrame.from_records(records).drop_duplicates(subset=["ticker", "dt"], keep="last")


def fetch_twse_margin_day(trade_date: str | date | datetime) -> pd.DataFrame:
    """Fetch one TWSE margin-trading day and return normalized rows."""
    ts = pd.Timestamp(trade_date).normalize()
    endpoints = [
        "https://www.twse.com.tw/exchangeReport/MI_MARGN",
        "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
    ]

    last_error: Exception | None = None
    for url in endpoints:
        try:
            response = requests.get(
                url,
                params={
                    "response": "json",
                    "date": ts.strftime("%Y%m%d"),
                    "selectType": "ALL",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            table = _extract_twse_table_from_json(
                payload,
                required_tokens=["融資融券彙總"],
            )
            if table is not None:
                _, fields, rows = table
                return _parse_twse_margin_rows(fields, rows, ts)
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def fetch_tpex_margin_day(trade_date: str | date | datetime) -> pd.DataFrame:
    """Fetch one TPEX margin-trading day and return normalized rows."""
    ts = pd.Timestamp(trade_date).normalize()
    response = requests.get(
        "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php",
        params={
            "l": "zh-tw",
            "o": "csv",
            "d": _roc_date_string(ts),
            "s": "0,asc,0",
        },
        timeout=30,
    )
    response.raise_for_status()
    text = _decode_tpex_csv_bytes(response.content)
    return _parse_tpex_margin_csv(text, ts)


def fetch_twse_institutional_day(trade_date: str | date | datetime) -> pd.DataFrame:
    """Fetch one TWSE T86 day and return normalized institutional flows."""
    ts = pd.Timestamp(trade_date).normalize()
    url = "https://www.twse.com.tw/fund/T86"
    response = requests.get(
        url,
        params={
            "response": "csv",
            "date": ts.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
        },
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return _parse_twse_t86_csv(response.text, ts)


def fetch_tpex_institutional_day(trade_date: str | date | datetime) -> pd.DataFrame:
    """Fetch one TPEX institutional-flow day and return normalized rows."""
    ts = pd.Timestamp(trade_date).normalize()
    response = requests.get(
        "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php",
        params={
            "l": "zh-tw",
            "o": "csv",
            "se": "EW",
            "t": "D",
            "d": _roc_date_string(ts),
            "s": "0,asc",
        },
        timeout=30,
    )
    response.raise_for_status()
    text = _decode_tpex_csv_bytes(response.content)
    return _parse_tpex_institutional_csv(text, ts)


def aggregate_market_margin_day(rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate one-day full-market TWSE margin rows into a market-level record."""
    if rows is None or rows.empty:
        return pd.DataFrame()

    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for column in MARGIN_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)

    grouped = (
        frame.groupby("dt", as_index=False)[MARGIN_COLUMNS]
        .sum()
        .sort_values("dt")
        .reset_index(drop=True)
    )
    ticker_counts = frame.groupby("dt")["ticker"].nunique().rename("ticker_count").reset_index()
    grouped = grouped.merge(ticker_counts, on="dt", how="left")
    grouped["ticker_count"] = pd.to_numeric(grouped["ticker_count"], errors="coerce").fillna(0).astype(int)
    grouped["source"] = "twse_mi_margn_all"
    return grouped[
        [
            "dt",
            "ticker_count",
            "margin_buy",
            "margin_sell",
            "margin_repayment",
            "margin_limit",
            "margin_balance",
            "margin_prev_balance",
            "offset_loan_short",
            "short_buy",
            "short_sell",
            "short_repayment",
            "short_limit",
            "short_balance",
            "short_prev_balance",
            "source",
        ]
    ]


def upsert_margin_data(rows: pd.DataFrame) -> int:
    """Upsert margin rows into DuckDB."""
    if rows is None or rows.empty:
        return 0

    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for column in MARGIN_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)
    if "source" not in frame.columns:
        frame["source"] = "twse_mi_margn"
    frame = frame[
        [
            "ticker",
            "dt",
            "margin_buy",
            "margin_sell",
            "margin_repayment",
            "margin_limit",
            "margin_balance",
            "margin_prev_balance",
            "offset_loan_short",
            "short_buy",
            "short_sell",
            "short_repayment",
            "short_limit",
            "short_balance",
            "short_prev_balance",
            "source",
        ]
    ].drop_duplicates(subset=["ticker", "dt"], keep="last")

    conn = _conn()
    try:
        conn.execute(CREATE_MARGIN_TABLE_SQL)
        _ensure_indexes(conn)
        conn.register("incoming_margin", frame)
        conn.execute(
            """
            DELETE FROM margin_data
            USING incoming_margin
            WHERE margin_data.ticker = incoming_margin.ticker
              AND margin_data.dt = incoming_margin.dt
            """
        )
        conn.execute(
            """
            INSERT INTO margin_data (
                ticker,
                dt,
                margin_buy,
                margin_sell,
                margin_repayment,
                margin_limit,
                margin_balance,
                margin_prev_balance,
                offset_loan_short,
                short_buy,
                short_sell,
                short_repayment,
                short_limit,
                short_balance,
                short_prev_balance,
                source
            )
            SELECT
                ticker,
                dt,
                margin_buy,
                margin_sell,
                margin_repayment,
                margin_limit,
                margin_balance,
                margin_prev_balance,
                offset_loan_short,
                short_buy,
                short_sell,
                short_repayment,
                short_limit,
                short_balance,
                short_prev_balance,
                source
            FROM incoming_margin
            """
        )
        return int(len(frame))
    finally:
        conn.close()


def upsert_market_margin_data(rows: pd.DataFrame) -> int:
    """Upsert market-level margin rows into DuckDB."""
    if rows is None or rows.empty:
        return 0

    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    frame["ticker_count"] = pd.to_numeric(frame.get("ticker_count", 0), errors="coerce").fillna(0).astype(int)
    for column in MARGIN_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)
    if "source" not in frame.columns:
        frame["source"] = "twse_mi_margn_all"
    frame = frame[
        [
            "dt",
            "ticker_count",
            "margin_buy",
            "margin_sell",
            "margin_repayment",
            "margin_limit",
            "margin_balance",
            "margin_prev_balance",
            "offset_loan_short",
            "short_buy",
            "short_sell",
            "short_repayment",
            "short_limit",
            "short_balance",
            "short_prev_balance",
            "source",
        ]
    ].drop_duplicates(subset=["dt"], keep="last")

    conn = _conn()
    try:
        conn.execute(CREATE_MARKET_MARGIN_TABLE_SQL)
        _ensure_indexes(conn)
        conn.register("incoming_market_margin", frame)
        conn.execute(
            """
            DELETE FROM market_margin_data
            USING incoming_market_margin
            WHERE market_margin_data.dt = incoming_market_margin.dt
            """
        )
        conn.execute(
            """
            INSERT INTO market_margin_data (
                dt,
                ticker_count,
                margin_buy,
                margin_sell,
                margin_repayment,
                margin_limit,
                margin_balance,
                margin_prev_balance,
                offset_loan_short,
                short_buy,
                short_sell,
                short_repayment,
                short_limit,
                short_balance,
                short_prev_balance,
                source
            )
            SELECT
                dt,
                ticker_count,
                margin_buy,
                margin_sell,
                margin_repayment,
                margin_limit,
                margin_balance,
                margin_prev_balance,
                offset_loan_short,
                short_buy,
                short_sell,
                short_repayment,
                short_limit,
                short_balance,
                short_prev_balance,
                source
            FROM incoming_market_margin
            """
        )
        return int(len(frame))
    finally:
        conn.close()


def upsert_institutional_data(rows: pd.DataFrame) -> int:
    """Upsert institutional rows into DuckDB."""
    if rows is None or rows.empty:
        return 0

    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for column in INSTITUTIONAL_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)
    if "source" not in frame.columns:
        frame["source"] = "twse_t86"
    frame = frame[
        [
            "ticker",
            "dt",
            "foreign_net_buy",
            "investment_trust_net_buy",
            "dealer_net_buy",
            "institutional_total_net_buy",
            "source",
        ]
    ].drop_duplicates(subset=["ticker", "dt"], keep="last")

    conn = _conn()
    try:
        conn.execute(CREATE_INSTITUTIONAL_TABLE_SQL)
        _ensure_indexes(conn)
        conn.register("incoming_institutional", frame)
        conn.execute(
            """
            DELETE FROM institutional_data
            USING incoming_institutional
            WHERE institutional_data.ticker = incoming_institutional.ticker
              AND institutional_data.dt = incoming_institutional.dt
            """
        )
        conn.execute(
            """
            INSERT INTO institutional_data (
                ticker,
                dt,
                foreign_net_buy,
                investment_trust_net_buy,
                dealer_net_buy,
                institutional_total_net_buy,
                source
            )
            SELECT
                ticker,
                dt,
                foreign_net_buy,
                investment_trust_net_buy,
                dealer_net_buy,
                institutional_total_net_buy,
                source
            FROM incoming_institutional
            """
        )
        return int(len(frame))
    finally:
        conn.close()


def upsert_shareholding_distribution(rows: pd.DataFrame) -> int:
    """Upsert normalized TDCC/FinMind shareholding-tier rows into DuckDB."""
    if rows is None or rows.empty:
        return 0

    frame = rows.copy()
    frame["stock_id"] = frame["stock_id"].map(_normalize_shareholding_stock_id)
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    frame["holding_level"] = pd.to_numeric(frame["holding_level"], errors="coerce")
    frame["people"] = pd.to_numeric(frame["people"], errors="coerce").fillna(0).astype("int64")
    frame["shares"] = pd.to_numeric(frame["shares"], errors="coerce").fillna(0).astype("int64")
    frame["percent"] = pd.to_numeric(frame["percent"], errors="coerce").fillna(0.0).astype(float)
    if "source" not in frame.columns:
        frame["source"] = "tdcc_openapi_1_5"
    frame = frame.dropna(subset=["stock_id", "dt", "holding_level"])
    frame["holding_level"] = frame["holding_level"].astype("int64")
    frame = frame[
        ["stock_id", "dt", "holding_level", "people", "shares", "percent", "source"]
    ].drop_duplicates(subset=["stock_id", "dt", "holding_level"], keep="last")

    conn = _conn()
    try:
        conn.execute(CREATE_SHAREHOLDING_DISTRIBUTION_TABLE_SQL)
        _ensure_indexes(conn)
        conn.register("incoming_shareholding", frame)
        conn.execute(
            """
            DELETE FROM shareholding_distribution
            USING incoming_shareholding
            WHERE shareholding_distribution.stock_id = incoming_shareholding.stock_id
              AND shareholding_distribution.dt = incoming_shareholding.dt
              AND shareholding_distribution.holding_level = incoming_shareholding.holding_level
            """
        )
        conn.execute(
            """
            INSERT INTO shareholding_distribution (
                stock_id, dt, holding_level, people, shares, percent, source
            )
            SELECT stock_id, dt, holding_level, people, shares, percent, source
            FROM incoming_shareholding
            """
        )
        return int(len(frame))
    finally:
        conn.close()


def cmd_add_shareholding_distribution(input_path: str | None = None) -> dict[str, object]:
    """Import the latest full-market TDCC shareholding distribution snapshot."""
    source = "tdcc_openapi_1_5"
    if input_path:
        path = Path(input_path).expanduser().resolve()
        if path.suffix.lower() == ".csv":
            payload = pd.read_csv(path, dtype={"stock_id": str}).to_dict(orient="records")
            source = f"finmind_file:{path.name}"
        else:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            source = f"tdcc_file:{path.name}"
    else:
        response = requests.get("https://openapi.tdcc.com.tw/v1/opendata/1-5", timeout=60)
        response.raise_for_status()
        payload = response.json()
    rows = parse_shareholding_distribution_rows(payload, source=source)
    if rows.empty:
        return {"error": "No shareholding distribution rows found"}
    rows_written = upsert_shareholding_distribution(rows)
    return {
        "rows_written": rows_written,
        "stock_count": int(rows["stock_id"].nunique()),
        "start_date": str(rows["dt"].min()),
        "end_date": str(rows["dt"].max()),
        "source": source,
    }


# ─── Core operations ──────────────────────────────────────────────────────────

def cmd_build() -> dict:
    """完整重建（刪除舊資料，寫入所有 parquet）"""
    conn = _conn()
    conn.execute("DROP TABLE IF EXISTS ohlcv")
    conn.execute(CREATE_TABLE_SQL)
    _ensure_schema_compat(conn)
    _ensure_indexes(conn)

    files = sorted(CACHE_DIR.glob("*.parquet"))
    if not files:
        print("[build] No parquet files found in cache.")
        return {"ingested": 0}

    all_rows = []
    errors = []

    for i, f in enumerate(files):
        ticker = _extract_ticker(f.name)
        try:
            # SQL injection prevention: sanitize table name from file glob
            # f.name comes from Path.glob("*.parquet"), safe but still validate
            safe_table = f.name.replace("'", "_").replace(";", "_").replace("--", "_")
            df = conn.execute(f"SELECT * FROM '{safe_table}'").fetchdf()
            date_col = next((c for c in ["date", "datetime", "timestamp"] if c in df.columns), None)
            if not date_col:
                errors.append((f.name, "No date column"))
                continue
            df["dt"] = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.date
            df["ticker"] = ticker
            df["source_file"] = f.name
            keep = ["ticker", "dt", "open", "high", "low", "close", "volume",
                    "dividends", "stock_splits", "source_file"]
            for c in keep:
                if c not in df.columns:
                    df[c] = 0.0
            df = df[[c for c in keep if c in df.columns]]
            all_rows.append(df)
        except Exception as e:
            errors.append((f.name, str(e)))

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined = combined.drop_duplicates(subset=["ticker", "dt"], keep="last")
        combined["dt"] = pd.to_datetime(combined["dt"]).dt.date
        conn.execute("INSERT INTO ohlcv SELECT * FROM combined")

    conn.close()
    return {"ingested": len(combined) if all_rows else 0, "files": len(files), "errors": errors}


def cmd_rebuild() -> dict:
    """快速重建：移除噪音 ticker（wf 等），重新匯入"""
    conn = _conn()
    # 只保留乾淨的 ticker
    conn.execute("""
        DELETE FROM ohlcv
        WHERE ticker NOT IN (
            SELECT DISTINCT ticker FROM ohlcv
            WHERE ticker NOT IN ('wf', 'benchmark', 'cash')
              AND ticker SIMILAR TO '^[0-9]{4,6}\\.?TW?$'
        )
    """)
    # 重新整理 source_file（用最新檔名）
    conn.execute("""
        UPDATE ohlcv SET source_file = (
            SELECT source_file FROM ohlcv o2
            WHERE o2.ticker = ohlcv.ticker AND o2.dt = ohlcv.dt
            LIMIT 1
        ) WHERE 1=0
    """)
    count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchdf().iloc[0, 0]
    conn.close()
    return {"retained": int(count)}


def cmd_update() -> dict:
    """增量更新：只寫入 DB 中沒有的 (ticker, dt) 組合"""
    conn = _conn()

    # 取得 DB 現有的 (ticker, dt) set
    existing = set(conn.execute("SELECT ticker, CAST(dt AS VARCHAR) FROM ohlcv").fetchall())

    files = sorted(CACHE_DIR.glob("*.parquet"))
    if not files:
        return {"new_rows": 0, "skipped": 0}

    all_new: list[pd.DataFrame] = []
    skipped = 0

    for f in files:
        ticker = _extract_ticker(f.name)
        try:
            # SQL injection prevention: sanitize table name
            safe_table = f.name.replace("'", "_").replace(";", "_").replace("--", "_")
            df = conn.execute(f"SELECT * FROM '{safe_table}'").fetchdf()
            date_col = next((c for c in ["date", "datetime", "timestamp"] if c in df.columns), None)
            if not date_col:
                continue
            df["dt"] = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.date
            df["ticker"] = ticker
            df["source_file"] = f.name
            keep = ["ticker", "dt", "open", "high", "low", "close", "volume",
                    "dividends", "stock_splits", "source_file"]
            for c in keep:
                if c not in df.columns:
                    df[c] = 0.0
            df = df[[c for c in keep if c in df.columns]]

            # 過濾已存在的
            mask = [f"{r['ticker']}|{r['dt']}" not in existing for _, r in df.iterrows()]
            new_rows = df[mask]
            if new_rows.empty:
                skipped += len(df)
            else:
                all_new.append(new_rows)
                skipped += len(df) - len(new_rows)
        except Exception:
            pass

    if all_new:
        combined = pd.concat(all_new, ignore_index=True)
        conn.execute("INSERT INTO ohlcv SELECT * FROM combined")

    conn.close()
    return {"new_rows": sum(len(x) for x in all_new), "skipped": skipped, "files_checked": len(files)}


def cmd_add(symbol: str, start: str, end: str) -> dict:
    """從網路下載新股票，寫入 DB"""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed. Run: pip install yfinance"}

    yf_sym = _normalize_yf_symbol(symbol)

    print(f"[add] Downloading {yf_sym} ({start} ~ {end})...")
    try:
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(start=start, end=_inclusive_history_end(end), interval="1d")
    except Exception as e:
        return {"error": f"yfinance failed: {e}"}

    if df.empty:
        return {"error": "No data returned from yfinance"}

    df = df.reset_index()
    if "Datetime" in str(df["Date"].dtype):
        df["Date"] = df["Date"].dt.tz_localize(None)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"date": "dt"})
    df["ticker"] = symbol.upper()
    df["dt"] = pd.to_datetime(df["dt"]).dt.date
    df["dividends"] = 0.0
    df["stock_splits"] = 0.0
    df["source_file"] = f"yfinance_{datetime.now().strftime('%Y%m%d')}"
    insert_cols = [
        "ticker",
        "dt",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "dividends",
        "stock_splits",
        "source_file",
    ]
    df = df[[col for col in insert_cols if col in df.columns]].copy()

    conn = _conn()
    conn.execute(CREATE_TABLE_SQL)
    _ensure_schema_compat(conn)
    _ensure_indexes(conn)
    new_rows = df[~df.set_index(["ticker", "dt"]).index.isin(
        conn.execute("SELECT ticker, dt FROM ohlcv").fetchdf().set_index(["ticker", "dt"]).index
    )]
    conn.execute(
        "INSERT INTO ohlcv (ticker, dt, open, high, low, close, volume, dividends, stock_splits, source_file) "
        "SELECT ticker, dt, open, high, low, close, volume, dividends, stock_splits, source_file FROM new_rows"
    )
    count = len(new_rows)
    conn.close()

    return {"ticker": symbol.upper(), "rows_written": count, "total_in_db": len(df)}


def cmd_add_institutional(symbols: str, start: str, end: str) -> dict:
    """Fetch TWSE/TPEX institutional net-buy data for a ticker list and write to DB."""
    requested = [part.strip() for part in str(symbols).split(",") if part.strip()]
    if not requested:
        return {"error": "No symbols provided"}

    target_tickers = {_normalize_twse_institutional_ticker(symbol) for symbol in requested}
    twse_targets = {ticker for ticker in target_tickers if ticker.endswith(".TW")}
    tpex_targets = {ticker for ticker in target_tickers if ticker.endswith(".TWO")}
    frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []
    business_days = list(pd.date_range(start, end, freq="B"))
    checked_days = len(business_days)
    days_with_data = 0

    def _fetch_one(ts: pd.Timestamp) -> tuple[str, pd.DataFrame, list[dict[str, str]]]:
        day_frames: list[pd.DataFrame] = []
        day_errors: list[dict[str, str]] = []
        if twse_targets:
            try:
                daily_twse = fetch_twse_institutional_day(ts)
                if daily_twse is not None and not daily_twse.empty:
                    day_frames.append(daily_twse)
            except Exception as exc:
                day_errors.append({"market": "TWSE", "error": str(exc)})
        if tpex_targets:
            try:
                daily_tpex = fetch_tpex_institutional_day(ts)
                if daily_tpex is not None and not daily_tpex.empty:
                    day_frames.append(daily_tpex)
            except Exception as exc:
                day_errors.append({"market": "TPEX", "error": str(exc)})
        if day_frames:
            combined = pd.concat(day_frames, ignore_index=True).drop_duplicates(subset=["ticker", "dt"], keep="last")
            return ts.strftime("%Y-%m-%d"), combined, day_errors
        return ts.strftime("%Y-%m-%d"), pd.DataFrame(), day_errors

    max_workers = min(8, max(1, checked_days))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_one, ts): ts for ts in business_days}
        for idx, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            trade_date, daily, day_errors = future.result()
            for entry in day_errors:
                errors.append({"date": trade_date, **entry})
            if daily is None or daily.empty:
                continue
            days_with_data += 1
            matched = daily[daily["ticker"].isin(target_tickers)].copy()
            if not matched.empty:
                frames.append(matched)
            if idx % 250 == 0 or idx == checked_days:
                print(
                    f"  progress {idx}/{checked_days} days, matched_rows={sum(len(frame) for frame in frames)}, "
                    f"errors={len(errors)}"
                )

    if not frames:
        return {
            "tickers": sorted(target_tickers),
            "rows_written": 0,
            "checked_days": checked_days,
            "days_with_data": days_with_data,
            "errors": errors[:20],
        }

    combined = pd.concat(frames, ignore_index=True)
    rows_written = upsert_institutional_data(combined)
    return {
        "tickers": sorted(target_tickers),
        "rows_written": rows_written,
        "checked_days": checked_days,
        "days_with_data": days_with_data,
        "errors": errors[:20],
    }


def cmd_add_margin(symbols: str, start: str, end: str) -> dict:
    """Fetch TWSE/TPEX margin-trading data for a ticker list and write to DB."""
    requested = [part.strip() for part in str(symbols).split(",") if part.strip()]
    if not requested:
        return {"error": "No symbols provided"}

    target_tickers = {_normalize_twse_margin_ticker(symbol) for symbol in requested}
    twse_targets = {ticker for ticker in target_tickers if ticker.endswith(".TW")}
    tpex_targets = {ticker for ticker in target_tickers if ticker.endswith(".TWO")}
    frames: list[pd.DataFrame] = []
    market_frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []
    business_days = list(pd.date_range(start, end, freq="B"))
    checked_days = len(business_days)
    days_with_data = 0

    def _fetch_one(ts: pd.Timestamp) -> tuple[str, pd.DataFrame, pd.DataFrame, list[dict[str, str]]]:
        day_frames: list[pd.DataFrame] = []
        day_errors: list[dict[str, str]] = []
        market_daily = pd.DataFrame()
        if twse_targets:
            try:
                daily_twse = fetch_twse_margin_day(ts)
                if daily_twse is not None and not daily_twse.empty:
                    day_frames.append(daily_twse)
                    market_daily = aggregate_market_margin_day(daily_twse)
            except Exception as exc:
                day_errors.append({"market": "TWSE", "error": str(exc)})
        if tpex_targets:
            try:
                daily_tpex = fetch_tpex_margin_day(ts)
                if daily_tpex is not None and not daily_tpex.empty:
                    day_frames.append(daily_tpex)
            except Exception as exc:
                day_errors.append({"market": "TPEX", "error": str(exc)})
        if day_frames:
            combined = pd.concat(day_frames, ignore_index=True).drop_duplicates(subset=["ticker", "dt"], keep="last")
            return ts.strftime("%Y-%m-%d"), combined, market_daily, day_errors
        return ts.strftime("%Y-%m-%d"), pd.DataFrame(), market_daily, day_errors

    max_workers = min(8, max(1, checked_days))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_one, ts): ts for ts in business_days}
        for idx, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            trade_date, daily, market_daily, day_errors = future.result()
            for entry in day_errors:
                errors.append({"date": trade_date, **entry})
            if daily is None or daily.empty:
                continue
            days_with_data += 1
            if not market_daily.empty:
                market_frames.append(market_daily)
            matched = daily[daily["ticker"].isin(target_tickers)].copy()
            if not matched.empty:
                frames.append(matched)
            if idx % 250 == 0 or idx == checked_days:
                print(
                    f"  progress {idx}/{checked_days} days, matched_rows={sum(len(frame) for frame in frames)}, "
                    f"errors={len(errors)}"
                )

    if not frames:
        return {
            "tickers": sorted(target_tickers),
            "rows_written": 0,
            "checked_days": checked_days,
            "days_with_data": days_with_data,
            "errors": errors[:20],
        }

    combined = pd.concat(frames, ignore_index=True)
    rows_written = upsert_margin_data(combined)
    market_rows_written = 0
    if market_frames:
        market_combined = pd.concat(market_frames, ignore_index=True)
        market_rows_written = upsert_market_margin_data(market_combined)
    return {
        "tickers": sorted(target_tickers),
        "rows_written": rows_written,
        "market_rows_written": market_rows_written,
        "checked_days": checked_days,
        "days_with_data": days_with_data,
        "errors": errors[:20],
    }


def cmd_add_market_margin(start: str, end: str) -> dict:
    """Fetch full-market TWSE margin-trading aggregates and write to DB."""
    frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []
    business_days = list(pd.date_range(start, end, freq="B"))
    checked_days = len(business_days)
    days_with_data = 0

    def _fetch_one(ts: pd.Timestamp) -> tuple[str, pd.DataFrame | None, str | None]:
        try:
            daily = fetch_twse_margin_day(ts)
            return ts.strftime("%Y-%m-%d"), daily, None
        except Exception as exc:
            return ts.strftime("%Y-%m-%d"), None, str(exc)

    max_workers = min(8, max(1, checked_days))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_one, ts): ts for ts in business_days}
        for idx, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            trade_date, daily, error = future.result()
            if error is not None:
                errors.append({"date": trade_date, "error": error})
                continue
            if daily is None or daily.empty:
                continue
            market_daily = aggregate_market_margin_day(daily)
            if market_daily.empty:
                continue
            days_with_data += 1
            frames.append(market_daily)
            if idx % 250 == 0 or idx == checked_days:
                print(
                    f"  progress {idx}/{checked_days} days, market_rows={sum(len(frame) for frame in frames)}, "
                    f"errors={len(errors)}"
                )

    if not frames:
        return {
            "rows_written": 0,
            "checked_days": checked_days,
            "days_with_data": days_with_data,
            "errors": errors[:20],
        }

    combined = pd.concat(frames, ignore_index=True)
    rows_written = upsert_market_margin_data(combined)
    return {
        "rows_written": rows_written,
        "checked_days": checked_days,
        "days_with_data": days_with_data,
        "errors": errors[:20],
    }


def cmd_validate(show_gaps: bool = True) -> dict:
    """驗證資料完整性：缺交易日、價格異常（0 或負）、vol=0"""
    conn = _conn()
    tickers = [r[0] for r in conn.execute("SELECT DISTINCT ticker FROM ohlcv ORDER BY ticker").fetchall()]
    issues = []
    gap_reports = []

    for tic in tickers:
        # 使用參數化查詢防止 SQL injection（ticker 來自 DB 內部，但仍需參數化最佳化）
        df = conn.execute(
            "SELECT dt, open, high, low, close, volume FROM ohlcv WHERE ticker = ? ORDER BY dt",
            (tic,)
        ).fetchdf()
        if df.empty:
            continue

        # 價格異常
        bad_price = df[(df["close"] <= 0) | (df["high"] < df["low"]) | (df["open"] <= 0)]
        if not bad_price.empty:
            issues.append({"ticker": tic, "type": "bad_price", "rows": len(bad_price)})

        # vol = 0 警告（非假日的 vol=0 可能代表問題）
        zero_vol = df[df["volume"] == 0]
        if not zero_vol.empty and len(zero_vol) > 5:
            issues.append({"ticker": tic, "type": "zero_volume", "count": len(zero_vol)})

        # 缺交易日（每次最多報告 5 個 gap）
        df["dt"] = pd.to_datetime(df["dt"])
        df = df.sort_values("dt").reset_index(drop=True)
        date_idx = pd.DatetimeIndex(df["dt"])
        expected = pd.date_range(date_idx.min(), date_idx.max(), freq="B")  # 平日
        missing = expected.difference(date_idx)

        # 只看最大 gap（排除週末）
        if len(missing) > 0:
            # 合併連續 missing 為 gap
            missing = missing.sort_values()
            gap_groups = []
            start = missing[0]
            prev = missing[0]
            for d in missing[1:]:
                if (d - prev).days > 3:  # gap > 3 business days 才報告
                    gap_groups.append((start, prev))
                    start = d
                prev = d
            gap_groups.append((start, prev))

            for g_start, g_end in gap_groups[:5]:
                gap_reports.append({"ticker": tic, "gap_start": str(g_start.date()),
                                    "gap_end": str(g_end.date()), "missing_days": (g_end - g_start).days})

    conn.close()
    return {"issues": issues, "gaps": gap_reports, "tickers_checked": len(tickers)}


def cmd_dedup() -> dict:
    """移除重複：同 ticker+dt 只留最新的一筆（按 updated_at）"""
    conn = _conn()
    before = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchdf().iloc[0, 0]
    conn.execute("""
        DELETE FROM ohlcv WHERE rowid NOT IN (
            SELECT MAX(rowid) FROM ohlcv GROUP BY ticker, dt
        )
    """)
    after = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchdf().iloc[0, 0]
    conn.close()
    return {"removed": before - after, "remaining": after}


def cmd_stats() -> pd.DataFrame:
    """顯示 DB 狀態"""
    conn = _read_conn()
    df = conn.execute("""
        SELECT
            ticker,
            COUNT(*)                                    as rows,
            MIN(dt)::VARCHAR                            as start_date,
            MAX(dt)::VARCHAR                            as end_date,
            ROUND(AVG(close), 2)                       as avg_close,
            MAX(volume)                                 as max_volume,
            COUNT(CASE WHEN volume = 0 THEN 1 END)      as zero_vol_days
        FROM ohlcv
        GROUP BY ticker
        ORDER BY ticker
    """).fetchdf()
    total = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchdf().iloc[0, 0]
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    institutional_total = 0
    margin_total = 0
    market_margin_total = 0
    shareholding_total = 0
    if "institutional_data" in tables:
        institutional_total = conn.execute("SELECT COUNT(*) FROM institutional_data").fetchdf().iloc[0, 0]
    if "margin_data" in tables:
        margin_total = conn.execute("SELECT COUNT(*) FROM margin_data").fetchdf().iloc[0, 0]
    if "market_margin_data" in tables:
        market_margin_total = conn.execute("SELECT COUNT(*) FROM market_margin_data").fetchdf().iloc[0, 0]
    if "shareholding_distribution" in tables:
        shareholding_total = conn.execute("SELECT COUNT(*) FROM shareholding_distribution").fetchdf().iloc[0, 0]
    conn.close()
    return df, total, institutional_total, margin_total, market_margin_total, shareholding_total


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Stock DB Maintenance")
    parser.add_argument("--build",  action="store_true", help="Full rebuild from cache")
    parser.add_argument("--rebuild", action="store_true", help="Quick rebuild (remove noise tickers)")
    parser.add_argument("--update", action="store_true", help="Incremental update from cache")
    parser.add_argument("--add", metavar="SYMBOL", help="Add new ticker from network")
    parser.add_argument(
        "--add-institutional",
        metavar="SYMBOLS",
        help="Fetch TWSE institutional net-buy data for comma-separated tickers, e.g. 0050.TW,00631L.TW",
    )
    parser.add_argument(
        "--add-margin",
        metavar="SYMBOLS",
        help="Fetch TWSE margin-trading data for comma-separated tickers, e.g. 0050.TW,00631L.TW",
    )
    parser.add_argument(
        "--add-market-margin",
        action="store_true",
        help="Fetch full-market TWSE margin-trading aggregates into market_margin_data",
    )
    parser.add_argument(
        "--add-shareholding",
        action="store_true",
        help="Fetch latest full-market TDCC shareholding distribution snapshot",
    )
    parser.add_argument(
        "--shareholding-file",
        metavar="PATH",
        help="Import a downloaded TDCC JSON or FinMind TaiwanStockHoldingSharesPer CSV file",
    )
    parser.add_argument("--start", default="2020-01-01", help="Start date for --add")
    parser.add_argument("--end",   default=str(date.today()), help="End date for --add")
    parser.add_argument("--query", metavar="TICKER", help="Query ticker data")
    parser.add_argument("--query-institutional", metavar="TICKER", help="Query institutional flow data")
    parser.add_argument("--query-margin", metavar="TICKER", help="Query margin-trading data")
    parser.add_argument("--query-market-margin", action="store_true", help="Query market-level margin-trading data")
    parser.add_argument("--query-shareholding", metavar="STOCK_ID", help="Query TDCC/FinMind shareholding tiers")
    parser.add_argument("--query-shareholding-features", metavar="STOCK_ID", help="Query derived weekly holder features")
    parser.add_argument("--start-date", dest="start_dt", help="Start date for --query")
    parser.add_argument("--end-date",   dest="end_dt",   help="End date for --query")
    parser.add_argument("--validate",   action="store_true", help="Validate data quality")
    parser.add_argument("--stats",      action="store_true", help="Show DB statistics")
    parser.add_argument("--dedup",      action="store_true", help="Remove duplicate rows")
    args = parser.parse_args()

    if not any([args.build, args.rebuild, args.update, args.add, args.add_institutional, args.add_margin, args.add_market_margin,
                args.add_shareholding, args.shareholding_file, args.query,
                args.query_institutional, args.query_margin, args.query_market_margin, args.query_shareholding,
                args.query_shareholding_features,
                args.validate, args.stats, args.dedup]):
        parser.print_help()
        return

    print(f"[stock_db] DB={DB_PATH}")

    if args.build:
        print("[build] Full rebuild...")
        stats = cmd_build()
        print(f"  Done: {stats['ingested']:,} rows from {stats['files']} files")
        for f, e in stats.get("errors", []):
            print(f"  ERROR {f}: {e}")

    elif args.rebuild:
        print("[rebuild] Quick rebuild...")
        stats = cmd_rebuild()
        print(f"  Retained: {stats['retained']:,} rows")

    elif args.update:
        print("[update] Incremental update...")
        stats = cmd_update()
        print(f"  new_rows={stats['new_rows']}, skipped={stats['skipped']}, files={stats['files_checked']}")

    elif args.add:
        stats = cmd_add(args.add, args.start_dt or args.start, args.end_dt or args.end)
        if "error" in stats:
            print(f"  ERROR: {stats['error']}")
        else:
            print(f"  Added {stats['ticker']}: {stats['rows_written']} new rows")

    elif args.add_institutional:
        print(f"[add-institutional] Fetching {args.add_institutional} ({args.start_dt or args.start} ~ {args.end_dt or args.end})...")
        stats = cmd_add_institutional(args.add_institutional, args.start_dt or args.start, args.end_dt or args.end)
        if "error" in stats:
            print(f"  ERROR: {stats['error']}")
        else:
            print(
                f"  Institutional rows_written={stats['rows_written']}, "
                f"checked_days={stats['checked_days']}, days_with_data={stats['days_with_data']}"
            )
            for item in stats.get("errors", [])[:10]:
                print(f"  WARN {item['date']}: {item['error']}")

    elif args.add_margin:
        print(f"[add-margin] Fetching {args.add_margin} ({args.start_dt or args.start} ~ {args.end_dt or args.end})...")
        stats = cmd_add_margin(args.add_margin, args.start_dt or args.start, args.end_dt or args.end)
        if "error" in stats:
            print(f"  ERROR: {stats['error']}")
        else:
            print(
                f"  Margin rows_written={stats['rows_written']}, "
                f"market_rows_written={stats.get('market_rows_written', 0)}, "
                f"checked_days={stats['checked_days']}, days_with_data={stats['days_with_data']}"
            )
            for item in stats.get("errors", [])[:10]:
                print(f"  WARN {item['date']}: {item['error']}")

    elif args.add_market_margin:
        print(f"[add-market-margin] Fetching TWSE market margin ({args.start_dt or args.start} ~ {args.end_dt or args.end})...")
        stats = cmd_add_market_margin(args.start_dt or args.start, args.end_dt or args.end)
        if "error" in stats:
            print(f"  ERROR: {stats['error']}")
        else:
            print(
                f"  Market margin rows_written={stats['rows_written']}, "
                f"checked_days={stats['checked_days']}, days_with_data={stats['days_with_data']}"
            )
            for item in stats.get("errors", [])[:10]:
                print(f"  WARN {item['date']}: {item['error']}")

    elif args.add_shareholding or args.shareholding_file:
        print("[add-shareholding] Importing TDCC full-market snapshot...")
        stats = cmd_add_shareholding_distribution(args.shareholding_file)
        if "error" in stats:
            print(f"  ERROR: {stats['error']}")
        else:
            print(
                f"  Shareholding rows_written={stats['rows_written']}, "
                f"stock_count={stats['stock_count']}, "
                f"date={stats['start_date']} ~ {stats['end_date']}"
            )

    elif args.query:
        tic = args.query.upper()
        conn = _conn()
        # 參數化查詢，防止 SQL injection（攻擊者可能輸入 ' OR 1=1 -- 等）
        sql = "SELECT ticker, dt, open, high, low, close, volume FROM ohlcv WHERE ticker = ?"
        params = [tic]
        if args.start_dt:
            sql += " AND dt >= ?"
            params.append(args.start_dt)
        if args.end_dt:
            sql += " AND dt <= ?"
            params.append(args.end_dt)
        sql += " ORDER BY dt LIMIT 200"
        df = conn.execute(sql, params).fetchdf()
        conn.close()
        if df.empty:
            print("No data.")
        else:
            print(f"{tic}: {len(df)} rows")
            df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
            print(df.to_string(index=False))

    elif args.query_institutional:
        tic = _normalize_twse_institutional_ticker(args.query_institutional)
        df = query_institutional_data(tic, args.start_dt, args.end_dt)
        if df.empty:
            print("No institutional data.")
        else:
            df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
            print(f"{tic}: {len(df)} rows")
            print(df.to_string(index=False))

    elif args.query_margin:
        tic = _normalize_twse_margin_ticker(args.query_margin)
        df = query_margin_data(tic, args.start_dt, args.end_dt)
        if df.empty:
            print("No margin data.")
        else:
            df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
            print(f"{tic}: {len(df)} rows")
            print(df.to_string(index=False))

    elif args.query_market_margin:
        df = query_market_margin_data(args.start_dt, args.end_dt)
        if df.empty:
            print("No market margin data.")
        else:
            df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
            print(f"market_margin_data: {len(df)} rows")
            print(df.to_string(index=False))

    elif args.query_shareholding:
        stock_id = _normalize_shareholding_stock_id(args.query_shareholding)
        df = query_shareholding_distribution(stock_id, args.start_dt, args.end_dt)
        if df.empty:
            print("No shareholding distribution data.")
        else:
            df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
            print(f"{stock_id}: {len(df)} rows")
            print(df.to_string(index=False))

    elif args.query_shareholding_features:
        stock_id = _normalize_shareholding_stock_id(args.query_shareholding_features)
        df = query_shareholding_features(stock_id, args.start_dt, args.end_dt)
        if df.empty:
            print("No shareholding feature data.")
        else:
            df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
            print(f"{stock_id}: {len(df)} weekly feature rows")
            print(df.to_string(index=False))

    elif args.validate:
        print("[validate] Checking data quality...")
        result = cmd_validate()
        issues = result["issues"]
        gaps = result["gaps"]
        print(f"  Tickers checked: {result['tickers_checked']}")
        if issues:
            print(f"  Issues found: {len(issues)}")
            for it in issues[:10]:
                print(f"    [{it['ticker']}] {it['type']}: {list(it.values())}")
        else:
            print("  No issues found.")
        if gaps:
            print(f"  Gaps found: {len(gaps)}")
            for g in gaps[:10]:
                print(f"    [{g['ticker']}] {g['gap_start']}~{g['gap_end']} ({g['missing_days']} days)")
        else:
            print("  No gaps found.")

    elif args.stats:
        df, total, institutional_total, margin_total, market_margin_total, shareholding_total = cmd_stats()
        print(f"\nTotal rows in DB: {total:,}")
        print(f"Institutional rows in DB: {institutional_total:,}")
        print(f"Margin rows in DB: {margin_total:,}")
        print(f"Market margin rows in DB: {market_margin_total:,}")
        print(f"Shareholding distribution rows in DB: {shareholding_total:,}")
        print(f"Tickers: {len(df)}")
        print()
        print(df.to_string(index=False))

    elif args.dedup:
        stats = cmd_dedup()
        print(f"Removed: {stats['removed']}, remaining: {stats['remaining']}")


if __name__ == "__main__":
    main()
