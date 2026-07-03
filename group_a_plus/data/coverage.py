"""Check local data coverage required by GroupA+ runners."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import NEWS_DIR
from tw_output_standard import OutputStandardizer, write_standard_output


REQUIRED_TABLES = {
    "ohlcv": "price",
    "institutional_data": "chip",
    "margin_data": "chip",
    "market_margin_data": "chip",
    "foreign_shareholding_data": "chip",
    "shareholding_distribution": "chip",
    "short_sale_balance_data": "chip",
    "securities_lending_data": "chip",
    "day_trading_data": "chip",
    "dealer_futures_data": "derivative",
    "dealer_options_data": "derivative",
    "derivative_institutional_data": "derivative",
}


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]).fetchone()[0])


def _table_date_summary(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, Any]:
    cols = [row[0] for row in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]).fetchall()]
    date_col = "dt" if "dt" in cols else ("date" if "date" in cols else None)
    row_count = int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    out: dict[str, Any] = {"table": table, "row_count": row_count, "date_column": date_col}
    if date_col:
        min_dt, max_dt = con.execute(f"SELECT min({date_col}), max({date_col}) FROM {table}").fetchone()
        out["date_start"] = str(min_dt) if min_dt is not None else None
        out["date_end"] = str(max_dt) if max_dt is not None else None
    return out


def _news_coverage(news_dir: Path) -> dict[str, Any]:
    dates = []
    files = 0
    rows = 0
    if not news_dir.exists():
        return {"exists": False, "files": 0, "rows": 0, "date_start": None, "date_end": None}
    for path in sorted(news_dir.glob("ltn_mainstream_*.jsonl")):
        files += 1
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                dt = pd.to_datetime(payload.get("date"), errors="coerce")
                if pd.notna(dt):
                    dates.append(dt.date())
                rows += 1
    return {
        "exists": True,
        "files": files,
        "rows": rows,
        "date_start": str(min(dates)) if dates else None,
        "date_end": str(max(dates)) if dates else None,
    }


def build_coverage(db_path: Path, news_dir: Path, start: str, end: str) -> dict[str, Any]:
    requested_start = pd.Timestamp(start).date()
    requested_end = pd.Timestamp(end).date()
    table_results = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for table, group in REQUIRED_TABLES.items():
            if not _table_exists(con, table):
                table_results.append({"table": table, "group": group, "exists": False, "covers_window": False})
                continue
            summary = _table_date_summary(con, table)
            start_ok = summary.get("date_start") is not None and pd.Timestamp(summary["date_start"]).date() <= requested_start
            end_ok = summary.get("date_end") is not None and pd.Timestamp(summary["date_end"]).date() >= requested_end
            table_results.append(
                {
                    **summary,
                    "group": group,
                    "exists": True,
                    "covers_window": bool(start_ok and end_ok),
                    "start_ok": bool(start_ok),
                    "end_ok": bool(end_ok),
                }
            )
    finally:
        con.close()

    news = _news_coverage(news_dir)
    news_start_ok = news["date_start"] is not None and pd.Timestamp(news["date_start"]).date() <= requested_start
    news_end_ok = news["date_end"] is not None and pd.Timestamp(news["date_end"]).date() >= requested_end
    news["covers_window"] = bool(news_start_ok and news_end_ok)
    news["start_ok"] = bool(news_start_ok)
    news["end_ok"] = bool(news_end_ok)
    hard_failures = [row for row in table_results if row["table"] == "ohlcv" and not row["covers_window"]]
    soft_gaps = [row for row in table_results if row["table"] != "ohlcv" and (not row.get("exists") or not row.get("covers_window"))]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": start, "end": end},
        "db_path": str(db_path),
        "tables": table_results,
        "news": news,
        "status": "fail" if hard_failures else ("warn" if soft_gaps or not news["covers_window"] else "pass"),
        "hard_failures": hard_failures,
        "soft_gaps": soft_gaps,
        "notes": [
            "OHLCV coverage is a hard requirement.",
            "Chip/news/derivative gaps are warnings because existing runners zero-fill missing optional features.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--news-dir", default=str(NEWS_DIR))
    parser.add_argument("--output", default="results/group_a_plus_data_coverage_20260619.json")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.data.coverage")
    try:
        report = build_coverage(Path(args.db), Path(args.news_dir), args.start, args.end)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Coverage: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
