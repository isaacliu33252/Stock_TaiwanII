#!/usr/bin/env python3
"""Build a source-status artifact for the 0050 securities-lending soft source."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "securities_lending_0050_source_status.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "securities_lending_0050_source_status.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "securities_lending_source_status" / "history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _recent_rows(db_path: Path, ticker: str, limit: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, SUM(volume) AS volume
            FROM securities_lending_data
            WHERE ticker = ?
            GROUP BY dt
            ORDER BY dt DESC
            LIMIT ?
            """,
            [ticker, limit],
        ).fetchall()
    finally:
        con.close()
    return [{"dt": str(dt), "volume": float(volume or 0.0)} for dt, volume in rows]


def build_status(
    *,
    db_path: Path = DEFAULT_DB,
    ticker: str = "0050.TW",
    query_start: str,
    query_end: str,
    provider_rows_written: int | None = None,
    provider_message: str | None = None,
    as_of: str,
    recent_limit: int = 8,
) -> dict[str, Any]:
    recent = _recent_rows(db_path, ticker, recent_limit)
    latest_dt = recent[0]["dt"] if recent else None
    rows_written_zero = provider_rows_written == 0
    provider_no_rows = rows_written_zero and bool(provider_message and "no rows" in provider_message.lower())
    db_lagged_after_query = bool(latest_dt and latest_dt < query_end)
    status = "provider_no_rows" if provider_no_rows and db_lagged_after_query else "available"
    if not recent:
        status = "missing_db_rows"
    elif provider_rows_written is None:
        status = "db_snapshot_only"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_securities_lending_0050_source_status",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "ticker": ticker,
        "status": status,
        "policy": "source_status_only_no_strategy_change_no_weight_change",
        "query_window": {
            "start": query_start,
            "end": query_end,
        },
        "provider_observation": {
            "rows_written": provider_rows_written,
            "message": provider_message,
            "provider_no_rows": provider_no_rows,
        },
        "database_observation": {
            "db_path": str(db_path),
            "latest_dt": latest_dt,
            "db_lagged_after_query": db_lagged_after_query,
            "recent_rows": recent,
        },
        "summary": {
            "soft_source": True,
            "provider_no_rows_confirmed": provider_no_rows,
            "latest_available_dt": latest_dt,
            "query_end": query_end,
            "db_lagged_after_query": db_lagged_after_query,
            "strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
        "decision": {
            "blocks_deployment": False,
            "strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(status: dict[str, Any]) -> str:
    summary = status["summary"]
    provider = status["provider_observation"]
    db = status["database_observation"]
    return "\n".join(
        [
            "# Securities Lending 0050 Source Status",
            "",
            f"- Status: `{status['status']}`",
            f"- Ticker: `{status['ticker']}`",
            f"- Query window: `{status['query_window']['start']}` to `{status['query_window']['end']}`",
            f"- Provider rows written: `{provider.get('rows_written')}`",
            f"- Provider message: `{provider.get('message')}`",
            f"- Provider no rows confirmed: `{summary['provider_no_rows_confirmed']}`",
            f"- Latest DB date: `{db.get('latest_dt')}`",
            f"- DB lagged after query: `{summary['db_lagged_after_query']}`",
            f"- Soft source: `{summary['soft_source']}`",
            f"- Blocks deployment: `{status['decision']['blocks_deployment']}`",
            f"- Keep golden1_0531 unchanged: `{summary['keep_golden1_0531_unchanged']}`",
            "",
        ]
    )


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"securities_lending_0050_source_status_{as_of.replace('-', '')}.json"


def write_outputs(
    status: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(status), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(status["as_of"])).write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--query-start", required=True)
    parser.add_argument("--query-end", required=True)
    parser.add_argument("--provider-rows-written", type=int, default=None)
    parser.add_argument("--provider-message", default=None)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    status = build_status(
        db_path=_resolve(args.db),
        ticker=args.ticker,
        query_start=args.query_start,
        query_end=args.query_end,
        provider_rows_written=args.provider_rows_written,
        provider_message=args.provider_message,
        as_of=args.as_of,
    )
    write_outputs(
        status,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Securities lending 0050 source status: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": status["status"],
                "latest_dt": status["summary"]["latest_available_dt"],
                "provider_no_rows_confirmed": status["summary"]["provider_no_rows_confirmed"],
                "blocks_deployment": status["decision"]["blocks_deployment"],
                "keep_golden1_0531_unchanged": status["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
