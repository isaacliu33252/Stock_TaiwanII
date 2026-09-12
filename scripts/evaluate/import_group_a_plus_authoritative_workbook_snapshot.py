#!/usr/bin/env python3
"""Import a user-supplied authoritative holdings workbook snapshot.

The supported workbook shape is a flat sheet where one row contains ticker
labels such as "元大台灣50\\n0050" and a row labelled "即時庫存" contains share
counts. The output can feed broker reconciliation and execution-plan
--holdings-json, but this script never creates orders or changes weights.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "taiwan_stock_20260824.xlsx"
DEFAULT_SAMPLE_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_time_series_sample.json"
DEFAULT_HOLDINGS_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/holdings_authoritative_snapshot.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
GROUP_A_PLUS_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
TICKER_SUFFIX_TWO = {"00679B", "00751B"}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _extract_code(value: Any) -> str | None:
    text = "" if pd.isna(value) else str(value).upper()
    matches = re.findall(r"\b\d{4,5}[A-Z]?\b", text)
    return matches[-1] if matches else None


def _normalize_ticker(code: str) -> str:
    return f"{code}.TWO" if code in TICKER_SUFFIX_TWO else f"{code}.TW"


def parse_flat_workbook_holdings(path: Path, *, row_label: str = "即時庫存") -> tuple[str | None, dict[str, int]]:
    frame = pd.read_excel(path, sheet_name=0, header=None)
    as_of = None
    if frame.shape[0] and pd.notna(frame.iloc[0, 0]):
        parsed = pd.to_datetime(frame.iloc[0, 0], errors="coerce")
        if pd.notna(parsed):
            as_of = parsed.date().isoformat()

    holdings_row = None
    for idx in range(len(frame)):
        if any(str(value).strip() == row_label for value in frame.iloc[idx].tolist()):
            holdings_row = idx
            break
    if holdings_row is None:
        raise ValueError(f"workbook row not found: {row_label}")

    header_row = holdings_row - 1
    if header_row < 0:
        raise ValueError("workbook has no ticker header row above holdings row")

    holdings: dict[str, int] = {}
    for col_idx in range(frame.shape[1]):
        code = _extract_code(frame.iloc[header_row, col_idx])
        if code is None:
            continue
        ticker = _normalize_ticker(code)
        value = frame.iloc[holdings_row, col_idx]
        holdings[ticker] = 0 if pd.isna(value) else int(round(float(value)))
    if not holdings:
        raise ValueError("no holdings parsed from workbook")
    return as_of, holdings


def _latest_prices(db_path: Path, tickers: list[str], as_of: str | None) -> dict[str, float]:
    if not db_path.exists() or not tickers or not as_of:
        return {}
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT ticker, arg_max(close, dt) AS close
            FROM ohlcv
            WHERE ticker IN ({', '.join('?' for _ in tickers)}) AND dt <= ?
            GROUP BY ticker
            """,
            [*tickers, as_of],
        ).fetchdf()
    finally:
        con.close()
    return {str(row.ticker): float(row.close) for row in rows.itertuples(index=False) if pd.notna(row.close)}


def build_authoritative_outputs(
    *,
    input_path: Path,
    cash_balance: float,
    account_id_or_alias: str = "user_supplied_workbook",
    db_path: Path = DEFAULT_DB,
) -> tuple[dict[str, Any], dict[str, Any]]:
    as_of, parsed_holdings = parse_flat_workbook_holdings(input_path)
    latest_positions = {ticker: int(parsed_holdings.get(ticker, 0)) for ticker in GROUP_A_PLUS_TICKERS}
    excluded_positions = {
        ticker: int(shares)
        for ticker, shares in sorted(parsed_holdings.items())
        if ticker not in GROUP_A_PLUS_TICKERS and int(shares) != 0
    }
    negative_positions = {ticker: shares for ticker, shares in latest_positions.items() if shares < 0}
    prices = _latest_prices(db_path, list(latest_positions), as_of)
    market_values = {ticker: latest_positions[ticker] * prices.get(ticker, 0.0) for ticker in latest_positions}
    status = "authoritative_sample_ready" if as_of and cash_balance >= 0 and not negative_positions else "invalid"
    errors: list[str] = []
    if not as_of:
        errors.append("as_of_date_missing")
    if cash_balance < 0:
        errors.append("cash_balance_negative")
    if negative_positions:
        errors.append("negative_long_only_positions")

    sample = {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_holdings_time_series_sample",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "history_type": "user_supplied_authoritative_workbook_snapshot",
        "authoritative_broker_export": status == "authoritative_sample_ready",
        "authoritative_source_note": "user_supplied_workbook_and_cash_declared_authoritative",
        "source_file": str(input_path),
        "cash_balance": float(cash_balance),
        "coverage": {
            "transaction_count": 0,
            "snapshot_count": 1 if as_of else 0,
            "first_transaction_date": as_of,
            "last_transaction_date": as_of,
            "latest_position_count": len(latest_positions),
            "negative_position_count": len(negative_positions),
            "unknown_name_count": 0,
            "account_count": 1,
        },
        "latest_positions": latest_positions,
        "negative_positions": negative_positions,
        "unknown_names": [],
        "excluded_non_group_a_plus_positions": excluded_positions,
        "snapshots": [{"date": as_of, "positions": latest_positions}] if as_of else [],
        "market_values": market_values,
        "errors": errors,
        "warnings": [
            "source_is_user_supplied_workbook_not_broker_api_export",
            *(
                ["excluded_non_group_a_plus_positions_present"]
                if excluded_positions
                else []
            ),
        ],
        "decision": {
            "can_feed_reconciliation": status == "authoritative_sample_ready",
            "creates_orders": False,
            "target_weight_change_allowed": False,
        },
    }
    holdings = {
        "schema_version": 1,
        "report_type": "group_a_plus_authoritative_holdings_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "account_id_or_alias": account_id_or_alias,
        "source_file": str(input_path),
        "cash_balance": float(cash_balance),
        "holdings": latest_positions,
        "excluded_non_group_a_plus_positions": excluded_positions,
        "market_values": market_values,
        "policy": "execution_plan_input_only_no_orders_no_weight_change",
    }
    return sample, holdings


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--cash-balance", type=float, required=True)
    parser.add_argument("--account-id-or-alias", default="user_supplied_workbook")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--sample-output", default=str(DEFAULT_SAMPLE_OUTPUT))
    parser.add_argument("--holdings-output", default=str(DEFAULT_HOLDINGS_OUTPUT))
    args = parser.parse_args()

    sample, holdings = build_authoritative_outputs(
        input_path=_resolve(args.input),
        cash_balance=args.cash_balance,
        account_id_or_alias=args.account_id_or_alias,
        db_path=_resolve(args.db),
    )
    _write(_resolve(args.sample_output), sample)
    _write(_resolve(args.holdings_output), holdings)
    print(
        json.dumps(
            {
                "sample_output": str(_resolve(args.sample_output)),
                "holdings_output": str(_resolve(args.holdings_output)),
                "status": sample["status"],
                "as_of": holdings["as_of"],
                "holdings": holdings["holdings"],
                "cash_balance": holdings["cash_balance"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if sample["status"] == "authoritative_sample_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
