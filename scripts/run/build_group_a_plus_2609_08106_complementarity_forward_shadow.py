#!/usr/bin/env python3
"""Daily forward-shadow log for 2609.08106 complementarity sleeve.

This records what the mom5-gated sleeve would do using data available as of a
date. It never changes live weights, Golden1_0531, Golden2_0830, execution
plans, or orders.
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

from scripts.evaluate import backtest_group_a_plus_2609_08106_complementarity_sleeve_shadow as sleeve


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_LOG = PROJECT_ROOT / "results/2609_08106_complementarity_forward_shadow_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_forward_shadow_latest.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_forward_shadow_latest.md"


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


def _latest_db_date(db_path: Path) -> str:
    with duckdb.connect(str(db_path), read_only=True) as con:
        value = con.execute(
            "SELECT max(dt) FROM ohlcv WHERE ticker IN (SELECT * FROM UNNEST(?))",
            [list(sleeve.TICKERS)],
        ).fetchone()[0]
    if value is None:
        raise RuntimeError("No OHLCV data for forward shadow log")
    return str(pd.Timestamp(value).date())


def _load_prices_through(db_path: Path, as_of: str, warmup_days: int) -> pd.DataFrame:
    start = str((pd.Timestamp(as_of) - pd.Timedelta(days=warmup_days)).date())
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(sleeve.TICKERS), start, as_of],
        ).fetchdf()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows through {as_of}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])


def _next_available_returns(db_path: Path, signal_date: str) -> dict[str, Any]:
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
        dates = [signal_date, str(pd.Timestamp(next_date).date())]
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?)) AND dt IN (SELECT * FROM UNNEST(?))
            """,
            [list(sleeve.TICKERS), dates],
        ).fetchdf()
    if rows.empty:
        return {"next_date": str(pd.Timestamp(next_date).date()), "returns": None}
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    if len(panel) < 2:
        return {"next_date": str(pd.Timestamp(next_date).date()), "returns": None}
    returns = panel.pct_change(fill_method=None).iloc[-1].dropna()
    return {
        "next_date": str(pd.Timestamp(next_date).date()),
        "returns": {ticker: float(value) for ticker, value in returns.items()},
    }


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
    gross = sum(float(weights_delta.get(ticker, 0.0)) * float(returns.get(ticker, 0.0)) for ticker in sleeve.TICKERS)
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
    as_of = args.as_of or _latest_db_date(db_path)
    prices = _load_prices_through(db_path, as_of, args.window + 30)
    scores = sleeve._score_frame(prices, args.window)
    if scores.empty:
        raise RuntimeError(f"No score row available through {as_of}")
    score_date = str(scores.index[-1].date())
    score_row = scores.iloc[-1]
    baseline = dict(sleeve.BASE_WEIGHTS)
    shadow = sleeve._weights_for_day(
        score_row,
        shift_weight=args.shift_weight,
        threshold=args.threshold,
        risk_gate="momentum5_weak",
        momentum_5d_max=args.momentum_5d_max,
        drawdown_max=args.drawdown_max,
        ann_vol_min=args.ann_vol_min,
    )
    gap = float(score_row["best_bond_score"]) - float(score_row["score_00631l"])
    gate_passes = sleeve._risk_gate_passes(
        score_row,
        risk_gate="momentum5_weak",
        momentum_5d_max=args.momentum_5d_max,
        drawdown_max=args.drawdown_max,
        ann_vol_min=args.ann_vol_min,
    )
    weights_delta = _weights_delta(shadow, baseline)
    next_result = _next_available_returns(db_path, score_date)
    realized = _score_pickup(weights_delta, next_result["returns"], args.cost_bps)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_complementarity_forward_shadow_entry",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "forward_shadow_only_no_orders_no_live_weight_change",
        "source_paper": "2609.08106",
        "strategy": {
            "name": "complementarity_sleeve_window42_threshold2_shift3pct_momentum5_weak",
            "window": int(args.window),
            "threshold": float(args.threshold),
            "shift_weight": float(args.shift_weight),
            "cost_bps": float(args.cost_bps),
            "risk_gate": "momentum5_weak",
            "momentum_5d_max": float(args.momentum_5d_max),
        },
        "as_of_requested": as_of,
        "signal_date": score_date,
        "data_end": str(prices.index[-1].date()),
        "signal": {
            "triggered": shadow != baseline,
            "best_bond": score_row.get("best_bond"),
            "score_00631l": float(score_row["score_00631l"]),
            "best_bond_score": float(score_row["best_bond_score"]),
            "score_gap": gap,
            "threshold_passes": bool(np.isfinite(gap) and gap >= args.threshold),
            "risk_gate_passes": bool(gate_passes),
            "momentum_5d_00631l": float(score_row["momentum_5d_00631l"]),
            "drawdown_window_00631l": float(score_row["drawdown_window_00631l"]),
            "ann_vol_00631l": float(score_row["ann_vol_00631l"]),
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
            "reason": "Forward shadow logging only; lockdown Golden1_0531 and Golden2_0830 are comparators and cannot be modified.",
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
    lines = [
        "# 2609.08106 Complementarity Forward Shadow",
        "",
        f"- generated_at: `{entry['generated_at']}`",
        f"- signal_date: `{entry['signal_date']}`",
        f"- policy: `{entry['policy']}`",
        f"- triggered: `{signal['triggered']}`",
        f"- best_bond: `{signal['best_bond']}`",
        f"- score_gap: `{signal['score_gap']:.6f}`",
        f"- momentum_5d_00631l: `{signal['momentum_5d_00631l']:.6f}`",
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
        "- Forward shadow only.",
        "- No live target-weight change, no execution plan change, and no orders.",
        "- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of")
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--shift-weight", type=float, default=0.03)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
    parser.add_argument("--drawdown-max", type=float, default=-0.03)
    parser.add_argument("--ann-vol-min", type=float, default=0.35)
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    entry = build_entry(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(entry, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(entry), encoding="utf-8")
    _upsert_jsonl(_resolve(args.log), entry)
    print(f"Forward shadow JSON: {output}")
    print(f"Forward shadow Markdown: {markdown}")
    print(f"Forward shadow log: {_resolve(args.log)}")


if __name__ == "__main__":
    main()
