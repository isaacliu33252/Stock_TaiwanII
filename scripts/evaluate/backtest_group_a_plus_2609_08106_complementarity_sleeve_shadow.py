#!/usr/bin/env python3
"""Backtest 2609.08106 complementarity sleeve as GroupA++ shadow only."""

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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_sleeve_backtest.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_complementarity_sleeve_backtest.md"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW", "00751B.TWO", "00878.TW")
BASE_WEIGHTS = {
    "0050.TW": 0.5262536057168191,
    "00631L.TW": 0.17374639428318092,
    "00632R.TW": 0.0,
    "00679B.TWO": 0.0,
    "00713.TW": 0.12,
    "00751B.TWO": 0.0,
    "00878.TW": 0.0,
    "cash": 0.18,
}
BOND_CANDIDATES = ("00679B.TWO", "00751B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


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
        raise RuntimeError("No OHLCV rows for complementarity sleeve backtest")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.ffill(limit=3).dropna(subset=["0050.TW", "00631L.TW", "00713.TW"])


def _zscore(values: pd.Series) -> pd.Series:
    std = values.std(ddof=1)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return ((values - values.mean()) / std).fillna(0.0)


def _score_frame(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    returns = prices.pct_change(fill_method=None)
    rows: list[dict[str, Any]] = []
    for i in range(window, len(returns) + 1):
        frame = returns.iloc[i - window : i]
        dt = returns.index[i - 1]
        usable = [ticker for ticker in TICKERS if ticker in frame and frame[ticker].notna().sum() >= int(window * 0.6)]
        if "0050.TW" not in usable or "00631L.TW" not in usable:
            continue
        vols = frame[usable].std(ddof=1) * np.sqrt(252)
        mom_5 = prices[usable].pct_change(5, fill_method=None).loc[dt]
        mom_20 = prices[usable].pct_change(20, fill_method=None).loc[dt]
        drawdown_window = prices[usable].iloc[max(0, i - window) : i]
        drawdowns = drawdown_window.iloc[-1] / drawdown_window.max() - 1.0
        corr_0050 = pd.Series({ticker: frame[ticker].corr(frame["0050.TW"]) for ticker in usable}, dtype=float)
        corr_631 = pd.Series({ticker: frame[ticker].corr(frame["00631L.TW"]) for ticker in usable}, dtype=float)
        score = (
            -0.45 * _zscore(corr_0050.abs())
            -0.30 * _zscore(corr_631.abs())
            -0.15 * _zscore(vols)
            +0.05 * _zscore(mom_5)
            +0.05 * _zscore(mom_20)
        )
        best_bond = max(
            (ticker for ticker in BOND_CANDIDATES if ticker in usable),
            key=lambda ticker: float(score.get(ticker, -np.inf)),
            default=None,
        )
        rows.append(
            {
                "dt": dt,
                "score_00631l": float(score.get("00631L.TW", np.nan)),
                "score_00713": float(score.get("00713.TW", np.nan)),
                "best_bond": best_bond,
                "best_bond_score": float(score.get(best_bond, np.nan)) if best_bond else np.nan,
                "corr_00631l_0050": float(corr_0050.get("00631L.TW", np.nan)),
                "corr_00713_0050": float(corr_0050.get("00713.TW", np.nan)),
                "momentum_5d_00631l": float(mom_5.get("00631L.TW", np.nan)),
                "momentum_20d_00631l": float(mom_20.get("00631L.TW", np.nan)),
                "ann_vol_00631l": float(vols.get("00631L.TW", np.nan)),
                "drawdown_window_00631l": float(drawdowns.get("00631L.TW", np.nan)),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("dt").sort_index()


def _risk_gate_passes(
    score_row: pd.Series,
    *,
    risk_gate: str,
    momentum_5d_max: float,
    drawdown_max: float,
    ann_vol_min: float,
) -> bool:
    if risk_gate == "none":
        return True
    momentum_5d = float(score_row.get("momentum_5d_00631l", np.nan))
    drawdown = float(score_row.get("drawdown_window_00631l", np.nan))
    ann_vol = float(score_row.get("ann_vol_00631l", np.nan))
    if risk_gate == "momentum5_weak":
        return np.isfinite(momentum_5d) and momentum_5d <= momentum_5d_max
    if risk_gate == "drawdown_or_momentum5_weak":
        return (np.isfinite(momentum_5d) and momentum_5d <= momentum_5d_max) or (
            np.isfinite(drawdown) and drawdown <= drawdown_max
        )
    if risk_gate == "vol_and_momentum5_weak":
        return (
            np.isfinite(momentum_5d)
            and momentum_5d <= momentum_5d_max
            and np.isfinite(ann_vol)
            and ann_vol >= ann_vol_min
        )
    raise ValueError(f"Unknown risk gate: {risk_gate}")


def _weights_for_day(
    score_row: pd.Series,
    *,
    shift_weight: float,
    threshold: float,
    risk_gate: str,
    momentum_5d_max: float,
    drawdown_max: float,
    ann_vol_min: float,
) -> dict[str, float]:
    weights = dict(BASE_WEIGHTS)
    best_bond = score_row.get("best_bond")
    gap = float(score_row.get("best_bond_score", np.nan)) - float(score_row.get("score_00631l", np.nan))
    gate_passes = _risk_gate_passes(
        score_row,
        risk_gate=risk_gate,
        momentum_5d_max=momentum_5d_max,
        drawdown_max=drawdown_max,
        ann_vol_min=ann_vol_min,
    )
    if isinstance(best_bond, str) and np.isfinite(gap) and gap >= threshold and gate_passes and weights["00631L.TW"] > 0:
        shift = min(float(shift_weight), weights["00631L.TW"])
        weights["00631L.TW"] -= shift
        weights[best_bond] = weights.get(best_bond, 0.0) + shift
    return weights


def _simulate(
    prices: pd.DataFrame,
    scores: pd.DataFrame,
    *,
    start: str,
    end: str,
    shift_weight: float,
    threshold: float,
    cost_bps: float,
    risk_gate: str,
    momentum_5d_max: float,
    drawdown_max: float,
    ann_vol_min: float,
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
        baseline = dict(BASE_WEIGHTS)
        score_row = scores.loc[dt]
        shadow = _weights_for_day(
            score_row,
            shift_weight=shift_weight,
            threshold=threshold,
            risk_gate=risk_gate,
            momentum_5d_max=momentum_5d_max,
            drawdown_max=drawdown_max,
            ann_vol_min=ann_vol_min,
        )
        usable_returns = returns.loc[dt]
        baseline_ret = sum(float(baseline.get(ticker, 0.0)) * float(usable_returns.get(ticker, 0.0)) for ticker in TICKERS)
        shadow_gross = sum(float(shadow.get(ticker, 0.0)) * float(usable_returns.get(ticker, 0.0)) for ticker in TICKERS)
        turnover = sum(abs(float(shadow.get(k, 0.0)) - float(prev_shadow.get(k, 0.0))) for k in set(shadow) | set(prev_shadow))
        shadow_ret = shadow_gross - turnover * cost_rate
        baseline_rets.append(float(baseline_ret))
        shadow_rets.append(float(shadow_ret))
        turnovers.append(float(turnover))
        if shadow != baseline:
            bond_ret = float(usable_returns.get(scores.loc[dt].get("best_bond"), np.nan))
            levered_ret = float(usable_returns.get("00631L.TW", np.nan))
            events.append(
                {
                    "dt": str(dt.date()),
                    "best_bond": scores.loc[dt].get("best_bond"),
                    "best_bond_score": round(float(scores.loc[dt].get("best_bond_score")), 6),
                    "score_00631l": round(float(scores.loc[dt].get("score_00631l")), 6),
                    "score_gap": round(
                        float(scores.loc[dt].get("best_bond_score")) - float(scores.loc[dt].get("score_00631l")), 6
                    ),
                    "momentum_5d_00631l": round(float(scores.loc[dt].get("momentum_5d_00631l")), 6),
                    "drawdown_window_00631l": round(float(scores.loc[dt].get("drawdown_window_00631l")), 6),
                    "ann_vol_00631l": round(float(scores.loc[dt].get("ann_vol_00631l")), 6),
                    "bond_daily_return": round(bond_ret, 6) if np.isfinite(bond_ret) else None,
                    "00631l_daily_return": round(levered_ret, 6) if np.isfinite(levered_ret) else None,
                    "daily_return_pickup_before_cost": round((bond_ret - levered_ret) * float(shift_weight), 8)
                    if np.isfinite(bond_ret) and np.isfinite(levered_ret)
                    else None,
                    "shift_from_00631l": float(shift_weight),
                }
            )
        prev_shadow = shadow
    index = dates[: len(baseline_rets)]
    baseline_series = pd.Series(baseline_rets, index=index)
    shadow_series = pd.Series(shadow_rets, index=index)
    turnover_series = pd.Series(turnovers, index=index)
    return {
        "baseline_metrics": _metrics(baseline_series),
        "shadow_metrics": _metrics(shadow_series, turnover_series),
        "delta_shadow_minus_baseline": _delta(_metrics(shadow_series, turnover_series), _metrics(baseline_series)),
        "event_count": len(events),
        "recent_events": events[-10:],
        "total_turnover": float(turnover_series.sum()) if len(turnover_series) else 0.0,
    }


def _metrics(returns: pd.Series, turnover: pd.Series | None = None) -> dict[str, Any]:
    r = returns.dropna()
    if r.empty:
        return {}
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    ann_return = float(equity.iloc[-1] ** (252 / len(r)) - 1.0)
    ann_vol = float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else 0.0
    return {
        "rows": int(len(r)),
        "final_value_ratio": float(equity.iloc[-1]),
        "total_return": float(equity.iloc[-1] - 1.0),
        "annual_return": ann_return,
        "annual_volatility": ann_vol,
        "sharpe_ratio": None if ann_vol == 0 else float(ann_return / ann_vol),
        "max_drawdown": float(dd.min()),
        "mean_daily_turnover": float(turnover.mean()) if turnover is not None and len(turnover) else 0.0,
        "total_turnover": float(turnover.sum()) if turnover is not None and len(turnover) else 0.0,
    }


def _delta(shadow: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    keys = ("final_value_ratio", "total_return", "annual_return", "annual_volatility", "sharpe_ratio", "max_drawdown", "total_turnover")
    out = {}
    for key in keys:
        left = shadow.get(key)
        right = baseline.get(key)
        out[key] = None if left is None or right is None else float(left) - float(right)
    return out


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    prices = _load_prices(_resolve(args.db), args.start, args.end, args.window + 30)
    scores = _score_frame(prices, args.window)
    sim = _simulate(
        prices,
        scores,
        start=args.start,
        end=args.end,
        shift_weight=args.shift_weight,
        threshold=args.threshold,
        cost_bps=args.cost_bps,
        risk_gate=args.risk_gate,
        momentum_5d_max=args.momentum_5d_max,
        drawdown_max=args.drawdown_max,
        ann_vol_min=args.ann_vol_min,
    )
    delta = sim["delta_shadow_minus_baseline"]
    promotion_ready = bool(
        (delta.get("sharpe_ratio") or 0.0) > 0
        and (delta.get("max_drawdown") or -1.0) >= 0
        and (delta.get("total_return") or -1.0) >= 0
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_complementarity_sleeve_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "research_only",
        "policy": "shadow_only_no_orders_no_live_weight_change",
        "inputs": {
            "db": str(_resolve(args.db)),
            "start": args.start,
            "end": args.end,
            "window": int(args.window),
            "threshold": float(args.threshold),
            "shift_weight": float(args.shift_weight),
            "cost_bps": float(args.cost_bps),
            "risk_gate": args.risk_gate,
            "momentum_5d_max": float(args.momentum_5d_max),
            "drawdown_max": float(args.drawdown_max),
            "ann_vol_min": float(args.ann_vol_min),
            "base_weights": BASE_WEIGHTS,
        },
        "simulation": sim,
        "latest_scores": {} if scores.empty else scores.tail(1).reset_index().assign(dt=lambda x: x["dt"].dt.strftime("%Y-%m-%d")).to_dict(orient="records")[0],
        "decision": {
            "promotion_ready": promotion_ready,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "order_generation_allowed": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "keep_golden1_0531_unchanged": True,
            "keep_golden2_0830_unchanged": True,
            "reason": "Shadow research cannot modify lockdown Golden1_0531 or Golden2_0830; any candidate must stay outside live GroupA++ until separate governance approval.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    sim = report["simulation"]
    b = sim["baseline_metrics"]
    s = sim["shadow_metrics"]
    d = sim["delta_shadow_minus_baseline"]
    lines = [
        "# 2609.08106 Complementarity Sleeve Backtest",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- window: `{report['inputs']['start']} -> {report['inputs']['end']}`",
        f"- policy: `{report['policy']}`",
        f"- events: `{sim['event_count']}`",
        "",
        "| metric | baseline | shadow | delta |",
        "|---|---:|---:|---:|",
    ]
    for key in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown", "total_turnover"):
        lines.append(f"| {key} | {b.get(key)} | {s.get(key)} | {d.get(key)} |")
    lines.extend(
        [
            "",
            "## Latest Score",
            "",
            f"```json\n{json.dumps(report['latest_scores'], ensure_ascii=False, indent=2)}\n```",
            "",
            "## Decision",
            "",
            f"- promotion_ready: `{report['decision']['promotion_ready']}`",
            "- promote_to_live: `False`",
            "- No target-weight change and no order generation.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators; this report cannot modify or overwrite them.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-09-09")
    parser.add_argument("--window", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=1.5)
    parser.add_argument("--shift-weight", type=float, default=0.05)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument(
        "--risk-gate",
        choices=("none", "momentum5_weak", "drawdown_or_momentum5_weak", "vol_and_momentum5_weak"),
        default="none",
    )
    parser.add_argument("--momentum-5d-max", type=float, default=0.0)
    parser.add_argument("--drawdown-max", type=float, default=-0.03)
    parser.add_argument("--ann-vol-min", type=float, default=0.35)
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
    print(f"Backtest JSON: {output}")
    print(f"Backtest Markdown: {markdown}")


if __name__ == "__main__":
    main()
