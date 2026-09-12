#!/usr/bin/env python3
"""Build the GroupA+ OMD residual-distance crowding shadow snapshot."""

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

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.omd_residual_distance_shadow import (
    DEFAULT_TICKERS,
    append_omd_residual_distance_shadow_log,
    build_omd_residual_distance_shadow,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/omd_residual_distance_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/omd_residual_distance_shadow/history"
DEFAULT_LOG = PROJECT_ROOT / "results/omd_residual_distance_shadow_log.jsonl"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_close_panel(db_path: Path, tickers: tuple[str, ...], as_of: str | None) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    placeholders = ", ".join("?" for _ in tickers)
    params: list[Any] = list(tickers)
    date_filter = ""
    if as_of:
        date_filter = "AND dt <= ?"
        params.append(as_of)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) {date_filter}
            ORDER BY dt, ticker
            """,
            params,
        ).fetchdf()
    if rows.empty:
        return pd.DataFrame()
    rows = rows.dropna(subset=["ticker", "dt", "close"]).copy()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _history_path(history_dir: Path, payload: dict[str, Any]) -> Path:
    stamp = str(payload.get("as_of") or payload.get("actual_data_end") or datetime.now().strftime("%Y-%m-%d"))
    return history_dir / f"omd_residual_distance_shadow_{stamp.replace('-', '')}.json"


def write_payload(
    payload: dict[str, Any],
    *,
    output: Path,
    history_dir: Path | None,
    log_path: Path | None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, payload).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if log_path is not None:
        append_omd_residual_distance_shadow_log(log_path, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--window", type=int, default=126)
    parser.add_argument("--analysis-lookback", type=int, default=504)
    parser.add_argument("--min-history", type=int, default=126)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    tickers = tuple(str(ticker) for ticker in args.tickers)
    close = _load_close_panel(_resolve(args.db), tickers, args.as_of)
    payload = build_omd_residual_distance_shadow(
        close,
        as_of=args.as_of,
        tickers=tickers,
        window=int(args.window),
        analysis_lookback=int(args.analysis_lookback),
        min_history=int(args.min_history),
    )
    write_payload(
        payload,
        output=_resolve(args.output),
        history_dir=None if args.no_history else _resolve(args.history_dir),
        log_path=None if args.no_log else _resolve(args.log),
    )
    latest = payload.get("latest") or {}
    print(f"OMD residual-distance shadow: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload.get("status"),
                "actual_data_end": payload.get("actual_data_end"),
                "state": latest.get("state"),
                "mean_pairwise_residual_distance": latest.get("mean_pairwise_residual_distance"),
                "low_distance_risk_percentile": latest.get("low_distance_risk_percentile"),
                "target_weight_change_allowed": (payload.get("decision") or {}).get("target_weight_change_allowed"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

