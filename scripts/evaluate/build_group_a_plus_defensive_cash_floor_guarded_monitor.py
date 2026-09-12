#!/usr/bin/env python3
"""Build monitoring/rollback report for the defensive cash-floor candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.defensive_cash_floor_monitor import (  # noqa: E402
    CORE_TICKERS,
    build_defensive_cash_floor_monitor,
    load_candidate_log,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_LOG = PROJECT_ROOT / "results/defensive_cash_floor_guarded_candidate_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_guarded_monitor.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/defensive_cash_floor_guarded_monitor/history"


def _load_prices(db_path: Path, *, start: str = "2015-01-01", as_of: str | None = None) -> Any:
    if not db_path.exists():
        raise FileNotFoundError(f"missing db: {db_path}")
    query = """
        SELECT dt, ticker, close
        FROM ohlcv
        WHERE ticker IN (?, ?, ?, ?)
          AND dt >= ?
    """
    params: list[Any] = [*CORE_TICKERS, start]
    if as_of:
        query += " AND dt <= ?"
        params.append(as_of)
    query += " ORDER BY dt, ticker"
    with duckdb.connect(str(db_path), read_only=True) as conn:
        return conn.execute(query, params).df()


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"defensive_cash_floor_guarded_monitor_{as_of.replace('-', '')}.json"


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    log_path: Path = DEFAULT_LOG,
    as_of: str,
    start: str = "2015-01-01",
    first_n_triggers: int = 10,
) -> dict[str, Any]:
    rows = load_candidate_log(log_path)
    prices = _load_prices(db_path, start=start, as_of=as_of)
    report = build_defensive_cash_floor_monitor(
        candidate_log_rows=rows,
        price_frame=prices,
        as_of=as_of,
        first_n_triggers=first_n_triggers,
    )
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    report["sources"] = {
        "candidate_log": str(log_path),
        "db": str(db_path),
    }
    return report


def write_report(report: dict[str, Any], *, output_path: Path = DEFAULT_OUTPUT, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(report["as_of"])).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--first-n-triggers", type=int, default=10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        db_path=Path(args.db),
        log_path=Path(args.log),
        as_of=args.as_of,
        start=args.start,
        first_n_triggers=args.first_n_triggers,
    )
    write_report(report, output_path=Path(args.output), history_dir=None if args.no_history else Path(args.history_dir))
    print(
        "as_of={as_of} trigger_rows={triggers} evaluated={evaluated} rollback={rollback}".format(
            as_of=report["as_of"],
            triggers=report["input_counts"]["trigger_rows"],
            evaluated=report["input_counts"]["evaluated_trigger_rows"],
            rollback=report["rollback"]["disable_candidate"],
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), str(report['as_of']))}")


if __name__ == "__main__":
    main()
