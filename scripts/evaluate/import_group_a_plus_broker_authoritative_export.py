#!/usr/bin/env python3
"""Import an authoritative broker export CSV into the reconciliation sample schema.

The default output is a staging artifact. It does not overwrite the live
broker_holdings_time_series_sample.json unless --output explicitly points there.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_authoritative_export_template.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_authoritative_export_staging_sample.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/broker_authoritative_export/history"
REQUIRED_COLUMNS = {
    "as_of_date",
    "account_id_or_alias",
    "ticker",
    "shares",
    "market_value",
    "cash_balance",
    "currency",
    "source_file_name",
    "export_generated_at",
}
GROUP_A_PLUS_TICKERS = {"0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00751B.TWO"}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _float_or_none(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    return float(str(value).replace(",", "").strip())


def _int_or_zero(value: str | None) -> int:
    parsed = _float_or_none(value)
    return 0 if parsed is None else int(round(parsed))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"broker export missing required columns: {missing}")
        return [{str(k): "" if v is None else str(v).strip() for k, v in row.items()} for row in reader]


def build_authoritative_sample(input_path: Path) -> dict[str, Any]:
    rows = [row for row in _read_rows(input_path) if row.get("ticker")]
    position_rows = [row for row in rows if row["ticker"].upper() != "CASH"]
    as_of_dates = sorted({row.get("as_of_date", "") for row in rows if row.get("as_of_date")})
    cash_values = [_float_or_none(row.get("cash_balance")) for row in rows if _float_or_none(row.get("cash_balance")) is not None]
    source_names = sorted({row.get("source_file_name", "") for row in rows if row.get("source_file_name")})
    export_times = sorted({row.get("export_generated_at", "") for row in rows if row.get("export_generated_at")})
    latest_positions = {
        row["ticker"].upper(): _int_or_zero(row.get("shares"))
        for row in position_rows
        if row["ticker"].upper() in GROUP_A_PLUS_TICKERS
    }
    unknown_tickers = sorted(
        {
            row["ticker"].upper()
            for row in position_rows
            if row["ticker"].upper() not in GROUP_A_PLUS_TICKERS
        }
    )
    negative_positions = {ticker: shares for ticker, shares in latest_positions.items() if shares < 0}
    missing_required_tickers = sorted(GROUP_A_PLUS_TICKERS - set(latest_positions))
    errors: list[str] = []
    warnings: list[str] = []
    if not rows:
        errors.append("broker_export_empty")
    if not as_of_dates:
        errors.append("as_of_date_missing")
    if len(as_of_dates) > 1:
        errors.append("multiple_as_of_dates")
    if not cash_values:
        errors.append("cash_balance_missing")
    if missing_required_tickers:
        errors.append("group_a_plus_tickers_missing")
    if negative_positions:
        errors.append("negative_long_only_positions")
    if unknown_tickers:
        warnings.append("non_group_a_plus_tickers_ignored")

    status = "authoritative_sample_ready" if not errors else "invalid"
    as_of = as_of_dates[-1] if as_of_dates else None
    cash_balance = cash_values[-1] if cash_values else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_holdings_time_series_sample",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "history_type": "authoritative_broker_export_positions",
        "authoritative_broker_export": status == "authoritative_sample_ready",
        "source_file": str(input_path),
        "cash_balance": cash_balance,
        "coverage": {
            "transaction_count": 0,
            "snapshot_count": 1 if as_of else 0,
            "first_transaction_date": as_of,
            "last_transaction_date": as_of,
            "latest_position_count": len(latest_positions),
            "negative_position_count": len(negative_positions),
            "unknown_name_count": len(unknown_tickers),
            "account_count": len({row.get("account_id_or_alias", "") for row in rows if row.get("account_id_or_alias")}),
        },
        "latest_positions": dict(sorted(latest_positions.items())),
        "negative_positions": dict(sorted(negative_positions.items())),
        "unknown_names": unknown_tickers,
        "snapshots": [{"date": as_of, "positions": dict(sorted(latest_positions.items()))}] if as_of else [],
        "export_metadata": {
            "as_of_dates": as_of_dates,
            "currency_values": sorted({row.get("currency", "") for row in rows if row.get("currency")}),
            "source_file_names": source_names,
            "export_generated_at_values": export_times,
            "missing_required_tickers": missing_required_tickers,
        },
        "errors": errors,
        "warnings": warnings,
        "decision": {
            "can_feed_reconciliation": status == "authoritative_sample_ready",
            "creates_orders": False,
            "target_weight_change_allowed": False,
        },
    }


def _history_path(history_dir: Path, sample: dict[str, Any]) -> Path:
    last = (sample.get("coverage") or {}).get("last_transaction_date") or datetime.now().strftime("%Y%m%d")
    return history_dir / f"{str(last).replace('-', '')}.json"


def write_sample(sample: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, sample).write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    sample = build_authoritative_sample(_resolve(args.input))
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_sample(sample, output, history_dir)
    print(
        json.dumps(
            {
                "output": str(output),
                "status": sample["status"],
                "errors": sample["errors"],
                "can_feed_reconciliation": sample["decision"]["can_feed_reconciliation"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if sample["status"] == "authoritative_sample_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
