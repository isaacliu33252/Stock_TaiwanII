#!/usr/bin/env python3
"""Build a 2607.16450 tail-sensitive scorecard for GroupA+ latest strategy.

The scorecard converts the paper review into daily governance checks using the
existing CVaR diagnostic snapshot. It is review-only and cannot alter weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAPER_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_taiwan_etf_heavy_tail_cvar_review.json"
DEFAULT_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/cvar_tail_risk_diagnostic.json"
DEFAULT_PROFIT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/profit_deployment_readiness.json"
DEFAULT_COST_ROBUSTNESS = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_turnover_cost_robustness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_tail_sensitive_scorecard.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_tail_sensitive_scorecard/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_by_strategy(cvar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = cvar.get("ranking_by_starr95") or []
    return {str(row.get("strategy")): row for row in rows if isinstance(row, dict) and row.get("strategy")}


def _score_row(row: dict[str, Any], best_es95: float | None) -> dict[str, Any]:
    es95 = row.get("expected_shortfall_loss_95")
    starr = row.get("starr_95")
    rachev = row.get("rachev_95_95")
    sharpe = row.get("sharpe")
    penalties: list[str] = []
    if isinstance(best_es95, (int, float)) and isinstance(es95, (int, float)) and es95 > best_es95 * 1.25:
        penalties.append("es95_more_than_25pct_above_best_reference")
    if isinstance(rachev, (int, float)) and rachev < 1.05:
        penalties.append("rachev95_below_1_05")
    if isinstance(starr, (int, float)) and starr < 10:
        penalties.append("starr95_below_10")
    score = 0.0
    if isinstance(starr, (int, float)):
        score += min(float(starr) / 20.0, 1.0) * 45.0
    if isinstance(rachev, (int, float)):
        score += min(float(rachev) / 1.25, 1.0) * 30.0
    if isinstance(sharpe, (int, float)):
        score += min(float(sharpe) / 2.5, 1.0) * 25.0
    score -= 8.0 * len(penalties)
    return {
        "strategy": row.get("strategy"),
        "score": round(max(0.0, min(score, 100.0)), 4),
        "annualized_return": row.get("annualized_return"),
        "max_drawdown": row.get("max_drawdown"),
        "expected_shortfall_loss_95": es95,
        "starr_95": starr,
        "rachev_95_95": rachev,
        "sharpe": sharpe,
        "penalties": penalties,
    }


def build_scorecard(
    *,
    paper_review_path: Path,
    cvar_path: Path,
    profit_readiness_path: Path | None = DEFAULT_PROFIT_READINESS,
    cost_robustness_path: Path | None = DEFAULT_COST_ROBUSTNESS,
) -> dict[str, Any]:
    paper_review = _load(paper_review_path)
    cvar = _load(cvar_path)
    profit = _load(profit_readiness_path)
    cost_robustness = _load(cost_robustness_path)
    rows = _rows_by_strategy(cvar)

    required_refs = [
        "defensive_0050_70_cash30",
        "golden1_frozen_proxy_50_20_30",
        "0050_only",
        "00631l_only",
    ]
    missing_refs = [name for name in required_refs if name not in rows]
    es_values = [
        float(rows[name]["expected_shortfall_loss_95"])
        for name in required_refs
        if name in rows
        and isinstance(rows[name].get("expected_shortfall_loss_95"), (int, float))
        and float(rows[name]["expected_shortfall_loss_95"]) > 0
    ]
    best_es95 = min(es_values) if es_values else None
    scored = sorted(
        (_score_row(rows[name], best_es95) for name in required_refs if name in rows),
        key=lambda row: row["score"],
        reverse=True,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if not paper_review:
        blockers.append("missing_2607_16450_paper_review")
    if not cvar:
        blockers.append("missing_cvar_tail_risk_diagnostic")
    if missing_refs:
        blockers.append("missing_required_strategy_references:" + ",".join(sorted(missing_refs)))
    if paper_review.get("decision", {}).get("target_weight_change_allowed") is not False:
        warnings.append("paper_review_target_weight_policy_unexpected")
    if cvar.get("promotion_decision") != "research_only":
        warnings.append("cvar_tail_risk_promotion_state_unexpected")
    cost_decision = cost_robustness.get("decision") if isinstance(cost_robustness.get("decision"), dict) else {}
    if cost_robustness and cost_decision.get("promote_dynamic_cvar_optimizer") is not False:
        warnings.append("cost_robustness_dynamic_cvar_policy_unexpected")

    latest_context = paper_review.get("latest_strategy_context") or {}
    active_shadow_candidates = profit.get("active_shadow_candidates") or []
    defensive = next((row for row in scored if row["strategy"] == "defensive_0050_70_cash30"), {})
    golden = next((row for row in scored if row["strategy"] == "golden1_frozen_proxy_50_20_30"), {})
    if defensive and golden:
        defensive_score = float(defensive.get("score") or 0.0)
        golden_score = float(golden.get("score") or 0.0)
        if defensive_score > golden_score:
            warnings.append("defensive_0050_70_cash30_tail_score_above_golden1_proxy")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_tail_sensitive_scorecard",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_no_target_weight_change",
        "status": "available" if not blockers else "blocked",
        "source_paper_review": str(paper_review_path),
        "latest_strategy_context": {
            "strategy_id": latest_context.get("strategy_id"),
            "strategy_status": latest_context.get("strategy_status"),
            "actual_data_date": latest_context.get("actual_data_date"),
            "execution_regime": latest_context.get("execution_regime"),
            "action": latest_context.get("action"),
            "target_weights": latest_context.get("target_weights"),
        },
        "score_method": {
            "purpose": "rank tail-sensitive review references, not live targets",
            "components": {
                "starr_95": "45pct weight, capped at STARR 20",
                "rachev_95_95": "30pct weight, capped at Rachev 1.25",
                "sharpe": "25pct weight, capped at Sharpe 2.5",
            },
            "penalties": [
                "ES95 more than 25pct above best reference",
                "Rachev95 below 1.05",
                "STARR95 below 10",
            ],
        },
        "ranked_references": scored,
        "cost_robustness": {
            "status": cost_robustness.get("status") if cost_robustness else "missing",
            "as_of": cost_robustness.get("as_of") if cost_robustness else None,
            "promote_dynamic_cvar_optimizer": cost_decision.get("promote_dynamic_cvar_optimizer"),
            "allow_00631l_add_from_cost_sweep": cost_decision.get("allow_00631l_add_from_cost_sweep"),
            "blocking_reasons": cost_robustness.get("blocking_reasons") if cost_robustness else [],
        },
        "active_shadow_candidates": active_shadow_candidates,
        "decision": {
            "scorecard_ready": not blockers,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_scorecard": False,
            "promote_dynamic_cvar_optimizer": False,
            "use_for_promotion_review": not blockers,
            "summary": "Use this scorecard to review latest and shadow candidates under tail-sensitive metrics; do not trade from it.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {
            "paper_review": str(paper_review_path),
            "cvar_tail_risk_diagnostic": str(cvar_path),
            "profit_deployment_readiness": str(profit_readiness_path) if profit_readiness_path else None,
            "turnover_cost_robustness_2607_16450": str(cost_robustness_path) if cost_robustness_path else None,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_tail_sensitive_scorecard_{stamp}.json"


def write_scorecard(scorecard: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = scorecard.get("latest_strategy_context", {}).get("actual_data_date")
        _history_path(history_dir, as_of).write_text(
            json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-review", default=str(DEFAULT_PAPER_REVIEW))
    parser.add_argument("--cvar", default=str(DEFAULT_CVAR))
    parser.add_argument("--profit-readiness", default=str(DEFAULT_PROFIT_READINESS))
    parser.add_argument("--cost-robustness", default=str(DEFAULT_COST_ROBUSTNESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    scorecard = build_scorecard(
        paper_review_path=_resolve(args.paper_review),
        cvar_path=_resolve(args.cvar),
        profit_readiness_path=_resolve(args.profit_readiness) if args.profit_readiness else None,
        cost_robustness_path=_resolve(args.cost_robustness) if args.cost_robustness else None,
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_scorecard(scorecard, output, history_dir)
    print(f"2607.16450 tail-sensitive scorecard: {output}")
    if history_dir is not None:
        as_of = scorecard.get("latest_strategy_context", {}).get("actual_data_date")
        print(f"History snapshot: {_history_path(history_dir, as_of)}")
    print(
        json.dumps(
            {
                "status": scorecard["status"],
                "top_reference": scorecard["ranked_references"][0]["strategy"] if scorecard["ranked_references"] else None,
                "target_weight_change_allowed": scorecard["decision"]["target_weight_change_allowed"],
                "allow_00631l_add_from_scorecard": scorecard["decision"]["allow_00631l_add_from_scorecard"],
                "promote_dynamic_cvar_optimizer": scorecard["decision"]["promote_dynamic_cvar_optimizer"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
