#!/usr/bin/env python3
"""Backtest 2609.07946 stock/bond/gold complementarity shadow for GroupA++.

Research-only. Tests whether a small weak-momentum 00631L sleeve shift to
bond/gold complements improves latest GroupA++ baseline. It never changes live
weights, Golden1_0531, Golden2_0830, signals, execution plans, or orders.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_stock_bond_gold_complementarity_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_stock_bond_gold_complementarity_shadow.md"
CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW", "00751B.TWO", "00878.TW")
BASE_WEIGHTS = {
    "0050.TW": 0.5299999999999999,
    "00631L.TW": 0.17166845262777064,
    "00632R.TW": 0.0,
    "00679B.TWO": 0.0,
    "00713.TW": 0.12,
    "00751B.TWO": 0.0,
    "00878.TW": 0.0,
    "00635U.TW": 0.0,
    "GC=F": 0.0,
    "cash": 0.17833154737222945,
}
WINDOWS = (
    ("2018", "2018-01-02", "2018-12-28"),
    ("2020_covid", "2020-01-02", "2020-12-31"),
    ("2022_rate", "2022-01-03", "2022-10-31"),
    ("2024", "2024-01-02", "2024-12-31"),
    ("2025_2026", "2025-01-02", "2026-09-10"),
)
CANDIDATE_UNIVERSES = {
    "bond_only": ("00679B.TWO", "00751B.TWO"),
    "bond_plus_gold_proxy": ("00679B.TWO", "00751B.TWO", "GC=F"),
    "bond_plus_00635u": ("00679B.TWO", "00751B.TWO", "00635U.TW"),
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _load_prices(db_path: Path, start: str, end: str, warmup_days: int) -> pd.DataFrame:
    start_ts = pd.Timestamp(start) - pd.Timedelta(days=warmup_days)
    core = [*CORE_TICKERS, "00635U.TW"]
    with duckdb.connect(str(db_path), read_only=True) as con:
        ohlcv = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [core, str(start_ts.date()), end],
        ).fetchdf()
        external = con.execute(
            """
            SELECT dt, ticker, close
            FROM external_market_ohlcv
            WHERE ticker IN ('GC=F')
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [str(start_ts.date()), end],
        ).fetchdf()
    rows = pd.concat([ohlcv, external], ignore_index=True)
    if rows.empty:
        raise RuntimeError("No OHLCV rows for stock/bond/gold complementarity shadow")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])


def _zscore(values: pd.Series) -> pd.Series:
    std = values.std(ddof=1)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return ((values - values.mean()) / std).fillna(0.0)


def _score_frame(prices: pd.DataFrame, window: int, candidates: tuple[str, ...]) -> pd.DataFrame:
    returns = prices.pct_change(fill_method=None)
    scoring_tickers = tuple(dict.fromkeys([*CORE_TICKERS, "00635U.TW", "GC=F"]))
    rows: list[dict[str, Any]] = []
    for i in range(window, len(returns) + 1):
        frame = returns.iloc[i - window : i]
        dt = returns.index[i - 1]
        usable = [ticker for ticker in scoring_tickers if ticker in frame and frame[ticker].notna().sum() >= int(window * 0.6)]
        if "0050.TW" not in usable or "00631L.TW" not in usable:
            continue
        vols = frame[usable].std(ddof=1) * np.sqrt(252)
        mom_5 = prices[usable].pct_change(5, fill_method=None).loc[dt]
        mom_20 = prices[usable].pct_change(20, fill_method=None).loc[dt]
        corr_0050 = pd.Series({ticker: frame[ticker].corr(frame["0050.TW"]) for ticker in usable}, dtype=float)
        corr_631 = pd.Series({ticker: frame[ticker].corr(frame["00631L.TW"]) for ticker in usable}, dtype=float)
        score = (
            -0.40 * _zscore(corr_0050.abs())
            -0.30 * _zscore(corr_631.abs())
            -0.15 * _zscore(vols)
            +0.10 * _zscore(mom_5)
            +0.05 * _zscore(mom_20)
        )
        available_candidates = [ticker for ticker in candidates if ticker in usable]
        best = max(available_candidates, key=lambda ticker: float(score.get(ticker, -np.inf)), default=None)
        rows.append(
            {
                "dt": dt,
                "score_00631l": float(score.get("00631L.TW", np.nan)),
                "best_complement": best,
                "best_complement_score": float(score.get(best, np.nan)) if best else np.nan,
                "best_complement_type": "gold_proxy"
                if best == "GC=F"
                else "gold_etf"
                if best == "00635U.TW"
                else "bond",
                "momentum_5d_00631l": float(mom_5.get("00631L.TW", np.nan)),
                "ann_vol_00631l": float(vols.get("00631L.TW", np.nan)),
                "corr_best_0050": float(corr_0050.get(best, np.nan)) if best else np.nan,
                "corr_best_00631l": float(corr_631.get(best, np.nan)) if best else np.nan,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("dt").sort_index()


def _weights_for_day(score_row: pd.Series, *, threshold: float, shift_weight: float, momentum_5d_max: float) -> dict[str, float]:
    weights = dict(BASE_WEIGHTS)
    best = score_row.get("best_complement")
    gap = float(score_row.get("best_complement_score", np.nan)) - float(score_row.get("score_00631l", np.nan))
    momentum_5d = float(score_row.get("momentum_5d_00631l", np.nan))
    if isinstance(best, str) and np.isfinite(gap) and gap >= threshold and np.isfinite(momentum_5d) and momentum_5d <= momentum_5d_max:
        shift = min(float(shift_weight), float(weights["00631L.TW"]))
        weights["00631L.TW"] -= shift
        weights[best] = weights.get(best, 0.0) + shift
    return weights


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
    scores: pd.DataFrame,
    *,
    start: str,
    end: str,
    threshold: float,
    shift_weight: float,
    momentum_5d_max: float,
    cost_bps: float,
) -> dict[str, Any]:
    dates = prices.loc[(prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))].index
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    baseline_rets: list[float] = []
    shadow_rets: list[float] = []
    turnovers: list[float] = []
    events: list[dict[str, Any]] = []
    prev_shadow = dict(BASE_WEIGHTS)
    cost_rate = float(cost_bps) / 10000.0
    for dt in dates:
        if dt not in scores.index:
            continue
        score_row = scores.loc[dt]
        baseline = dict(BASE_WEIGHTS)
        shadow = _weights_for_day(score_row, threshold=threshold, shift_weight=shift_weight, momentum_5d_max=momentum_5d_max)
        usable_returns = returns.loc[dt]
        baseline_ret = sum(float(baseline.get(ticker, 0.0)) * float(usable_returns.get(ticker, 0.0)) for ticker in baseline if ticker != "cash")
        shadow_gross = sum(float(shadow.get(ticker, 0.0)) * float(usable_returns.get(ticker, 0.0)) for ticker in shadow if ticker != "cash")
        turnover = sum(abs(float(shadow.get(k, 0.0)) - float(prev_shadow.get(k, 0.0))) for k in set(shadow) | set(prev_shadow))
        shadow_ret = shadow_gross - turnover * cost_rate
        baseline_rets.append(float(baseline_ret))
        shadow_rets.append(float(shadow_ret))
        turnovers.append(float(turnover))
        if shadow != baseline:
            best = score_row.get("best_complement")
            comp_ret = float(usable_returns.get(best, np.nan))
            levered_ret = float(usable_returns.get("00631L.TW", np.nan))
            events.append(
                {
                    "dt": str(dt.date()),
                    "best_complement": best,
                    "best_complement_type": score_row.get("best_complement_type"),
                    "score_gap": float(score_row["best_complement_score"] - score_row["score_00631l"]),
                    "momentum_5d_00631l": float(score_row["momentum_5d_00631l"]),
                    "complement_return": comp_ret if np.isfinite(comp_ret) else None,
                    "00631l_return": levered_ret if np.isfinite(levered_ret) else None,
                    "daily_return_pickup_before_cost": float((comp_ret - levered_ret) * shift_weight)
                    if np.isfinite(comp_ret) and np.isfinite(levered_ret)
                    else None,
                    "shift_from_00631l": float(shift_weight),
                }
            )
        prev_shadow = shadow
    index = dates[: len(baseline_rets)]
    baseline_series = pd.Series(baseline_rets, index=index)
    shadow_series = pd.Series(shadow_rets, index=index)
    turnover_series = pd.Series(turnovers, index=index)
    baseline_metrics = _metrics(baseline_series)
    shadow_metrics = _metrics(shadow_series, turnover_series)
    return {
        "baseline_metrics": baseline_metrics,
        "shadow_metrics": shadow_metrics,
        "delta_shadow_minus_baseline": _delta(shadow_metrics, baseline_metrics),
        "event_count": len(events),
        "recent_events": events[-10:],
        "event_type_counts": pd.Series([event["best_complement_type"] for event in events]).value_counts().to_dict() if events else {},
        "total_turnover": float(turnover_series.sum()) if len(turnover_series) else 0.0,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    thresholds = _parse_floats(args.thresholds)
    shifts = _parse_floats(args.shift_weights)
    rows: list[dict[str, Any]] = []
    for label, start, end in WINDOWS:
        prices = _load_prices(_resolve(args.db), start, end, args.window + 30)
        for universe_name, candidates in CANDIDATE_UNIVERSES.items():
            scores = _score_frame(prices, args.window, candidates)
            for threshold in thresholds:
                for shift_weight in shifts:
                    sim = _simulate(
                        prices,
                        scores,
                        start=start,
                        end=end,
                        threshold=threshold,
                        shift_weight=shift_weight,
                        momentum_5d_max=args.momentum_5d_max,
                        cost_bps=args.cost_bps,
                    )
                    delta = sim["delta_shadow_minus_baseline"]
                    rows.append(
                        {
                            "window": label,
                            "start": start,
                            "end": end,
                            "universe": universe_name,
                            "candidates": list(candidates),
                            "threshold": threshold,
                            "shift_weight": shift_weight,
                            "cost_bps": args.cost_bps,
                            "event_count": sim["event_count"],
                            "event_type_counts": sim["event_type_counts"],
                            "delta_total_return": delta["total_return"],
                            "delta_sharpe": delta["sharpe_ratio"],
                            "delta_max_drawdown": delta["max_drawdown"],
                            "total_turnover": sim["total_turnover"],
                            "pass": bool(
                                (delta.get("total_return") or 0.0) > 0
                                and (delta.get("sharpe_ratio") or 0.0) > 0
                                and (delta.get("max_drawdown") or 0.0) >= 0
                            ),
                        }
                    )
    combos: list[dict[str, Any]] = []
    for universe_name in CANDIDATE_UNIVERSES:
        for threshold in thresholds:
            for shift_weight in shifts:
                subset = [
                    row
                    for row in rows
                    if row["universe"] == universe_name and row["threshold"] == threshold and row["shift_weight"] == shift_weight
                ]
                combos.append(
                    {
                        "universe": universe_name,
                        "threshold": threshold,
                        "shift_weight": shift_weight,
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
    top = sorted(combos, key=lambda row: (row["pass_count"], row["positive_return_count"], row["avg_delta_total_return"], row["avg_delta_sharpe"]), reverse=True)[:8]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_stock_bond_gold_complementarity_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_orders_no_live_weight_change",
        "source_paper": "2609.07946",
        "base_weights": BASE_WEIGHTS,
        "inputs": {
            "db": str(_resolve(args.db)),
            "window": args.window,
            "thresholds": thresholds,
            "shift_weights": shifts,
            "cost_bps": args.cost_bps,
            "momentum_5d_max": args.momentum_5d_max,
            "candidate_universes": CANDIDATE_UNIVERSES,
            "gold_proxy_note": "GC=F is data-only and not a directly executable GroupA++ instrument.",
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
            "reason": "Stock/bond/gold complementarity is research-only; gold proxy/executable mapping and Taiwan OOS evidence are insufficient for live use.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07946 Stock/Bond/Gold Complementarity Shadow",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- robust_combo_count: `{report['robust_combo_count']}`",
        f"- promotion_ready: `{report['decision']['promotion_ready']}`",
        "",
        "| universe | threshold | shift | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["top_screened_combos"]:
        lines.append(
            "| {universe} | {threshold:.2f} | {shift:.2%} | {passed}/{count} | {ret:.4%} | {sharpe:.4f} | {mdd:.4%} | {turn:.3f} |".format(
                universe=row["universe"],
                threshold=row["threshold"],
                shift=row["shift_weight"],
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
            f"- {report['inputs']['gold_proxy_note']}",
            f"- {report['inputs']['00635u_note']}",
            "",
            "## Decision",
            "",
            "- Keep as shadow-only research.",
            "- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--thresholds", default="1.8,2.0,2.2")
    parser.add_argument("--shift-weights", default="0.02,0.03,0.04")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
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
    print(f"Stock/bond/gold shadow JSON: {output}")
    print(f"Stock/bond/gold shadow Markdown: {markdown}")


if __name__ == "__main__":
    main()
