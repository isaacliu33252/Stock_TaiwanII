#!/usr/bin/env python3
"""Build Group A+ regime-weighted tail-conformal shadow diagnostics.

This is a review-only artifact inspired by arXiv:2602.03903. It does not
change target weights, block trades, or replace the existing tail_conformal
guard.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.regime_weighted_tail_conformal import (
    DEFAULT_TARGET_TICKER,
    build_regime_weighted_tail_conformal_shadow,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/regime_weighted_tail_conformal_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/regime_weighted_tail_conformal_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_close(db_path: Path, ticker: str, start: str, as_of: str | None) -> pd.Series:
    params: list[Any] = [ticker, start]
    end_clause = ""
    if as_of:
        end_clause = "AND dt <= ?"
        params.append(as_of)
    query = f"""
        SELECT dt, close
        FROM ohlcv
        WHERE ticker = ?
          AND dt >= ?
          {end_clause}
        ORDER BY dt
    """
    with duckdb.connect(str(db_path), read_only=True) as conn:
        df = conn.execute(query, params).fetchdf()
    if df.empty:
        return pd.Series(dtype=float)
    df["dt"] = pd.to_datetime(df["dt"])
    return df.set_index("dt")["close"].astype(float).sort_index()


def _write_report(report: dict[str, Any], output: Path, history_dir: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    history_dir.mkdir(parents=True, exist_ok=True)
    as_of = report.get("as_of") or datetime.now().strftime("%Y%m%d")
    history_path = history_dir / f"regime_weighted_tail_conformal_shadow_{str(as_of).replace('-', '')}.json"
    history_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    close = _load_close(db_path, args.ticker, args.start, args.as_of)
    report = build_regime_weighted_tail_conformal_shadow(
        close=close,
        ticker=args.ticker,
        as_of=args.as_of,
        alpha=args.alpha,
        calibration_window=args.calibration_window,
        min_calibration=args.min_calibration,
        half_life=args.half_life,
        bandwidth=args.bandwidth,
        min_effective_sample_size=args.min_effective_sample_size,
    )
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    report["inputs"] = {
        "db": str(db_path),
        "ticker": args.ticker,
        "start": args.start,
        "as_of": args.as_of,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", default=DEFAULT_TARGET_TICKER)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--alpha", type=float, default=0.10)
    parser.add_argument("--calibration-window", type=int, default=504)
    parser.add_argument("--min-calibration", type=int, default=120)
    parser.add_argument("--half-life", type=float, default=126.0)
    parser.add_argument("--bandwidth", type=float, default=1.0)
    parser.add_argument("--min-effective-sample-size", type=int, default=60)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    _write_report(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps({"status": report.get("status"), "as_of": report.get("as_of"), "output": str(_resolve(args.output))}))


if __name__ == "__main__":
    main()
