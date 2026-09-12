#!/usr/bin/env python3
"""Minimum Regime Performance (MRP) strategy-decay diagnostic (arXiv 2604.08356).

Research-only. Computes MRP1 (Alexander & Fabozzi 2026) -- the worst
realized Sharpe ratio across a single exhaustive-search split of the return
history -- for the production GroupA+ switch policy, and for the golden1 and
defensive baselines it switches between. This is a governance/monitoring
diagnostic only: it reads an existing backtest equity curve and reports a
robustness statistic. It never changes target weights, creates orders, or
triggers rebalance.

Caveat from the paper's own Appendix A: MRP1 is a biased, INCONSISTENT
estimator -- as the number of valid split points grows, MRP1 trends toward
negative infinity even for a stationary process, purely from searching over
more candidate splits. This script therefore reports MRP1 at more than one
minimum-segment-length `d` and treats agreement in ranking (not the raw
number at a single `d`) as the reliable signal, consistent with the paper's
own sensitivity-check methodology.
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CURVE_CSV = PROJECT_ROOT / "results/whatif_four_axis_switch_backtest_20260819_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_08356_mrp_strategy_decay.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_08356_mrp_strategy_decay.md"
STRATEGIES = {
    "switch_ma80_dd11_production": "switch_risk_ma80_dd11_total6_hold5_eg015_xg015",
    "golden1_0531_baseline": "golden1_0531_1m",
    "defensive_baseline": "group_a_plus_defensive_1m",
}
D_DAYS_YEARS = (1.0, 2.0)
TRADING_DAYS_PER_YEAR = 252


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _sharpe(returns: pd.Series) -> float | None:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    std = float(clean.std(ddof=1))
    if std <= 0:
        return None
    return float(clean.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def mrp1(returns: pd.Series, d_days: int) -> dict[str, Any]:
    """Eq. 1-2 of arXiv:2604.08356: MRP1(x) = min over valid splits t of
    min(Sharpe(x[0:t]), Sharpe(x[t:])), each segment at least `d_days` long.
    """
    n = len(returns)
    if n < 2 * d_days:
        return {"feasible": False, "reason": "series shorter than 2*d_days"}

    best_m: float | None = None
    best_t: int | None = None
    valid_splits = 0
    for t in range(d_days, n - d_days + 1):
        s1 = _sharpe(returns.iloc[:t])
        s2 = _sharpe(returns.iloc[t:])
        if s1 is None or s2 is None:
            continue
        valid_splits += 1
        m = min(s1, s2)
        if best_m is None or m < best_m:
            best_m = m
            best_t = t

    if best_m is None or best_t is None:
        return {"feasible": False, "reason": "no valid split produced finite Sharpe on both sides"}

    return {
        "feasible": True,
        "mrp1": float(best_m),
        "valid_splits": int(valid_splits),
        "split_index": int(best_t),
        "split_date": str(returns.index[best_t].date()),
        "left_sharpe": _sharpe(returns.iloc[:best_t]),
        "right_sharpe": _sharpe(returns.iloc[best_t:]),
    }


def build_report(*, curve_csv: Path, d_days_years: tuple[float, ...]) -> dict[str, Any]:
    curve = pd.read_csv(curve_csv)
    curve["dt"] = pd.to_datetime(curve["dt"])
    curve = curve.set_index("dt").sort_index()

    results: dict[str, Any] = {}
    for label, column in STRATEGIES.items():
        if column not in curve:
            results[label] = {"available": False, "reason": f"column {column} missing from {curve_csv}"}
            continue
        returns = curve[column].pct_change().dropna()
        full_sample_sharpe = _sharpe(returns)
        by_d: dict[str, Any] = {}
        for years in d_days_years:
            d_days = int(round(years * TRADING_DAYS_PER_YEAR))
            solved = mrp1(returns, d_days)
            if solved.get("feasible"):
                mrp_value = solved["mrp1"]
                ratio = None if full_sample_sharpe in (None, 0) else mrp_value / full_sample_sharpe
                solved["mrp_over_full_sample_sharpe"] = ratio
                solved["decay_gap_full_sample_minus_mrp"] = (
                    None if full_sample_sharpe is None else full_sample_sharpe - mrp_value
                )
            by_d[f"d_{years:g}y"] = solved
        results[label] = {
            "available": True,
            "column": column,
            "rows": int(len(returns)),
            "start": str(returns.index.min().date()),
            "end": str(returns.index.max().date()),
            "full_sample_sharpe": full_sample_sharpe,
            "mrp_by_d": by_d,
        }

    production = results.get("switch_ma80_dd11_production", {})
    d1 = (production.get("mrp_by_d") or {}).get("d_1y", {})
    d2 = (production.get("mrp_by_d") or {}).get("d_2y", {})

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_08356_mrp_strategy_decay",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2604.08356.pdf",
            "title": "Measuring Strategy-Decay Risk: Minimum Regime Performance and the Durability of Systematic Investing",
            "authors": "Nolan Alexander, Frank J. Fabozzi",
            "adapted_concepts": [
                "MRP1: worst realized Sharpe across one exhaustive-search split of the return history",
                "decay-risk frontier (full-sample Sharpe vs MRP) as a robustness screen",
                "MRP as a governance/monitoring diagnostic, recomputed periodically, not a live trading signal",
            ],
        },
        "policy": "research_only_mrp_strategy_decay_monitor_no_weight_change",
        "status": "diagnostic_available",
        "caveats": [
            "mrp1_is_a_biased_inconsistent_estimator_appendix_a",
            "do_not_trust_a_single_d_value_check_ranking_stability_across_d",
            "not_a_switch_trigger_diagnostic_only",
            "does_not_change_target_weights_or_orders",
        ],
        "as_of": str(curve.index.max().date()),
        "parameters": {
            "curve_csv": str(curve_csv),
            "d_days_years": list(d_days_years),
            "trading_days_per_year": TRADING_DAYS_PER_YEAR,
        },
        "strategies": results,
        "summary": {
            "production_full_sample_sharpe": production.get("full_sample_sharpe"),
            "production_mrp1_d1y": d1.get("mrp1") if d1.get("feasible") else None,
            "production_mrp1_d2y": d2.get("mrp1") if d2.get("feasible") else None,
            "production_mrp_over_sharpe_d1y": d1.get("mrp_over_full_sample_sharpe") if d1.get("feasible") else None,
            "production_mrp_over_sharpe_d2y": d2.get("mrp_over_full_sample_sharpe") if d2.get("feasible") else None,
            "production_worst_regime_split_date_d1y": d1.get("split_date"),
            "production_worst_regime_split_date_d2y": d2.get("split_date"),
        },
        "decision": {
            "review_complete": True,
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "promote_to_live": False,
            "recommended_use": "periodic_shadow_governance_monitor",
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2604.08356 MRP Strategy-Decay Diagnostic",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report['as_of']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "| strategy | full-sample Sharpe | MRP1 (d=1y) | MRP1 (d=2y) | MRP/Sharpe (d=2y) | worst-regime split (d=2y) |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for label, row in report["strategies"].items():
        if not row.get("available"):
            lines.append(f"| {label} | unavailable | | | | |")
            continue
        d1 = (row.get("mrp_by_d") or {}).get("d_1y", {})
        d2 = (row.get("mrp_by_d") or {}).get("d_2y", {})
        lines.append(
            "| {name} | {fs} | {m1} | {m2} | {ratio} | {split} |".format(
                name=label,
                fs=_fmt(row.get("full_sample_sharpe")),
                m1=_fmt(d1.get("mrp1")) if d1.get("feasible") else "NA",
                m2=_fmt(d2.get("mrp1")) if d2.get("feasible") else "NA",
                ratio=_fmt(d2.get("mrp_over_full_sample_sharpe")) if d2.get("feasible") else "NA",
                split=d2.get("split_date") if d2.get("feasible") else "NA",
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Diagnostic only, computed from an existing backtest equity curve.",
            "- Not a switch-decision input.",
            "- No target-weight change, no orders, no automatic rebalance.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curve-csv", default=str(DEFAULT_CURVE_CSV))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(curve_csv=Path(args.curve_csv), d_days_years=D_DAYS_YEARS)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"2604.08356 MRP strategy-decay diagnostic: {output}")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
