#!/usr/bin/env python3
"""Build turnover/cost robustness review for the 2607.16450 GroupA+ import.

The experiment replays the existing CVaR diagnostic across transaction-cost
assumptions and checks whether dynamic CVaR allocation remains robust after
turnover costs. It is shadow-only and never changes live weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import build_report  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_turnover_cost_robustness.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_turnover_cost_robustness/history"


def _float_list(raw: str) -> list[float]:
    values = [float(item.strip()) for item in raw.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("cost list must not be empty")
    return values


def _row(report: dict[str, Any], strategy: str) -> dict[str, Any]:
    for row in report.get("ranking_by_starr95") or []:
        if isinstance(row, dict) and row.get("strategy") == strategy:
            return row
    return {}


def _dynamic_key(cost_bps: float) -> str:
    return f"dynamic_tangency_cvar_net_cost{int(cost_bps)}bps"


def _allocation_summary(report: dict[str, Any], strategy: str) -> dict[str, Any]:
    item = (report.get("strategy_summary") or {}).get(strategy) or {}
    allocations = item.get("recent_allocations") or []
    latest = allocations[-1] if allocations and isinstance(allocations[-1], dict) else {}
    weights = latest.get("weights") if isinstance(latest.get("weights"), dict) else {}
    return {
        "mean_rebalance_turnover": item.get("mean_rebalance_turnover"),
        "latest_allocation_date": latest.get("date"),
        "latest_weights": weights,
    }


def build_cost_robustness_review(
    *,
    as_of: str,
    reports_by_cost: dict[float, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if not reports_by_cost:
        blockers.append("missing_cost_sweep_reports")

    for cost_bps in sorted(reports_by_cost):
        report = reports_by_cost[cost_bps]
        dynamic_strategy = _dynamic_key(cost_bps)
        dynamic = _row(report, dynamic_strategy)
        defensive = _row(report, "defensive_0050_70_cash30")
        golden = _row(report, "golden1_frozen_proxy_50_20_30")
        alloc = _allocation_summary(report, dynamic_strategy)
        if not dynamic:
            blockers.append(f"missing_dynamic_tangency_cvar_row:{cost_bps:g}bps")
            continue
        rows.append(
            {
                "cost_bps": cost_bps,
                "dynamic_strategy": dynamic_strategy,
                "dynamic": dynamic,
                "defensive_0050_70_cash30": defensive,
                "golden1_frozen_proxy_50_20_30": golden,
                "delta_dynamic_vs_defensive": {
                    "annualized_return": (
                        None
                        if dynamic.get("annualized_return") is None or defensive.get("annualized_return") is None
                        else float(dynamic["annualized_return"]) - float(defensive["annualized_return"])
                    ),
                    "starr_95": (
                        None
                        if dynamic.get("starr_95") is None or defensive.get("starr_95") is None
                        else float(dynamic["starr_95"]) - float(defensive["starr_95"])
                    ),
                    "expected_shortfall_loss_95": (
                        None
                        if dynamic.get("expected_shortfall_loss_95") is None
                        or defensive.get("expected_shortfall_loss_95") is None
                        else float(dynamic["expected_shortfall_loss_95"]) - float(defensive["expected_shortfall_loss_95"])
                    ),
                },
                "allocation_summary": alloc,
            }
        )

    if rows:
        dynamic_starr_values = [
            float(row["dynamic"]["starr_95"])
            for row in rows
            if isinstance(row.get("dynamic", {}).get("starr_95"), (int, float))
        ]
        if dynamic_starr_values and min(dynamic_starr_values) < 10:
            warnings.append("dynamic_tangency_cvar_starr95_below_10_under_cost")
        if any(
            isinstance(row["delta_dynamic_vs_defensive"].get("starr_95"), (int, float))
            and float(row["delta_dynamic_vs_defensive"]["starr_95"]) < 0
            for row in rows
        ):
            blockers.append("dynamic_tangency_cvar_underperforms_defensive_reference_on_starr95")
        if any(
            isinstance(row["delta_dynamic_vs_defensive"].get("annualized_return"), (int, float))
            and float(row["delta_dynamic_vs_defensive"]["annualized_return"]) < 0
            for row in rows
        ):
            blockers.append("dynamic_tangency_cvar_underperforms_defensive_reference_on_return")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_turnover_cost_robustness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked_for_live_promotion" if blockers else "passed_shadow_cost_sweep",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.16450.pdf",
            "imported_concepts": [
                "cvar_optimizer_cost_robustness",
                "turnover_cost_sensitivity",
                "tail_sensitive_reference_comparison",
            ],
        },
        "cost_sweep": rows,
        "decision": {
            "promote_dynamic_cvar_optimizer": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_cost_sweep": False,
            "summary": "Cost sweep is a robustness check only; dynamic CVaR must beat defensive references after costs before any promotion discussion.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2607_16450_turnover_cost_robustness_{as_of.replace('-', '')}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(review["as_of"])).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def run_cost_sweep(
    *,
    db_path: Path,
    start: str,
    end: str,
    cost_bps_values: list[float],
    warmup_days: int,
    lookback: int,
    min_lookback: int,
    rebalance_every: int,
    grid_step: float,
    max_00631l: float,
) -> dict[float, dict[str, Any]]:
    reports: dict[float, dict[str, Any]] = {}
    for cost_bps in cost_bps_values:
        report, _, _ = build_report(
            db_path=db_path,
            start=start,
            end=end,
            warmup_days=warmup_days,
            lookback=lookback,
            min_lookback=min_lookback,
            rebalance_every=rebalance_every,
            cost_bps=float(cost_bps),
            grid_step=grid_step,
            max_00631l=max_00631l,
        )
        reports[float(cost_bps)] = report
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--cost-bps-values", type=_float_list, default=_float_list("0,5,10,20,50"))
    parser.add_argument("--warmup-days", type=int, default=900)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--min-lookback", type=int, default=126)
    parser.add_argument("--rebalance-every", type=int, default=21)
    parser.add_argument("--grid-step", type=float, default=0.05)
    parser.add_argument("--max-00631l", type=float, default=0.20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    end = _resolve_end_date(db_path, args.end)
    reports = run_cost_sweep(
        db_path=db_path,
        start=args.start,
        end=end,
        cost_bps_values=args.cost_bps_values,
        warmup_days=int(args.warmup_days),
        lookback=int(args.lookback),
        min_lookback=int(args.min_lookback),
        rebalance_every=int(args.rebalance_every),
        grid_step=float(args.grid_step),
        max_00631l=float(args.max_00631l),
    )
    review = build_cost_robustness_review(as_of=end, reports_by_cost=reports)
    output = Path(args.output)
    history_dir = None if args.no_history else Path(args.history_dir)
    write_review(review, output, history_dir)
    print(f"2607.16450 turnover/cost robustness: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, end)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "costs": [row["cost_bps"] for row in review["cost_sweep"]],
                "promote_dynamic_cvar_optimizer": review["decision"]["promote_dynamic_cvar_optimizer"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
