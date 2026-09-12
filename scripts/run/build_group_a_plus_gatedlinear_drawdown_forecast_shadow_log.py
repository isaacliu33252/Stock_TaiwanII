#!/usr/bin/env python3
"""Append today's GatedLinear-lite H=20 drawdown forecast to a live shadow log.

Research-only, pure logging step -- see
group_a_plus/integrations/gatedlinear_drawdown_forecast_shadow_log.py for why
this exists: the 2607.09537 (GatedLinear) follow-up found a small but
robust (3/3 sub-windows) forecasting edge over persistence at a 20-trading-
day horizon for 0050.TW's `drawdown` feature, on a single historical
backtest split. This starts accumulating real daily forecasts instead of
relying on that one split. Never changes target weights, execution guards,
or the latest live signal.

Safe to run standalone, or add as a best-effort step in
scripts/run/run_ncf_daily_pipeline.py (see BEST_EFFORT_STEP_NAMES there).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.gatedlinear_drawdown_forecast_shadow_log import (  # noqa: E402
    append_shadow_log_row,
    fit_and_forecast,
)

DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_LOG_PATH = PROJECT_ROOT / "results" / "group_a_plus_gatedlinear_drawdown_forecast_shadow_log.jsonl"
DEFAULT_LATEST_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gatedlinear_drawdown_forecast_shadow.json"
TICKER = "0050.TW"
START = "2015-01-01"  # avoids the unadjusted 2014-01-02 split break (see docs/HANDOFF_00631L_OHLCV_UNADJUSTED_CORPORATE_ACTIONS_DATA_BUG_20260816.md)


def _resolve_end_date(db_path: Path, requested_end: str) -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [TICKER]).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {TICKER}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def build_row(*, db_path: Path, end: str) -> dict:
    resolved_end = _resolve_end_date(db_path, end)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND dt >= ? AND dt <= ? AND volume > 0 ORDER BY dt",
            [TICKER, START, resolved_end],
        ).fetchdf()
    finally:
        con.close()
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.set_index("dt").sort_index()
    drawdown = df["close"] / df["close"].cummax() - 1
    return fit_and_forecast(drawdown)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--end", default="latest")
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_PATH))
    args = parser.parse_args()

    row = build_row(db_path=Path(args.db), end=args.end)
    appended = append_shadow_log_row(row, Path(args.log))

    latest_path = Path(args.latest_output)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"status={row.get('status')} date={row.get('date')} predicted_drawdown_h20={row.get('predicted_drawdown_h20')} appended={appended}")
    print(f"Log: {args.log}")
    print(f"Latest: {latest_path}")


if __name__ == "__main__":
    main()
