#!/usr/bin/env python3
"""In-sample CVaR-optimizer upper bound vs GroupA+ latest strategy (2606.26625).

Research-only diagnostic to answer one question: if a fully-fitted, in-sample
mean-CVaR optimizer (Rockafellar-Uryasev LP) had picked the best possible
static weights for each historical stress window, how much lower could ES95
and max drawdown have been compared to the actual latest strategy weights, at
the same or better achieved return?

This is an UPPER BOUND, not a deployable result:

- weights are fit with full knowledge of the window's own realized returns
  (in-sample / look-ahead by construction), so real-time performance would be
  worse than what is reported here;
- it does not walk-forward validate, does not account for transaction costs,
  and does not implement a live optimizer;
- it never changes target weights, creates orders, or triggers rebalance.

The only purpose is to size the headroom before deciding whether building a
real (walk-forward, cost-aware) CVaR optimizer is worth the engineering cost.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import (
    _load_close_panel,
    _portfolio_returns,
    _summarize_returns,
)

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_cvar_optimizer_upper_bound.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_cvar_optimizer_upper_bound.md"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
ALPHA = 0.95
WINDOWS = {
    "covid_2020": ("2020-02-03", "2020-06-30"),
    "rate_hike_2022": ("2022-01-03", "2022-12-30"),
    "post_2023": ("2023-01-03", None),
    "recent_2024_2026": ("2024-01-02", None),
    "active_2025_2026": ("2025-01-02", None),
}


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _load_latest_weights(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    weights = {str(k): float(v) for k, v in dict(data.get("target_weights") or {}).items()}
    for ticker in TICKERS:
        weights.setdefault(ticker, 0.0)
    weights["cash"] = float(weights.get("cash", max(0.0, 1.0 - sum(weights[t] for t in TICKERS))))
    total = sum(max(0.0, weights[k]) for k in (*TICKERS, "cash"))
    if total <= 0:
        raise ValueError("live signal target weights must have positive total")
    return {k: max(0.0, weights[k]) / total for k in (*TICKERS, "cash")}


def solve_min_cvar_weights(
    scenario_returns: np.ndarray,
    *,
    alpha: float,
    min_mean_return: float,
) -> dict[str, Any]:
    """Rockafellar-Uryasev mean-CVaR LP: minimize CVaR subject to a return floor.

    scenario_returns: (n_scenarios, n_assets) matrix of realized daily returns
    (cash column is all zeros). Long-only, fully invested, no leverage.
    """
    n_scenarios, n_assets = scenario_returns.shape
    n_vars = n_assets + 1 + n_scenarios  # weights, eta (VaR), z (CVaR slacks)

    c = np.zeros(n_vars)
    c[n_assets] = 1.0
    c[n_assets + 1 :] = 1.0 / (n_scenarios * (1.0 - alpha))

    # z_i >= -(r_i . w) - eta  ->  -r_i.w - eta - z_i <= 0
    a_ub_tail = np.zeros((n_scenarios, n_vars))
    a_ub_tail[:, :n_assets] = -scenario_returns
    a_ub_tail[:, n_assets] = -1.0
    a_ub_tail[np.arange(n_scenarios), n_assets + 1 + np.arange(n_scenarios)] = -1.0
    b_ub_tail = np.zeros(n_scenarios)

    # mean(r.w) >= min_mean_return  ->  -mean(r).w <= -min_mean_return
    mean_returns = scenario_returns.mean(axis=0)
    a_ub_return = np.zeros((1, n_vars))
    a_ub_return[0, :n_assets] = -mean_returns
    b_ub_return = np.array([-float(min_mean_return)])

    a_ub = np.vstack([a_ub_tail, a_ub_return])
    b_ub = np.concatenate([b_ub_tail, b_ub_return])

    a_eq = np.zeros((1, n_vars))
    a_eq[0, :n_assets] = 1.0
    b_eq = np.array([1.0])

    bounds = [(0.0, 1.0)] * n_assets + [(None, None)] + [(0.0, None)] * n_scenarios

    result = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not result.success:
        return {"feasible": False, "message": str(result.message)}

    weights = np.clip(result.x[:n_assets], 0.0, 1.0)
    weights = weights / weights.sum() if weights.sum() > 0 else weights
    return {
        "feasible": True,
        "weights": weights,
        "cvar_95_objective": float(result.fun),
    }


def build_report(
    *,
    db_path: Path,
    live_signal_path: Path,
    end: str,
) -> dict[str, Any]:
    latest_weights = _load_latest_weights(live_signal_path)
    start = min(w[0] for w in WINDOWS.values())
    panel = _load_close_panel(db_path, TICKERS, start, end, warmup_days=10).ffill()
    asset_returns = panel.pct_change().dropna(how="all")

    window_rows: list[dict[str, Any]] = []
    valid_windows = 0
    optimizer_beats_latest_es95 = 0
    optimizer_beats_latest_mdd = 0
    es95_gaps: list[float] = []
    mdd_gaps: list[float] = []

    for name, (window_start, raw_end) in WINDOWS.items():
        window_end = raw_end or end
        subset = asset_returns.loc[
            (asset_returns.index >= pd.Timestamp(window_start)) & (asset_returns.index <= pd.Timestamp(window_end))
        ]
        if subset.empty or len(subset) < 20:
            continue
        valid_windows += 1

        latest_returns = _portfolio_returns(subset, latest_weights)
        latest_summary = _summarize_returns(latest_returns)
        latest_mean = float(latest_returns.mean())

        scenario_matrix = subset[list(TICKERS)].fillna(0.0).to_numpy(dtype=float)
        solved = solve_min_cvar_weights(scenario_matrix, alpha=ALPHA, min_mean_return=latest_mean)

        row: dict[str, Any] = {
            "window": name,
            "start": str(subset.index.min().date()),
            "end": str(subset.index.max().date()),
            "rows": int(len(subset)),
            "latest_strategy": latest_summary,
            "latest_mean_daily_return": latest_mean,
            "optimizer_feasible": solved["feasible"],
        }

        if solved["feasible"]:
            opt_weights = {ticker: float(w) for ticker, w in zip(TICKERS, solved["weights"])}
            opt_weights["cash"] = float(max(0.0, 1.0 - sum(opt_weights.values())))
            opt_returns = _portfolio_returns(subset, opt_weights)
            opt_summary = _summarize_returns(opt_returns)

            latest_es95 = _finite(latest_summary.get("expected_shortfall_loss_95"))
            opt_es95 = _finite(opt_summary.get("expected_shortfall_loss_95"))
            latest_mdd = _finite(latest_summary.get("max_drawdown"))
            opt_mdd = _finite(opt_summary.get("max_drawdown"))

            es95_gap = None if latest_es95 is None or opt_es95 is None else latest_es95 - opt_es95
            mdd_gap = None if latest_mdd is None or opt_mdd is None else opt_mdd - latest_mdd

            if es95_gap is not None:
                es95_gaps.append(es95_gap)
                optimizer_beats_latest_es95 += int(es95_gap > 0)
            if mdd_gap is not None:
                mdd_gaps.append(mdd_gap)
                optimizer_beats_latest_mdd += int(mdd_gap > 0)

            row.update(
                {
                    "optimizer_weights": opt_weights,
                    "optimizer_strategy": opt_summary,
                    "es95_gap_latest_minus_optimizer": es95_gap,
                    "mdd_gap_optimizer_minus_latest": mdd_gap,
                }
            )
        else:
            row["optimizer_message"] = solved.get("message")

        window_rows.append(row)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_26625_cvar_optimizer_upper_bound",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.26625.pdf",
            "title": "Portfolio Optimization for Commodity ETFs under Heavy-Tailed Returns",
            "adapted_concepts": ["Rockafellar-Uryasev mean-CVaR LP as an in-sample upper-bound diagnostic"],
        },
        "policy": "research_only_in_sample_upper_bound_not_a_live_optimizer",
        "status": "diagnostic_only",
        "caveats": [
            "in_sample_look_ahead_weights_not_walk_forward",
            "no_transaction_cost_accounted",
            "not_a_deployable_optimizer",
            "does_not_change_target_weights_or_orders",
        ],
        "as_of": end,
        "parameters": {
            "end": end,
            "alpha": ALPHA,
            "live_signal_path": str(live_signal_path),
            "latest_weights": latest_weights,
        },
        "summary": {
            "valid_windows": valid_windows,
            "optimizer_beats_latest_es95_windows": optimizer_beats_latest_es95,
            "optimizer_beats_latest_mdd_windows": optimizer_beats_latest_mdd,
            "mean_es95_gap_latest_minus_optimizer": float(np.mean(es95_gaps)) if es95_gaps else None,
            "mean_mdd_gap_optimizer_minus_latest": float(np.mean(mdd_gaps)) if mdd_gaps else None,
        },
        "windows": window_rows,
        "decision": {
            "review_complete": True,
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "dynamic_optimizer_ready": False,
            "promote_to_live": False,
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2606.26625 CVaR-Optimizer Upper Bound (In-Sample, Diagnostic Only)",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report['as_of']}`",
        f"- Valid windows: `{report['summary']['valid_windows']}`",
        f"- Optimizer beats latest on ES95 in: `{report['summary']['optimizer_beats_latest_es95_windows']}` windows",
        f"- Optimizer beats latest on MDD in: `{report['summary']['optimizer_beats_latest_mdd_windows']}` windows",
        f"- Mean ES95 gap (latest - optimizer): `{_fmt(report['summary']['mean_es95_gap_latest_minus_optimizer'])}`",
        f"- Mean MDD gap (optimizer - latest): `{_fmt(report['summary']['mean_mdd_gap_optimizer_minus_latest'])}`",
        "",
        "| window | latest ES95 | optimizer ES95 | ES95 gap | latest MDD | optimizer MDD | MDD gap |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["windows"]:
        if not row.get("optimizer_feasible"):
            lines.append(f"| {row['window']} | infeasible | | | | | |")
            continue
        lines.append(
            "| {w} | {le} | {oe} | {ge} | {lm} | {om} | {gm} |".format(
                w=row["window"],
                le=_fmt(row["latest_strategy"].get("expected_shortfall_loss_95")),
                oe=_fmt(row["optimizer_strategy"].get("expected_shortfall_loss_95")),
                ge=_fmt(row.get("es95_gap_latest_minus_optimizer")),
                lm=_fmt(row["latest_strategy"].get("max_drawdown")),
                om=_fmt(row["optimizer_strategy"].get("max_drawdown")),
                gm=_fmt(row.get("mdd_gap_optimizer_minus_latest")),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Diagnostic only: in-sample look-ahead upper bound, not walk-forward.",
            "- Does not account for transaction costs.",
            "- Not a live optimizer; no target-weight change, no orders, no rebalance.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(db_path=Path(args.db), live_signal_path=Path(args.live_signal), end=args.end)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"2606.26625 CVaR optimizer upper bound: {output}")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
