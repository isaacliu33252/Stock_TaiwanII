#!/usr/bin/env python3
"""Backtest 2609.07946 monthly constrained Markowitz shadow for GroupA++.

Research-only. Tests a paper-style monthly optimizer around latest GroupA++
weights with tight trust-region and cash bounds. It never changes live weights,
Golden1_0531, Golden2_0830, signals, execution plans, or orders.
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
from scipy.optimize import minimize


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_monthly_markowitz_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_monthly_markowitz_shadow.md"

TICKERS = ("0050.TW", "00631L.TW", "00713.TW", "00679B.TWO", "00751B.TWO", "00635U.TW", "cash")
RISK_TICKERS = tuple(t for t in TICKERS if t != "cash")
BASE_WEIGHTS = {
    "0050.TW": 0.5299999999999999,
    "00631L.TW": 0.17166845262777064,
    "00713.TW": 0.12,
    "00679B.TWO": 0.0,
    "00751B.TWO": 0.0,
    "00635U.TW": 0.0,
    "cash": 0.17833154737222945,
}
BOUNDS = {
    "0050.TW": (0.35, 0.65),
    "00631L.TW": (0.05, 0.22),
    "00713.TW": (0.08, 0.16),
    "00679B.TWO": (0.0, 0.08),
    "00751B.TWO": (0.0, 0.08),
    "00635U.TW": (0.0, 0.06),
    "cash": (0.10, 0.30),
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
            [list(RISK_TICKERS), str(start_ts.date()), end],
        ).fetchdf()
    if rows.empty:
        raise RuntimeError("No OHLCV rows for monthly Markowitz shadow")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    panel = panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])
    for ticker in RISK_TICKERS:
        if ticker not in panel:
            panel[ticker] = np.nan
    panel["cash"] = 1.0
    return panel[list(TICKERS)]


def _month_rebalance_dates(index: pd.DatetimeIndex, start: str, end: str) -> list[pd.Timestamp]:
    dates = pd.Series(index=index, data=index)
    dates = dates.loc[(dates.index >= pd.Timestamp(start)) & (dates.index <= pd.Timestamp(end))]
    if dates.empty:
        return []
    return [pd.Timestamp(x) for x in dates.groupby(dates.index.to_period("M")).first().tolist()]


def _expected_returns(returns: pd.DataFrame, rebalance_dt: pd.Timestamp, lookback: int, momentum_days: int) -> pd.Series:
    hist = returns.loc[:rebalance_dt].tail(lookback)
    vol = hist.std(ddof=1).replace(0.0, np.nan)
    trend = returns.add(1.0).rolling(momentum_days).apply(np.prod, raw=True).sub(1.0).loc[rebalance_dt]
    # Shrink return forecast so covariance/risk and trust region dominate.
    mu = (0.70 * trend.fillna(0.0) + 0.30 * hist.mean().fillna(0.0) * momentum_days) / momentum_days
    mu = mu.clip(lower=-0.003, upper=0.003)
    mu["cash"] = 0.0
    return mu.reindex(TICKERS).fillna(0.0) / vol.reindex(TICKERS).fillna(1.0).clip(lower=0.02)


def _optimize_day(
    returns: pd.DataFrame,
    rebalance_dt: pd.Timestamp,
    *,
    lookback: int,
    momentum_days: int,
    risk_aversion: float,
    trust_region: float,
    turnover_penalty: float,
    prev_weights: dict[str, float],
) -> dict[str, float]:
    hist = returns.loc[:rebalance_dt].tail(lookback).reindex(columns=TICKERS).fillna(0.0)
    raw_hist = returns.loc[:rebalance_dt].tail(lookback).reindex(columns=TICKERS)
    cov = hist.cov().fillna(0.0).to_numpy(dtype=float)
    mu = _expected_returns(returns, rebalance_dt, lookback, momentum_days).to_numpy(dtype=float)
    base = np.array([BASE_WEIGHTS[t] for t in TICKERS], dtype=float)
    prev = np.array([prev_weights.get(t, 0.0) for t in TICKERS], dtype=float)
    bounds = []
    for ticker in TICKERS:
        lo, hi = BOUNDS[ticker]
        if ticker != "cash" and raw_hist[ticker].notna().sum() < int(lookback * 0.6):
            lo, hi = 0.0, 0.0
        bounds.append((lo, hi))
    x0 = np.array([min(max(BASE_WEIGHTS[t], BOUNDS[t][0]), BOUNDS[t][1]) for t in TICKERS], dtype=float)
    x0 = x0 / x0.sum()

    def objective(x: np.ndarray) -> float:
        expected = float(mu @ x)
        variance = float(x @ cov @ x)
        distance = float(np.square(x - base).sum())
        turnover = float(np.square(x - prev).sum())
        trust_penalty = 10.0
        return -(expected - risk_aversion * variance - trust_penalty * distance - turnover_penalty * turnover)

    constraints = [
        {"type": "eq", "fun": lambda x: float(np.sum(x) - 1.0)},
    ]
    result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints, options={"maxiter": 80, "ftol": 1e-8})
    weights = x0 if not result.success else result.x
    weights = np.clip(weights, [b[0] for b in bounds], [b[1] for b in bounds])
    weights = weights / weights.sum()
    l1_distance = float(np.abs(weights - base).sum())
    if l1_distance > trust_region:
        weights = base + (weights - base) * (trust_region / l1_distance)
        weights = np.clip(weights, [b[0] for b in bounds], [b[1] for b in bounds])
        weights = weights / weights.sum()
    return {ticker: float(weight) for ticker, weight in zip(TICKERS, weights)}


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


def _simulate(
    prices: pd.DataFrame,
    *,
    start: str,
    end: str,
    lookback: int,
    momentum_days: int,
    risk_aversion: float,
    trust_region: float,
    turnover_penalty: float,
    cost_bps: float,
) -> dict[str, Any]:
    raw_returns = prices.pct_change(fill_method=None)
    returns = raw_returns.fillna(0.0)
    test_dates = prices.loc[(prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))].index
    rebalance_dates = set(_month_rebalance_dates(prices.index, start, end))
    prev_shadow = dict(BASE_WEIGHTS)
    current_shadow = dict(BASE_WEIGHTS)
    cost_rate = float(cost_bps) / 10000.0
    baseline_rets: list[float] = []
    shadow_rets: list[float] = []
    turnovers: list[float] = []
    rebalances: list[dict[str, Any]] = []
    for dt in test_dates:
        turnover = 0.0
        if dt in rebalance_dates:
            current_shadow = _optimize_day(
                raw_returns,
                dt,
                lookback=lookback,
                momentum_days=momentum_days,
                risk_aversion=risk_aversion,
                trust_region=trust_region,
                turnover_penalty=turnover_penalty,
                prev_weights=prev_shadow,
            )
            turnover = sum(abs(current_shadow.get(t, 0.0) - prev_shadow.get(t, 0.0)) for t in TICKERS)
            prev_shadow = dict(current_shadow)
            rebalances.append(
                {
                    "dt": str(dt.date()),
                    "turnover": float(turnover),
                    "weights": {k: round(v, 6) for k, v in current_shadow.items() if abs(v) > 1e-6},
                }
            )
        daily = returns.loc[dt]
        baseline_ret = sum(float(BASE_WEIGHTS.get(t, 0.0)) * float(daily.get(t, 0.0)) for t in TICKERS if t != "cash")
        shadow_gross = sum(float(current_shadow.get(t, 0.0)) * float(daily.get(t, 0.0)) for t in TICKERS if t != "cash")
        baseline_rets.append(float(baseline_ret))
        shadow_rets.append(float(shadow_gross - turnover * cost_rate))
        turnovers.append(float(turnover))
    idx = test_dates[: len(baseline_rets)]
    baseline_series = pd.Series(baseline_rets, index=idx)
    shadow_series = pd.Series(shadow_rets, index=idx)
    turnover_series = pd.Series(turnovers, index=idx)
    baseline_metrics = _metrics(baseline_series)
    shadow_metrics = _metrics(shadow_series, turnover_series)
    return {
        "baseline_metrics": baseline_metrics,
        "shadow_metrics": shadow_metrics,
        "delta_shadow_minus_baseline": _delta(shadow_metrics, baseline_metrics),
        "rebalance_count": len(rebalances),
        "recent_rebalances": rebalances[-6:],
        "total_turnover": float(turnover_series.sum()) if len(turnover_series) else 0.0,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    risk_aversions = _parse_floats(args.risk_aversions)
    trust_regions = _parse_floats(args.trust_regions)
    turnover_penalties = _parse_floats(args.turnover_penalties)
    rows: list[dict[str, Any]] = []
    for label, start, end in WINDOWS:
        prices = _load_prices(_resolve(args.db), start, end, args.lookback + args.momentum_days + 10)
        for risk_aversion in risk_aversions:
            for trust_region in trust_regions:
                for turnover_penalty in turnover_penalties:
                    sim = _simulate(
                        prices,
                        start=start,
                        end=end,
                        lookback=args.lookback,
                        momentum_days=args.momentum_days,
                        risk_aversion=risk_aversion,
                        trust_region=trust_region,
                        turnover_penalty=turnover_penalty,
                        cost_bps=args.cost_bps,
                    )
                    delta = sim["delta_shadow_minus_baseline"]
                    rows.append(
                        {
                            "window": label,
                            "start": start,
                            "end": end,
                            "risk_aversion": risk_aversion,
                            "trust_region": trust_region,
                            "turnover_penalty": turnover_penalty,
                            "cost_bps": args.cost_bps,
                            "rebalance_count": sim["rebalance_count"],
                            "delta_total_return": delta["total_return"],
                            "delta_sharpe": delta["sharpe_ratio"],
                            "delta_max_drawdown": delta["max_drawdown"],
                            "total_turnover": sim["total_turnover"],
                            "recent_rebalances": sim["recent_rebalances"],
                            "pass": bool(
                                (delta.get("total_return") or 0.0) > 0
                                and (delta.get("sharpe_ratio") or 0.0) > 0
                                and (delta.get("max_drawdown") or 0.0) >= 0
                            ),
                        }
                    )
    combos: list[dict[str, Any]] = []
    for risk_aversion in risk_aversions:
        for trust_region in trust_regions:
            for turnover_penalty in turnover_penalties:
                subset = [
                    row
                    for row in rows
                    if row["risk_aversion"] == risk_aversion
                    and row["trust_region"] == trust_region
                    and row["turnover_penalty"] == turnover_penalty
                ]
                combos.append(
                    {
                        "risk_aversion": risk_aversion,
                        "trust_region": trust_region,
                        "turnover_penalty": turnover_penalty,
                        "window_count": len(subset),
                        "pass_count": sum(1 for row in subset if row["pass"]),
                        "positive_return_count": sum(1 for row in subset if float(row["delta_total_return"] or 0.0) > 0),
                        "positive_sharpe_count": sum(1 for row in subset if float(row["delta_sharpe"] or 0.0) > 0),
                        "non_worse_drawdown_count": sum(1 for row in subset if float(row["delta_max_drawdown"] or 0.0) >= 0),
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
    top = sorted(combos, key=lambda row: (row["pass_count"], row["positive_return_count"], row["avg_delta_total_return"]), reverse=True)[:8]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_monthly_markowitz_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_orders_no_live_weight_change",
        "source_paper": "2609.07946",
        "base_weights": BASE_WEIGHTS,
        "inputs": {
            "db": str(_resolve(args.db)),
            "tickers": TICKERS,
            "bounds": BOUNDS,
            "lookback": args.lookback,
            "momentum_days": args.momentum_days,
            "risk_aversions": risk_aversions,
            "trust_regions": trust_regions,
            "turnover_penalties": turnover_penalties,
            "cost_bps": args.cost_bps,
            "00635u_note": "00635U.TW is a Taiwan gold-futures ETF in DB but not in current GroupA++ tradable core/watchlist.",
        },
        "combos": combos,
        "windows": rows,
        "robust_combo_count": len(robust),
        "top_screened_combos": top,
        "decision": {
            "promotion_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "Monthly constrained Markowitz is research-only; current evidence must pass robustness and forward shadow before any live proposal.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07946 Monthly Markowitz Shadow",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- robust_combo_count: `{report['robust_combo_count']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| risk_aversion | trust_region | turnover_penalty | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["top_screened_combos"]:
        lines.append(
            "| {risk:.2f} | {trust:.2f} | {pen:.4f} | {passed}/{count} | {ret:.4%} | {sharpe:.4f} | {mdd:.4%} | {turn:.3f} |".format(
                risk=row["risk_aversion"],
                trust=row["trust_region"],
                pen=row["turnover_penalty"],
                passed=row["pass_count"],
                count=row["window_count"],
                ret=row["avg_delta_total_return"],
                sharpe=row["avg_delta_sharpe"],
                mdd=row["avg_delta_max_drawdown"],
                turn=row["avg_total_turnover"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            f"- {report['inputs']['00635u_note']}",
            "- Monthly optimizer is bounded around latest GroupA++ baseline and remains shadow-only.",
            "",
            "## Decision",
            "",
            "- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--lookback", type=int, default=42)
    parser.add_argument("--momentum-days", type=int, default=21)
    parser.add_argument("--risk-aversions", default="0.5,1.0,2.0,4.0")
    parser.add_argument("--trust-regions", default="0.06,0.10,0.14")
    parser.add_argument("--turnover-penalties", default="0.0000,0.0005,0.0010")
    parser.add_argument("--cost-bps", type=float, default=10.0)
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
    print(f"Monthly Markowitz shadow JSON: {output}")
    print(f"Monthly Markowitz shadow Markdown: {markdown}")
    print(
        "Top combo:",
        json.dumps(report["top_screened_combos"][0] if report["top_screened_combos"] else {}, ensure_ascii=False),
    )


if __name__ == "__main__":
    main()
