#!/usr/bin/env python3
"""Build GroupA+ review for arXiv 2607.16450 Taiwan-exposed ETF paper.

This is a paper-to-strategy review artifact. It imports tail-risk evaluation
ideas only; it never changes live target weights or trading actions.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/cvar_tail_risk_diagnostic.json"
DEFAULT_A2118 = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_shadow.json"
DEFAULT_A2120 = PROJECT_ROOT / "report/group_a_plus/latest/a2120_small_00631l_reentry_shadow.json"
DEFAULT_GJR = PROJECT_ROOT / "report/group_a_plus/latest/gjr_post_trigger_severity_shadow.json"
DEFAULT_COST_ROBUSTNESS = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_turnover_cost_robustness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_taiwan_etf_heavy_tail_cvar_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_taiwan_etf_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _signal_data(live_signal: dict[str, Any]) -> dict[str, Any]:
    data = live_signal.get("data")
    return data if isinstance(data, dict) else live_signal


def _find_ranking(cvar: dict[str, Any], strategy: str) -> dict[str, Any]:
    ranking = cvar.get("ranking_by_starr95") or []
    return next(
        (row for row in ranking if isinstance(row, dict) and row.get("strategy") == strategy),
        {},
    )


def build_review(
    *,
    live_signal_path: Path,
    cvar_path: Path | None = DEFAULT_CVAR,
    a2118_path: Path | None = DEFAULT_A2118,
    a2120_path: Path | None = DEFAULT_A2120,
    gjr_path: Path | None = DEFAULT_GJR,
    cost_robustness_path: Path | None = DEFAULT_COST_ROBUSTNESS,
) -> dict[str, Any]:
    live_signal = _load(live_signal_path)
    cvar = _load(cvar_path)
    a2118 = _load(a2118_path)
    a2120 = _load(a2120_path)
    gjr = _load(gjr_path)
    cost_robustness = _load(cost_robustness_path)
    signal = _signal_data(live_signal)

    missing = [
        name
        for name, payload in {
            "live_signal": live_signal,
            "cvar_tail_risk_diagnostic": cvar,
            "a2118_seed_averaging_shadow": a2118,
            "a2120_small_00631l_reentry_shadow": a2120,
            "gjr_post_trigger_severity_shadow": gjr,
            "turnover_cost_robustness_2607_16450": cost_robustness,
        }.items()
        if not payload
    ]
    blockers: list[str] = []
    warnings: list[str] = []
    if missing:
        blockers.append("missing_required_inputs:" + ",".join(sorted(missing)))

    cvar_status = cvar.get("promotion_decision")
    if cvar_status != "research_only":
        warnings.append("cvar_tail_risk_promotion_state_unexpected")

    if a2118.get("decision", {}).get("production") != "promote":
        blockers.extend(a2118.get("decision", {}).get("production_blockers") or [])
    if a2120.get("status") != "active":
        blockers.extend(a2120.get("blockers") or [])
    if gjr.get("status") != "active":
        blockers.extend(gjr.get("blockers") or [])
    if cost_robustness:
        blockers.extend(
            f"turnover_cost_robustness:{item}"
            for item in (cost_robustness.get("blocking_reasons") or [])
        )
        warnings.extend(
            f"turnover_cost_robustness:{item}"
            for item in (cost_robustness.get("warning_reasons") or [])
        )

    blockers.extend(
        [
            "paper_is_not_a_live_signal",
            "cvar_optimizer_not_validated_for_groupa_plus",
        ]
    )
    if not cost_robustness:
        blockers.append("transaction_cost_and_turnover_validation_missing_for_2607_16450")

    latest_strategy_id = signal.get("strategy_id")
    latest_target_weights = signal.get("target_weights") or {}
    defensive_70_30 = _find_ranking(cvar, "defensive_0050_70_cash30")
    golden1_proxy = _find_ranking(cvar, "golden1_frozen_proxy_50_20_30")
    etf_00631l = cvar.get("00631l_only_tail_diagnostics") or {}

    candidate_imports = [
        {
            "id": "tail_sensitive_scorecard",
            "status": "ready_for_shadow_reporting",
            "action": "add_var_cvar_starr_rachev_to_latest_strategy_reviews",
            "rationale": "The paper shows Sharpe alone can disagree with STARR and Rachev rankings under heavy tails.",
            "live_weight_effect": "none",
        },
        {
            "id": "equal_weight_or_simple_diversification_benchmark",
            "status": "ready_for_shadow_reporting",
            "action": "add_hard_comparator_against_simple_0050_cash_baskets",
            "rationale": "The paper finds simple equal-weighting can remain competitive on Sharpe/STARR.",
            "live_weight_effect": "none",
        },
        {
            "id": "gjr_garch_post_trigger_severity",
            "status": gjr.get("status") or "missing",
            "action": "keep_as_post_trigger_severity_modifier_only",
            "rationale": "GJR asymmetry is useful after an existing tail/vol/drawdown trigger, not as a new trigger.",
            "current_blockers": gjr.get("blockers") or [],
            "live_weight_effect": "none",
        },
        {
            "id": "direct_cvar_optimizer",
            "status": "rejected_for_live_promotion_after_cost_sweep"
            if cost_robustness
            else "rejected_for_live_promotion",
            "action": "do_not_replace_latest_strategy",
            "rationale": "Paper CVaR allocations can become concentrated in high-vol semiconductor beta; GroupA+ needs existing live gates to prevent premature 00631L re-entry.",
            "cost_robustness_status": cost_robustness.get("status") if cost_robustness else "missing",
            "cost_robustness_blockers": cost_robustness.get("blocking_reasons") if cost_robustness else [],
            "live_weight_effect": "none",
        },
        {
            "id": "hill_tail_index",
            "status": "low_priority_diagnostic",
            "action": "use_after_var_cvar_scale_diagnostics",
            "rationale": "The paper indicates risk differences are driven more by return scale/volatility than by tail-index differences alone.",
            "live_weight_effect": "none",
        },
        {
            "id": "geopolitical_risk_cvar_conditioning",
            "status": "backlog_shadow_only",
            "action": "requires_external_risk_index_and_walk_forward_validation",
            "rationale": "The paper lists geopolitical risk conditioning as future work, not a validated trading rule.",
            "live_weight_effect": "none",
        },
    ]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_taiwan_etf_heavy_tail_cvar_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_no_target_weight_change",
        "status": "review_complete_blocked_for_live_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.16450.pdf",
            "title": "Portfolio Optimization under Heavy Tails and Asymmetric Volatility: Evidence from Taiwan-Exposed ETFs",
            "authors": [
                "Ting-Jung Lee",
                "Abootaleb Shirvani",
                "Farzana Afroz",
                "Svetlozar T. Rachev",
                "Frank J. Fabozzi",
            ],
            "date": "2026-07-21",
            "paper_scope": "30 U.S.-listed Taiwan-exposed ETFs, 2015-02 to 2025-02",
        },
        "latest_strategy_context": {
            "strategy_id": latest_strategy_id,
            "strategy_status": signal.get("strategy_status"),
            "requested_as_of_date": signal.get("requested_as_of_date"),
            "actual_data_date": signal.get("actual_data_date"),
            "execution_regime": signal.get("execution_regime"),
            "action": signal.get("action"),
            "target_weights": latest_target_weights,
            "market_state": signal.get("market_state", {}).get("state"),
            "dominant_direction": signal.get("market_state", {}).get("inputs", {}).get("dominant_direction"),
        },
        "paper_findings_mapped_to_group_a_plus": [
            "Heavy-tail and CVaR diagnostics should be added to review scorecards.",
            "GJR-GARCH asymmetry supports severity adjustment after existing triggers only.",
            "CVaR optimization should not bypass live gates because it may concentrate in semiconductor or leveraged beta.",
            "Sharpe/MDD alone is insufficient; STARR and Rachev should be monitored.",
            "Simple diversified benchmarks should remain hard comparators.",
        ],
        "candidate_imports": candidate_imports,
        "current_tail_reference": {
            "cvar_report_status": cvar.get("status"),
            "cvar_promotion_decision": cvar.get("promotion_decision"),
            "defensive_0050_70_cash30": {
                "annualized_return": defensive_70_30.get("annualized_return"),
                "max_drawdown": defensive_70_30.get("max_drawdown"),
                "expected_shortfall_loss_95": defensive_70_30.get("expected_shortfall_loss_95"),
                "starr_95": defensive_70_30.get("starr_95"),
                "rachev_95_95": defensive_70_30.get("rachev_95_95"),
            },
            "golden1_frozen_proxy_50_20_30": {
                "annualized_return": golden1_proxy.get("annualized_return"),
                "max_drawdown": golden1_proxy.get("max_drawdown"),
                "expected_shortfall_loss_95": golden1_proxy.get("expected_shortfall_loss_95"),
                "starr_95": golden1_proxy.get("starr_95"),
                "rachev_95_95": golden1_proxy.get("rachev_95_95"),
            },
            "00631l_only_tail": {
                "max_drawdown": etf_00631l.get("max_drawdown"),
                "expected_shortfall_loss_95": etf_00631l.get("expected_shortfall_loss_95"),
                "expected_shortfall_loss_99": etf_00631l.get("expected_shortfall_loss_99"),
                "hill_xi_95": (etf_00631l.get("hill_95") or {}).get("hill_xi"),
                "pot_gpd_shape_xi_95": (etf_00631l.get("pot_gpd_95") or {}).get("shape_xi"),
            },
        },
        "cost_robustness_reference": {
            "status": cost_robustness.get("status"),
            "as_of": cost_robustness.get("as_of"),
            "promote_dynamic_cvar_optimizer": (cost_robustness.get("decision") or {}).get(
                "promote_dynamic_cvar_optimizer"
            ),
            "allow_00631l_add_from_cost_sweep": (cost_robustness.get("decision") or {}).get(
                "allow_00631l_add_from_cost_sweep"
            ),
            "blocking_reasons": cost_robustness.get("blocking_reasons") or [],
            "warning_reasons": cost_robustness.get("warning_reasons") or [],
        },
        "decision": {
            "latest_strategy_remains": latest_strategy_id,
            "promote_paper_directly_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_this_paper": False,
            "add_tail_sensitive_review_layer": True,
            "keep_gjr_severity_only": True,
            "summary": "Adopt the paper as a review-layer upgrade, not as a live allocation engine.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {
            "live_signal": str(live_signal_path),
            "cvar_tail_risk_diagnostic": str(cvar_path) if cvar_path else None,
            "a2118_seed_averaging_shadow": str(a2118_path) if a2118_path else None,
            "a2120_small_00631l_reentry_shadow": str(a2120_path) if a2120_path else None,
            "gjr_post_trigger_severity_shadow": str(gjr_path) if gjr_path else None,
            "turnover_cost_robustness_2607_16450": str(cost_robustness_path) if cost_robustness_path else None,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_taiwan_etf_review_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = review.get("latest_strategy_context", {}).get("actual_data_date")
        _history_path(history_dir, as_of).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--cvar", default=str(DEFAULT_CVAR))
    parser.add_argument("--a2118", default=str(DEFAULT_A2118))
    parser.add_argument("--a2120", default=str(DEFAULT_A2120))
    parser.add_argument("--gjr", default=str(DEFAULT_GJR))
    parser.add_argument("--cost-robustness", default=str(DEFAULT_COST_ROBUSTNESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        cvar_path=_resolve(args.cvar) if args.cvar else None,
        a2118_path=_resolve(args.a2118) if args.a2118 else None,
        a2120_path=_resolve(args.a2120) if args.a2120 else None,
        gjr_path=_resolve(args.gjr) if args.gjr else None,
        cost_robustness_path=_resolve(args.cost_robustness) if args.cost_robustness else None,
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_review(review, output, history_dir)
    print(f"2607.16450 Taiwan ETF review: {output}")
    if history_dir is not None:
        as_of = review.get("latest_strategy_context", {}).get("actual_data_date")
        print(f"History snapshot: {_history_path(history_dir, as_of)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "latest_strategy_remains": review["decision"]["latest_strategy_remains"],
                "add_tail_sensitive_review_layer": review["decision"]["add_tail_sensitive_review_layer"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
