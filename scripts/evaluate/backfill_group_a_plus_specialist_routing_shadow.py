#!/usr/bin/env python3
"""Backfill specialist-routing shadow log from existing diagnostic logs.

This reconstructs only the information present in older shadow logs. It does
not invent missing TSMC/semiconductor state; those routes start accumulating
once daily_signal writes specialist_routing directly.
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

from group_a_plus.integrations.garch_regime_shadow import volatility_gate_reference
from group_a_plus.integrations.specialist_router import (
    append_specialist_routing_shadow_log,
    route_specialist,
)


DEFAULT_GARCH_LOG = PROJECT_ROOT / "results" / "garch_regime_shadow_log.jsonl"
DEFAULT_MARKET_STATE_LOG = PROJECT_ROOT / "results" / "market_state_shadow_log.jsonl"
DEFAULT_SIGNAL_ALIGNMENT_LOG = PROJECT_ROOT / "results" / "signal_alignment_shadow_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "specialist_routing_shadow_log.jsonl"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        date = row.get("date") or row.get("signal_date")
        if date:
            rows[str(pd.Timestamp(date).date())] = row
    return rows


def _volatility_gate_from_garch(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    gate = row.get("volatility_gate")
    if isinstance(gate, dict):
        return gate
    if row.get("status") != "available":
        return None
    if not all(key in row for key in ("high_vol_flag", "garch_proxy_vol_ratio", "garch_proxy_vol_percentile", "return_0050_5d")):
        return None
    return volatility_gate_reference(
        high_vol=bool(row.get("high_vol_flag")),
        ratio=float(row.get("garch_proxy_vol_ratio")),
        percentile=float(row.get("garch_proxy_vol_percentile")),
        return_5d=float(row.get("return_0050_5d")),
    )


def build_backfill_rows(
    *,
    garch_rows: dict[str, dict[str, Any]],
    market_rows: dict[str, dict[str, Any]],
    alignment_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    dates = sorted(set(garch_rows) | set(market_rows) | set(alignment_rows))
    out: list[dict[str, Any]] = []
    for date in dates:
        garch = garch_rows.get(date) or {}
        market = market_rows.get(date) or {}
        alignment = alignment_rows.get(date) or {}
        latest_features = dict(market.get("inputs") or {})
        routing = route_specialist(
            volatility_gate=_volatility_gate_from_garch(garch),
            market_state=market,
            signal_alignment=alignment,
            latest_features=latest_features,
        )
        out.append(
            {
                "date": date,
                "routing": routing,
                "execution_regime": market.get("logged_execution_regime") or garch.get("logged_execution_regime"),
            }
        )
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garch-log", default=str(DEFAULT_GARCH_LOG))
    parser.add_argument("--market-state-log", default=str(DEFAULT_MARKET_STATE_LOG))
    parser.add_argument("--signal-alignment-log", default=str(DEFAULT_SIGNAL_ALIGNMENT_LOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = _resolve(args.output)
    rows = build_backfill_rows(
        garch_rows=_read_jsonl(_resolve(args.garch_log)),
        market_rows=_read_jsonl(_resolve(args.market_state_log)),
        alignment_rows=_read_jsonl(_resolve(args.signal_alignment_log)),
    )
    for row in rows:
        append_specialist_routing_shadow_log(
            output,
            row["routing"],
            date=row["date"],
            execution_regime=row.get("execution_regime"),
        )
    print(f"Output: {output}")
    print(f"Backfilled rows: {len(rows)}")


if __name__ == "__main__":
    main()
