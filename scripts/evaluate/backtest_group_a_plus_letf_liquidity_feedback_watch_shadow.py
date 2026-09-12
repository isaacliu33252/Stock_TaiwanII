#!/usr/bin/env python3
"""Backtest LETF liquidity feedback watch shadow for GroupA+."""

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

from group_a_plus.integrations.letf_liquidity_feedback import (  # noqa: E402
    build_letf_liquidity_feedback_backtest,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/letf_liquidity_feedback_watch_shadow/history"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW")


def _load_ohlcv(db_path: Path, tickers: tuple[str, ...] = TICKERS) -> Any:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            f"""
            SELECT ticker, dt, open, high, low, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders})
            ORDER BY dt, ticker
            """,
            list(tickers),
        ).fetchdf()
    finally:
        con.close()


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"letf_liquidity_feedback_watch_shadow_backtest_{stamp}.json"


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    start: str = "2015-01-01",
    range_threshold: float = 0.035,
    volume_z_min: float = 1.5,
    dislocation_z_min: float = 1.5,
    min_trigger_count: int = 20,
) -> dict[str, Any]:
    report = build_letf_liquidity_feedback_backtest(
        ohlcv=_load_ohlcv(db_path),
        as_of=as_of,
        start=start,
        range_threshold=range_threshold,
        volume_z_min=volume_z_min,
        dislocation_z_min=dislocation_z_min,
        min_trigger_count=min_trigger_count,
    )
    report.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {"db": str(db_path)},
        }
    )
    return report


def write_report(report: dict[str, Any], *, output_path: Path = DEFAULT_OUTPUT, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--range-threshold", type=float, default=0.035)
    parser.add_argument("--volume-z-min", type=float, default=1.5)
    parser.add_argument("--dislocation-z-min", type=float, default=1.5)
    parser.add_argument("--min-trigger-count", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        db_path=Path(args.db),
        as_of=args.as_of,
        start=args.start,
        range_threshold=args.range_threshold,
        volume_z_min=args.volume_z_min,
        dislocation_z_min=args.dislocation_z_min,
        min_trigger_count=args.min_trigger_count,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
    )
    print(
        "as_of={as_of} triggers={triggers} recommendation={rec} target_allowed={target}".format(
            as_of=report.get("as_of"),
            triggers=report.get("input_coverage", {}).get("trigger_count"),
            rec=report.get("summary", {}).get("recommendation"),
            target=report.get("decision", {}).get("target_weight_change_allowed"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
