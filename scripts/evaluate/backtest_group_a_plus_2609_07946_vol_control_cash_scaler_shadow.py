#!/usr/bin/env python3
"""Backtest 2609.07946-inspired volatility-control cash scaler for GroupA++.

Research-only. This tests a capped cash scaler around the latest GroupA++ base
weights. It does not change live strategy, Golden1_0531, Golden2_0830, signals,
execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_vol_control_cash_scaler_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_vol_control_cash_scaler_shadow.md"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW")
BASE_WEIGHTS = {
    "0050.TW": 0.5299999999999999,
    "00631L.TW": 0.17166845262777064,
    "00632R.TW": 0.0,
    "00679B.TWO": 0.0,
    "00713.TW": 0.12,
    "cash": 0.17833154737222945,
}
WINDOWS = (
    ("2018", "2018-01-02", "2018-12-28"),
    ("2020_covid", "2020-01-02", "2020-12-31"),
    ("2022_rate", "2022-01-03", "2022-10-31"),
    ("2024", "2024-01-02", "2024-12-31"),
    ("2025_2026", "2025-01-02", "2026-09-10"),
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


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
            [list(TICKERS), str(start_ts.date()), end],
        ).fetchdf()
    if rows.empty:
        raise RuntimeError("No OHLCV rows for vol-control shadow")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])


def _metrics(returns: pd.Series, turnover: pd.Series | None = None) -> dict[str, Any]:
    r = returns.dropna()
    if r.empty:
        return {}
    equity = (1.0 + r).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    ann_return = float(equity.iloc[-1] ** (252 / len(r)) - 1.0)
    ann_vol = float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else 0.0
    return {
        "rows": int(len(r)),
        "final_value_ratio": float(equity.iloc[-1]),
        "total_return": float(equity.iloc[-1] - 1.0),
        "annual_return": ann_return,
        "annual_volatility": ann_vol,
        "sharpe_ratio": None if ann_vol == 0 else float(ann_return / ann_vol),
        "max_drawdown": float(drawdown.min()),
        "mean_daily_turnover": float(turnover.mean()) if turnover is not None and len(turnover) else 0.0,
        "total_turnover": float(turnover.sum()) if turnover is not None and len(turnover) else 0.0,
    }


def _delta(shadow: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    keys = ("total_return", "annual_return", "annual_volatility", "sharpe_ratio", "max_drawdown", "total_turnover")
    return {
        key: None
        if shadow.get(key) is None or baseline.get(key) is None
        else float(shadow.get(key)) - float(baseline.get(key))
        for key in keys
    }


def _base_return(returns: pd.DataFrame) -> pd.Series:
    out = pd.Series(0.0, index=returns.index)
    for ticker in TICKERS:
        out = out + float(BASE_WEIGHTS.get(ticker, 0.0)) * returns[ticker].fillna(0.0)
    return out


def _scale_weights(scale: float) -> dict[str, float]:
    risky_sum = sum(float(BASE_WEIGHTS.get(ticker, 0.0)) for ticker in TICKERS)
    scaled = {ticker: float(BASE_WEIGHTS.get(ticker, 0.0)) * scale for ticker in TICKERS}
    scaled["cash"] = float(BASE_WEIGHTS.get("cash", 0.0)) + risky_sum * (1.0 - scale)
    return scaled


def _rebalance_dates(dates: pd.DatetimeIndex, mode: str) -> set[pd.Timestamp]:
    if mode == "daily":
        return set(dates)
    if mode != "monthly":
        raise ValueError(f"Unknown rebalance mode: {mode}")
    by_month = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).last()
    return set(pd.DatetimeIndex(by_month.values))


def _simulate(
    prices: pd.DataFrame,
    *,
    start: str,
    end: str,
    lookback: int,
    target_vol: float,
    max_extra_cash: float,
    cost_bps: float,
    rebalance: str,
) -> dict[str, Any]:
    dates = prices.loc[(prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))].index
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    baseline_daily = _base_return(returns).reindex(dates)
    trailing_vol = _base_return(returns).rolling(lookback).std(ddof=1).shift(1) * np.sqrt(252)
    rebalance_set = _rebalance_dates(dates, rebalance)
    prev_weights = dict(BASE_WEIGHTS)
    current_weights = dict(BASE_WEIGHTS)
    cost_rate = float(cost_bps) / 10000.0
    shadow_rets: list[float] = []
    turnovers: list[float] = []
    events: list[dict[str, Any]] = []
    for dt in dates:
        vol = float(trailing_vol.get(dt, np.nan))
        if dt in rebalance_set and np.isfinite(vol) and vol > 0:
            raw_scale = min(1.0, float(target_vol) / vol)
            min_scale = max(0.0, 1.0 - float(max_extra_cash) / sum(float(BASE_WEIGHTS.get(t, 0.0)) for t in TICKERS))
            scale = max(raw_scale, min_scale)
            current_weights = _scale_weights(scale)
        row_ret = returns.loc[dt]
        gross = sum(float(current_weights.get(ticker, 0.0)) * float(row_ret.get(ticker, 0.0)) for ticker in TICKERS)
        turnover = 0.0
        if dt in rebalance_set:
            turnover = 0.5 * sum(abs(float(current_weights.get(k, 0.0)) - float(prev_weights.get(k, 0.0))) for k in set(current_weights) | set(prev_weights) if k != "cash")
            prev_weights = dict(current_weights)
        shadow_rets.append(float(gross - turnover * cost_rate))
        turnovers.append(float(turnover))
        if turnover > 0:
            events.append(
                {
                    "dt": str(dt.date()),
                    "trailing_ann_vol": vol,
                    "scale": float(current_weights["0050.TW"] / BASE_WEIGHTS["0050.TW"]),
                    "extra_cash": float(current_weights["cash"] - BASE_WEIGHTS["cash"]),
                    "turnover": float(turnover),
                }
            )
    baseline_series = pd.Series(baseline_daily.values, index=dates)
    shadow_series = pd.Series(shadow_rets, index=dates)
    turnover_series = pd.Series(turnovers, index=dates)
    baseline_metrics = _metrics(baseline_series)
    shadow_metrics = _metrics(shadow_series, turnover_series)
    return {
        "baseline_metrics": baseline_metrics,
        "shadow_metrics": shadow_metrics,
        "delta_shadow_minus_baseline": _delta(shadow_metrics, baseline_metrics),
        "event_count": len(events),
        "recent_events": events[-10:],
        "total_turnover": float(turnover_series.sum()),
        "latest_trailing_ann_vol": None if trailing_vol.dropna().empty else float(trailing_vol.dropna().iloc[-1]),
        "latest_weights": current_weights,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    target_vols = _parse_floats(args.target_vols)
    max_extra_cash_values = _parse_floats(args.max_extra_cash_values)
    rows: list[dict[str, Any]] = []
    for label, start, end in WINDOWS:
        prices = _load_prices(_resolve(args.db), start, end, args.lookback + 30)
        for target_vol in target_vols:
            for max_extra_cash in max_extra_cash_values:
                sim = _simulate(
                    prices,
                    start=start,
                    end=end,
                    lookback=args.lookback,
                    target_vol=target_vol,
                    max_extra_cash=max_extra_cash,
                    cost_bps=args.cost_bps,
                    rebalance=args.rebalance,
                )
                delta = sim["delta_shadow_minus_baseline"]
                rows.append(
                    {
                        "window": label,
                        "start": start,
                        "end": end,
                        "rebalance": args.rebalance,
                        "lookback": args.lookback,
                        "target_vol": target_vol,
                        "max_extra_cash": max_extra_cash,
                        "cost_bps": args.cost_bps,
                        "event_count": sim["event_count"],
                        "delta_total_return": delta["total_return"],
                        "delta_sharpe": delta["sharpe_ratio"],
                        "delta_max_drawdown": delta["max_drawdown"],
                        "total_turnover": sim["total_turnover"],
                        "pass": bool(
                            (delta.get("total_return") or 0.0) > 0
                            and
                            (delta.get("sharpe_ratio") or 0.0) > 0
                            and (delta.get("max_drawdown") or 0.0) >= 0
                            and (delta.get("total_turnover") or 0.0) <= args.max_total_turnover_delta
                        ),
                    }
                )
    combos: list[dict[str, Any]] = []
    for target_vol in target_vols:
        for max_extra_cash in max_extra_cash_values:
            subset = [row for row in rows if row["target_vol"] == target_vol and row["max_extra_cash"] == max_extra_cash]
            combos.append(
                {
                    "target_vol": target_vol,
                    "max_extra_cash": max_extra_cash,
                    "window_count": len(subset),
                    "pass_count": sum(1 for row in subset if row["pass"]),
                    "positive_sharpe_count": sum(1 for row in subset if float(row["delta_sharpe"] or 0.0) > 0),
                    "non_worse_drawdown_count": sum(1 for row in subset if float(row["delta_max_drawdown"] or 0.0) >= 0),
                    "positive_return_count": sum(1 for row in subset if float(row["delta_total_return"] or 0.0) > 0),
                    "avg_delta_total_return": sum(float(row["delta_total_return"] or 0.0) for row in subset) / len(subset),
                    "avg_delta_sharpe": sum(float(row["delta_sharpe"] or 0.0) for row in subset) / len(subset),
                    "avg_delta_max_drawdown": sum(float(row["delta_max_drawdown"] or 0.0) for row in subset) / len(subset),
                    "avg_total_turnover": sum(float(row["total_turnover"] or 0.0) for row in subset) / len(subset),
                }
            )
    robust = [
        row
        for row in combos
        if row["pass_count"] == row["window_count"]
        and row["positive_return_count"] == row["window_count"]
        and row["positive_sharpe_count"] == row["window_count"]
        and row["non_worse_drawdown_count"] == row["window_count"]
    ]
    top = sorted(robust, key=lambda row: (row["avg_delta_sharpe"], row["avg_delta_max_drawdown"]), reverse=True)[:5]
    best_screened = sorted(
        combos,
        key=lambda row: (
            row["positive_return_count"],
            row["positive_sharpe_count"],
            row["non_worse_drawdown_count"],
            row["avg_delta_total_return"],
            row["avg_delta_sharpe"],
        ),
        reverse=True,
    )[:5]
    latest_prices = _load_prices(_resolve(args.db), "2026-09-10", "2026-09-10", args.lookback + 30)
    latest_sim = _simulate(
        latest_prices,
        start="2026-09-10",
        end="2026-09-10",
        lookback=args.lookback,
        target_vol=top[0]["target_vol"] if top else target_vols[0],
        max_extra_cash=top[0]["max_extra_cash"] if top else max_extra_cash_values[0],
        cost_bps=args.cost_bps,
        rebalance="daily",
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_vol_control_cash_scaler_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_orders_no_live_weight_change",
        "source_paper": "2609.07946",
        "base_weights": BASE_WEIGHTS,
        "inputs": {
            "db": str(_resolve(args.db)),
            "lookback": args.lookback,
            "rebalance": args.rebalance,
            "target_vols": target_vols,
            "max_extra_cash_values": max_extra_cash_values,
            "cost_bps": args.cost_bps,
            "max_total_turnover_delta": args.max_total_turnover_delta,
        },
        "combos": combos,
        "windows": rows,
        "robust_combo_count": len(robust),
        "top_robust_combos": top,
        "best_screened_combos": best_screened,
        "latest_shadow_snapshot_2026_09_10": latest_sim,
        "decision": {
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "Vol-control scaler is not promotion-ready; it must improve return, Sharpe, and drawdown across OOS windows without rebound suppression.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07946 Vol-Control Cash Scaler Shadow",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- robust_combo_count: `{report['robust_combo_count']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| target_vol | max_extra_cash | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    table_rows = report["top_robust_combos"] or report["best_screened_combos"]
    for row in table_rows:
        lines.append(
            "| {target:.1%} | {cash:.1%} | {passed}/{count} | {ret:.4%} | {sharpe:.4f} | {mdd:.4%} | {turn:.3f} |".format(
                target=row["target_vol"],
                cash=row["max_extra_cash"],
                passed=row["pass_count"],
                count=row["window_count"],
                ret=row["avg_delta_total_return"],
                sharpe=row["avg_delta_sharpe"],
                mdd=row["avg_delta_max_drawdown"],
                turn=row["avg_total_turnover"],
            )
        )
    latest = report["latest_shadow_snapshot_2026_09_10"]
    lines.extend(
        [
            "",
            "## Latest Snapshot",
            "",
            f"- latest_trailing_ann_vol: `{latest['latest_trailing_ann_vol']}`",
            f"- latest_weights: `{latest['latest_weights']}`",
            "",
            "## Decision",
            "",
            "- Keep as shadow-only candidate.",
            "- Current screen did not find a robust parameter set that improves return, Sharpe, and drawdown in every validation window.",
            "- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--lookback", type=int, default=11)
    parser.add_argument("--rebalance", choices=("daily", "monthly"), default="monthly")
    parser.add_argument("--target-vols", default="0.12,0.15,0.18,0.21,0.24,0.27,0.30")
    parser.add_argument("--max-extra-cash-values", default="0.05,0.10,0.15,0.20")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--max-total-turnover-delta", type=float, default=3.0)
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
    print(f"Vol-control shadow JSON: {output}")
    print(f"Vol-control shadow Markdown: {markdown}")


if __name__ == "__main__":
    main()
