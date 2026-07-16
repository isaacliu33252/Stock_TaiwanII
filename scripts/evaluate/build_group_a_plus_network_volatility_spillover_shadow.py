#!/usr/bin/env python3
"""Build the latest GroupA+ network volatility-spillover shadow snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.network_volatility_spillover_shadow import (
    DEFAULT_TICKERS,
    build_log_realized_variance_panel,
    build_spillover_network_frame,
    latest_spillover_snapshot,
    spillover_recovery_boost_gate,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_network_vol_spillover_shadow_latest.json"
DEFAULT_FRAME_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_network_vol_spillover_shadow_frame_latest.csv"


def _load_ohlcv(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> "pd.DataFrame":  # type: ignore[name-defined]
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, open, high, low, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--target", default="0050.TW")
    parser.add_argument("--window", type=int, default=252)
    parser.add_argument("--edge-threshold", type=float, default=0.25)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--frame-output", default=str(DEFAULT_FRAME_OUTPUT))
    args = parser.parse_args()

    tickers = tuple(args.tickers)
    ohlcv = _load_ohlcv(Path(args.db), tickers, args.start, args.end)
    log_rv = build_log_realized_variance_panel(ohlcv, tickers=tickers)
    available_tickers = tuple(col for col in tickers if col in log_rv.columns and log_rv[col].notna().any())
    log_rv = log_rv[list(available_tickers)].dropna(how="all").ffill()
    frame = build_spillover_network_frame(
        log_rv,
        target=args.target,
        window=args.window,
        edge_threshold=args.edge_threshold,
    )
    snapshot = latest_spillover_snapshot(frame, target=args.target)
    gate = spillover_recovery_boost_gate(snapshot)
    payload = {
        "schema_version": 1,
        "report_type": "group_a_plus_network_volatility_spillover_shadow",
        "research_only": True,
        "source_paper": {
            "arxiv": "2606.03828v1",
            "title": "Network Time Series Models for Multivariate Volatility Forecasting",
            "implemented_as": "rolling_lagged_vol_spillover_shadow_not_full_gnhar",
        },
        "inputs": {
            "db": str(Path(args.db).resolve().relative_to(PROJECT_ROOT)),
            "start": args.start,
            "end": args.end,
            "tickers": list(available_tickers),
            "target": args.target,
            "window": args.window,
            "edge_threshold": args.edge_threshold,
        },
        "latest_snapshot": snapshot,
        "recovery_boost_gate": gate,
    }
    output = Path(args.output)
    frame_output = Path(args.frame_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    print(f"Snapshot: {output.resolve()}")
    print(f"Frame:    {frame_output.resolve()}")
    print(f"Gate:     {gate['reason']} allow={gate['allow_recovery_boost']}")


if __name__ == "__main__":
    main()
