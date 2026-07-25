#!/usr/bin/env python3
"""Build a transaction-derived broker holdings time-series sample.

The input xlsx is a transaction ledger sample. The output is useful for
diagnostics, but it is not an authoritative broker holdings export and must not
unlock live orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "isaac_tra_20260718.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_time_series_sample.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/broker_holdings_time_series_sample/history"

NAME_TO_TICKER = {
    "元大台灣50": "0050.TW",
    "元大高股息": "0056.TW",
    "元大台灣50正2": "00631L.TW",
    "元大台灣50反1": "00632R.TW",
    "元大台灣50反一": "00632R.TW",
    "元大S&P500": "00646.TW",
    "元大美債20年": "00679B.TWO",
    "元大台灣高息低波": "00713.TW",
    "元大AAA至A公司債": "00751B.TWO",
    "國泰永續高股息": "00878.TW",
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _side(raw: Any) -> str:
    text = str(raw or "")
    if "買" in text:
        return "buy"
    if "賣" in text:
        return "sell"
    return "unknown"


def _clean_date(raw: Any) -> str | None:
    if pd.isna(raw):
        return None
    text = str(raw).replace("2925-", "2025-")
    value = pd.to_datetime(text, errors="coerce")
    if pd.isna(value):
        return None
    return value.date().isoformat()


def _float(raw: Any) -> float:
    try:
        if pd.isna(raw):
            return 0.0
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _transaction_rows(input_path: Path, sheet: str | int | None = None) -> list[dict[str, Any]]:
    frame = pd.read_excel(input_path, sheet_name=0 if sheet is None else sheet)
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        date = _clean_date(row.get("成交日期"))
        name = str(row.get("股票名稱") or "").strip()
        shares = _float(row.get("成交股數"))
        side = _side(row.get("交易類別"))
        if not date or not name or shares <= 0 or side == "unknown":
            continue
        signed_shares = shares if side == "buy" else -shares
        rows.append(
            {
                "date": date,
                "side": side,
                "name": name,
                "ticker": NAME_TO_TICKER.get(name),
                "shares": int(round(shares)),
                "signed_shares": int(round(signed_shares)),
                "price": _float(row.get("成交單價")),
                "gross_amount": _float(row.get("成交價金")),
                "fee": _float(row.get("手續費")),
                "tax": _float(row.get("交易稅")),
                "net_cashflow": _float(row.get("淨收付金額")),
            }
        )
    rows.sort(key=lambda item: (item["date"], item["ticker"] or item["name"], item["side"]))
    return rows


def _snapshots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positions: dict[str, int] = {}
    snapshots: list[dict[str, Any]] = []
    current_date: str | None = None
    for row in rows:
        ticker = row.get("ticker") or f"UNKNOWN:{row['name']}"
        if current_date is not None and row["date"] != current_date:
            snapshots.append({"date": current_date, "positions": dict(sorted(positions.items()))})
        current_date = row["date"]
        positions[ticker] = positions.get(ticker, 0) + int(row["signed_shares"])
    if current_date is not None:
        snapshots.append({"date": current_date, "positions": dict(sorted(positions.items()))})
    return snapshots


def build_sample(*, input_path: Path, sheet: str | int | None = None) -> dict[str, Any]:
    rows = _transaction_rows(input_path, sheet)
    snapshots = _snapshots(rows)
    latest_positions = snapshots[-1]["positions"] if snapshots else {}
    negative_positions = {ticker: shares for ticker, shares in latest_positions.items() if shares < 0}
    unknown_names = sorted({row["name"] for row in rows if not row.get("ticker")})
    dates = sorted({row["date"] for row in rows})
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_holdings_time_series_sample",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "sample_available" if rows else "empty",
        "history_type": "transaction_derived_incomplete_not_authoritative_broker_positions",
        "authoritative_broker_export": False,
        "source_file": str(input_path),
        "coverage": {
            "transaction_count": len(rows),
            "snapshot_count": len(snapshots),
            "first_transaction_date": dates[0] if dates else None,
            "last_transaction_date": dates[-1] if dates else None,
            "latest_position_count": len(latest_positions),
            "negative_position_count": len(negative_positions),
            "unknown_name_count": len(unknown_names),
        },
        "latest_positions": latest_positions,
        "negative_positions": negative_positions,
        "unknown_names": unknown_names,
        "snapshots": snapshots,
        "limitations": [
            "transaction_file_is_not_complete_broker_position_ledger",
            "negative_positions_imply_missing_initial_holdings_or_transfers",
            "current_cash_balance_missing",
            "do_not_generate_live_orders_from_this_sample",
        ],
    }


def _history_path(history_dir: Path, sample: dict[str, Any]) -> Path:
    last = (sample.get("coverage") or {}).get("last_transaction_date") or datetime.now().strftime("%Y%m%d")
    return history_dir / f"{str(last).replace('-', '')}.json"


def write_sample(sample: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, sample).write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    sample = build_sample(input_path=_resolve(args.input), sheet=args.sheet)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_sample(sample, output, history_dir)
    print(f"Broker holdings time-series sample: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, sample)}")
    print(json.dumps({"status": sample["status"], **sample["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
