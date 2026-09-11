#!/usr/bin/env python3
"""Replay 2609.08106 complementarity sleeve on latest strategy weights.

This is a research-only replay. It reads the exported latest-strategy
historical target weights, applies the mom5-gated complementarity sleeve only
when an existing 00631L allocation is present, and compares after-cost returns.
It never changes live target weights, execution plans, or orders.
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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate import backtest_group_a_plus_2609_08106_complementarity_sleeve_shadow as sleeve


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_TARGET_WEIGHTS = PROJECT_ROOT / "report/group_a_plus/latest/latest_strategy_historical_target_weights.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_latest_target_weight_replay.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_latest_target_weight_replay.md"
WEIGHT_COLUMNS = {
    "target_weight_0050": "0050.TW",
    "target_weight_00631L": "00631L.TW",
    "target_weight_00632R": "00632R.TW",
    "target_weight_00679B": "00679B.TWO",
    "target_weight_00713": "00713.TW",
    "target_weight_cash": "cash",
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_target_weights(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        raise ValueError("target weights CSV must contain a date column")
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        out: dict[str, Any] = {"date": row["date"]}
        if "execution_regime" in frame.columns:
            out["execution_regime"] = row.get("execution_regime")
        for column, ticker in WEIGHT_COLUMNS.items():
            out[ticker] = float(row.get(column, 0.0) or 0.0)
        for ticker in sleeve.TICKERS:
            out.setdefault(ticker, 0.0)
        out.setdefault("cash", 0.0)
        rows.append(out)
    weights = pd.DataFrame(rows).set_index("date").sort_index()
    numeric_cols = [ticker for ticker in (*sleeve.TICKERS, "cash") if ticker in weights.columns]
    totals = weights[numeric_cols].sum(axis=1)
    nonzero = totals > 1e-12
    weights.loc[nonzero, numeric_cols] = weights.loc[nonzero, numeric_cols].div(totals[nonzero], axis=0)
    return weights


def _load_prices(db_path: Path, start: str, end: str, warmup_days: int) -> pd.DataFrame:
    start_ts = pd.Timestamp(start) - pd.Timedelta(days=warmup_days)
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(sleeve.TICKERS), str(start_ts.date()), end],
        ).fetchdf()
    if rows.empty:
        raise RuntimeError("No OHLCV rows for latest target-weight replay")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])


def _apply_sleeve(
    base_weights: pd.DataFrame,
    scores: pd.DataFrame,
    *,
    shift_weight: float,
    threshold: float,
    momentum_5d_max: float,
    drawdown_max: float,
    ann_vol_min: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    adjusted = base_weights.copy()
    events: list[dict[str, Any]] = []
    weight_cols = [ticker for ticker in (*sleeve.TICKERS, "cash") if ticker in adjusted.columns]
    for dt in adjusted.index:
        if dt not in scores.index:
            continue
        row = adjusted.loc[dt].copy()
        score_row = scores.loc[dt]
        best_bond = score_row.get("best_bond")
        available_631l = float(row.get("00631L.TW", 0.0) or 0.0)
        gap = float(score_row.get("best_bond_score", np.nan)) - float(score_row.get("score_00631l", np.nan))
        gate_passes = sleeve._risk_gate_passes(
            score_row,
            risk_gate="momentum5_weak",
            momentum_5d_max=momentum_5d_max,
            drawdown_max=drawdown_max,
            ann_vol_min=ann_vol_min,
        )
        if (
            isinstance(best_bond, str)
            and best_bond in adjusted.columns
            and available_631l > 1e-12
            and np.isfinite(gap)
            and gap >= threshold
            and gate_passes
        ):
            shift = min(float(shift_weight), available_631l)
            adjusted.loc[dt, "00631L.TW"] = available_631l - shift
            adjusted.loc[dt, best_bond] = float(row.get(best_bond, 0.0) or 0.0) + shift
            events.append(
                {
                    "date": str(dt.date()),
                    "best_bond": best_bond,
                    "shift_from_00631l": float(shift),
                    "00631l_before": float(available_631l),
                    "00631l_after": float(available_631l - shift),
                    "score_gap": float(gap),
                    "momentum_5d_00631l": float(score_row.get("momentum_5d_00631l", np.nan)),
                }
            )
    totals = adjusted[weight_cols].sum(axis=1)
    nonzero = totals > 1e-12
    adjusted.loc[nonzero, weight_cols] = adjusted.loc[nonzero, weight_cols].div(totals[nonzero], axis=0)
    return adjusted, events


def _simulate(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    cost_bps: float,
) -> tuple[pd.Series, dict[str, Any]]:
    dates = weights.index.intersection(prices.index)
    returns = prices.pct_change(fill_method=None).fillna(0.0).reindex(dates).fillna(0.0)
    aligned = weights.reindex(dates).fillna(0.0)
    daily_returns: list[float] = []
    turnovers: list[float] = []
    prev: pd.Series | None = None
    weight_cols = [ticker for ticker in (*sleeve.TICKERS, "cash") if ticker in aligned.columns]
    for dt, row in aligned.iterrows():
        gross = sum(float(row.get(ticker, 0.0) or 0.0) * float(returns.loc[dt].get(ticker, 0.0) or 0.0) for ticker in sleeve.TICKERS)
        if prev is None:
            turnover = sum(abs(float(row.get(key, 0.0) or 0.0)) for key in weight_cols)
        else:
            turnover = sum(abs(float(row.get(key, 0.0) or 0.0) - float(prev.get(key, 0.0) or 0.0)) for key in weight_cols)
        cost = turnover * float(cost_bps) / 10000.0
        daily_returns.append(float(gross - cost))
        turnovers.append(float(turnover))
        prev = row
    series = pd.Series(daily_returns, index=dates, dtype=float)
    turnover_series = pd.Series(turnovers, index=dates, dtype=float)
    return series, {
        "total_turnover": float(turnover_series.sum()) if len(turnover_series) else 0.0,
        "mean_daily_turnover": float(turnover_series.mean()) if len(turnover_series) else 0.0,
    }


def _metrics(returns: pd.Series, initial_value: float) -> dict[str, Any]:
    r = returns.dropna()
    if r.empty:
        return {}
    equity = float(initial_value) * (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    total_return = float(equity.iloc[-1] / float(initial_value) - 1.0)
    ann_return = float((1.0 + total_return) ** (252 / len(r)) - 1.0)
    ann_vol = float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else 0.0
    return {
        "rows": int(len(r)),
        "final_value": float(equity.iloc[-1]),
        "total_return": total_return,
        "annual_return": ann_return,
        "annual_volatility": ann_vol,
        "sharpe_ratio": None if ann_vol == 0 else float(ann_return / ann_vol),
        "max_drawdown": float(dd.min()),
    }


def _delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "final_value",
        "total_return",
        "annual_return",
        "annual_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "total_turnover",
        "mean_daily_turnover",
    )
    return {
        key: None if left.get(key) is None or right.get(key) is None else float(left[key]) - float(right[key])
        for key in keys
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    target_weights_path = _resolve(args.target_weights)
    weights = _load_target_weights(target_weights_path)
    if weights.empty:
        raise RuntimeError("No latest target weights to replay")
    start = args.start or str(weights.index.min().date())
    end = args.end or str(weights.index.max().date())
    weights = weights.loc[(weights.index >= pd.Timestamp(start)) & (weights.index <= pd.Timestamp(end))]
    prices = _load_prices(_resolve(args.db), start, end, args.window + 30)
    scores = sleeve._score_frame(prices, args.window)
    base_returns, base_turnover = _simulate(prices, weights, cost_bps=args.cost_bps)
    adjusted, events = _apply_sleeve(
        weights,
        scores,
        shift_weight=args.shift_weight,
        threshold=args.threshold,
        momentum_5d_max=args.momentum_5d_max,
        drawdown_max=args.drawdown_max,
        ann_vol_min=args.ann_vol_min,
    )
    sleeve_returns, sleeve_turnover = _simulate(prices, adjusted, cost_bps=args.cost_bps)
    baseline_metrics = _metrics(base_returns, args.initial_value) | base_turnover
    sleeve_metrics = _metrics(sleeve_returns, args.initial_value) | sleeve_turnover
    delta = _delta(sleeve_metrics, baseline_metrics)
    event_count = len(events)
    positive = bool(
        event_count > 0
        and (delta.get("total_return") or 0.0) > 0.0
        and (delta.get("sharpe_ratio") or 0.0) > 0.0
        and (delta.get("max_drawdown") or -1.0) >= 0.0
    )
    blockers: list[str] = []
    if event_count == 0:
        blockers.append("no_sleeve_events_on_latest_target_weights")
    if not positive:
        blockers.append("latest_target_weight_replay_not_positive_on_all_core_metrics")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_latest_target_weight_replay",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_orders_no_live_weight_change",
        "inputs": {
            "db": str(_resolve(args.db)),
            "target_weights": str(target_weights_path),
            "start": start,
            "end": end,
            "window": int(args.window),
            "threshold": float(args.threshold),
            "shift_weight": float(args.shift_weight),
            "cost_bps": float(args.cost_bps),
            "risk_gate": "momentum5_weak",
            "momentum_5d_max": float(args.momentum_5d_max),
            "initial_value": float(args.initial_value),
        },
        "coverage": {
            "target_weight_rows": int(len(weights)),
            "price_rows": int(len(prices.loc[(prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))])),
            "score_rows": int(len(scores.loc[(scores.index >= pd.Timestamp(start)) & (scores.index <= pd.Timestamp(end))])),
            "days_with_00631l_weight": int((weights["00631L.TW"] > 1e-12).sum()),
        },
        "event_count": event_count,
        "recent_events": events[-10:],
        "baseline_metrics": baseline_metrics,
        "sleeve_metrics": sleeve_metrics,
        "delta_sleeve_minus_baseline": delta,
        "decision": {
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "advisory_import_allowed": True,
            "blockers": blockers,
            "reason": "Latest target-weight replay is validation evidence only; no live target weights, execution plans, or orders are changed.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    d = report["delta_sleeve_minus_baseline"]
    b = report["baseline_metrics"]
    s = report["sleeve_metrics"]
    lines = [
        "# 2609.08106 Latest Target-Weight Replay",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- window: `{report['inputs']['start']} -> {report['inputs']['end']}`",
        f"- event_count: `{report['event_count']}`",
        f"- days_with_00631l_weight: `{report['coverage']['days_with_00631l_weight']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| metric | latest baseline | 08106 sleeve | delta |",
        "|---|---:|---:|---:|",
    ]
    for key in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown", "total_turnover"):
        lines.append(f"| {key} | {b.get(key)} | {s.get(key)} | {d.get(key)} |")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Use as latest-target-weight validation evidence only.",
            "- Keep the complementarity score in advisory/reporting and continue forward shadow logging.",
            "- Do not change latest GroupA++ target weights, execution plans, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--target-weights", default=str(DEFAULT_TARGET_WEIGHTS))
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--shift-weight", type=float, default=0.03)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
    parser.add_argument("--drawdown-max", type=float, default=-0.03)
    parser.add_argument("--ann-vol-min", type=float, default=0.35)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Replay JSON: {output}")
    print(f"Replay Markdown: {markdown}")


if __name__ == "__main__":
    main()
