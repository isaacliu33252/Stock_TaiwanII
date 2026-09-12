#!/usr/bin/env python3
"""Build a 2607.15195 soft-budget / cash-accounting shadow.

This imports the paper's soft self-financing idea as a diagnostic: compare
fixed partial moves toward target holdings while charging trading cost and a
residual budget-deviation penalty. It never changes target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR,
    DEFAULT_LIVE_SNAPSHOT,
    DEFAULT_TICKERS,
    _load_adv,
    _load_json,
    _scenario,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_soft_budget_cash_accounting_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_15195_soft_budget_cash_accounting_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _weights(payload: dict[str, Any]) -> dict[str, float]:
    return {str(k): float(v or 0.0) for k, v in payload.items()}


def _blend(current: dict[str, float], target: dict[str, float], fraction: float) -> dict[str, float]:
    keys = [*DEFAULT_TICKERS, "cash"]
    target_full = {key: float(target.get(key, 0.0) or 0.0) for key in keys}
    current_full = {key: float(current.get(key, 0.0) or 0.0) for key in keys}
    return {key: current_full[key] + fraction * (target_full[key] - current_full[key]) for key in keys}


def _residual_l1_half(candidate: dict[str, float], target: dict[str, float]) -> float:
    keys = [*DEFAULT_TICKERS, "cash"]
    target_full = {key: float(target.get(key, 0.0) or 0.0) for key in keys}
    return 0.5 * sum(abs(float(candidate.get(key, 0.0) or 0.0) - target_full[key]) for key in keys)


def _cash_flow_delta(
    current: dict[str, float],
    candidate: dict[str, float],
    *,
    total_assets: float,
) -> float:
    current_cash = float(current.get("cash", 0.0) or 0.0) * total_assets
    candidate_cash = float(candidate.get("cash", 0.0) or 0.0) * total_assets
    return candidate_cash - current_cash


def _evaluate_ladder(
    *,
    name: str,
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    current_shares: dict[str, float],
    prices: dict[str, float],
    total_assets: float,
    cash_balance: float,
    adv_notional: dict[str, float],
    fractions: tuple[float, ...],
    linear_cost_bps: float,
    quadratic_impact_bps: float,
    min_trade_notional: float,
    max_turnover_for_low_cost: float,
    budget_penalty_bps_per_l1_unit: float,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for fraction in fractions:
        candidate = _blend(current_weights, target_weights, fraction)
        scenario = _scenario(
            name=f"{name}_partial_{int(round(fraction * 100))}",
            target_weights=candidate,
            current_shares=current_shares,
            current_weights=current_weights,
            prices=prices,
            total_assets=total_assets,
            cash_balance=cash_balance,
            adv_notional=adv_notional,
            linear_cost_bps=linear_cost_bps,
            quadratic_impact_bps=quadratic_impact_bps,
            min_trade_notional=min_trade_notional,
            max_turnover_for_low_cost=max_turnover_for_low_cost,
        )
        residual = _residual_l1_half(candidate, target_weights)
        penalty_bps = budget_penalty_bps_per_l1_unit * residual * residual
        cost_bps = float(scenario.get("total_estimated_cost_bps_of_assets") or 0.0)
        rows.append(
            {
                "fraction_to_target": _float(fraction),
                "candidate_weights": candidate,
                "residual_deviation_l1_half": _float(residual),
                "cash_flow_delta": _float(_cash_flow_delta(current_weights, candidate, total_assets=total_assets)),
                "turnover": scenario.get("turnover"),
                "total_trade_notional": scenario.get("total_trade_notional"),
                "total_estimated_cost_bps_of_assets": scenario.get("total_estimated_cost_bps_of_assets"),
                "soft_budget_penalty_bps": _float(penalty_bps),
                "soft_budget_objective_bps": _float(cost_bps + penalty_bps),
                "execution_cost_state": scenario.get("execution_cost_state"),
                "trade_count": scenario.get("trade_count"),
            }
        )
    best = min(rows, key=lambda row: float(row["soft_budget_objective_bps"]))
    return {
        "target_name": name,
        "target_weights": {key: float(target_weights.get(key, 0.0) or 0.0) for key in [*DEFAULT_TICKERS, "cash"]},
        "ladder": rows,
        "best_shadow_fraction": best["fraction_to_target"],
        "best_shadow_objective_bps": best["soft_budget_objective_bps"],
        "best_shadow_state": (
            "FULL_ALIGNMENT_LOW_COST"
            if float(best["fraction_to_target"] or 0.0) >= 1.0
            else "PARTIAL_ALIGNMENT_PREFERRED_BY_SOFT_BUDGET"
        ),
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
    fractions: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75, 1.0),
    linear_cost_bps: float = 5.0,
    quadratic_impact_bps: float = 25.0,
    adv_window: int = 20,
    min_trade_notional: float = 5000.0,
    max_turnover_for_low_cost: float = 0.05,
    budget_penalty_bps_per_l1_unit: float = 12.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    current_weights = _weights(portfolio.get("weights") if isinstance(portfolio.get("weights"), dict) else {})
    if "cash_weight" in portfolio:
        current_weights["cash"] = float(portfolio.get("cash_weight") or 0.0)
    current_shares = _weights(portfolio.get("shares") if isinstance(portfolio.get("shares"), dict) else {})
    prices = _weights(portfolio.get("latest_prices") if isinstance(portfolio.get("latest_prices"), dict) else {})
    total_assets = float(portfolio.get("total_assets", 0.0) or 0.0)
    cash_balance = float(portfolio.get("cash_balance", 0.0) or 0.0)
    guarded_target = _weights(live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {})
    raw_target = _weights(
        live_snapshot.get("target_weights_for_action")
        if isinstance(live_snapshot.get("target_weights_for_action"), dict)
        else {}
    )
    as_of = str(live_snapshot.get("as_of") or forward_monitor.get("as_of") or datetime.now().date())
    if not current_weights or total_assets <= 0:
        blockers.append("portfolio_state_missing")
    if not guarded_target:
        blockers.append("guarded_target_missing")
    if not raw_target:
        warnings.append("raw_a2118_target_missing")

    adv = _load_adv(_resolve(db_path), tickers=DEFAULT_TICKERS, as_of=as_of, adv_window=adv_window)
    reviews: list[dict[str, Any]] = []
    if not blockers:
        reviews.append(
            _evaluate_ladder(
                name="guarded_live_target",
                current_weights=current_weights,
                target_weights=guarded_target,
                current_shares=current_shares,
                prices=prices,
                total_assets=total_assets,
                cash_balance=cash_balance,
                adv_notional=adv,
                fractions=fractions,
                linear_cost_bps=linear_cost_bps,
                quadratic_impact_bps=quadratic_impact_bps,
                min_trade_notional=min_trade_notional,
                max_turnover_for_low_cost=max_turnover_for_low_cost,
                budget_penalty_bps_per_l1_unit=budget_penalty_bps_per_l1_unit,
            )
        )
        if raw_target:
            reviews.append(
                _evaluate_ladder(
                    name="raw_a2118_seed_ensemble_target",
                    current_weights=current_weights,
                    target_weights=raw_target,
                    current_shares=current_shares,
                    prices=prices,
                    total_assets=total_assets,
                    cash_balance=cash_balance,
                    adv_notional=adv,
                    fractions=fractions,
                    linear_cost_bps=linear_cost_bps,
                    quadratic_impact_bps=quadratic_impact_bps,
                    min_trade_notional=min_trade_notional,
                    max_turnover_for_low_cost=max_turnover_for_low_cost,
                    budget_penalty_bps_per_l1_unit=budget_penalty_bps_per_l1_unit,
                )
            )
    raw_review = next((row for row in reviews if row["target_name"] == "raw_a2118_seed_ensemble_target"), {})
    if raw_review and float(raw_review.get("best_shadow_fraction") or 0.0) < 1.0:
        warnings.append("raw_a2118_target_prefers_partial_alignment_under_soft_budget")
    guarded_review = next((row for row in reviews if row["target_name"] == "guarded_live_target"), {})
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_15195_soft_budget_cash_accounting_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.15195.pdf",
            "paper_title": "SciPhy Reinforcement Learning for Portfolio Optimization",
            "imported_concept": "soft_budget_penalty_and_explicit_cash_flow_accounting",
            "not_imported": ["oracle_signal", "pinn_hjb_optimizer", "live_soft_budget_execution"],
        },
        "parameters": {
            "fractions": list(fractions),
            "linear_cost_bps": linear_cost_bps,
            "quadratic_impact_bps": quadratic_impact_bps,
            "budget_penalty_bps_per_l1_unit": budget_penalty_bps_per_l1_unit,
            "min_trade_notional": min_trade_notional,
        },
        "current_context": {
            "portfolio_total_assets": _float(total_assets),
            "cash_balance": _float(cash_balance),
            "current_weights": current_weights,
            "market_state": live_signal.get("market_state"),
            "strategy_id": live_signal.get("strategy_id"),
        },
        "target_ladder_reviews": reviews,
        "decision": {
            "guarded_live_target_best_shadow_fraction": guarded_review.get("best_shadow_fraction"),
            "guarded_live_target_best_shadow_state": guarded_review.get("best_shadow_state"),
            "raw_a2118_best_shadow_fraction": raw_review.get("best_shadow_fraction"),
            "raw_a2118_can_override_guarded_target": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "Soft-budget ladder is diagnostic only; partial alignment suggestions cannot override A21.18 guarded targets.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2607_15195_soft_budget_cash_accounting_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--fractions", default="0,0.25,0.5,0.75,1.0")
    parser.add_argument("--linear-cost-bps", type=float, default=5.0)
    parser.add_argument("--quadratic-impact-bps", type=float, default=25.0)
    parser.add_argument("--budget-penalty-bps-per-l1-unit", type=float, default=12.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fractions = tuple(float(item.strip()) for item in args.fractions.split(",") if item.strip())
    report = build_shadow(
        db_path=_resolve(args.db_path),
        live_snapshot_path=_resolve(args.live_snapshot),
        forward_monitor_path=_resolve(args.forward_monitor),
        fractions=fractions,
        linear_cost_bps=args.linear_cost_bps,
        quadratic_impact_bps=args.quadratic_impact_bps,
        budget_penalty_bps_per_l1_unit=args.budget_penalty_bps_per_l1_unit,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
