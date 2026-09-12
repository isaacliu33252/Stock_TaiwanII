#!/usr/bin/env python3
"""Build a research-only capacity/crowding readiness review for GroupA+.

This imports governance ideas from arXiv 2608.08405. The paper is about
capacity estimands and experimental design, not a new forecasting signal, so
this report deliberately cannot change live target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_LIQUIDITY_FEEDBACK = (
    PROJECT_ROOT / "report/group_a_plus/latest/letf_liquidity_feedback_watch_shadow_backtest.json"
)
DEFAULT_CAPACITY_GRID = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_capacity_grid_shadow.json"
DEFAULT_EROSION_PERSISTENCE = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.json"
DEFAULT_INSTRUMENT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_instrument_readiness_shadow.json"
DEFAULT_RAMP_PATH_DEPENDENCE = (
    PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_capacity_crowding_readiness.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_capacity_crowding_readiness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_08405_capacity_crowding_readiness/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite_hold_fraction(*, persistence: float, hold_periods: int) -> dict[str, Any]:
    if hold_periods <= 0 or not 0.0 <= persistence < 1.0:
        return {"hold_periods": hold_periods, "valid": False}
    terminal = 1.0 - persistence**hold_periods
    average = 1.0 - persistence * (1.0 - persistence**hold_periods) / (hold_periods * (1.0 - persistence))
    return {
        "hold_periods": int(hold_periods),
        "persistence": float(persistence),
        "terminal_fraction_f_l": float(terminal),
        "block_average_fraction_g_l": float(average),
        "steady_state_shortfall_terminal": float(1.0 - terminal),
        "steady_state_shortfall_block_average": float(1.0 - average),
        "interpretation": "illustrative_only_paper_calibration_not_fitted_to_taiwan_etfs",
    }


def _target_weights(live: dict[str, Any]) -> dict[str, float]:
    raw = live.get("target_weights") if isinstance(live.get("target_weights"), dict) else {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        number = _num(value)
        if number is not None:
            out[str(key)] = number
    return out


def _target_values(live: dict[str, Any], capital: float) -> dict[str, float]:
    raw = live.get("target_values") if isinstance(live.get("target_values"), dict) else {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        number = _num(value)
        if number is not None:
            out[str(key)] = number
    if out:
        return out
    return {key: float(weight * capital) for key, weight in _target_weights(live).items()}


def _impact_rows(market_impact: dict[str, Any]) -> list[dict[str, Any]]:
    computed = market_impact.get("computed") if isinstance(market_impact.get("computed"), dict) else {}
    rows = computed.get("trade_rows") if isinstance(computed.get("trade_rows"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _assigned_vs_realized(live: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    target_weights = bool(live.get("target_weights"))
    target_shares = bool(plan.get("target_shares"))
    theoretical_target_shares = bool(plan.get("theoretical_target_shares"))
    return {
        "assigned_target_weights_logged": target_weights,
        "assigned_target_shares_logged": target_shares,
        "pre_staging_theoretical_target_logged": theoretical_target_shares,
        "realized_fill_or_broker_execution_logged": False,
        "paper_mapping": (
            "GroupA+ records assigned targets and staged targets, but this report did not find "
            "a same-run realized fill series that can instrument assigned versus realized deployment."
        ),
    }


def _pre_registration_protocol() -> dict[str, Any]:
    return {
        "required_before_any_capacity_experiment": True,
        "items": [
            "estimand_capacity_curve_or_capacity_crossing",
            "deployment_arms_allocation_and_hold_length",
            "hold_length_justified_by_dissipation_half_life",
            "outcome_timestamp_and_adjustment_convention",
            "assigned_and_realized_deployment_measurement_plan",
            "within_block_trajectory_recording_plan",
            "model_free_bound_and_deattenuated_point_reporting_rule",
            "path_dependence_alternative_class_if_ramp_tested",
            "pooled_scale_and_detectable_gap_power_budget",
        ],
        "current_group_a_plus_status": "not_preregistered_for_capacity_experiment",
    }


def _natural_experiment_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate": "securities_lending_supply_shifts",
            "group_a_plus_mapping": "0050/00631L/00632R borrow and lending-source stress diagnostics",
            "allowed_use": "future_shadow_instrument_only",
            "promotion_requirement": "credible_exclusion_restriction_and_reported_first_stage",
        },
        {
            "candidate": "index_reconstitution_or_index_weight_events",
            "group_a_plus_mapping": "Taiwan ETF constituent/index-flow event windows",
            "allowed_use": "future_shadow_instrument_only",
            "promotion_requirement": "credible_exclusion_restriction_and_reported_first_stage",
        },
    ]


def _capacity_shadow_next_steps() -> list[dict[str, Any]]:
    return [
        {
            "step": "log_assigned_vs_realized_daily_deployment",
            "purpose": "separate intended target exposure from realized fill/deployment before any capacity claim",
            "live_weight_change_allowed": False,
        },
        {
            "step": "build_shadow_capacity_grid_report",
            "purpose": "report a finite-grid capacity interval and simultaneous band instead of a point estimate",
            "live_weight_change_allowed": False,
        },
        {
            "step": "calibrate_taiwan_etf_erosion_persistence",
            "purpose": "replace the illustrative persistence bridge with GroupA+-specific evidence",
            "live_weight_change_allowed": False,
        },
        {
            "step": "evaluate_lending_or_index_event_instruments",
            "purpose": "test first-stage strength and exclusion plausibility before using natural experiments",
            "live_weight_change_allowed": False,
        },
        {
            "step": "build_ramp_path_dependence_shadow",
            "purpose": "keep ramp-up/ramp-down path dependence separate from capacity-level grid evidence",
            "live_weight_change_allowed": False,
        },
    ]


def build_report(
    *,
    live_signal_path: Path,
    execution_plan_path: Path,
    market_impact_path: Path,
    liquidity_feedback_path: Path,
    capacity_grid_path: Path,
    erosion_persistence_path: Path,
    instrument_readiness_path: Path,
    ramp_path_dependence_path: Path,
    capital: float,
    persistence: float,
    hold_periods: tuple[int, ...],
) -> dict[str, Any]:
    live = _unwrap(_load_optional(live_signal_path))
    plan = _unwrap(_load_optional(execution_plan_path))
    market_impact = _unwrap(_load_optional(market_impact_path))
    liquidity_feedback = _unwrap(_load_optional(liquidity_feedback_path))
    capacity_grid = _unwrap(_load_optional(capacity_grid_path))
    erosion_persistence = _unwrap(_load_optional(erosion_persistence_path))
    instrument_readiness = _unwrap(_load_optional(instrument_readiness_path))
    ramp_path_dependence = _unwrap(_load_optional(ramp_path_dependence_path))

    weights = _target_weights(live)
    values = _target_values(live, capital)
    risky_weights = {key: value for key, value in weights.items() if key != "cash"}
    levered_inverse_weight = sum(weights.get(ticker, 0.0) for ticker in ("00631L.TW", "00632R.TW"))
    impact_computed = market_impact.get("computed") if isinstance(market_impact.get("computed"), dict) else {}
    trade_rows = _impact_rows(market_impact)
    assigned_realized = _assigned_vs_realized(live, plan)

    checks = {
        "capacity_experiment_feasible_for_single_account": False,
        "randomized_parallel_sleeves_available": False,
        "same_date_contrast_identifies_aggregate_crowding": False,
        "finite_grid_capacity_interval_reported": bool(
            (capacity_grid.get("decision") or {}).get("capacity_interval_reported")
        ),
        "steady_state_kernel_calibrated_to_group_a_plus": False,
        "impact_model_is_only_one_sided_upper_bound": True,
        "impact_or_liquidity_artifacts_available": bool(market_impact or liquidity_feedback),
        "assigned_targets_logged": bool(
            assigned_realized["assigned_target_weights_logged"] and assigned_realized["assigned_target_shares_logged"]
        ),
        "realized_deployment_logged": bool(assigned_realized["realized_fill_or_broker_execution_logged"]),
        "changes_latest_strategy": False,
    }

    blockers = [
        "no_randomized_parallel_sleeves",
        "aggregate_crowding_not_identified_by_same_date_contrast",
        "steady_state_kernel_not_calibrated_to_group_a_plus",
        "impact_model_upper_bound_only",
        "realized_deployment_series_missing",
    ]
    if not capacity_grid:
        blockers.append("finite_grid_capacity_interval_missing")
    elif not (capacity_grid.get("decision") or {}).get("capacity_interval_reported"):
        blockers.append("finite_grid_capacity_interval_not_identified")
    if not market_impact:
        blockers.append("missing_market_impact_readiness_review")
    elif market_impact.get("status") == "blocked":
        blockers.append("market_impact_readiness_blocked")
    if not liquidity_feedback:
        blockers.append("missing_letf_liquidity_feedback_watch")
    if not instrument_readiness:
        blockers.append("natural_experiment_instrument_readiness_missing")
    elif not (instrument_readiness.get("decision") or {}).get("instrument_promotable"):
        blockers.append("natural_experiment_instrument_not_promotable")
    if not ramp_path_dependence:
        blockers.append("ramp_path_dependence_shadow_missing")
    elif not (ramp_path_dependence.get("decision") or {}).get("ramp_path_dependence_claim_allowed"):
        blockers.append("ramp_path_dependence_not_identified")
    live_date = live.get("actual_data_date")
    plan_date = plan.get("actual_data_date")
    if live_date and plan_date and live_date != plan_date:
        blockers.append("execution_plan_stale_vs_live_signal")

    warnings: list[str] = []
    if weights.get("00631L.TW", 0.0) > 0:
        warnings.append("leveraged_etf_positive_weight_capacity_review_required_before_scaling")
    if weights.get("00632R.TW", 0.0) > 0:
        warnings.append("inverse_etf_positive_weight_capacity_review_required_before_scaling")

    finite_hold = [_finite_hold_fraction(persistence=persistence, hold_periods=period) for period in hold_periods]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_08405_capacity_crowding_readiness",
        "status": "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": live.get("requested_as_of_date") or live_date,
        "policy": "research_only_capacity_crowding_readiness_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf",
            "title": "Robustness or Crowding: Experimental Design for Trading Strategy Capacity",
            "date": "2026-08-05",
            "imported_concepts": [
                "capacity_is_a_causal_estimand_not_a_backtest_metric",
                "same_date_sleeve_contrasts_remove_calendar_shocks_but_do_not_identify_aggregate_crowding",
                "finite_hold_trials_attenuate_steady_state_erosion",
                "impact_models_bound_capacity_from_one_side_only",
                "finite_arm_grids_should_report_capacity_intervals_not_point_estimates",
                "assigned_and_realized_deployment_must_be_separated",
                "path_dependence_requires_a_separate_ramp_experiment",
                "capacity_experiment_requires_pre_registration",
                "natural_experiments_require_exclusion_restriction_and_first_stage",
                "outcome_adjustment_must_not_condition_on_treatment_moved_quantities",
            ],
            "not_imported": [
                "live_randomized_sleeve_experiment",
                "automatic_capacity_based_position_scaling",
                "steady_state_deattenuated_capacity_point_estimate",
                "natural_experiment_capacity_claim_without_first_stage",
            ],
        },
        "capital_context": {
            "capital": float(capital),
            "live_actual_data_date": live_date,
            "execution_plan_actual_data_date": plan_date,
            "target_weights": weights,
            "target_values": values,
            "max_single_risky_weight": max(risky_weights.values(), default=0.0),
            "leveraged_or_inverse_weight": float(levered_inverse_weight),
            "cash_weight": float(weights.get("cash", 0.0)),
        },
        "paper_method_mapping": {
            "capacity_experiment": "not_feasible_for_current_single_account_group_a_plus",
            "same_date_contrast": "use_as_warning_about_estimand_limits_not_as_promotion_evidence",
            "finite_hold_attenuation": finite_hold,
            "impact_model": "treat_market_impact_review_as_upper_bound_only_for_capacity",
            "finite_grid": "future_capacity_study_must_report_interval_with_simultaneous_band",
            "path_dependence": "future_ramp_up_down_shadow_only_before_any_capacity_scaling",
            "outcome_adjustment": (
                "future study must predeclare whether adjusted returns use arm-invariant "
                "covariates or treatment-moved exposures; do not condition on post-treatment "
                "quantities when claiming capacity."
            ),
        },
        "future_experiment_pre_registration": _pre_registration_protocol(),
        "future_natural_experiment_candidates": _natural_experiment_candidates(),
        "capacity_shadow_next_steps": _capacity_shadow_next_steps(),
        "assigned_vs_realized_deployment": assigned_realized,
        "current_artifact_summary": {
            "market_impact_status": market_impact.get("status"),
            "market_impact_turnover": impact_computed.get("turnover"),
            "market_impact_max_participation_of_volume": impact_computed.get("max_participation_of_volume"),
            "market_impact_trade_rows": len(trade_rows),
            "liquidity_feedback_decision": (
                liquidity_feedback.get("decision") if isinstance(liquidity_feedback.get("decision"), dict) else {}
            ),
            "liquidity_feedback_as_of": liquidity_feedback.get("as_of"),
            "capacity_grid_status": capacity_grid.get("status"),
            "capacity_grid_interval_reported": (capacity_grid.get("decision") or {}).get("capacity_interval_reported"),
            "erosion_persistence_status": erosion_persistence.get("status"),
            "erosion_persistence_proxy_available_count": (
                erosion_persistence.get("summary") or {}
            ).get("proxy_available_count"),
            "erosion_persistence_kernel_calibrated": (
                erosion_persistence.get("decision") or {}
            ).get("steady_state_kernel_calibrated_to_group_a_plus"),
            "instrument_readiness_status": instrument_readiness.get("status"),
            "instrument_promotable": (instrument_readiness.get("decision") or {}).get("instrument_promotable"),
            "instrument_first_stage_reported": (instrument_readiness.get("checks") or {}).get("first_stage_reported"),
            "instrument_exclusion_restriction_pre_registered": (
                instrument_readiness.get("checks") or {}
            ).get("exclusion_restriction_pre_registered"),
            "ramp_path_dependence_status": ramp_path_dependence.get("status"),
            "ramp_path_dependence_claim_allowed": (
                ramp_path_dependence.get("decision") or {}
            ).get("ramp_path_dependence_claim_allowed"),
            "ramp_realized_two_sided_path_ticker_count": (
                ramp_path_dependence.get("coverage") or {}
            ).get("realized_two_sided_path_ticker_count"),
        },
        "checks": checks,
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Import the paper as capacity/crowding governance only. It adds a mandatory "
                "research-only review before scaling capital, but it does not justify changing "
                "golden1_0531, golden2_0830, or the latest strategy weights."
            ),
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "golden1_0531_change_allowed": False,
            "golden2_0830_change_allowed": False,
            "latest_strategy_change_allowed": False,
            "capacity_scaling_allowed": False,
            "requires_human_review_before_scaling_above_current_capital": True,
            "blockers": blockers,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path),
            "market_impact": str(market_impact_path),
            "liquidity_feedback": str(liquidity_feedback_path),
            "capacity_grid": str(capacity_grid_path),
            "erosion_persistence": str(erosion_persistence_path),
            "instrument_readiness": str(instrument_readiness_path),
            "ramp_path_dependence": str(ramp_path_dependence_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    decision = report["decision"]
    cap = report["capital_context"]
    artifacts = report.get("current_artifact_summary", {})
    prereg = report.get("future_experiment_pre_registration", {})
    natural_candidates = report.get("future_natural_experiment_candidates", [])
    next_steps = report.get("capacity_shadow_next_steps", [])
    lines = [
        "# 2608.08405 Capacity/Crowding Readiness",
        "",
        f"- status: {report['status']}",
        f"- as_of: {report.get('as_of')}",
        f"- policy: {report['policy']}",
        f"- promotion_allowed: {decision['promotion_allowed']}",
        f"- target_weight_change_allowed: {decision['target_weight_change_allowed']}",
        f"- capital: {cap['capital']:.2f}",
        f"- leveraged_or_inverse_weight: {cap['leveraged_or_inverse_weight']:.6f}",
        f"- cash_weight: {cap['cash_weight']:.6f}",
        "",
        "## Imported Ideas",
    ]
    lines.extend(f"- {item}" for item in report["source_paper"]["imported_concepts"])
    lines.extend(["", "## Blocking Reasons"])
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Current Artifact Summary"])
    for key in [
        "market_impact_status",
        "capacity_grid_status",
        "capacity_grid_interval_reported",
        "erosion_persistence_status",
        "erosion_persistence_proxy_available_count",
        "erosion_persistence_kernel_calibrated",
        "instrument_readiness_status",
        "instrument_promotable",
        "instrument_first_stage_reported",
        "instrument_exclusion_restriction_pre_registered",
        "ramp_path_dependence_status",
        "ramp_path_dependence_claim_allowed",
        "ramp_realized_two_sided_path_ticker_count",
    ]:
        lines.append(f"- {key}: {artifacts.get(key)}")
    lines.extend(["", "## Future Experiment Pre-Registration"])
    lines.append(f"- required_before_any_capacity_experiment: {prereg.get('required_before_any_capacity_experiment')}")
    lines.extend(f"- {item}" for item in prereg.get("items", []))
    lines.extend(["", "## Future Natural Experiment Candidates"])
    for item in natural_candidates:
        lines.append(
            "- {candidate}: {allowed_use}; requirement={requirement}".format(
                candidate=item.get("candidate"),
                allowed_use=item.get("allowed_use"),
                requirement=item.get("promotion_requirement"),
            )
        )
    lines.extend(["", "## Shadow Next Steps"])
    for item in next_steps:
        lines.append(
            "- {step}: {purpose}; live_weight_change_allowed={allowed}".format(
                step=item.get("step"),
                purpose=item.get("purpose"),
                allowed=item.get("live_weight_change_allowed"),
            )
        )
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    as_of = str(report.get("as_of") or "unknown").replace("-", "")
    return history_dir / f"2608_08405_capacity_crowding_readiness_{as_of}.json"


def write_report(report: dict[str, Any], *, output_path: Path, markdown_path: Path | None, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--liquidity-feedback", default=str(DEFAULT_LIQUIDITY_FEEDBACK))
    parser.add_argument("--capacity-grid", default=str(DEFAULT_CAPACITY_GRID))
    parser.add_argument("--erosion-persistence", default=str(DEFAULT_EROSION_PERSISTENCE))
    parser.add_argument("--instrument-readiness", default=str(DEFAULT_INSTRUMENT_READINESS))
    parser.add_argument("--ramp-path-dependence", default=str(DEFAULT_RAMP_PATH_DEPENDENCE))
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--persistence", type=float, default=0.9177)
    parser.add_argument("--hold-periods", type=int, nargs="+", default=[20, 60, 120])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        market_impact_path=_resolve(args.market_impact),
        liquidity_feedback_path=_resolve(args.liquidity_feedback),
        capacity_grid_path=_resolve(args.capacity_grid),
        erosion_persistence_path=_resolve(args.erosion_persistence),
        instrument_readiness_path=_resolve(args.instrument_readiness),
        ramp_path_dependence_path=_resolve(args.ramp_path_dependence),
        capital=float(args.capital),
        persistence=float(args.persistence),
        hold_periods=tuple(args.hold_periods),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown) if args.markdown else None
    history = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output_path=output, markdown_path=markdown, history_dir=history)
    print(f"2608.08405 capacity/crowding readiness: {output}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
