#!/usr/bin/env python3
"""CVaR and extreme-tail diagnostic shadow for GroupA+.

Research-only implementation inspired by 2607.03082v1. It evaluates existing
GroupA+ Taiwan ETF exposures with VaR, expected shortfall, max drawdown, Hill,
and POT-GPD diagnostics. It also tests simple rolling long-only/cash CVaR grid
allocations under the existing 00631L cap. No live allocation, target weight,
or strategy manifest is changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import genpareto

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "cvar_tail_risk_diagnostic_shadow_20250102_20260716.json"


@dataclass(frozen=True)
class GridSpec:
    step: float = 0.05
    max_00631l: float = 0.20
    max_0050: float = 1.00


def _safe_rate(num: float, den: float) -> float | None:
    return None if den == 0 else float(num / den)


def _load_close_panel(db_path: Path, symbols: tuple[str, ...], start: str, end: str, warmup_days: int) -> pd.DataFrame:
    start_ts = pd.Timestamp(start).normalize() - pd.Timedelta(days=warmup_days)
    end_ts = pd.Timestamp(end).normalize()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(symbols), str(start_ts.date()), str(end_ts.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No close data for {symbols} from {start_ts.date()} to {end_ts.date()}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index().astype(float)


def _max_drawdown(returns: pd.Series) -> float | None:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return None
    wealth = (1.0 + clean).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    return float(dd.min())


def _annualized_return(returns: pd.Series) -> float | None:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return None
    wealth = float((1.0 + clean).prod())
    years = len(clean) / 252.0
    if years <= 0:
        return None
    return float(wealth ** (1.0 / years) - 1.0)


def _expected_shortfall_loss(losses: np.ndarray, confidence: float) -> float | None:
    clean = losses[np.isfinite(losses)]
    if len(clean) == 0:
        return None
    var = float(np.quantile(clean, confidence))
    tail = clean[clean >= var]
    return float(np.mean(tail)) if len(tail) else var


def _expected_tail_gain(returns: np.ndarray, confidence: float) -> float | None:
    clean = returns[np.isfinite(returns)]
    if len(clean) == 0:
        return None
    threshold = float(np.quantile(clean, confidence))
    tail = clean[clean >= threshold]
    return float(np.mean(tail)) if len(tail) else threshold


def _hill_tail_index(losses: np.ndarray, threshold_quantile: float) -> dict[str, Any]:
    clean = losses[np.isfinite(losses)]
    clean = clean[clean > 0]
    if len(clean) < 20:
        return {"threshold_quantile": threshold_quantile, "threshold": None, "exceedances": 0, "hill_xi": None}
    threshold = float(np.quantile(clean, threshold_quantile))
    exceed = clean[clean > threshold]
    if len(exceed) < 5 or threshold <= 0:
        return {
            "threshold_quantile": threshold_quantile,
            "threshold": threshold,
            "exceedances": int(len(exceed)),
            "hill_xi": None,
        }
    xi = float(np.mean(np.log(exceed / threshold)))
    return {
        "threshold_quantile": threshold_quantile,
        "threshold": threshold,
        "exceedances": int(len(exceed)),
        "hill_xi": xi,
    }


def _pot_gpd(losses: np.ndarray, threshold_quantile: float) -> dict[str, Any]:
    clean = losses[np.isfinite(losses)]
    clean = clean[clean > 0]
    if len(clean) < 40:
        return {"threshold_quantile": threshold_quantile, "threshold": None, "exceedances": 0, "shape_xi": None, "scale": None}
    threshold = float(np.quantile(clean, threshold_quantile))
    excess = clean[clean > threshold] - threshold
    if len(excess) < 8 or float(np.std(excess)) <= 1e-12:
        return {
            "threshold_quantile": threshold_quantile,
            "threshold": threshold,
            "exceedances": int(len(excess)),
            "shape_xi": None,
            "scale": None,
        }
    shape, loc, scale = genpareto.fit(excess, floc=0.0)
    return {
        "threshold_quantile": threshold_quantile,
        "threshold": threshold,
        "exceedances": int(len(excess)),
        "shape_xi": float(shape),
        "scale": float(scale),
        "loc": float(loc),
    }


def _summarize_returns(returns: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    losses = -clean.to_numpy(dtype=float)
    ann_ret = _annualized_return(clean)
    ann_vol = float(clean.std(ddof=1) * np.sqrt(252.0)) if len(clean) > 1 else None
    downside = clean[clean < 0]
    ann_downside = float(downside.std(ddof=1) * np.sqrt(252.0)) if len(downside) > 1 else None
    mdd = _max_drawdown(clean)
    var95 = float(np.quantile(losses, 0.95)) if len(losses) else None
    var99 = float(np.quantile(losses, 0.99)) if len(losses) else None
    es95 = _expected_shortfall_loss(losses, 0.95)
    es99 = _expected_shortfall_loss(losses, 0.99)
    etg95 = _expected_tail_gain(clean.to_numpy(dtype=float), 0.95)
    etg99 = _expected_tail_gain(clean.to_numpy(dtype=float), 0.99)
    return {
        "rows": int(len(clean)),
        "start": str(clean.index.min().date()) if len(clean) else None,
        "end": str(clean.index.max().date()) if len(clean) else None,
        "cumulative_return": float((1.0 + clean).prod() - 1.0) if len(clean) else None,
        "annualized_return": ann_ret,
        "annualized_volatility": ann_vol,
        "sharpe": _safe_rate(ann_ret or 0.0, ann_vol or 0.0),
        "sortino": _safe_rate(ann_ret or 0.0, ann_downside or 0.0),
        "max_drawdown": mdd,
        "calmar": _safe_rate(ann_ret or 0.0, abs(mdd or 0.0)),
        "var_loss_95": var95,
        "var_loss_99": var99,
        "expected_shortfall_loss_95": es95,
        "expected_shortfall_loss_99": es99,
        "expected_tail_gain_95": etg95,
        "expected_tail_gain_99": etg99,
        "starr_95": _safe_rate(ann_ret or 0.0, es95 or 0.0),
        "rachev_95_95": _safe_rate(etg95 or 0.0, es95 or 0.0),
        "rachev_99_99": _safe_rate(etg99 or 0.0, es99 or 0.0),
        "hill_95": _hill_tail_index(losses, 0.95),
        "hill_99": _hill_tail_index(losses, 0.99),
        "pot_gpd_95": _pot_gpd(losses, 0.95),
        "pot_gpd_99": _pot_gpd(losses, 0.99),
    }


def _portfolio_returns(asset_returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=asset_returns.index)
    for symbol, weight in weights.items():
        if symbol == "cash":
            continue
        if symbol in asset_returns:
            out = out + float(weight) * asset_returns[symbol].fillna(0.0)
    return out.rename("portfolio_return")


def _candidate_grid(spec: GridSpec) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    vals_631 = np.arange(0.0, spec.max_00631l + spec.step / 2.0, spec.step)
    vals_50 = np.arange(0.0, spec.max_0050 + spec.step / 2.0, spec.step)
    for w631 in vals_631:
        for w50 in vals_50:
            if w631 + w50 <= 1.0 + 1e-9:
                out.append({
                    "0050.TW": round(float(w50), 6),
                    "00631L.TW": round(float(w631), 6),
                    "cash": round(float(max(0.0, 1.0 - w50 - w631)), 6),
                })
    return out


def _loss_es_for_weights(train_returns: pd.DataFrame, weights: dict[str, float], confidence: float) -> float:
    r = _portfolio_returns(train_returns, weights)
    es = _expected_shortfall_loss((-r).to_numpy(dtype=float), confidence)
    return float(es if es is not None else np.inf)


def _mean_for_weights(train_returns: pd.DataFrame, weights: dict[str, float]) -> float:
    return float(_portfolio_returns(train_returns, weights).mean())


def _select_weights(train_returns: pd.DataFrame, candidates: list[dict[str, float]], objective: str, confidence: float) -> dict[str, float]:
    if objective == "min_cvar":
        return min(candidates, key=lambda w: (_loss_es_for_weights(train_returns, w, confidence), -_mean_for_weights(train_returns, w)))
    if objective == "tangency_cvar":
        def score(w: dict[str, float]) -> float:
            es = max(_loss_es_for_weights(train_returns, w, confidence), 1e-9)
            return _mean_for_weights(train_returns, w) / es
        return max(candidates, key=score)
    raise ValueError(f"Unsupported objective: {objective}")


def _run_dynamic_grid(
    asset_returns: pd.DataFrame,
    *,
    objective: str,
    confidence: float,
    lookback: int,
    min_lookback: int,
    rebalance_every: int,
    cost_bps: float,
    grid: GridSpec,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    candidates = _candidate_grid(grid)
    gross = pd.Series(index=asset_returns.index, dtype=float)
    net = pd.Series(index=asset_returns.index, dtype=float)
    records: list[dict[str, Any]] = []
    current = {"0050.TW": 0.0, "00631L.TW": 0.0, "cash": 1.0}
    next_rebalance_idx = min_lookback

    for idx in range(len(asset_returns)):
        date = asset_returns.index[idx]
        if idx >= next_rebalance_idx:
            train = asset_returns.iloc[max(0, idx - lookback):idx].dropna(how="any")
            if len(train) >= min_lookback:
                selected = _select_weights(train, candidates, objective, confidence)
                turnover = 0.5 * sum(abs(float(selected[k]) - float(current.get(k, 0.0))) for k in ("0050.TW", "00631L.TW", "cash"))
                current = selected
                records.append({
                    "date": str(date.date()),
                    "objective": objective,
                    "weights": dict(current),
                    "turnover": float(turnover),
                    "train_rows": int(len(train)),
                    "train_es_loss": _loss_es_for_weights(train, current, confidence),
                    "train_mean_daily_return": _mean_for_weights(train, current),
                })
                cost = turnover * float(cost_bps) / 10000.0
            else:
                cost = 0.0
            next_rebalance_idx = idx + rebalance_every
        else:
            cost = 0.0
        row = asset_returns.iloc[idx]
        day_return = float(current.get("0050.TW", 0.0)) * float(row.get("0050.TW", 0.0)) + float(current.get("00631L.TW", 0.0)) * float(row.get("00631L.TW", 0.0))
        gross.iloc[idx] = day_return
        net.iloc[idx] = day_return - cost
    return gross.rename(f"{objective}_gross"), net.rename(f"{objective}_net"), pd.DataFrame(records)


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    lookback: int,
    min_lookback: int,
    rebalance_every: int,
    cost_bps: float,
    grid_step: float,
    max_00631l: float,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    prices = _load_close_panel(db_path, ("0050.TW", "00631L.TW"), start, end, warmup_days)
    returns = prices.pct_change(fill_method=None).dropna(how="any")
    eval_returns = returns.loc[pd.Timestamp(start).normalize(): pd.Timestamp(end).normalize()].copy()
    fixed_weights = {
        "0050_only": {"0050.TW": 1.0, "00631L.TW": 0.0, "cash": 0.0},
        "00631l_only": {"0050.TW": 0.0, "00631L.TW": 1.0, "cash": 0.0},
        "golden1_frozen_proxy_50_20_30": {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30},
        "defensive_0050_70_cash30": {"0050.TW": 0.70, "00631L.TW": 0.0, "cash": 0.30},
    }
    strategy_returns: dict[str, pd.Series] = {}
    strategy_summary: dict[str, Any] = {}
    for name, weights in fixed_weights.items():
        r = _portfolio_returns(eval_returns, weights)
        strategy_returns[name] = r
        strategy_summary[name] = {"weights": weights, "summary": _summarize_returns(r)}

    grid = GridSpec(step=grid_step, max_00631l=max_00631l)
    dynamic_frames: list[pd.DataFrame] = []
    for objective in ("min_cvar", "tangency_cvar"):
        gross, net, allocations = _run_dynamic_grid(
            returns.loc[: pd.Timestamp(end).normalize()].dropna(how="any"),
            objective=objective,
            confidence=0.95,
            lookback=lookback,
            min_lookback=min_lookback,
            rebalance_every=rebalance_every,
            cost_bps=cost_bps,
            grid=grid,
        )
        gross = gross.loc[pd.Timestamp(start).normalize(): pd.Timestamp(end).normalize()]
        net = net.loc[pd.Timestamp(start).normalize(): pd.Timestamp(end).normalize()]
        strategy_returns[f"dynamic_{objective}_gross"] = gross
        strategy_returns[f"dynamic_{objective}_net_cost{int(cost_bps)}bps"] = net
        recent_alloc = allocations.tail(10).to_dict(orient="records") if not allocations.empty else []
        turnover = float(allocations["turnover"].mean()) if "turnover" in allocations and len(allocations) else None
        dynamic_frames.append(allocations)
        strategy_summary[f"dynamic_{objective}_gross"] = {
            "objective": objective,
            "confidence": 0.95,
            "summary": _summarize_returns(gross),
            "mean_rebalance_turnover": turnover,
            "recent_allocations": recent_alloc,
        }
        strategy_summary[f"dynamic_{objective}_net_cost{int(cost_bps)}bps"] = {
            "objective": objective,
            "confidence": 0.95,
            "transaction_cost_bps": cost_bps,
            "summary": _summarize_returns(net),
            "mean_rebalance_turnover": turnover,
            "recent_allocations": recent_alloc,
        }

    frame = pd.DataFrame(strategy_returns)
    allocation_frame = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
    ranking = sorted(
        (
            {
                "strategy": name,
                "annualized_return": item["summary"].get("annualized_return"),
                "max_drawdown": item["summary"].get("max_drawdown"),
                "expected_shortfall_loss_95": item["summary"].get("expected_shortfall_loss_95"),
                "expected_tail_gain_95": item["summary"].get("expected_tail_gain_95"),
                "sharpe": item["summary"].get("sharpe"),
                "starr_95": item["summary"].get("starr_95"),
                "rachev_95_95": item["summary"].get("rachev_95_95"),
            }
            for name, item in strategy_summary.items()
        ),
        key=lambda row: (
            row["starr_95"] if row["starr_95"] is not None else -999.0,
            row["rachev_95_95"] if row["rachev_95_95"] is not None else -999.0,
            row["sharpe"] if row["sharpe"] is not None else -999.0,
        ),
        reverse=True,
    )
    report = {
        "report_type": "cvar_tail_risk_diagnostic_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.03082v1.pdf",
            "title": "Portfolio Optimization and Tail-Risk Analytics of Actively Managed ETFs",
            "implementation_note": "Long-only/cash Taiwan ETF diagnostic proxy, not active-ETF optimizer promotion.",
        },
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": str(frame.index.min().date()) if len(frame) else start,
            "end": str(frame.index.max().date()) if len(frame) else end,
            "rows": int(len(frame)),
        },
        "parameters": {
            "symbols": ["0050.TW", "00631L.TW"],
            "lookback": lookback,
            "min_lookback": min_lookback,
            "rebalance_every": rebalance_every,
            "transaction_cost_bps": cost_bps,
            "grid_step": grid_step,
            "max_00631l": max_00631l,
            "cash_return": 0.0,
        },
        "strategy_summary": strategy_summary,
        "ranking_by_starr95": ranking,
        "promotion_decision": "research_only",
        "interpretation": (
            "CVaR and POT/Hill diagnostics are useful risk-reporting tools. "
            "Dynamic CVaR grid allocations here are research-only and do not replace GroupA+ weights."
        ),
    }
    return report, frame, allocation_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--warmup-days", type=int, default=900)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--min-lookback", type=int, default=126)
    parser.add_argument("--rebalance-every", type=int, default=21)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--grid-step", type=float, default=0.05)
    parser.add_argument("--max-00631l", type=float, default=0.20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame, allocations = build_report(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        warmup_days=int(args.warmup_days),
        lookback=int(args.lookback),
        min_lookback=int(args.min_lookback),
        rebalance_every=int(args.rebalance_every),
        cost_bps=float(args.cost_bps),
        grid_step=float(args.grid_step),
        max_00631l=float(args.max_00631l),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_returns.csv")
    allocation_output = output.with_name(output.stem + "_allocations.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    allocations.to_csv(allocation_output, index=False, encoding="utf-8-sig")
    report["returns_output"] = str(frame_output)
    report["allocations_output"] = str(allocation_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = [
        {
            "strategy": row["strategy"],
            "ann_return": row["annualized_return"],
            "mdd": row["max_drawdown"],
            "es95": row["expected_shortfall_loss_95"],
            "sharpe": row["sharpe"],
            "starr95": row["starr_95"],
        }
        for row in report["ranking_by_starr95"]
    ]
    print(f"Saved: {output}")
    print(f"Returns: {frame_output}")
    print(f"Allocations: {allocation_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
