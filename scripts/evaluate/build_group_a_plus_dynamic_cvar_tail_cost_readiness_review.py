#!/usr/bin/env python3
"""Build a research-only dynamic CVaR / tail / cost readiness review.

Inspired by arXiv 2606.26625. This reviews whether GroupA+ has enough tail-risk,
scenario, turnover, and transaction-cost governance to even consider a future
dynamic CVaR optimizer. It does not optimize weights and never changes target
weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/cvar_tail_risk_diagnostic.json"
DEFAULT_DENSITY = PROJECT_ROOT / "report/group_a_plus/latest/density_head_tail_risk_advisory.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_REBALANCE = PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review_20260720.json"
DEFAULT_SYSTEMIC_BUBBLE = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json"
DEFAULT_HMM_WJ = PROJECT_ROOT / "report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/dynamic_cvar_tail_cost_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _cvar_summary(cvar: dict[str, Any]) -> dict[str, Any]:
    diag = cvar.get("00631l_only_tail_diagnostics") or {}
    ranking = cvar.get("ranking_by_starr95") or []
    golden = next(
        (row for row in ranking if isinstance(row, dict) and row.get("strategy") == "golden1_frozen_proxy_50_20_30"),
        {},
    )
    return {
        "status": cvar.get("status"),
        "promotion_decision": cvar.get("promotion_decision"),
        "00631l_expected_shortfall_loss_95": diag.get("expected_shortfall_loss_95"),
        "00631l_expected_shortfall_loss_99": diag.get("expected_shortfall_loss_99"),
        "00631l_max_drawdown": diag.get("max_drawdown"),
        "00631l_hill_xi_95": _nested(diag, "hill_95", "hill_xi"),
        "00631l_pot_gpd_shape_xi_95": _nested(diag, "pot_gpd_95", "shape_xi"),
        "golden1_starr_95": golden.get("starr_95"),
        "golden1_expected_shortfall_loss_95": golden.get("expected_shortfall_loss_95"),
    }


def build_review(
    *,
    cvar_path: Path,
    density_path: Path,
    market_impact_path: Path,
    rebalance_path: Path,
    systemic_bubble_path: Path,
    hmm_wj_path: Path,
) -> dict[str, Any]:
    cvar = _load(cvar_path)
    density = _load(density_path)
    market_impact = _load(market_impact_path)
    rebalance = _load(rebalance_path)
    systemic = _load(systemic_bubble_path)
    hmm_wj = _load(hmm_wj_path)

    cvar_summary = _cvar_summary(cvar)
    density_best = density.get("best_heads") or {}
    market_decision = _decision(market_impact)
    rebalance_decision = _decision(rebalance)
    systemic_decision = _decision(systemic)
    hmm_decision = _decision(hmm_wj)

    blockers: list[str] = []
    warnings: list[str] = []

    missing = [
        name
        for name, payload in {
            "cvar_tail_risk_diagnostic": cvar,
            "density_head_tail_risk_advisory": density,
            "market_impact_readiness_review": market_impact,
            "rebalance_review": rebalance,
            "systemic_bubble_time_at_risk_review": systemic,
            "hmm_wj_synthetic_scenario_readiness_review": hmm_wj,
        }.items()
        if not payload
    ]
    if missing:
        blockers.append("missing_required_inputs:" + ",".join(sorted(missing)))

    if cvar.get("promotion_decision") != "research_only":
        warnings.append("cvar_tail_risk_promotion_state_unexpected")
    else:
        blockers.append("cvar_tail_risk_diagnostic_research_only")

    hill_xi = cvar_summary.get("00631l_hill_xi_95")
    pot_xi = cvar_summary.get("00631l_pot_gpd_shape_xi_95")
    if isinstance(hill_xi, (int, float)) and hill_xi > 0:
        blockers.append("00631l_hill_tail_index_positive_heavy_tail")
    if isinstance(pot_xi, (int, float)) and pot_xi > 0:
        blockers.append("00631l_pot_gpd_shape_positive_heavy_tail")

    if density.get("status") != "available":
        blockers.append("density_head_tail_risk_not_available")
    if density_best.get("recommended_research_baseline") != "gaussian_residual_head":
        warnings.append("density_head_recommended_baseline_changed")
    if density_best.get("gmm_status") == "unstable_across_windows_research_only":
        blockers.append("density_tail_model_unstable_research_only")

    if market_impact.get("status") == "blocked":
        blockers.append("market_impact_readiness_blocked")
    if market_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("market_impact_disallows_auto_rebalance")

    if rebalance_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("rebalance_review_disallows_auto_rebalance")
    if rebalance_decision.get("target_weight_change_allowed") is not True:
        blockers.append("rebalance_review_disallows_target_weight_change")

    if _nested(systemic, "states", "overall_state") == "blocked_for_leverage_add":
        blockers.append("systemic_bubble_time_at_risk_blocks_leverage_add")
    if systemic_decision.get("allow_00631l_add") is not True:
        blockers.append("systemic_bubble_disallows_00631l_add")

    if hmm_wj.get("status") == "blocked":
        blockers.append("hmm_wj_scenario_readiness_blocked")
    if hmm_decision.get("can_generate_scenarios_for_decision") is not True:
        blockers.append("scenario_generator_not_decision_ready")

    blockers.append("dynamic_cvar_optimizer_not_implemented")
    blockers.append("taiwan_etf_walkforward_validation_missing")

    as_of = (
        _nested(rebalance, "dates", "requested_as_of_date")
        or hmm_wj.get("as_of")
        or _nested(systemic, "latest", "date")
        or "2026-07-20"
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_dynamic_cvar_tail_cost_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_dynamic_cvar_tail_cost_readiness_no_optimizer_no_weight_change",
        "status": "blocked" if blockers else "research_ready",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.26625.pdf",
            "title": "Portfolio Optimization for Commodity ETFs under Heavy-Tailed Returns",
            "imported_concepts": [
                "cvar_before_return_seeking_tangency",
                "evt_hill_tail_diagnostics_after_optimization",
                "turnover_and_transaction_cost_robustness",
                "dynamic_arma_garch_student_t_copula_scenario_concept",
            ],
            "not_imported": [
                "commodity_etf_allocation",
                "arma_garch_student_t_copula_live_optimizer",
                "dynamic_tangent_portfolio_weights",
                "automatic_target_weight_change",
            ],
        },
        "component_readiness": {
            "cvar_tail_risk": cvar_summary,
            "density_head_tail_risk": {
                "status": density.get("status"),
                "recommended_research_baseline": density_best.get("recommended_research_baseline"),
                "gmm_status": density_best.get("gmm_status"),
            },
            "market_impact": {
                "status": market_impact.get("status"),
                "turnover": _nested(market_impact, "computed", "turnover"),
                "auto_rebalance_allowed": market_decision.get("auto_rebalance_allowed"),
                "allow_00631l_add": market_decision.get("allow_00631l_add"),
            },
            "rebalance": {
                "status": rebalance.get("status"),
                "auto_rebalance_allowed": rebalance_decision.get("auto_rebalance_allowed"),
                "target_weight_change_allowed": rebalance_decision.get("target_weight_change_allowed"),
                "allow_00631l_add": rebalance_decision.get("allow_00631l_add"),
            },
            "systemic_bubble": {
                "overall_state": _nested(systemic, "states", "overall_state"),
                "systemic_score": _nested(systemic, "states", "systemic_score"),
                "allow_00631l_add": systemic_decision.get("allow_00631l_add"),
            },
            "hmm_wj_scenario_readiness": {
                "status": hmm_wj.get("status"),
                "all_required_tickers_ready": _nested(hmm_wj, "data_readiness", "all_required_tickers_ready"),
                "can_generate_scenarios_for_decision": hmm_decision.get("can_generate_scenarios_for_decision"),
            },
        },
        "validation_readiness": {
            "dynamic_optimizer_implemented": False,
            "arma_garch_student_t_copula_validated": False,
            "turnover_cost_walkforward_validated": False,
            "tail_thickness_improvement_validated": False,
            "taiwan_etf_walkforward_validated": False,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Dynamic CVaR/tail/cost readiness is diagnostic only. Existing tail, turnover, "
                "scenario-readiness, and rebalance blockers prevent any optimizer-driven execution."
            ),
            "dynamic_optimizer_ready": False,
            "tail_cost_readiness_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "cvar_tail_risk": str(cvar_path),
            "density_head_tail_risk": str(density_path),
            "market_impact": str(market_impact_path),
            "rebalance": str(rebalance_path),
            "systemic_bubble": str(systemic_bubble_path),
            "hmm_wj": str(hmm_wj_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review.get("as_of")).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cvar", default=str(DEFAULT_CVAR))
    parser.add_argument("--density", default=str(DEFAULT_DENSITY))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--rebalance", default=str(DEFAULT_REBALANCE))
    parser.add_argument("--systemic-bubble", default=str(DEFAULT_SYSTEMIC_BUBBLE))
    parser.add_argument("--hmm-wj", default=str(DEFAULT_HMM_WJ))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        cvar_path=_resolve(args.cvar),
        density_path=_resolve(args.density),
        market_impact_path=_resolve(args.market_impact),
        rebalance_path=_resolve(args.rebalance),
        systemic_bubble_path=_resolve(args.systemic_bubble),
        hmm_wj_path=_resolve(args.hmm_wj),
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_review(review, output, history_dir)
    print(f"Dynamic CVaR tail/cost readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "dynamic_optimizer_ready": review["decision"]["dynamic_optimizer_ready"],
                "tail_cost_readiness_ready": review["decision"]["tail_cost_readiness_ready"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
