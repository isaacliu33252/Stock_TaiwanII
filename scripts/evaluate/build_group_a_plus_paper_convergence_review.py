#!/usr/bin/env python3
"""Build GroupA+ cross-paper convergence review.

The report ranks paper-derived candidate uses by current evidence and blockers.
It is review-only and cannot change live targets or orders.
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

from group_a_plus.integrations.paper_convergence_review import load_inputs_and_build  # noqa: E402


DEFAULT_SIGNED_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json"
DEFAULT_SIGNED_APPROVAL_VALIDATION = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json"
DEFAULT_GUARDED_CANDIDATE = PROJECT_ROOT / "report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json"
DEFAULT_LIQUIDITY_FEEDBACK = PROJECT_ROOT / "report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json"
DEFAULT_TRACKING_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_MOIRA_VALIDATION = PROJECT_ROOT / "report/group_a_plus/latest/moira_policy_critic_validation_shadow.json"
DEFAULT_MOIRA_BACKTEST = PROJECT_ROOT / "report/group_a_plus/latest/moira_execution_guard_hard_stop_backtest_shadow.json"
DEFAULT_EVENT_QUALITY = PROJECT_ROOT / "report/group_a_plus/latest/event_aware_execution_quality_shadow.json"
DEFAULT_CVAR_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_CVAR_COST_WINDOW_SPLIT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json"
DEFAULT_TAIL_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json"
DEFAULT_RE_EVALUATION_GATE = PROJECT_ROOT / "report/group_a_plus/latest/current_policy_re_evaluation_gate.json"
DEFAULT_AUXILIARY_TASK_READINESS = (
    PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json"
)
DEFAULT_2609_07946_ADOPTION = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_adoption_matrix.json"
DEFAULT_2609_07946_PROMOTION_GATE = (
    PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_complementarity_promotion_gate.json"
)
DEFAULT_00635U_INSTRUMENT_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/00635u_instrument_review.json"
DEFAULT_2609_08106_ADOPTION = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_adoption_matrix.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/paper_convergence_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/paper_convergence_review/history"


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"paper_convergence_review_{as_of.replace('-', '')}.json"


def build_report(
    *,
    as_of: str,
    signed_review_path: Path | None = DEFAULT_SIGNED_REVIEW,
    signed_approval_validation_path: Path | None = DEFAULT_SIGNED_APPROVAL_VALIDATION,
    guarded_candidate_path: Path | None = DEFAULT_GUARDED_CANDIDATE,
    liquidity_feedback_path: Path | None = DEFAULT_LIQUIDITY_FEEDBACK,
    tracking_review_path: Path | None = DEFAULT_TRACKING_REVIEW,
    market_impact_path: Path | None = DEFAULT_MARKET_IMPACT,
    moira_validation_path: Path | None = DEFAULT_MOIRA_VALIDATION,
    moira_backtest_path: Path | None = DEFAULT_MOIRA_BACKTEST,
    event_quality_path: Path | None = DEFAULT_EVENT_QUALITY,
    cvar_review_path: Path | None = DEFAULT_CVAR_REVIEW,
    cvar_cost_window_split_path: Path | None = DEFAULT_CVAR_COST_WINDOW_SPLIT,
    tail_review_path: Path | None = DEFAULT_TAIL_REVIEW,
    re_evaluation_gate_path: Path | None = DEFAULT_RE_EVALUATION_GATE,
    auxiliary_task_readiness_path: Path | None = DEFAULT_AUXILIARY_TASK_READINESS,
    adoption_2609_07946_path: Path | None = DEFAULT_2609_07946_ADOPTION,
    promotion_gate_2609_07946_path: Path | None = DEFAULT_2609_07946_PROMOTION_GATE,
    instrument_review_00635u_path: Path | None = DEFAULT_00635U_INSTRUMENT_REVIEW,
    adoption_2609_08106_path: Path | None = DEFAULT_2609_08106_ADOPTION,
) -> dict[str, Any]:
    report = load_inputs_and_build(
        as_of=as_of,
        signed_review_path=signed_review_path,
        signed_approval_validation_path=signed_approval_validation_path,
        guarded_candidate_path=guarded_candidate_path,
        liquidity_feedback_path=liquidity_feedback_path,
        tracking_review_path=tracking_review_path,
        market_impact_path=market_impact_path,
        moira_validation_path=moira_validation_path,
        moira_backtest_path=moira_backtest_path,
        event_quality_path=event_quality_path,
        cvar_review_path=cvar_review_path,
        cvar_cost_window_split_path=cvar_cost_window_split_path,
        tail_review_path=tail_review_path,
        re_evaluation_gate_path=re_evaluation_gate_path,
        auxiliary_task_readiness_path=auxiliary_task_readiness_path,
        adoption_2609_07946_path=adoption_2609_07946_path,
        promotion_gate_2609_07946_path=promotion_gate_2609_07946_path,
        instrument_review_00635u_path=instrument_review_00635u_path,
        adoption_2609_08106_path=adoption_2609_08106_path,
    )
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    report["sources"] = {
        "signed_review": str(signed_review_path) if signed_review_path else None,
        "signed_approval_validation": str(signed_approval_validation_path) if signed_approval_validation_path else None,
        "guarded_candidate": str(guarded_candidate_path) if guarded_candidate_path else None,
        "liquidity_feedback": str(liquidity_feedback_path) if liquidity_feedback_path else None,
        "tracking_review": str(tracking_review_path) if tracking_review_path else None,
        "market_impact": str(market_impact_path) if market_impact_path else None,
        "moira_validation": str(moira_validation_path) if moira_validation_path else None,
        "moira_backtest": str(moira_backtest_path) if moira_backtest_path else None,
        "event_quality": str(event_quality_path) if event_quality_path else None,
        "cvar_review": str(cvar_review_path) if cvar_review_path else None,
        "cvar_cost_window_split": str(cvar_cost_window_split_path) if cvar_cost_window_split_path else None,
        "tail_review": str(tail_review_path) if tail_review_path else None,
        "re_evaluation_gate": str(re_evaluation_gate_path) if re_evaluation_gate_path else None,
        "auxiliary_task_readiness": str(auxiliary_task_readiness_path) if auxiliary_task_readiness_path else None,
        "adoption_2609_07946": str(adoption_2609_07946_path) if adoption_2609_07946_path else None,
        "promotion_gate_2609_07946": str(promotion_gate_2609_07946_path) if promotion_gate_2609_07946_path else None,
        "instrument_review_00635u": str(instrument_review_00635u_path) if instrument_review_00635u_path else None,
        "adoption_2609_08106": str(adoption_2609_08106_path) if adoption_2609_08106_path else None,
    }
    return report


def write_report(report: dict[str, Any], *, output_path: Path = DEFAULT_OUTPUT, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(report["as_of"])).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--signed-review", default=str(DEFAULT_SIGNED_REVIEW))
    parser.add_argument("--signed-approval-validation", default=str(DEFAULT_SIGNED_APPROVAL_VALIDATION))
    parser.add_argument("--guarded-candidate", default=str(DEFAULT_GUARDED_CANDIDATE))
    parser.add_argument("--liquidity-feedback", default=str(DEFAULT_LIQUIDITY_FEEDBACK))
    parser.add_argument("--tracking-review", default=str(DEFAULT_TRACKING_REVIEW))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--moira-validation", default=str(DEFAULT_MOIRA_VALIDATION))
    parser.add_argument("--moira-backtest", default=str(DEFAULT_MOIRA_BACKTEST))
    parser.add_argument("--event-quality", default=str(DEFAULT_EVENT_QUALITY))
    parser.add_argument("--cvar-review", default=str(DEFAULT_CVAR_REVIEW))
    parser.add_argument("--cvar-cost-window-split", default=str(DEFAULT_CVAR_COST_WINDOW_SPLIT))
    parser.add_argument("--tail-review", default=str(DEFAULT_TAIL_REVIEW))
    parser.add_argument("--re-evaluation-gate", default=str(DEFAULT_RE_EVALUATION_GATE))
    parser.add_argument("--auxiliary-task-readiness", default=str(DEFAULT_AUXILIARY_TASK_READINESS))
    parser.add_argument("--adoption-2609-07946", default=str(DEFAULT_2609_07946_ADOPTION))
    parser.add_argument("--promotion-gate-2609-07946", default=str(DEFAULT_2609_07946_PROMOTION_GATE))
    parser.add_argument("--instrument-review-00635u", default=str(DEFAULT_00635U_INSTRUMENT_REVIEW))
    parser.add_argument("--adoption-2609-08106", default=str(DEFAULT_2609_08106_ADOPTION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        as_of=args.as_of,
        signed_review_path=Path(args.signed_review) if args.signed_review else None,
        signed_approval_validation_path=Path(args.signed_approval_validation) if args.signed_approval_validation else None,
        guarded_candidate_path=Path(args.guarded_candidate) if args.guarded_candidate else None,
        liquidity_feedback_path=Path(args.liquidity_feedback) if args.liquidity_feedback else None,
        tracking_review_path=Path(args.tracking_review) if args.tracking_review else None,
        market_impact_path=Path(args.market_impact) if args.market_impact else None,
        moira_validation_path=Path(args.moira_validation) if args.moira_validation else None,
        moira_backtest_path=Path(args.moira_backtest) if args.moira_backtest else None,
        event_quality_path=Path(args.event_quality) if args.event_quality else None,
        cvar_review_path=Path(args.cvar_review) if args.cvar_review else None,
        cvar_cost_window_split_path=Path(args.cvar_cost_window_split) if args.cvar_cost_window_split else None,
        tail_review_path=Path(args.tail_review) if args.tail_review else None,
        re_evaluation_gate_path=Path(args.re_evaluation_gate) if args.re_evaluation_gate else None,
        auxiliary_task_readiness_path=Path(args.auxiliary_task_readiness) if args.auxiliary_task_readiness else None,
        adoption_2609_07946_path=Path(args.adoption_2609_07946) if args.adoption_2609_07946 else None,
        promotion_gate_2609_07946_path=Path(args.promotion_gate_2609_07946) if args.promotion_gate_2609_07946 else None,
        instrument_review_00635u_path=Path(args.instrument_review_00635u) if args.instrument_review_00635u else None,
        adoption_2609_08106_path=Path(args.adoption_2609_08106) if args.adoption_2609_08106 else None,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
    )
    print(
        "as_of={as_of} top={top} decision={decision}".format(
            as_of=report.get("as_of"),
            top=report.get("top_candidate_id"),
            decision=report.get("top_candidate_decision"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), str(report['as_of']))}")


if __name__ == "__main__":
    main()
