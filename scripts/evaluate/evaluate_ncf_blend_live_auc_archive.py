#!/usr/bin/env python3
"""Compare ncf_dynamic_horizon_signal's blend_live_auc candidates against realized outcomes.

Research-only. Joins results/ncf_signal_archive.jsonl (built by
append_ncf_signal_archive.py) against realized forward price direction from
the OHLCV database, and reports each blend_live_auc candidate's hit rate per
horizon -- once enough forward-realized samples exist.

As of 2026-07-11 the archive only has ~11 trading days of history (backfilled
from results/ncf_{00631l,00632r}_latest_YYYYMMDD.json), so every horizon will
almost certainly report insufficient_data on first use, especially h=20
(needs 20 trading days to elapse per sample). This is expected -- run again
after the archive accumulates enough history (append_ncf_signal_archive.py
should run daily). Do not change ncf.py's blend_live_auc default based on a
result with n below min_samples.
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

from group_a_plus.integrations.ncf_signal_archive import (
    BLEND_VARIANTS,
    HORIZONS_DAYS,
    evaluate_archive_against_realized,
    load_archive,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_ARCHIVE_PATH = PROJECT_ROOT / "results" / "ncf_signal_archive.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "ncf_blend_live_auc_archive_evaluation_latest.json"


def _load_close(db_path: Path, ticker: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE_PATH))
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    archive = load_archive(Path(args.archive))
    if archive.empty:
        print(f"Archive empty or missing: {args.archive}")
        return

    tickers = sorted(archive["ticker"].unique())
    close_by_ticker = {ticker: _load_close(DB_PATH, ticker) for ticker in tickers}

    result = evaluate_archive_against_realized(
        archive,
        close_by_ticker,
        blend_variants=BLEND_VARIANTS,
        horizons=HORIZONS_DAYS,
        min_samples=args.min_samples,
    )

    print(f"Archive: {len(archive)} rows across {len(tickers)} ticker(s): {tickers}")
    for horizon, res in result.items():
        if res.get("status") == "insufficient_data":
            print(f"h={horizon}: insufficient_data (n={res['n']}, need >={res['min_samples_required']})")
            continue
        print(f"h={horizon}: n={res['n']}")
        for blend, stats in res["blend_hit_rates"].items():
            print(f"  blend_live_auc={blend}: n={stats['n']} hit_rate={stats['hit_rate']:.3f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"archive_rows": len(archive), "tickers": tickers, "results": result}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
