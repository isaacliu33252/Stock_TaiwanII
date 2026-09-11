#!/usr/bin/env python3
"""Daily forward-shadow log for 2609.07946 stock/bond/gold complementarity.

Research-only. This records what the selected complementarity sleeve would do
with data available as of a date. It never changes live weights, Golden1_0531,
Golden2_0830, execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate import backtest_group_a_plus_2609_07946_stock_bond_gold_complementarity_shadow as sbg


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_LOG = PROJECT_ROOT / "results/2609_07946_stock_bond_gold_forward_shadow_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_stock_bond_gold_forward_shadow_latest.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_stock_bond_gold_forward_shadow_latest.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _latest_db_date(db_path: Path, tickers: tuple[str, ...]) -> str:
    with duckdb.connect(str(db_path), read_only=True) as con:
        value = con.execute(
            "SELECT min(max_dt) FROM (SELECT ticker, max(dt) max_dt FROM ohlcv WHERE ticker IN (SELECT * FROM UNNEST(?)) GROUP BY ticker)",
            [list(tickers)],
        ).fetchone()[0]
    if value is None:
        raise RuntimeError("No OHLCV data for stock/bond/gold forward shadow log")
    return str(pd.Timestamp(value).date())


def _load_prices_through(db_path: Path, as_of: str, warmup_days: int) -> pd.DataFrame:
    start = str((pd.Timestamp(as_of) - pd.Timedelta(days=warmup_days)).date())
    core = [*sbg.CORE_TICKERS, "00635U.TW"]
    with duckdb.connect(str(db_path), read_only=True) as con:
        ohlcv = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [core, start, as_of],
        ).fetchdf()
        external = con.execute(
            """
            SELECT dt, ticker, close
            FROM external_market_ohlcv
            WHERE ticker IN ('GC=F')
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [start, as_of],
        ).fetchdf()
    rows = pd.concat([ohlcv, external], ignore_index=True)
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows through {as_of}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])


def _next_available_returns(db_path: Path, signal_date: str) -> dict[str, Any]:
    tracked = tuple(dict.fromkeys([*sbg.CORE_TICKERS, "00635U.TW", "GC=F"]))
    with duckdb.connect(str(db_path), read_only=True) as con:
        next_date = con.execute(
            """
            SELECT min(dt)
            FROM ohlcv
            WHERE ticker = '0050.TW' AND dt > ?
            """,
            [signal_date],
        ).fetchone()[0]
        if next_date is None:
            return {"next_date": None, "returns": None}
        next_date_str = str(pd.Timestamp(next_date).date())
        dates = [signal_date, next_date_str]
        ohlcv = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?)) AND dt IN (SELECT * FROM UNNEST(?))
            """,
            [list(ticker for ticker in tracked if ticker != "GC=F"), dates],
        ).fetchdf()
        external = con.execute(
            """
            SELECT dt, ticker, close
            FROM external_market_ohlcv
            WHERE ticker = 'GC=F' AND dt IN (SELECT * FROM UNNEST(?))
            """,
            [dates],
        ).fetchdf()
    rows = pd.concat([ohlcv, external], ignore_index=True)
    if rows.empty:
        return {"next_date": next_date_str, "returns": None}
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    if len(panel) < 2:
        return {"next_date": next_date_str, "returns": None}
    returns = panel.pct_change(fill_method=None).iloc[-1].dropna()
    return {"next_date": next_date_str, "returns": {ticker: float(value) for ticker, value in returns.items()}}


def _weights_delta(shadow: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    keys = sorted(set(shadow) | set(baseline))
    return {key: float(shadow.get(key, 0.0)) - float(baseline.get(key, 0.0)) for key in keys}


def _score_pickup(weights_delta: dict[str, float], returns: dict[str, float] | None, cost_bps: float) -> dict[str, Any]:
    if not returns:
        return {
            "available": False,
            "reason": "next_trading_day_not_available_yet",
            "gross_delta_return": None,
            "turnover": None,
            "cost_return": None,
            "net_delta_return": None,
        }
    gross = sum(float(weights_delta.get(ticker, 0.0)) * float(returns.get(ticker, 0.0)) for ticker in weights_delta if ticker != "cash")
    turnover = sum(abs(value) for value in weights_delta.values())
    cost = turnover * float(cost_bps) / 10000.0
    return {
        "available": True,
        "gross_delta_return": float(gross),
        "turnover": float(turnover),
        "cost_return": float(cost),
        "net_delta_return": float(gross - cost),
    }


def build_entry(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    candidates = sbg.CANDIDATE_UNIVERSES[args.universe]
    as_of = args.as_of or _latest_db_date(db_path, ("0050.TW", "00631L.TW", "00713.TW", "00635U.TW"))
    prices = _load_prices_through(db_path, as_of, args.window + 30)
    scores = sbg._score_frame(prices, args.window, candidates)
    if scores.empty:
        raise RuntimeError(f"No score row available through {as_of}")
    score_date = str(scores.index[-1].date())
    score_row = scores.iloc[-1]
    baseline = dict(sbg.BASE_WEIGHTS)
    shadow = sbg._weights_for_day(
        score_row,
        threshold=args.threshold,
        shift_weight=args.shift_weight,
        momentum_5d_max=args.momentum_5d_max,
    )
    gap = float(score_row["best_complement_score"]) - float(score_row["score_00631l"])
    threshold_passes = bool(np.isfinite(gap) and gap >= args.threshold)
    momentum_gate_passes = bool(
        np.isfinite(float(score_row["momentum_5d_00631l"])) and float(score_row["momentum_5d_00631l"]) <= args.momentum_5d_max
    )
    weights_delta = _weights_delta(shadow, baseline)
    next_result = _next_available_returns(db_path, score_date)
    realized = _score_pickup(weights_delta, next_result["returns"], args.cost_bps)
    instrument_review_required = "00635U.TW" in candidates
    reason = (
        "Forward shadow logging only. 00635U.TW is not in the current GroupA++ tradable core/watchlist, so executable use requires separate instrument review. Golden1_0531 and Golden2_0830 are lockdown comparators."
        if instrument_review_required
        else "Forward shadow logging only. Bond-only variant uses existing pipeline tickers, but still needs live-forward history and explicit execution approval before any target-weight change. Golden1_0531 and Golden2_0830 are lockdown comparators."
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_stock_bond_gold_forward_shadow_entry",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "forward_shadow_only_no_orders_no_live_weight_change",
        "source_paper": "2609.07946",
        "strategy": {
            "name": f"stock_bond_gold_complementarity_{args.universe}_window{args.window}_threshold{args.threshold:g}_shift{args.shift_weight:.0%}_mom5weak",
            "universe": args.universe,
            "candidates": list(candidates),
            "window": int(args.window),
            "threshold": float(args.threshold),
            "shift_weight": float(args.shift_weight),
            "cost_bps": float(args.cost_bps),
            "momentum_5d_max": float(args.momentum_5d_max),
        },
        "as_of_requested": as_of,
        "signal_date": score_date,
        "data_end": str(prices.index[-1].date()),
        "signal": {
            "triggered": shadow != baseline,
            "best_complement": score_row.get("best_complement"),
            "best_complement_type": score_row.get("best_complement_type"),
            "score_00631l": float(score_row["score_00631l"]),
            "best_complement_score": float(score_row["best_complement_score"]),
            "score_gap": gap,
            "threshold_passes": threshold_passes,
            "momentum_gate_passes": momentum_gate_passes,
            "momentum_5d_00631l": float(score_row["momentum_5d_00631l"]),
            "ann_vol_00631l": float(score_row["ann_vol_00631l"]),
            "corr_best_0050": float(score_row["corr_best_0050"]),
            "corr_best_00631l": float(score_row["corr_best_00631l"]),
        },
        "baseline_weights": baseline,
        "shadow_weights": shadow,
        "weights_delta": weights_delta,
        "realized_next_day": {
            "next_date": next_result["next_date"],
            **realized,
        },
        "decision": {
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "instrument_review_required": instrument_review_required,
            "reason": reason,
        },
    }


def _upsert_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = (entry["strategy"]["name"], entry["signal_date"])
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row_key = (row.get("strategy", {}).get("name"), row.get("signal_date"))
            if row_key != key:
                rows.append(row)
    rows.append(entry)
    rows.sort(key=lambda row: (row.get("signal_date", ""), row.get("strategy", {}).get("name", "")))
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, default=_json_default) for row in rows) + "\n", encoding="utf-8")


def render_markdown(entry: dict[str, Any]) -> str:
    signal = entry["signal"]
    realized = entry["realized_next_day"]
    decision_notes = [
        "- Keep as forward shadow only.",
        "- Do not change latest GroupA++ live weights, execution plans, or orders.",
    ]
    if entry["decision"]["instrument_review_required"]:
        decision_notes.append("- `00635U.TW` executable use requires separate instrument review before any watchlist/core addition.")
    else:
        decision_notes.append("- Bond-only variant still needs live-forward history and explicit execution approval before target-weight use.")
    decision_notes.append("- `golden1_0531` and `golden2_0830` are lockdown comparators.")
    lines = [
        "# 2609.07946 Stock/Bond/Gold Forward Shadow",
        "",
        f"- generated_at: `{entry['generated_at']}`",
        f"- signal_date: `{entry['signal_date']}`",
        f"- policy: `{entry['policy']}`",
        f"- universe: `{entry['strategy']['universe']}`",
        f"- candidates: `{', '.join(entry['strategy']['candidates'])}`",
        f"- triggered: `{signal['triggered']}`",
        f"- best_complement: `{signal['best_complement']}`",
        f"- best_complement_type: `{signal['best_complement_type']}`",
        f"- score_gap: `{signal['score_gap']:.6f}`",
        f"- threshold_passes: `{signal['threshold_passes']}`",
        f"- momentum_5d_00631l: `{signal['momentum_5d_00631l']:.6f}`",
        f"- momentum_gate_passes: `{signal['momentum_gate_passes']}`",
        f"- realized_next_day_available: `{realized['available']}`",
        f"- net_delta_return: `{realized['net_delta_return']}`",
        "",
        "## Weights Delta",
        "",
        "```json",
        json.dumps(entry["weights_delta"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Decision",
        "",
        *decision_notes,
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--universe", choices=sorted(sbg.CANDIDATE_UNIVERSES), default="bond_plus_00635u")
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--shift-weight", type=float, default=0.03)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
    args = parser.parse_args()

    entry = build_entry(args)
    log_path = _resolve(args.log)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    _upsert_jsonl(log_path, entry)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(entry, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(entry), encoding="utf-8")
    print(f"Stock/bond/gold forward shadow log: {log_path}")
    print(f"Stock/bond/gold forward shadow JSON: {output}")
    print(f"Stock/bond/gold forward shadow Markdown: {markdown}")
    print(
        "Signal:",
        json.dumps(
            {
                "signal_date": entry["signal_date"],
                "triggered": entry["signal"]["triggered"],
                "best_complement": entry["signal"]["best_complement"],
                "score_gap": entry["signal"]["score_gap"],
                "momentum_5d_00631l": entry["signal"]["momentum_5d_00631l"],
            },
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
