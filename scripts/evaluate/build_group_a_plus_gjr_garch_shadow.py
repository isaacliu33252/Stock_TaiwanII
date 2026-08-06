#!/usr/bin/env python3
"""Build the daily GJR-GARCH asymmetry shadow diagnostic."""

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

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.gjr_garch_shadow import (  # noqa: E402
    DEFAULT_TICKER,
    append_gjr_garch_shadow_log,
    compute_gjr_garch_shadow,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_garch_shadow.json"
DEFAULT_LOG = PROJECT_ROOT / "results" / "gjr_garch_shadow_log.jsonl"


def _latest_ohlcv_date(db_path: Path, ticker: str) -> str:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT max(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if value is None:
        raise ValueError(f"no ohlcv rows for {ticker}")
    return str(pd.Timestamp(value).date())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default=DEFAULT_TICKER)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    as_of = _latest_ohlcv_date(db_path, args.ticker) if args.as_of == "latest" else args.as_of
    shadow = compute_gjr_garch_shadow(db_path, as_of, ticker=args.ticker)
    payload = {"schema_version": 1, "report_type": "gjr_garch_shadow", "as_of": as_of, **shadow}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.no_log:
        append_gjr_garch_shadow_log(Path(args.log), payload)

    print(f"GJR-GARCH shadow: {output}")
    print(
        "  "
        f"status={payload.get('status')} "
        f"date={payload.get('date')} "
        f"evidence={payload.get('evidence_level')} "
        f"disagreement={payload.get('vol_model_disagreement')}"
    )


if __name__ == "__main__":
    main()
