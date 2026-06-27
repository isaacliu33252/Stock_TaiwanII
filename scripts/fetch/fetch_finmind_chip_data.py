#!/usr/bin/env python3
"""Fetch FinMind chip datasets into the local DuckDB tables."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import (  # noqa: E402
    parse_shareholding_distribution_rows,
    upsert_institutional_data,
    upsert_margin_data,
    upsert_shareholding_distribution,
)


API_URL = "https://api.finmindtrade.com/api/v4/data"
DEFAULT_TICKERS = "0050,00631L,00632R,00679B"
DEFAULT_OTC_CODES = {"00679B", "00751B"}
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"


CREATE_FOREIGN_SHAREHOLDING_SQL = """
CREATE TABLE IF NOT EXISTS foreign_shareholding_data (
    ticker                                  TEXT    NOT NULL,
    dt                                      DATE    NOT NULL,
    foreign_investment_remaining_shares    DOUBLE  NOT NULL DEFAULT 0.0,
    foreign_investment_shares              DOUBLE  NOT NULL DEFAULT 0.0,
    foreign_investment_remain_ratio        DOUBLE  NOT NULL DEFAULT 0.0,
    foreign_investment_shares_ratio        DOUBLE  NOT NULL DEFAULT 0.0,
    foreign_investment_upper_limit_ratio   DOUBLE  NOT NULL DEFAULT 0.0,
    chinese_investment_upper_limit_ratio   DOUBLE  NOT NULL DEFAULT 0.0,
    number_of_shares_issued                DOUBLE  NOT NULL DEFAULT 0.0,
    recently_declare_date                  TEXT    NOT NULL DEFAULT '',
    source                                  TEXT    NOT NULL DEFAULT 'finmind_v4_shareholding',
    updated_at                              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_DERIVATIVE_INSTITUTIONAL_SQL = """
CREATE TABLE IF NOT EXISTS derivative_institutional_data (
    market                                  TEXT    NOT NULL,
    product_id                              TEXT    NOT NULL,
    dt                                      DATE    NOT NULL,
    name                                    TEXT    NOT NULL DEFAULT '',
    put_call                                TEXT    NOT NULL DEFAULT '',
    institutional_investors                 TEXT    NOT NULL DEFAULT '',
    long_deal_volume                        DOUBLE  NOT NULL DEFAULT 0.0,
    long_deal_amount                        DOUBLE  NOT NULL DEFAULT 0.0,
    short_deal_volume                       DOUBLE  NOT NULL DEFAULT 0.0,
    short_deal_amount                       DOUBLE  NOT NULL DEFAULT 0.0,
    long_open_interest_balance_volume       DOUBLE  NOT NULL DEFAULT 0.0,
    long_open_interest_balance_amount       DOUBLE  NOT NULL DEFAULT 0.0,
    short_open_interest_balance_volume      DOUBLE  NOT NULL DEFAULT 0.0,
    short_open_interest_balance_amount      DOUBLE  NOT NULL DEFAULT 0.0,
    net_open_interest_balance_volume        DOUBLE  NOT NULL DEFAULT 0.0,
    source                                  TEXT    NOT NULL DEFAULT 'finmind_v4_derivative_institutional',
    updated_at                              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market, product_id, dt, name, put_call, institutional_investors)
);
"""

CREATE_DERIVATIVE_LARGE_TRADER_SQL = """
CREATE TABLE IF NOT EXISTS derivative_large_trader_data (
    market                                      TEXT    NOT NULL,
    product_id                                  TEXT    NOT NULL,
    dt                                          DATE    NOT NULL,
    name                                        TEXT    NOT NULL DEFAULT '',
    contract_type                               TEXT    NOT NULL DEFAULT '',
    put_call                                    TEXT    NOT NULL DEFAULT '',
    buy_top5_trader_open_interest               DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top5_trader_open_interest_per           DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top10_trader_open_interest              DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top10_trader_open_interest_per          DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top5_trader_open_interest              DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top5_trader_open_interest_per          DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top10_trader_open_interest             DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top10_trader_open_interest_per         DOUBLE  NOT NULL DEFAULT 0.0,
    market_open_interest                        DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top5_specific_open_interest             DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top5_specific_open_interest_per         DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top10_specific_open_interest            DOUBLE  NOT NULL DEFAULT 0.0,
    buy_top10_specific_open_interest_per        DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top5_specific_open_interest            DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top5_specific_open_interest_per        DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top10_specific_open_interest           DOUBLE  NOT NULL DEFAULT 0.0,
    sell_top10_specific_open_interest_per       DOUBLE  NOT NULL DEFAULT 0.0,
    net_top5_specific_open_interest             DOUBLE  NOT NULL DEFAULT 0.0,
    net_top10_specific_open_interest            DOUBLE  NOT NULL DEFAULT 0.0,
    source                                      TEXT    NOT NULL DEFAULT 'finmind_v4_derivative_large_trader',
    updated_at                                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market, product_id, dt, name, contract_type, put_call)
);
"""

CREATE_STOCK_PER_SQL = """
CREATE TABLE IF NOT EXISTS stock_per_data (
    ticker              TEXT    NOT NULL,
    dt                  DATE    NOT NULL,
    dividend_yield      DOUBLE  NOT NULL DEFAULT 0.0,
    per                 DOUBLE  NOT NULL DEFAULT 0.0,
    pbr                 DOUBLE  NOT NULL DEFAULT 0.0,
    source              TEXT    NOT NULL DEFAULT 'finmind_v4_stock_per',
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_SECURITIES_LENDING_SQL = """
CREATE TABLE IF NOT EXISTS securities_lending_data (
    ticker                      TEXT    NOT NULL,
    dt                          DATE    NOT NULL,
    transaction_type            TEXT    NOT NULL DEFAULT '',
    original_return_date        TEXT    NOT NULL DEFAULT '',
    original_lending_period     DOUBLE  NOT NULL DEFAULT 0.0,
    fee_rate                    DOUBLE  NOT NULL DEFAULT 0.0,
    close                       DOUBLE  NOT NULL DEFAULT 0.0,
    volume                      DOUBLE  NOT NULL DEFAULT 0.0,
    source                      TEXT    NOT NULL DEFAULT 'finmind_v4_securities_lending',
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt, transaction_type, original_return_date, original_lending_period, fee_rate, close)
);
"""

CREATE_SHORT_SALE_BALANCE_SQL = """
CREATE TABLE IF NOT EXISTS short_sale_balance_data (
    ticker                                      TEXT    NOT NULL,
    dt                                          DATE    NOT NULL,
    margin_short_previous_balance               DOUBLE  NOT NULL DEFAULT 0.0,
    margin_short_sales                          DOUBLE  NOT NULL DEFAULT 0.0,
    margin_short_covering                       DOUBLE  NOT NULL DEFAULT 0.0,
    margin_short_stock_redemption               DOUBLE  NOT NULL DEFAULT 0.0,
    margin_short_current_balance                DOUBLE  NOT NULL DEFAULT 0.0,
    margin_short_quota                          DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_previous_balance                  DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_sales                             DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_returns                           DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_adjustments                       DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_current_balance                   DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_quota                             DOUBLE  NOT NULL DEFAULT 0.0,
    sbl_short_covering                          DOUBLE  NOT NULL DEFAULT 0.0,
    source                                      TEXT    NOT NULL DEFAULT 'finmind_v4_short_sale_balances',
    updated_at                                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_TOTAL_RETURN_INDEX_SQL = """
CREATE TABLE IF NOT EXISTS total_return_index_data (
    index_id            TEXT    NOT NULL,
    dt                  DATE    NOT NULL,
    price               DOUBLE  NOT NULL DEFAULT 0.0,
    source              TEXT    NOT NULL DEFAULT 'finmind_v4_total_return_index',
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (index_id, dt)
);
"""

CREATE_MARGIN_MAINTENANCE_SQL = """
CREATE TABLE IF NOT EXISTS margin_maintenance_data (
    dt                                      DATE    NOT NULL,
    total_exchange_margin_maintenance      DOUBLE  NOT NULL DEFAULT 0.0,
    source                                  TEXT    NOT NULL DEFAULT 'finmind_v4_margin_maintenance',
    updated_at                              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt)
);
"""

CREATE_GOVERNMENT_BANK_SQL = """
CREATE TABLE IF NOT EXISTS government_bank_data (
    ticker                      TEXT    NOT NULL,
    dt                          DATE    NOT NULL,
    name                        TEXT    NOT NULL DEFAULT '',
    buy                         DOUBLE  NOT NULL DEFAULT 0.0,
    sell                        DOUBLE  NOT NULL DEFAULT 0.0,
    net                         DOUBLE  NOT NULL DEFAULT 0.0,
    volume                      DOUBLE  NOT NULL DEFAULT 0.0,
    turnover                    DOUBLE  NOT NULL DEFAULT 0.0,
    source                      TEXT    NOT NULL DEFAULT 'finmind_v4_government_bank',
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt, name)
);
"""

CREATE_DAY_TRADING_SQL = """
CREATE TABLE IF NOT EXISTS day_trading_data (
    ticker                      TEXT    NOT NULL,
    dt                          DATE    NOT NULL,
    day_trade_buy               DOUBLE  NOT NULL DEFAULT 0.0,
    day_trade_sell              DOUBLE  NOT NULL DEFAULT 0.0,
    day_trade_volume            DOUBLE  NOT NULL DEFAULT 0.0,
    day_trade_tx                DOUBLE  NOT NULL DEFAULT 0.0,
    source                      TEXT    NOT NULL DEFAULT 'finmind_v4_day_trading',
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, dt)
);
"""

CREATE_DEALER_FUTURES_SQL = """
CREATE TABLE IF NOT EXISTS dealer_futures_data (
    dt                          DATE    NOT NULL,
    futures_id                  TEXT    NOT NULL,
    dealer_code                 TEXT    NOT NULL,
    dealer_name                 TEXT    NOT NULL,
    volume                      DOUBLE  NOT NULL DEFAULT 0.0,
    is_after_hour               INTEGER NOT NULL DEFAULT 0,
    source                      TEXT    NOT NULL DEFAULT 'finmind_v4_futures_dealer',
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt, futures_id, dealer_code, is_after_hour)
);
"""

CREATE_DEALER_OPTIONS_SQL = """
CREATE TABLE IF NOT EXISTS dealer_options_data (
    dt                          DATE    NOT NULL,
    option_id                   TEXT    NOT NULL,
    dealer_code                 TEXT    NOT NULL,
    dealer_name                 TEXT    NOT NULL,
    volume                      DOUBLE  NOT NULL DEFAULT 0.0,
    is_after_hour               INTEGER NOT NULL DEFAULT 0,
    source                      TEXT    NOT NULL DEFAULT 'finmind_v4_options_dealer',
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dt, option_id, dealer_code, is_after_hour)
);
"""

CREATE_DERIVATIVE_AFTERHOURS_SQL = """
CREATE TABLE IF NOT EXISTS derivative_afterhours_data (
    market                      TEXT    NOT NULL,
    product_id                  TEXT    NOT NULL,
    dt                          DATE    NOT NULL,
    name                        TEXT    NOT NULL DEFAULT '',
    put_call                    TEXT    NOT NULL DEFAULT '',
    institutional_investors     TEXT    NOT NULL DEFAULT '',
    long_deal_volume            DOUBLE  NOT NULL DEFAULT 0.0,
    short_deal_volume           DOUBLE  NOT NULL DEFAULT 0.0,
    net_deal_volume             DOUBLE  NOT NULL DEFAULT 0.0,
    long_open_interest_balance  DOUBLE  NOT NULL DEFAULT 0.0,
    short_open_interest_balance DOUBLE  NOT NULL DEFAULT 0.0,
    net_open_interest_balance   DOUBLE  NOT NULL DEFAULT 0.0,
    source                      TEXT    NOT NULL DEFAULT 'finmind_v4_derivative_afterhours',
    updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market, product_id, dt, name, put_call, institutional_investors)
);
"""


def _stock_id(value: str) -> str:
    value = value.upper().strip()
    if value.endswith(".TWO"):
        return value[:-4]
    if value.endswith(".TW"):
        return value[:-3]
    return value


def _local_ticker(value: str) -> str:
    code = _stock_id(value)
    if code in DEFAULT_OTC_CODES:
        return f"{code}.TWO"
    return f"{code}.TW"


def _get(dataset: str, stock_id: str, start: str, end: str, token: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get(
        API_URL,
        headers=headers,
        params={
            "dataset": dataset,
            "data_id": stock_id,
            "start_date": start,
            "end_date": end,
        },
        timeout=60,
    )
    payload = response.json()
    if response.status_code != 200:
        raise RuntimeError(f"FinMind {dataset} {stock_id}: HTTP {response.status_code}: {payload}")
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise RuntimeError(f"FinMind {dataset} {stock_id}: unexpected response: {payload}")
    return rows


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)


def _text(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype=str)
    return frame[column].fillna("").astype(str)


def upsert_foreign_shareholding(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    columns = [
        "foreign_investment_remaining_shares",
        "foreign_investment_shares",
        "foreign_investment_remain_ratio",
        "foreign_investment_shares_ratio",
        "foreign_investment_upper_limit_ratio",
        "chinese_investment_upper_limit_ratio",
        "number_of_shares_issued",
    ]
    for column in columns:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["recently_declare_date"] = frame.get("recently_declare_date", "").fillna("").astype(str)
    frame["source"] = frame.get("source", "finmind_v4_shareholding")
    frame = frame[
        [
            "ticker",
            "dt",
            "foreign_investment_remaining_shares",
            "foreign_investment_shares",
            "foreign_investment_remain_ratio",
            "foreign_investment_shares_ratio",
            "foreign_investment_upper_limit_ratio",
            "chinese_investment_upper_limit_ratio",
            "number_of_shares_issued",
            "recently_declare_date",
            "source",
        ]
    ].drop_duplicates(subset=["ticker", "dt"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_FOREIGN_SHAREHOLDING_SQL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_foreign_shareholding_ticker_dt ON foreign_shareholding_data(ticker, dt)")
        con.register("incoming_foreign_shareholding", frame)
        con.execute(
            """
            DELETE FROM foreign_shareholding_data
            USING incoming_foreign_shareholding
            WHERE foreign_shareholding_data.ticker = incoming_foreign_shareholding.ticker
              AND foreign_shareholding_data.dt = incoming_foreign_shareholding.dt
            """
        )
        con.execute(
            """
            INSERT INTO foreign_shareholding_data (
                ticker,
                dt,
                foreign_investment_remaining_shares,
                foreign_investment_shares,
                foreign_investment_remain_ratio,
                foreign_investment_shares_ratio,
                foreign_investment_upper_limit_ratio,
                chinese_investment_upper_limit_ratio,
                number_of_shares_issued,
                recently_declare_date,
                source
            )
            SELECT
                ticker,
                dt,
                foreign_investment_remaining_shares,
                foreign_investment_shares,
                foreign_investment_remain_ratio,
                foreign_investment_shares_ratio,
                foreign_investment_upper_limit_ratio,
                chinese_investment_upper_limit_ratio,
                number_of_shares_issued,
                recently_declare_date,
                source
            FROM incoming_foreign_shareholding
            """
        )
        return int(len(frame))
    finally:
        con.close()


def upsert_derivative_institutional(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    text_columns = ["market", "product_id", "name", "put_call", "institutional_investors", "source"]
    for column in text_columns:
        frame[column] = frame.get(column, "").fillna("").astype(str)
    numeric_columns = [
        "long_deal_volume",
        "long_deal_amount",
        "short_deal_volume",
        "short_deal_amount",
        "long_open_interest_balance_volume",
        "long_open_interest_balance_amount",
        "short_open_interest_balance_volume",
        "short_open_interest_balance_amount",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["net_open_interest_balance_volume"] = (
        frame["long_open_interest_balance_volume"] - frame["short_open_interest_balance_volume"]
    )
    frame = frame[
        [
            "market",
            "product_id",
            "dt",
            "name",
            "put_call",
            "institutional_investors",
            "long_deal_volume",
            "long_deal_amount",
            "short_deal_volume",
            "short_deal_amount",
            "long_open_interest_balance_volume",
            "long_open_interest_balance_amount",
            "short_open_interest_balance_volume",
            "short_open_interest_balance_amount",
            "net_open_interest_balance_volume",
            "source",
        ]
    ].drop_duplicates(subset=["market", "product_id", "dt", "name", "put_call", "institutional_investors"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        existing_columns = {
            row[1]
            for row in con.execute("PRAGMA table_info('derivative_institutional_data')").fetchall()
        } if con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'derivative_institutional_data'"
        ).fetchone()[0] else set()
        if existing_columns and "put_call" not in existing_columns:
            con.execute("DROP TABLE derivative_institutional_data")
        con.execute(CREATE_DERIVATIVE_INSTITUTIONAL_SQL)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_derivative_institutional_product_dt "
            "ON derivative_institutional_data(market, product_id, dt)"
        )
        con.register("incoming_derivative_institutional", frame)
        con.execute(
            """
            DELETE FROM derivative_institutional_data
            USING incoming_derivative_institutional
            WHERE derivative_institutional_data.market = incoming_derivative_institutional.market
              AND derivative_institutional_data.product_id = incoming_derivative_institutional.product_id
              AND derivative_institutional_data.dt = incoming_derivative_institutional.dt
              AND derivative_institutional_data.name = incoming_derivative_institutional.name
              AND derivative_institutional_data.put_call = incoming_derivative_institutional.put_call
              AND derivative_institutional_data.institutional_investors = incoming_derivative_institutional.institutional_investors
            """
        )
        con.execute(
            """
            INSERT INTO derivative_institutional_data
            SELECT *, CURRENT_TIMESTAMP
            FROM incoming_derivative_institutional
            """
        )
        return int(len(frame))
    finally:
        con.close()


def upsert_derivative_large_trader(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    text_columns = ["market", "product_id", "name", "contract_type", "put_call", "source"]
    for column in text_columns:
        frame[column] = frame.get(column, "").fillna("").astype(str)
    numeric_columns = [
        "buy_top5_trader_open_interest",
        "buy_top5_trader_open_interest_per",
        "buy_top10_trader_open_interest",
        "buy_top10_trader_open_interest_per",
        "sell_top5_trader_open_interest",
        "sell_top5_trader_open_interest_per",
        "sell_top10_trader_open_interest",
        "sell_top10_trader_open_interest_per",
        "market_open_interest",
        "buy_top5_specific_open_interest",
        "buy_top5_specific_open_interest_per",
        "buy_top10_specific_open_interest",
        "buy_top10_specific_open_interest_per",
        "sell_top5_specific_open_interest",
        "sell_top5_specific_open_interest_per",
        "sell_top10_specific_open_interest",
        "sell_top10_specific_open_interest_per",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["net_top5_specific_open_interest"] = (
        frame["buy_top5_specific_open_interest"] - frame["sell_top5_specific_open_interest"]
    )
    frame["net_top10_specific_open_interest"] = (
        frame["buy_top10_specific_open_interest"] - frame["sell_top10_specific_open_interest"]
    )
    frame = frame[
        [
            "market",
            "product_id",
            "dt",
            "name",
            "contract_type",
            "put_call",
            "buy_top5_trader_open_interest",
            "buy_top5_trader_open_interest_per",
            "buy_top10_trader_open_interest",
            "buy_top10_trader_open_interest_per",
            "sell_top5_trader_open_interest",
            "sell_top5_trader_open_interest_per",
            "sell_top10_trader_open_interest",
            "sell_top10_trader_open_interest_per",
            "market_open_interest",
            "buy_top5_specific_open_interest",
            "buy_top5_specific_open_interest_per",
            "buy_top10_specific_open_interest",
            "buy_top10_specific_open_interest_per",
            "sell_top5_specific_open_interest",
            "sell_top5_specific_open_interest_per",
            "sell_top10_specific_open_interest",
            "sell_top10_specific_open_interest_per",
            "net_top5_specific_open_interest",
            "net_top10_specific_open_interest",
            "source",
        ]
    ].drop_duplicates(subset=["market", "product_id", "dt", "name", "contract_type", "put_call"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_DERIVATIVE_LARGE_TRADER_SQL)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_derivative_large_trader_product_dt "
            "ON derivative_large_trader_data(market, product_id, dt)"
        )
        con.register("incoming_derivative_large_trader", frame)
        con.execute(
            """
            DELETE FROM derivative_large_trader_data
            USING incoming_derivative_large_trader
            WHERE derivative_large_trader_data.market = incoming_derivative_large_trader.market
              AND derivative_large_trader_data.product_id = incoming_derivative_large_trader.product_id
              AND derivative_large_trader_data.dt = incoming_derivative_large_trader.dt
              AND derivative_large_trader_data.name = incoming_derivative_large_trader.name
              AND derivative_large_trader_data.contract_type = incoming_derivative_large_trader.contract_type
              AND derivative_large_trader_data.put_call = incoming_derivative_large_trader.put_call
            """
        )
        con.execute(
            """
            INSERT INTO derivative_large_trader_data
            SELECT *, CURRENT_TIMESTAMP
            FROM incoming_derivative_large_trader
            """
        )
        return int(len(frame))
    finally:
        con.close()


def upsert_stock_per(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for column in ["dividend_yield", "per", "pbr"]:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["source"] = frame.get("source", "finmind_v4_stock_per")
    frame = frame[["ticker", "dt", "dividend_yield", "per", "pbr", "source"]].drop_duplicates(
        subset=["ticker", "dt"], keep="last"
    )
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_STOCK_PER_SQL)
        con.register("incoming_stock_per", frame)
        con.execute(
            """
            DELETE FROM stock_per_data
            USING incoming_stock_per
            WHERE stock_per_data.ticker = incoming_stock_per.ticker
              AND stock_per_data.dt = incoming_stock_per.dt
            """
        )
        con.execute("INSERT INTO stock_per_data SELECT *, CURRENT_TIMESTAMP FROM incoming_stock_per")
        return int(len(frame))
    finally:
        con.close()


def upsert_securities_lending(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for column in ["transaction_type", "original_return_date", "source"]:
        frame[column] = frame.get(column, "").fillna("").astype(str)
    for column in ["original_lending_period", "fee_rate", "close", "volume"]:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0).astype(float)
    key_columns = [
        "ticker",
        "dt",
        "transaction_type",
        "original_return_date",
        "original_lending_period",
        "fee_rate",
        "close",
    ]
    frame = (
        frame.groupby([*key_columns, "source"], as_index=False)["volume"]
        .sum()
        .sort_values(["ticker", "dt"])
    )
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_SECURITIES_LENDING_SQL)
        con.register("incoming_securities_lending", frame)
        con.execute(
            """
            DELETE FROM securities_lending_data
            USING incoming_securities_lending
            WHERE securities_lending_data.ticker = incoming_securities_lending.ticker
              AND securities_lending_data.dt = incoming_securities_lending.dt
              AND securities_lending_data.transaction_type = incoming_securities_lending.transaction_type
              AND securities_lending_data.original_return_date = incoming_securities_lending.original_return_date
              AND securities_lending_data.original_lending_period = incoming_securities_lending.original_lending_period
              AND securities_lending_data.fee_rate = incoming_securities_lending.fee_rate
              AND securities_lending_data.close = incoming_securities_lending.close
            """
        )
        con.execute(
            """
            INSERT INTO securities_lending_data (
                ticker, dt, transaction_type, original_return_date, original_lending_period,
                fee_rate, close, source, volume, updated_at
            )
            SELECT
                ticker, dt, transaction_type, original_return_date, original_lending_period,
                fee_rate, close, source, volume, CURRENT_TIMESTAMP
            FROM incoming_securities_lending
            """
        )
        return int(len(frame))
    finally:
        con.close()


def upsert_short_sale_balance(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    numeric_columns = [
        "margin_short_previous_balance",
        "margin_short_sales",
        "margin_short_covering",
        "margin_short_stock_redemption",
        "margin_short_current_balance",
        "margin_short_quota",
        "sbl_short_previous_balance",
        "sbl_short_sales",
        "sbl_short_returns",
        "sbl_short_adjustments",
        "sbl_short_current_balance",
        "sbl_short_quota",
        "sbl_short_covering",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["source"] = frame.get("source", "finmind_v4_short_sale_balances")
    frame = frame[["ticker", "dt", *numeric_columns, "source"]].drop_duplicates(subset=["ticker", "dt"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_SHORT_SALE_BALANCE_SQL)
        con.register("incoming_short_sale_balance", frame)
        con.execute(
            """
            DELETE FROM short_sale_balance_data
            USING incoming_short_sale_balance
            WHERE short_sale_balance_data.ticker = incoming_short_sale_balance.ticker
              AND short_sale_balance_data.dt = incoming_short_sale_balance.dt
            """
        )
        con.execute("INSERT INTO short_sale_balance_data SELECT *, CURRENT_TIMESTAMP FROM incoming_short_sale_balance")
        return int(len(frame))
    finally:
        con.close()


def upsert_total_return_index(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["index_id"] = frame["index_id"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    frame["price"] = pd.to_numeric(frame.get("price", 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["source"] = frame.get("source", "finmind_v4_total_return_index")
    frame = frame[["index_id", "dt", "price", "source"]].drop_duplicates(subset=["index_id", "dt"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_TOTAL_RETURN_INDEX_SQL)
        con.register("incoming_total_return_index", frame)
        con.execute(
            """
            DELETE FROM total_return_index_data
            USING incoming_total_return_index
            WHERE total_return_index_data.index_id = incoming_total_return_index.index_id
              AND total_return_index_data.dt = incoming_total_return_index.dt
            """
        )
        con.execute("INSERT INTO total_return_index_data SELECT *, CURRENT_TIMESTAMP FROM incoming_total_return_index")
        return int(len(frame))
    finally:
        con.close()


def upsert_margin_maintenance(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    frame["total_exchange_margin_maintenance"] = pd.to_numeric(
        frame.get("total_exchange_margin_maintenance", 0.0), errors="coerce"
    ).fillna(0.0).astype(float)
    frame["source"] = frame.get("source", "finmind_v4_margin_maintenance")
    frame = frame[["dt", "total_exchange_margin_maintenance", "source"]].drop_duplicates(subset=["dt"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_MARGIN_MAINTENANCE_SQL)
        con.register("incoming_margin_maintenance", frame)
        con.execute(
            """
            DELETE FROM margin_maintenance_data
            USING incoming_margin_maintenance
            WHERE margin_maintenance_data.dt = incoming_margin_maintenance.dt
            """
        )
        con.execute("INSERT INTO margin_maintenance_data SELECT *, CURRENT_TIMESTAMP FROM incoming_margin_maintenance")
        return int(len(frame))
    finally:
        con.close()


def upsert_government_bank(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for col in ["name", "source"]:
        frame[col] = frame.get(col, "").fillna("").astype(str)
    for col in ["buy", "sell", "net", "volume", "turnover"]:
        frame[col] = pd.to_numeric(frame.get(col, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame = frame[["ticker", "dt", "name", "buy", "sell", "net", "volume", "turnover", "source"]].drop_duplicates(
        subset=["ticker", "dt", "name"], keep="last"
    )
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_GOVERNMENT_BANK_SQL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_gov_bank_ticker_dt ON government_bank_data(ticker, dt)")
        con.register("incoming_gov_bank", frame)
        con.execute(
            """
            DELETE FROM government_bank_data
            USING incoming_gov_bank
            WHERE government_bank_data.ticker = incoming_gov_bank.ticker
              AND government_bank_data.dt = incoming_gov_bank.dt
              AND government_bank_data.name = incoming_gov_bank.name
            """
        )
        con.execute("INSERT INTO government_bank_data SELECT *, CURRENT_TIMESTAMP FROM incoming_gov_bank")
        return int(len(frame))
    finally:
        con.close()


def upsert_day_trading(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for col in ["day_trade_buy", "day_trade_sell", "day_trade_volume", "day_trade_tx"]:
        frame[col] = pd.to_numeric(frame.get(col, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["source"] = frame.get("source", "finmind_v4_day_trading")
    frame = frame[["ticker", "dt", "day_trade_buy", "day_trade_sell", "day_trade_volume", "day_trade_tx", "source"]].drop_duplicates(
        subset=["ticker", "dt"], keep="last"
    )
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_DAY_TRADING_SQL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_day_trading_ticker_dt ON day_trading_data(ticker, dt)")
        con.register("incoming_day_trading", frame)
        con.execute(
            """
            DELETE FROM day_trading_data
            USING incoming_day_trading
            WHERE day_trading_data.ticker = incoming_day_trading.ticker
              AND day_trading_data.dt = incoming_day_trading.dt
            """
        )
        con.execute("INSERT INTO day_trading_data SELECT *, CURRENT_TIMESTAMP FROM incoming_day_trading")
        return int(len(frame))
    finally:
        con.close()


def upsert_dealer_futures(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for col in ["futures_id", "dealer_code", "dealer_name", "source"]:
        frame[col] = frame.get(col, "").fillna("").astype(str)
    frame["volume"] = pd.to_numeric(frame.get("volume", 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["is_after_hour"] = frame["is_after_hour"].astype(int)
    frame = frame[["dt", "futures_id", "dealer_code", "dealer_name", "volume", "is_after_hour", "source"]].drop_duplicates(
        subset=["dt", "futures_id", "dealer_code", "is_after_hour"], keep="last"
    )
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_DEALER_FUTURES_SQL)
        con.register("incoming_dealer_futures", frame)
        con.execute(
            """
            DELETE FROM dealer_futures_data
            USING incoming_dealer_futures
            WHERE dealer_futures_data.dt = incoming_dealer_futures.dt
              AND dealer_futures_data.futures_id = incoming_dealer_futures.futures_id
              AND dealer_futures_data.dealer_code = incoming_dealer_futures.dealer_code
              AND dealer_futures_data.is_after_hour = incoming_dealer_futures.is_after_hour
            """
        )
        con.execute("INSERT INTO dealer_futures_data SELECT *, CURRENT_TIMESTAMP FROM incoming_dealer_futures")
        return int(len(frame))
    finally:
        con.close()


def upsert_dealer_options(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for col in ["option_id", "dealer_code", "dealer_name", "source"]:
        frame[col] = frame.get(col, "").fillna("").astype(str)
    frame["volume"] = pd.to_numeric(frame.get("volume", 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["is_after_hour"] = frame["is_after_hour"].astype(int)
    frame = frame[["dt", "option_id", "dealer_code", "dealer_name", "volume", "is_after_hour", "source"]].drop_duplicates(
        subset=["dt", "option_id", "dealer_code", "is_after_hour"], keep="last"
    )
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_DEALER_OPTIONS_SQL)
        con.register("incoming_dealer_options", frame)
        con.execute(
            """
            DELETE FROM dealer_options_data
            USING incoming_dealer_options
            WHERE dealer_options_data.dt = incoming_dealer_options.dt
              AND dealer_options_data.option_id = incoming_dealer_options.option_id
              AND dealer_options_data.dealer_code = incoming_dealer_options.dealer_code
              AND dealer_options_data.is_after_hour = incoming_dealer_options.is_after_hour
            """
        )
        con.execute("INSERT INTO dealer_options_data SELECT *, CURRENT_TIMESTAMP FROM incoming_dealer_options")
        return int(len(frame))
    finally:
        con.close()


def upsert_derivative_afterhours(rows: pd.DataFrame) -> int:
    if rows is None or rows.empty:
        return 0
    frame = rows.copy()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.date
    for col in ["market", "product_id", "name", "put_call", "institutional_investors", "source"]:
        frame[col] = frame.get(col, "").fillna("").astype(str)
    for col in ["long_deal_volume", "short_deal_volume", "long_open_interest_balance", "short_open_interest_balance"]:
        frame[col] = pd.to_numeric(frame.get(col, 0.0), errors="coerce").fillna(0.0).astype(float)
    frame["net_deal_volume"] = frame["long_deal_volume"] - frame["short_deal_volume"]
    frame["net_open_interest_balance"] = frame["long_open_interest_balance"] - frame["short_open_interest_balance"]
    frame = frame[
        ["market", "product_id", "dt", "name", "put_call", "institutional_investors",
         "long_deal_volume", "short_deal_volume", "net_deal_volume",
         "long_open_interest_balance", "short_open_interest_balance", "net_open_interest_balance", "source"]
    ].drop_duplicates(subset=["market", "product_id", "dt", "name", "put_call", "institutional_investors"], keep="last")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_DERIVATIVE_AFTERHOURS_SQL)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_deriv_ah_product_dt "
            "ON derivative_afterhours_data(market, product_id, dt)"
        )
        con.register("incoming_deriv_ah", frame)
        con.execute(
            """
            DELETE FROM derivative_afterhours_data
            USING incoming_deriv_ah
            WHERE derivative_afterhours_data.market = incoming_deriv_ah.market
              AND derivative_afterhours_data.product_id = incoming_deriv_ah.product_id
              AND derivative_afterhours_data.dt = incoming_deriv_ah.dt
              AND derivative_afterhours_data.name = incoming_deriv_ah.name
              AND derivative_afterhours_data.put_call = incoming_deriv_ah.put_call
              AND derivative_afterhours_data.institutional_investors = incoming_deriv_ah.institutional_investors
            """
        )
        con.execute("INSERT INTO derivative_afterhours_data SELECT *, CURRENT_TIMESTAMP FROM incoming_deriv_ah")
        return int(len(frame))
    finally:
        con.close()


def fetch_institutional(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        rows = _get("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start, end, token)
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] institutional {stock_id}: no rows")
            continue
        frame["buy"] = _num(frame, "buy")
        frame["sell"] = _num(frame, "sell")
        frame["net"] = frame["buy"] - frame["sell"]
        grouped = frame.pivot_table(index=["date", "stock_id"], columns="name", values="net", aggfunc="sum").reset_index()
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(grouped["date"]).dt.date,
                "foreign_net_buy": _num(grouped, "Foreign_Investor") + _num(grouped, "Foreign_Dealer_Self"),
                "investment_trust_net_buy": _num(grouped, "Investment_Trust"),
                "dealer_net_buy": _num(grouped, "Dealer_self") + _num(grouped, "Dealer_Hedging"),
            }
        )
        out["institutional_total_net_buy"] = (
            out["foreign_net_buy"] + out["investment_trust_net_buy"] + out["dealer_net_buy"]
        )
        out["source"] = "finmind_v4_institutional"
        frames.append(out)
        print(f"[FinMind] institutional {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_margin(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        rows = _get("TaiwanStockMarginPurchaseShortSale", stock_id, start, end, token)
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] margin {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "margin_buy": _num(frame, "MarginPurchaseBuy"),
                "margin_sell": _num(frame, "MarginPurchaseSell"),
                "margin_repayment": _num(frame, "MarginPurchaseCashRepayment"),
                "margin_limit": _num(frame, "MarginPurchaseLimit"),
                "margin_balance": _num(frame, "MarginPurchaseTodayBalance"),
                "margin_prev_balance": _num(frame, "MarginPurchaseYesterdayBalance"),
                "offset_loan_short": pd.Series(0.0, index=frame.index, dtype=float),
                "short_buy": _num(frame, "ShortSaleBuy"),
                "short_sell": _num(frame, "ShortSaleSell"),
                "short_repayment": _num(frame, "ShortSaleCashRepayment"),
                "short_limit": _num(frame, "ShortSaleLimit"),
                "short_balance": _num(frame, "ShortSaleTodayBalance"),
                "short_prev_balance": _num(frame, "ShortSaleYesterdayBalance"),
                "source": "finmind_v4_margin",
            }
        )
        frames.append(out)
        print(f"[FinMind] margin {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_shareholding(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        rows = _get("TaiwanStockHoldingSharesPer", stock_id, start, end, token)
        frame = parse_shareholding_distribution_rows(rows, source="finmind_v4")
        if frame.empty:
            print(f"[FinMind] shareholding {stock_id}: no rows")
            continue
        frames.append(frame)
        print(f"[FinMind] shareholding {stock_id}: {len(frame)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_foreign_shareholding(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        rows = _get("TaiwanStockShareholding", stock_id, start, end, token)
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] foreign_shareholding {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "foreign_investment_remaining_shares": _num(frame, "ForeignInvestmentRemainingShares"),
                "foreign_investment_shares": _num(frame, "ForeignInvestmentShares"),
                "foreign_investment_remain_ratio": _num(frame, "ForeignInvestmentRemainRatio"),
                "foreign_investment_shares_ratio": _num(frame, "ForeignInvestmentSharesRatio"),
                "foreign_investment_upper_limit_ratio": _num(frame, "ForeignInvestmentUpperLimitRatio"),
                "chinese_investment_upper_limit_ratio": _num(frame, "ChineseInvestmentUpperLimitRatio"),
                "number_of_shares_issued": _num(frame, "NumberOfSharesIssued"),
                "recently_declare_date": frame.get("RecentlyDeclareDate", "").fillna("").astype(str),
                "source": "finmind_v4_shareholding",
            }
        )
        frames.append(out)
        print(f"[FinMind] foreign_shareholding {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_derivative_institutional(
    futures_ids: list[str],
    option_ids: list[str],
    start: str,
    end: str,
    token: str,
) -> pd.DataFrame:
    dataset_specs = [
        ("futures", "TaiwanFuturesInstitutionalInvestors", futures_ids),
        ("options", "TaiwanOptionInstitutionalInvestors", option_ids),
    ]
    frames = []
    for market, dataset, product_ids in dataset_specs:
        for product_id in product_ids:
            try:
                rows = _get(dataset, product_id, start, end, token)
            except RuntimeError as exc:
                print(f"[FinMind] derivative_institutional {market} {product_id}: skipped ({exc})")
                continue
            frame = pd.DataFrame(rows)
            if frame.empty:
                print(f"[FinMind] {dataset} {product_id}: no rows")
                continue
            out = pd.DataFrame(
                {
                    "market": market,
                    "product_id": product_id.upper(),
                    "dt": pd.to_datetime(frame["date"]).dt.date,
                    "name": _text(frame, "name"),
                    "put_call": _text(frame, "put_call") if "put_call" in frame.columns else _text(frame, "call_put"),
                    "institutional_investors": _text(frame, "institutional_investors"),
                    "long_deal_volume": _num(frame, "long_deal_volume"),
                    "long_deal_amount": _num(frame, "long_deal_amount"),
                    "short_deal_volume": _num(frame, "short_deal_volume"),
                    "short_deal_amount": _num(frame, "short_deal_amount"),
                    "long_open_interest_balance_volume": _num(frame, "long_open_interest_balance_volume"),
                    "long_open_interest_balance_amount": _num(frame, "long_open_interest_balance_amount"),
                    "short_open_interest_balance_volume": _num(frame, "short_open_interest_balance_volume"),
                    "short_open_interest_balance_amount": _num(frame, "short_open_interest_balance_amount"),
                    "source": f"finmind_v4_{dataset}",
                }
            )
            frames.append(out)
            print(f"[FinMind] derivative_institutional {market} {product_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_derivative_large_trader(
    futures_ids: list[str],
    option_ids: list[str],
    start: str,
    end: str,
    token: str,
) -> pd.DataFrame:
    dataset_specs = [
        ("futures", "TaiwanFuturesOpenInterestLargeTraders", futures_ids),
        ("options", "TaiwanOptionOpenInterestLargeTraders", option_ids),
    ]
    frames = []
    for market, dataset, product_ids in dataset_specs:
        for product_id in product_ids:
            try:
                rows = _get(dataset, product_id, start, end, token)
            except RuntimeError as exc:
                print(f"[FinMind] derivative_large_trader {market} {product_id}: skipped ({exc})")
                continue
            frame = pd.DataFrame(rows)
            if frame.empty:
                print(f"[FinMind] {dataset} {product_id}: no rows")
                continue
            out = pd.DataFrame(
                {
                    "market": market,
                    "product_id": product_id.upper(),
                    "dt": pd.to_datetime(frame["date"]).dt.date,
                    "name": _text(frame, "name"),
                    "contract_type": _text(frame, "contract_type"),
                    "put_call": _text(frame, "put_call") if "put_call" in frame.columns else _text(frame, "call_put"),
                    "buy_top5_trader_open_interest": _num(frame, "buy_top5_trader_open_interest"),
                    "buy_top5_trader_open_interest_per": _num(frame, "buy_top5_trader_open_interest_per"),
                    "buy_top10_trader_open_interest": _num(frame, "buy_top10_trader_open_interest"),
                    "buy_top10_trader_open_interest_per": _num(frame, "buy_top10_trader_open_interest_per"),
                    "sell_top5_trader_open_interest": _num(frame, "sell_top5_trader_open_interest"),
                    "sell_top5_trader_open_interest_per": _num(frame, "sell_top5_trader_open_interest_per"),
                    "sell_top10_trader_open_interest": _num(frame, "sell_top10_trader_open_interest"),
                    "sell_top10_trader_open_interest_per": _num(frame, "sell_top10_trader_open_interest_per"),
                    "market_open_interest": _num(frame, "market_open_interest"),
                    "buy_top5_specific_open_interest": _num(frame, "buy_top5_specific_open_interest"),
                    "buy_top5_specific_open_interest_per": _num(frame, "buy_top5_specific_open_interest_per"),
                    "buy_top10_specific_open_interest": _num(frame, "buy_top10_specific_open_interest"),
                    "buy_top10_specific_open_interest_per": _num(frame, "buy_top10_specific_open_interest_per"),
                    "sell_top5_specific_open_interest": _num(frame, "sell_top5_specific_open_interest"),
                    "sell_top5_specific_open_interest_per": _num(frame, "sell_top5_specific_open_interest_per"),
                    "sell_top10_specific_open_interest": _num(frame, "sell_top10_specific_open_interest"),
                    "sell_top10_specific_open_interest_per": _num(frame, "sell_top10_specific_open_interest_per"),
                    "source": f"finmind_v4_{dataset}",
                }
            )
            frames.append(out)
            print(f"[FinMind] derivative_large_trader {market} {product_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_stock_per(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        try:
            rows = _get("TaiwanStockPER", stock_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] per {stock_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] per {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "dividend_yield": _num(frame, "dividend_yield"),
                "per": _num(frame, "PER"),
                "pbr": _num(frame, "PBR"),
                "source": "finmind_v4_stock_per",
            }
        )
        frames.append(out)
        print(f"[FinMind] per {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_securities_lending(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        try:
            rows = _get("TaiwanStockSecuritiesLending", stock_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] securities_lending {stock_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] securities_lending {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "transaction_type": _text(frame, "transaction_type"),
                "volume": _num(frame, "volume"),
                "fee_rate": _num(frame, "fee_rate"),
                "close": _num(frame, "close"),
                "original_return_date": _text(frame, "original_return_date"),
                "original_lending_period": _num(frame, "original_lending_period"),
                "source": "finmind_v4_securities_lending",
            }
        )
        frames.append(out)
        print(f"[FinMind] securities_lending {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_short_sale_balances(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        try:
            rows = _get("TaiwanDailyShortSaleBalances", stock_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] short_sale_balances {stock_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] short_sale_balances {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "margin_short_previous_balance": _num(frame, "MarginShortSalesPreviousDayBalance"),
                "margin_short_sales": _num(frame, "MarginShortSalesShortSales"),
                "margin_short_covering": _num(frame, "MarginShortSalesShortCovering"),
                "margin_short_stock_redemption": _num(frame, "MarginShortSalesStockRedemption"),
                "margin_short_current_balance": _num(frame, "MarginShortSalesCurrentDayBalance"),
                "margin_short_quota": _num(frame, "MarginShortSalesQuota"),
                "sbl_short_previous_balance": _num(frame, "SBLShortSalesPreviousDayBalance"),
                "sbl_short_sales": _num(frame, "SBLShortSalesShortSales"),
                "sbl_short_returns": _num(frame, "SBLShortSalesReturns"),
                "sbl_short_adjustments": _num(frame, "SBLShortSalesAdjustments"),
                "sbl_short_current_balance": _num(frame, "SBLShortSalesCurrentDayBalance"),
                "sbl_short_quota": _num(frame, "SBLShortSalesQuota"),
                "sbl_short_covering": _num(frame, "SBLShortSalesShortCovering"),
                "source": "finmind_v4_short_sale_balances",
            }
        )
        frames.append(out)
        print(f"[FinMind] short_sale_balances {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_total_return_index(index_ids: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    frames = []
    for index_id in index_ids:
        try:
            rows = _get("TaiwanStockTotalReturnIndex", index_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] total_return_index {index_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] total_return_index {index_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "index_id": _text(frame, "stock_id").str.upper(),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "price": _num(frame, "price"),
                "source": "finmind_v4_total_return_index",
            }
        )
        frames.append(out)
        print(f"[FinMind] total_return_index {index_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_margin_maintenance(start: str, end: str, token: str) -> pd.DataFrame:
    try:
        rows = _get("TaiwanTotalExchangeMarginMaintenance", "", start, end, token)
    except RuntimeError as exc:
        print(f"[FinMind] margin_maintenance: skipped ({exc})")
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if frame.empty:
        print("[FinMind] margin_maintenance: no rows")
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "dt": pd.to_datetime(frame["date"]).dt.date,
            "total_exchange_margin_maintenance": _num(frame, "TotalExchangeMarginMaintenance"),
            "source": "finmind_v4_margin_maintenance",
        }
    )
    print(f"[FinMind] margin_maintenance: {len(out)} rows")
    return out


def fetch_government_bank(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    """八大公股行庫買賣超 (TaiwanStockGovernmentBankBuySell)."""
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        try:
            rows = _get("TaiwanStockGovernmentBankBuySell", stock_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] government_bank {stock_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] government_bank {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "name": _text(frame, "name"),
                "buy": _num(frame, "buy"),
                "sell": _num(frame, "sell"),
                "net": _num(frame, "buy") - _num(frame, "sell"),
                "volume": _num(frame, "volume"),
                "turnover": _num(frame, "turnover"),
                "source": "finmind_v4_government_bank",
            }
        )
        frames.append(out)
        print(f"[FinMind] government_bank {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_day_trading(tickers: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    """當日沖資料 (TaiwanStockDayTrading)."""
    frames = []
    for ticker in tickers:
        stock_id = _stock_id(ticker)
        try:
            rows = _get("TaiwanStockDayTrading", stock_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] day_trading {stock_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] day_trading {stock_id}: no rows")
            continue
        out = pd.DataFrame(
            {
                "ticker": _local_ticker(ticker),
                "dt": pd.to_datetime(frame["date"]).dt.date,
                "day_trade_buy": _num(frame, "DayTradeBuy"),
                "day_trade_sell": _num(frame, "DayTradeSell"),
                "day_trade_volume": _num(frame, "DayTradeVolume"),
                "day_trade_tx": _num(frame, "DayTradeTransaction"),
                "source": "finmind_v4_day_trading",
            }
        )
        frames.append(out)
        print(f"[FinMind] day_trading {stock_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_dealer_futures(product_ids: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    """期貨自營商交易量 (TaiwanFuturesDealerTradingVolumeDaily)."""
    frames = []
    for product_id in product_ids:
        try:
            rows = _get("TaiwanFuturesDealerTradingVolumeDaily", product_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] dealer_futures {product_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] dealer_futures {product_id}: no rows")
            continue
        out = pd.DataFrame({
            "dt": pd.to_datetime(frame["date"]).dt.date,
            "futures_id": frame["futures_id"].astype(str).str.upper(),
            "dealer_code": frame["dealer_code"].astype(str),
            "dealer_name": frame["dealer_name"].astype(str),
            "volume": _num(frame, "volume"),
            "is_after_hour": frame["is_after_hour"].astype(int),
            "source": "finmind_v4_futures_dealer",
        })
        frames.append(out)
        print(f"[FinMind] dealer_futures {product_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_dealer_options(product_ids: list[str], start: str, end: str, token: str) -> pd.DataFrame:
    """選擇權自營商交易量 (TaiwanOptionDealerTradingVolumeDaily)."""
    frames = []
    for product_id in product_ids:
        try:
            rows = _get("TaiwanOptionDealerTradingVolumeDaily", product_id, start, end, token)
        except RuntimeError as exc:
            print(f"[FinMind] dealer_options {product_id}: skipped ({exc})")
            continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            print(f"[FinMind] dealer_options {product_id}: no rows")
            continue
        out = pd.DataFrame({
            "dt": pd.to_datetime(frame["date"]).dt.date,
            "option_id": frame["option_id"].astype(str).str.upper(),
            "dealer_code": frame["dealer_code"].astype(str),
            "dealer_name": frame["dealer_name"].astype(str),
            "volume": _num(frame, "volume"),
            "is_after_hour": frame["is_after_hour"].astype(int),
            "source": "finmind_v4_options_dealer",
        })
        frames.append(out)
        print(f"[FinMind] dealer_options {product_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_derivative_afterhours(
    futures_ids: list[str],
    option_ids: list[str],
    start: str,
    end: str,
    token: str,
) -> pd.DataFrame:
    """期貨/選擇權法人夜盤 (TaiwanFutures/OptionInstitutionalInvestorsAfterHours)."""
    dataset_specs = [
        ("futures", "TaiwanFuturesInstitutionalInvestorsAfterHours", futures_ids),
        ("options", "TaiwanOptionInstitutionalInvestorsAfterHours", option_ids),
    ]
    frames = []
    for market, dataset, product_ids in dataset_specs:
        for product_id in product_ids:
            try:
                rows = _get(dataset, product_id, start, end, token)
            except RuntimeError as exc:
                print(f"[FinMind] afterhours {market} {product_id}: skipped ({exc})")
                continue
            frame = pd.DataFrame(rows)
            if frame.empty:
                print(f"[FinMind] {dataset} {product_id}: no rows")
                continue
            out = pd.DataFrame(
                {
                    "market": market,
                    "product_id": product_id.upper(),
                    "dt": pd.to_datetime(frame["date"]).dt.date,
                    "name": _text(frame, "name"),
                    "put_call": _text(frame, "put_call") if "put_call" in frame.columns else _text(frame, "call_put"),
                    "institutional_investors": _text(frame, "institutional_investors"),
                    "long_deal_volume": _num(frame, "long_deal_volume"),
                    "short_deal_volume": _num(frame, "short_deal_volume"),
                    "long_open_interest_balance": _num(frame, "long_open_interest_balance"),
                    "short_open_interest_balance": _num(frame, "short_open_interest_balance"),
                    "source": f"finmind_v4_{dataset.lower()}",
                }
            )
            frames.append(out)
            print(f"[FinMind] afterhours {market} {product_id}: {len(out)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=DEFAULT_TICKERS)
    parser.add_argument("--futures-ids", default="TX", help="Comma-separated futures ids, e.g. TX,MTX")
    parser.add_argument("--option-ids", default="TXO", help="Comma-separated option ids, e.g. TXO")
    parser.add_argument("--index-ids", default="TAIEX,TPEx", help="Comma-separated total-return index ids")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--datasets",
        default="institutional,margin,shareholding,foreign_shareholding",
        help=(
            "Comma-separated: institutional,margin,shareholding,foreign_shareholding,"
            "derivative_institutional,derivative_large_trader,per,securities_lending,"
            "short_sale_balances,total_return_index,margin_maintenance,"
            "government_bank,day_trading,derivative_afterhours,"
            "dealer_futures,dealer_options"
        ),
    )
    parser.add_argument("--token", default=os.environ.get("FINMIND_API_TOKEN", ""))
    args = parser.parse_args()

    tickers = [item.strip().upper() for item in args.tickers.split(",") if item.strip()]
    futures_ids = [item.strip().upper() for item in args.futures_ids.split(",") if item.strip()]
    option_ids = [item.strip().upper() for item in args.option_ids.split(",") if item.strip()]
    index_ids = [item.strip() for item in args.index_ids.split(",") if item.strip()]
    datasets = {item.strip().lower() for item in args.datasets.split(",") if item.strip()}
    if not args.token:
        print("[FinMind] no FINMIND_API_TOKEN/token supplied; anonymous request limits may apply")

    total_written = {}
    if "institutional" in datasets:
        rows = fetch_institutional(tickers, args.start, args.end, args.token)
        total_written["institutional"] = upsert_institutional_data(rows)
    if "margin" in datasets:
        rows = fetch_margin(tickers, args.start, args.end, args.token)
        total_written["margin"] = upsert_margin_data(rows)
    if "shareholding" in datasets:
        rows = fetch_shareholding(tickers, args.start, args.end, args.token)
        total_written["shareholding"] = upsert_shareholding_distribution(rows)
    if "foreign_shareholding" in datasets:
        rows = fetch_foreign_shareholding(tickers, args.start, args.end, args.token)
        total_written["foreign_shareholding"] = upsert_foreign_shareholding(rows)
    if "derivative_institutional" in datasets:
        rows = fetch_derivative_institutional(futures_ids, option_ids, args.start, args.end, args.token)
        total_written["derivative_institutional"] = upsert_derivative_institutional(rows)
    if "derivative_large_trader" in datasets:
        rows = fetch_derivative_large_trader(futures_ids, option_ids, args.start, args.end, args.token)
        total_written["derivative_large_trader"] = upsert_derivative_large_trader(rows)
    if "per" in datasets:
        rows = fetch_stock_per(tickers, args.start, args.end, args.token)
        total_written["per"] = upsert_stock_per(rows)
    if "securities_lending" in datasets:
        rows = fetch_securities_lending(tickers, args.start, args.end, args.token)
        total_written["securities_lending"] = upsert_securities_lending(rows)
    if "short_sale_balances" in datasets:
        rows = fetch_short_sale_balances(tickers, args.start, args.end, args.token)
        total_written["short_sale_balances"] = upsert_short_sale_balance(rows)
    if "total_return_index" in datasets:
        rows = fetch_total_return_index(index_ids, args.start, args.end, args.token)
        total_written["total_return_index"] = upsert_total_return_index(rows)
    if "margin_maintenance" in datasets:
        rows = fetch_margin_maintenance(args.start, args.end, args.token)
        total_written["margin_maintenance"] = upsert_margin_maintenance(rows)
    if "government_bank" in datasets:
        rows = fetch_government_bank(tickers, args.start, args.end, args.token)
        total_written["government_bank"] = upsert_government_bank(rows)
    if "day_trading" in datasets:
        rows = fetch_day_trading(tickers, args.start, args.end, args.token)
        total_written["day_trading"] = upsert_day_trading(rows)
    if "derivative_afterhours" in datasets:
        rows = fetch_derivative_afterhours(futures_ids, option_ids, args.start, args.end, args.token)
        total_written["derivative_afterhours"] = upsert_derivative_afterhours(rows)
    if "dealer_futures" in datasets:
        rows = fetch_dealer_futures(futures_ids, args.start, args.end, args.token)
        total_written["dealer_futures"] = upsert_dealer_futures(rows)
    if "dealer_options" in datasets:
        rows = fetch_dealer_options(option_ids, args.start, args.end, args.token)
        total_written["dealer_options"] = upsert_dealer_options(rows)

    print(f"[FinMind] rows_written={total_written}")


if __name__ == "__main__":
    main()
