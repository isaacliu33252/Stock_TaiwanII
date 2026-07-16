#!/usr/bin/env python3
"""Join every GroupA+ live shadow log on date, plus 00631L forward returns.

Research-only, pure analysis tool. Fable audit (2026-07-16, combination
opportunities #7): GroupA+ now has half a dozen independent shadow logs
(garch_regime, specialist_routing, market_state, signal_alignment,
ncf_signal_archive, the new a2120/recovery_boost_spillover_gate logs from this
session) that each accumulate one row per day, but nothing joins them on date
against realized forward returns the way
scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py already does for NCF.
Several previously-closed experiments (GNHAR, good/bad volatility, TXO chip
triggers) died from historical sample-size/split-sample instability -- these
live logs are now accumulating genuine forward-OOS samples every trading day,
so once enough rows exist, this join is what lets someone re-test those
signals cheaply instead of re-running expensive historical backtests.

As of 2026-07-16 the individual logs only have 5-8 rows each (just started
this session/this week), so there is nothing statistically meaningful to
report yet -- this script is infrastructure for later, not a finding today.
It never changes target weights, execution guards, or the live signal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices

DEFAULT_SOURCES: dict[str, Path] = {
    "garch_regime": PROJECT_ROOT / "results" / "garch_regime_shadow_log.jsonl",
    "specialist_routing": PROJECT_ROOT / "results" / "specialist_routing_shadow_log.jsonl",
    "market_state": PROJECT_ROOT / "results" / "market_state_shadow_log.jsonl",
    "signal_alignment": PROJECT_ROOT / "results" / "signal_alignment_shadow_log.jsonl",
    "ncf_signal_archive": PROJECT_ROOT / "results" / "ncf_signal_archive.jsonl",
    "recovery_boost_spillover_gate": PROJECT_ROOT / "results" / "group_a_plus_recovery_boost_spillover_gate_shadow_log.jsonl",
    "signal_alignment_shadow_variant": PROJECT_ROOT / "results" / "signal_alignment_shadow_variant_log.jsonl",
}
DEFAULT_TICKER = "00631L.TW"
DEFAULT_HORIZONS = (1, 5, 20)
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "results" / "group_a_plus_shadow_log_unified_join_latest.csv"
DEFAULT_OUTPUT_SUMMARY = PROJECT_ROOT / "results" / "group_a_plus_shadow_log_unified_join_summary_latest.json"


def _flatten(value: Any, prefix: str, out: dict[str, Any], *, max_depth: int = 2, depth: int = 0) -> None:
    if isinstance(value, dict) and depth < max_depth:
        for key, sub in value.items():
            _flatten(sub, f"{prefix}__{key}", out, max_depth=max_depth, depth=depth + 1)
    elif isinstance(value, (list, dict)):
        out[prefix] = json.dumps(value, ensure_ascii=False)
    else:
        out[prefix] = value


def _load_jsonl_rows(path: Path, *, ticker_filter: str | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if ticker_filter is not None and str(row.get("ticker")) != ticker_filter:
                continue
            rows.append(row)
    return rows


def load_source_frame(name: str, path: Path, *, ticker_filter: str | None = None) -> pd.DataFrame:
    rows = _load_jsonl_rows(path, ticker_filter=ticker_filter)
    if not rows:
        return pd.DataFrame()
    flattened: list[dict[str, Any]] = []
    for row in rows:
        if "date" not in row or not row["date"]:
            continue
        out: dict[str, Any] = {"date": pd.Timestamp(row["date"]).normalize()}
        for key, value in row.items():
            if key == "date":
                continue
            _flatten(value, f"{name}__{key}", out)
        flattened.append(out)
    if not flattened:
        return pd.DataFrame()
    frame = pd.DataFrame(flattened).drop_duplicates(subset="date", keep="last")
    return frame.set_index("date").sort_index()


def load_forward_returns(db_path: Path, dates: pd.DatetimeIndex, *, ticker: str, horizons: tuple[int, ...]) -> pd.DataFrame:
    if len(dates) == 0:
        return pd.DataFrame()
    start = str((dates.min() - pd.Timedelta(days=5)).date())
    end = str((dates.max() + pd.Timedelta(days=max(horizons) * 3 + 10)).date())
    prices = _load_prices(db_path, [ticker], start, end)
    close = prices[ticker].astype(float) if ticker in prices else pd.Series(dtype=float)
    out = pd.DataFrame(index=dates)
    for horizon in horizons:
        fwd = close.shift(-horizon) / close - 1.0
        out[f"fwd_return_{horizon}d_{ticker}"] = fwd.reindex(dates)
    return out


def build_unified_join(
    *,
    sources: dict[str, Path],
    db_path: Path,
    ticker: str = DEFAULT_TICKER,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for name, path in sources.items():
        ticker_filter = ticker if name == "ncf_signal_archive" else None
        frame = load_source_frame(name, path, ticker_filter=ticker_filter)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()

    joined = frames[0]
    for frame in frames[1:]:
        joined = joined.join(frame, how="outer")
    joined = joined.sort_index()

    forward_returns = load_forward_returns(db_path, joined.index, ticker=ticker, horizons=horizons)
    if not forward_returns.empty:
        joined = joined.join(forward_returns, how="left")
    return joined


def build_summary(joined: pd.DataFrame, sources: dict[str, Path]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "report_type": "group_a_plus_shadow_log_unified_join_summary",
        "research_only": True,
        "total_dates": int(len(joined)),
        "date_range": (
            {"start": str(joined.index.min().date()), "end": str(joined.index.max().date())}
            if len(joined)
            else None
        ),
        "sources": {},
    }
    for name in sources:
        cols = [col for col in joined.columns if col.startswith(f"{name}__")]
        non_null_dates = int(joined[cols].notna().any(axis=1).sum()) if cols else 0
        summary["sources"][name] = {
            "column_count": len(cols),
            "rows_with_data": non_null_dates,
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default=DEFAULT_TICKER)
    parser.add_argument("--horizons", type=int, nargs="+", default=list(DEFAULT_HORIZONS))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-summary", default=str(DEFAULT_OUTPUT_SUMMARY))
    args = parser.parse_args()

    joined = build_unified_join(
        sources=DEFAULT_SOURCES,
        db_path=Path(args.db),
        ticker=args.ticker,
        horizons=tuple(args.horizons),
    )
    summary = build_summary(joined, DEFAULT_SOURCES)

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    joined.to_csv(output_csv, encoding="utf-8-sig")

    output_summary = Path(args.output_summary)
    output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Joined CSV: {output_csv} ({len(joined)} dates, {len(joined.columns)} columns)")
    print(f"Summary: {output_summary}")
    print(json.dumps(summary["sources"], indent=2))


if __name__ == "__main__":
    main()
