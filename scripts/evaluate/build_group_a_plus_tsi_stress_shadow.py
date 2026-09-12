#!/usr/bin/env python3
"""Build the GroupA+ Triadic Stress Index shadow snapshot.

Inspired by arXiv:2608.10788. Research-only: this is a coincident stress-state
diagnostic and must not be read as a directional forecast or live allocation
rule.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.triadic_stress_index import (
    DEFAULT_ALARM_PERCENTILE,
    DEFAULT_ALPHA_DOWN,
    DEFAULT_ALPHA_UP,
    DEFAULT_MIN_OBSERVATIONS,
    DEFAULT_TICKER_SOURCES,
    DEFAULT_WINDOW_DAYS,
    latest_tsi_snapshot,
    load_tsi_price_panel,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_stress_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_stress_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "tsi_stress_shadow" / "history"


def _markdown(snapshot: dict[str, Any]) -> str:
    latest = snapshot.get("latest") or {}
    rows = []
    for item in snapshot.get("top_attribution") or []:
        rows.append(
            "| {ticker} | {triangle_share:.2%} | {degree_share:.2%} | {degree:.4f} |".format(
                ticker=item.get("ticker"),
                triangle_share=float(item.get("triangle_share") or 0.0),
                degree_share=float(item.get("degree_share") or 0.0),
                degree=float(item.get("degree") or 0.0),
            )
        )
    attr_table = "\n".join(rows) if rows else "| - | - | - | - |"
    return f"""# GroupA+ TSI Stress Shadow

- date: `{snapshot.get("date")}`
- status: `{snapshot.get("status")}`
- policy: `{snapshot.get("policy")}`
- production_effect: `{snapshot.get("production_effect")}`
- recommended_use: `{snapshot.get("recommended_use")}`
- alarm_active: `{snapshot.get("alarm_active")}`
- scope: {snapshot.get("scope_note")}

## Latest

- tsi: `{latest.get("tsi")}`
- tsi_memory: `{latest.get("tsi_memory")}`
- tsi_percentile: `{latest.get("tsi_percentile")}`
- tsi_memory_percentile: `{latest.get("tsi_memory_percentile")}`
- tsi_memory_zscore: `{latest.get("tsi_memory_zscore")}`
- effective_rank: `{latest.get("effective_rank")}`
- n_assets: `{latest.get("n_assets")}`
- observations: `{latest.get("observations")}`

## Top Attribution

| ticker | triangle_share | degree_share | degree |
|---|---:|---:|---:|
{attr_table}

## Governance

This report is research-only. It does not output target weights, target shares,
execution regime, or orders. The source paper frames TSI as a coincident state
index, not a forecast; any live use must pass out-of-sample GroupA+ validation
and promotion governance first.
"""


def build_and_write(
    *,
    db_path: Path,
    start: str,
    end: str,
    as_of: str,
    tickers: list[str] | None,
    window_days: int,
    min_observations: int,
    alpha_up: float,
    alpha_down: float,
    alarm_percentile: float,
    output: Path,
    output_md: Path,
    history_dir: Path,
) -> dict[str, Any]:
    source_map = DEFAULT_TICKER_SOURCES
    if tickers:
        missing = [ticker for ticker in tickers if ticker not in source_map]
        if missing:
            raise ValueError(f"Unsupported TSI tickers: {missing}")
        source_map = {ticker: source_map[ticker] for ticker in tickers}
    prices, source_status = load_tsi_price_panel(db_path=db_path, start=start, end=end, ticker_sources=source_map)
    snapshot = latest_tsi_snapshot(
        prices,
        source_status=source_status,
        as_of=as_of,
        window_days=window_days,
        min_observations=min_observations,
        alpha_up=alpha_up,
        alpha_down=alpha_down,
        alarm_percentile=alarm_percentile,
    )
    snapshot["source"] = {
        "paper": "2608.10788",
        "paper_title": "The Triadic Stress Index in Financial Markets",
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "ticker_count_requested": len(source_map),
    }

    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"tsi_stress_shadow_{snapshot.get('date') or as_of}.json"
    snapshot["history_path"] = str(history_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(snapshot), encoding="utf-8")
    history_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snapshot


def main() -> None:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--start", default=(today - timedelta(days=365 * 3)).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    parser.add_argument("--as-of", default=today.isoformat())
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKER_SOURCES))
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--min-observations", type=int, default=DEFAULT_MIN_OBSERVATIONS)
    parser.add_argument("--alpha-up", type=float, default=DEFAULT_ALPHA_UP)
    parser.add_argument("--alpha-down", type=float, default=DEFAULT_ALPHA_DOWN)
    parser.add_argument("--alarm-percentile", type=float, default=DEFAULT_ALARM_PERCENTILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    args = parser.parse_args()

    tickers = [item.strip() for item in args.tickers.split(",") if item.strip()]
    snapshot = build_and_write(
        db_path=args.db,
        start=args.start,
        end=args.end,
        as_of=args.as_of,
        tickers=tickers,
        window_days=args.window_days,
        min_observations=args.min_observations,
        alpha_up=args.alpha_up,
        alpha_down=args.alpha_down,
        alarm_percentile=args.alarm_percentile,
        output=args.output,
        output_md=args.output_md,
        history_dir=args.history_dir,
    )
    latest = snapshot.get("latest") or {}
    print(
        "TSI shadow: "
        f"date={snapshot.get('date')} "
        f"alarm={snapshot.get('alarm_active')} "
        f"memory_pct={latest.get('tsi_memory_percentile')} "
        f"top={(snapshot.get('top_attribution') or [{}])[0].get('ticker')}"
    )
    print(f"Output: {args.output}")
    print(f"Markdown: {args.output_md}")


if __name__ == "__main__":
    main()
