#!/usr/bin/env python3
"""Fetch a compact SOXX option-implied-volatility snapshot into DuckDB.

Yahoo Finance exposes the current option chain, not a historical IV surface.
This script stores one daily snapshot per run so the alert pipeline can build
an internal history over time.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH

MIN_REASONABLE_IV = 0.05
MAX_REASONABLE_IV = 2.0

CREATE_EXTERNAL_OPTIONS_IV_SQL = """
CREATE TABLE IF NOT EXISTS external_options_iv (
    provider              TEXT      NOT NULL,
    underlying            TEXT      NOT NULL,
    dt                    DATE      NOT NULL,
    spot                  DOUBLE,
    expiry                DATE,
    dte                   INTEGER,
    atm_iv                DOUBLE,
    atm_call_iv           DOUBLE,
    atm_put_iv            DOUBLE,
    otm_put_iv_95         DOUBLE,
    otm_call_iv_105       DOUBLE,
    put_call_iv_skew      DOUBLE,
    put_call_volume_ratio DOUBLE,
    put_call_oi_ratio     DOUBLE,
    contract_count        BIGINT,
    source                TEXT      NOT NULL DEFAULT 'yfinance_option_chain',
    fetched_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, underlying, dt)
);
"""


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except Exception:
        return None
    if not math.isfinite(result):
        return None
    return result


def _nearest_iv(chain: pd.DataFrame, target_strike: float, option_type: str) -> float | None:
    if chain.empty or "strike" not in chain or "impliedVolatility" not in chain:
        return None
    frame = chain[["strike", "impliedVolatility"]].copy()
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    frame["impliedVolatility"] = pd.to_numeric(frame["impliedVolatility"], errors="coerce")
    frame = frame.dropna()
    # Yahoo occasionally returns placeholder IV values near zero for otherwise
    # liquid contracts. Those poison the downstream SOXX option-state gate, so
    # reject implausible IVs before selecting the nearest strike.
    frame = frame[
        (frame["impliedVolatility"] >= MIN_REASONABLE_IV)
        & (frame["impliedVolatility"] <= MAX_REASONABLE_IV)
    ]
    if frame.empty:
        return None
    idx = (frame["strike"] - target_strike).abs().idxmin()
    return _finite_float(frame.loc[idx, "impliedVolatility"])


def _ratio(numerator: Any, denominator: Any) -> float | None:
    num = _finite_float(numerator)
    den = _finite_float(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def build_soxx_iv_snapshot(
    *,
    ticker_obj: Any,
    underlying: str = "SOXX",
    snapshot_date: str | date | None = None,
    target_dte: int = 30,
    min_dte: int = 7,
) -> dict[str, Any]:
    """Build one SOXX IV snapshot from a yfinance-like Ticker object."""
    snap_dt = pd.Timestamp(snapshot_date or date.today()).normalize()
    options = list(getattr(ticker_obj, "options", []) or [])
    if not options:
        raise RuntimeError(f"{underlying} has no option expiries from provider")

    spot = None
    try:
        fast_info = getattr(ticker_obj, "fast_info", {}) or {}
        spot = _finite_float(fast_info.get("last_price") or fast_info.get("lastPrice"))
    except Exception:
        spot = None
    if spot is None:
        hist = ticker_obj.history(period="5d", interval="1d")
        if hist is not None and not hist.empty and "Close" in hist:
            spot = _finite_float(hist["Close"].dropna().iloc[-1])
    if spot is None or spot <= 0:
        raise RuntimeError(f"{underlying} spot price unavailable")

    expiry_rows: list[dict[str, Any]] = []
    for expiry_raw in options:
        expiry = pd.Timestamp(expiry_raw).normalize()
        dte = int((expiry - snap_dt).days)
        if dte < min_dte:
            continue
        chain = ticker_obj.option_chain(str(expiry.date()))
        calls = getattr(chain, "calls", pd.DataFrame()).copy()
        puts = getattr(chain, "puts", pd.DataFrame()).copy()
        if calls.empty or puts.empty:
            continue

        atm_call_iv = _nearest_iv(calls, spot, "call")
        atm_put_iv = _nearest_iv(puts, spot, "put")
        atm_values = [value for value in (atm_call_iv, atm_put_iv) if value is not None]
        if not atm_values:
            continue

        otm_put_iv = _nearest_iv(puts, spot * 0.95, "put")
        otm_call_iv = _nearest_iv(calls, spot * 1.05, "call")
        call_volume = pd.to_numeric(calls.get("volume", pd.Series(dtype=float)), errors="coerce").sum()
        put_volume = pd.to_numeric(puts.get("volume", pd.Series(dtype=float)), errors="coerce").sum()
        call_oi = pd.to_numeric(calls.get("openInterest", pd.Series(dtype=float)), errors="coerce").sum()
        put_oi = pd.to_numeric(puts.get("openInterest", pd.Series(dtype=float)), errors="coerce").sum()
        expiry_rows.append(
            {
                "expiry": expiry.date(),
                "dte": dte,
                "atm_iv": sum(atm_values) / len(atm_values),
                "atm_call_iv": atm_call_iv,
                "atm_put_iv": atm_put_iv,
                "otm_put_iv_95": otm_put_iv,
                "otm_call_iv_105": otm_call_iv,
                "put_call_iv_skew": (
                    otm_put_iv - otm_call_iv
                    if otm_put_iv is not None and otm_call_iv is not None
                    else None
                ),
                "put_call_volume_ratio": _ratio(put_volume, call_volume),
                "put_call_oi_ratio": _ratio(put_oi, call_oi),
                "contract_count": int(len(calls) + len(puts)),
            }
        )

    if not expiry_rows:
        raise RuntimeError(f"{underlying} has no usable option expiries with dte >= {min_dte}")

    selected = min(expiry_rows, key=lambda row: abs(int(row["dte"]) - target_dte))
    return {
        "provider": "yfinance",
        "underlying": underlying.upper(),
        "dt": snap_dt.date(),
        "spot": spot,
        **selected,
        "source": "yfinance_option_chain",
        "fetched_at": datetime.now(UTC).replace(microsecond=0),
    }


def write_snapshot(db_path: Path, snapshot: dict[str, Any]) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(CREATE_EXTERNAL_OPTIONS_IV_SQL)
        con.execute(
            """
            INSERT OR REPLACE INTO external_options_iv (
                provider, underlying, dt, spot, expiry, dte, atm_iv, atm_call_iv,
                atm_put_iv, otm_put_iv_95, otm_call_iv_105, put_call_iv_skew,
                put_call_volume_ratio, put_call_oi_ratio, contract_count, source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                snapshot.get("provider"),
                snapshot.get("underlying"),
                snapshot.get("dt"),
                snapshot.get("spot"),
                snapshot.get("expiry"),
                snapshot.get("dte"),
                snapshot.get("atm_iv"),
                snapshot.get("atm_call_iv"),
                snapshot.get("atm_put_iv"),
                snapshot.get("otm_put_iv_95"),
                snapshot.get("otm_call_iv_105"),
                snapshot.get("put_call_iv_skew"),
                snapshot.get("put_call_volume_ratio"),
                snapshot.get("put_call_oi_ratio"),
                snapshot.get("contract_count"),
                snapshot.get("source", "yfinance_option_chain"),
                snapshot.get("fetched_at"),
            ],
        )
    finally:
        con.close()


def _latest_history_date(ticker_obj: Any) -> str:
    hist = ticker_obj.history(period="5d", interval="1d")
    if hist is None or hist.empty:
        return date.today().isoformat()
    return pd.Timestamp(hist.index[-1]).date().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--underlying", default="SOXX")
    parser.add_argument(
        "--snapshot-date",
        default="auto",
        help="Snapshot date in YYYY-MM-DD, or auto to use the latest SOXX trading date.",
    )
    parser.add_argument("--target-dte", type=int, default=30)
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError as exc:
        raise SystemExit("yfinance not installed") from exc

    ticker_obj = yf.Ticker(args.underlying)
    snapshot_date = _latest_history_date(ticker_obj) if str(args.snapshot_date).lower() == "auto" else args.snapshot_date
    snapshot = build_soxx_iv_snapshot(
        ticker_obj=ticker_obj,
        underlying=args.underlying,
        snapshot_date=snapshot_date,
        target_dte=args.target_dte,
        min_dte=args.min_dte,
    )
    if not args.dry_run:
        write_snapshot(args.db, snapshot)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
