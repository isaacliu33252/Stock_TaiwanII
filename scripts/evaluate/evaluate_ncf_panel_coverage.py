#!/usr/bin/env python3
"""Audit NCF panel date coverage against latest OHLCV dates."""

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
sys.path.insert(0, str(PROJECT_ROOT))
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _read_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        first_col = str(frame.columns[0]) if len(frame.columns) else ""
        if first_col.startswith("Unnamed"):
            frame = frame.rename(columns={frame.columns[0]: "date"})
    if "date" not in frame.columns:
        raise ValueError(f"panel has no date column: {path}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def _latest_ohlcv_date(db_path: Path, source: str, ticker: str, provider: str | None = None) -> str | None:
    if not db_path.exists():
        return None
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if source == "external_market_ohlcv":
            row = con.execute(
                "SELECT MAX(dt) FROM external_market_ohlcv WHERE provider = ? AND ticker = ?",
                [provider or "yfinance", ticker],
            ).fetchone()
        else:
            row = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()
    finally:
        con.close()
    if not row or row[0] is None:
        return None
    return str(row[0])


def _business_day_gap(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if end_ts <= start_ts:
        return 0
    return max(0, len(pd.bdate_range(start_ts, end_ts)) - 1)


def _parse_panel_ticker(value: str) -> tuple[Path, str, str, str | None]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected PANEL=TICKER or PANEL=external_market_ohlcv:PROVIDER:TICKER")
    panel, spec = value.split("=", 1)
    if not panel or not spec:
        raise argparse.ArgumentTypeError("expected PANEL=TICKER or PANEL=external_market_ohlcv:PROVIDER:TICKER")
    parts = spec.split(":", 2)
    if len(parts) == 3:
        source, provider, ticker = parts
        if source != "external_market_ohlcv":
            raise argparse.ArgumentTypeError("only external_market_ohlcv source is supported in extended specs")
        return _resolve(panel), ticker, source, provider
    return _resolve(panel), spec, "ohlcv", None


def audit_panel_coverage(
    panel_tickers: list[tuple[Path, str] | tuple[Path, str, str, str | None]],
    *,
    db_path: str | Path = DB_PATH,
    max_labeled_gap_bdays: int = 20,
) -> dict[str, Any]:
    db = _resolve(db_path)
    panels: list[dict[str, Any]] = []
    warn_count = 0
    fail_count = 0

    for item in panel_tickers:
        if len(item) == 2:
            panel_path, ticker = item
            source = "ohlcv"
            provider = None
        else:
            panel_path, ticker, source, provider = item
        frame = _read_panel(panel_path)
        valid_dates = frame["date"].dropna()
        panel_end = valid_dates.max().strftime("%Y-%m-%d") if not valid_dates.empty else None
        panel_start = valid_dates.min().strftime("%Y-%m-%d") if not valid_dates.empty else None
        latest_ohlcv = _latest_ohlcv_date(db, source, ticker, provider)
        gap = _business_day_gap(panel_end, latest_ohlcv)
        live_tail_rows = 0
        if "is_live" in frame.columns:
            live_tail_rows = int(frame["is_live"].fillna(False).astype(bool).sum())
        has_live_tail_to_latest = bool(live_tail_rows and panel_end == latest_ohlcv)

        if gap is None:
            status = "fail"
            reason = "missing latest OHLCV or panel date"
        elif gap == 0:
            status = "pass"
            reason = "panel reaches latest OHLCV date"
        elif gap <= max_labeled_gap_bdays:
            status = "warn"
            reason = "panel appears label-limited and does not include live tail"
        else:
            status = "fail"
            reason = "panel coverage lags latest OHLCV beyond label horizon"

        if status == "warn":
            warn_count += 1
        elif status == "fail":
            fail_count += 1

        panels.append(
            {
                "panel": str(panel_path),
                "ticker": ticker,
                "source": source,
                "provider": provider,
                "row_count": int(len(frame)),
                "date_start": panel_start,
                "date_end": panel_end,
                "latest_ohlcv_date": latest_ohlcv,
                "business_day_gap_to_latest": gap,
                "live_tail_rows": live_tail_rows,
                "has_live_tail_to_latest": has_live_tail_to_latest,
                "status": status,
                "reason": reason,
            }
        )

    overall = "fail" if fail_count else "warn" if warn_count else "pass"
    return {
        "report_type": "ncf_panel_coverage",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db),
        "max_labeled_gap_bdays": int(max_labeled_gap_bdays),
        "overall_status": overall,
        "panel_count": len(panels),
        "warn_count": warn_count,
        "fail_count": fail_count,
        "panels": panels,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel-ticker", nargs="+", required=True, type=_parse_panel_ticker)
    parser.add_argument("--max-labeled-gap-bdays", type=int, default=20)
    parser.add_argument("--output", default="results/ncf_panel_coverage_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = audit_panel_coverage(
        args.panel_ticker,
        db_path=args.db,
        max_labeled_gap_bdays=args.max_labeled_gap_bdays,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF panel coverage: {output}")
    print(f"Overall: {report['overall_status']}")
    for panel in report["panels"]:
        print(
            f"  {panel['ticker']}: {panel['status']} "
            f"panel_end={panel['date_end']} latest={panel['latest_ohlcv_date']} "
            f"gap_bdays={panel['business_day_gap_to_latest']} live_tail={panel['live_tail_rows']}"
        )


if __name__ == "__main__":
    main()
