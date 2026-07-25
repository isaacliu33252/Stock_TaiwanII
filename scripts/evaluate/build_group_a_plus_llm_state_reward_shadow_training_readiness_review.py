#!/usr/bin/env python3
"""Build shadow-training readiness for the GroupA+ GIFT design.

This is a pre-training governance artifact. It can describe what would be
needed for a future shadow training request, but it never trains a model, runs
PPO, outputs target weights, or authorizes live action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_model_design_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_DESIGN_REVIEW,
)
from scripts.evaluate.build_group_a_plus_llm_state_reward_cost_warning_remediation_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_COST_WARNING_REMEDIATION,
)
from scripts.evaluate.attribute_group_a_plus_llm_state_reward_cost_warning_failures import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_COST_WARNING_ATTRIBUTION,
)
from scripts.evaluate.attribute_group_a_plus_llm_state_reward_cost_warning_turnover import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_COST_WARNING_TURNOVER_ATTRIBUTION,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_regime_filtered_micro_tilt_shadow import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_REGIME_FILTERED_MICRO_TILT,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_shadow_training_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_shadow_training_readiness_review/history"
REQUIRED_HARD_CONSTRAINTS = [
    "no_live_signal_output",
    "no_target_weight_output",
    "no_auto_rebalance",
    "no_00631l_add",
    "no_00632r_open",
]


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def build_review(
    *,
    design_review_path: Path = DEFAULT_DESIGN_REVIEW,
    cost_warning_remediation_path: Path | None = None,
    cost_warning_attribution_path: Path | None = None,
    cost_warning_turnover_attribution_path: Path | None = None,
    regime_filtered_micro_tilt_path: Path | None = None,
    require_warning_cost_pass: bool = True,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    design_review = _load_json(design_review_path)
    cost_warning_remediation = _load_json(cost_warning_remediation_path) if cost_warning_remediation_path else {}
    cost_warning_attribution = _load_json(cost_warning_attribution_path) if cost_warning_attribution_path else {}
    cost_warning_turnover_attribution = (
        _load_json(cost_warning_turnover_attribution_path) if cost_warning_turnover_attribution_path else {}
    )
    regime_filtered_micro_tilt = _load_json(regime_filtered_micro_tilt_path) if regime_filtered_micro_tilt_path else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if not design_review:
        blockers.append("missing_shadow_model_design_review")
    elif design_review.get("status") != "available_for_manual_offline_review":
        blockers.append(f"shadow_model_design_review_not_available:{design_review.get('status')}")
    elif _decision(design_review).get("shadow_model_design_allowed") is not True:
        blockers.append("shadow_model_design_not_allowed")

    decision = _decision(design_review)
    if decision.get("model_training_allowed") is True or decision.get("ppo_training_allowed") is True:
        warnings.append("design_review_reports_training_allowed_unexpected")
    if decision.get("promote_to_live") is True or decision.get("target_weight_change_allowed") is True:
        warnings.append("design_review_reports_live_action_allowed_unexpected")

    design = design_review.get("design") if isinstance(design_review.get("design"), dict) else {}
    hard_constraints = design.get("hard_constraints") if isinstance(design.get("hard_constraints"), dict) else {}
    missing_constraints = [name for name in REQUIRED_HARD_CONSTRAINTS if hard_constraints.get(name) is not True]
    if missing_constraints:
        blockers.extend(f"missing_hard_constraint:{name}" for name in missing_constraints)

    blocked_tickers = design.get("blocked_live_tickers_present") if isinstance(design.get("blocked_live_tickers_present"), list) else []
    if blocked_tickers:
        blockers.append("blocked_live_ticker_present_in_design")

    warning_reasons = list(design_review.get("warning_reasons") or [])
    cost_warning_reasons = [reason for reason in warning_reasons if reason.startswith("warning_cost_scenario_failed:")]
    if require_warning_cost_pass and cost_warning_reasons:
        regime_filter_resolved = (
            regime_filtered_micro_tilt.get("decision", {}).get("regime_filter_resolves_5bps_warning") is True
        )
        if cost_warning_remediation_path is None:
            if not regime_filter_resolved:
                blockers.extend(f"unresolved_cost_warning:{reason.split(':', 1)[1]}" for reason in cost_warning_reasons)
        elif not cost_warning_remediation:
            if not regime_filter_resolved:
                blockers.append("missing_cost_warning_remediation_review")
        elif cost_warning_remediation.get("summary", {}).get("cost_warning_resolved") is not True:
            if not regime_filter_resolved:
                blockers.append("cost_warning_remediation_failed_to_resolve_warning_cost")
            else:
                warnings.append("cost_warning_resolved_by_regime_filtered_micro_tilt")
            if cost_warning_attribution_path is None:
                warnings.append("missing_cost_warning_failure_attribution_review")
            elif not cost_warning_attribution:
                warnings.append("missing_cost_warning_failure_attribution_review")
            elif cost_warning_attribution.get("decision", {}).get("cost_warning_failure_explained") is not True:
                warnings.append("cost_warning_failure_attribution_not_explained")
            if cost_warning_turnover_attribution_path is None:
                warnings.append("missing_cost_warning_turnover_attribution_review")
            elif not cost_warning_turnover_attribution:
                warnings.append("missing_cost_warning_turnover_attribution_review")
            elif cost_warning_turnover_attribution.get("decision", {}).get("turnover_cost_attribution_ready") is not True:
                warnings.append("cost_warning_turnover_attribution_not_ready")
    else:
        warnings.extend(cost_warning_reasons)

    state_columns = list(design.get("state_columns") or [])
    reward_columns = list(design.get("reward_columns") or [])
    eligible_tickers = list(design.get("eligible_tickers") or [])
    if not state_columns:
        blockers.append("missing_state_columns")
    if "reward_proxy" not in reward_columns:
        blockers.append("missing_reward_proxy_column")
    if len(eligible_tickers) < 2:
        blockers.append("too_few_eligible_tickers_for_shadow_training_design")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_shadow_training_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "shadow_training_readiness_review_only_no_training_no_live_action",
        "inputs": {
            "design_review": str(design_review_path),
            "design_review_sha256": _sha256_file(design_review_path),
            "cost_warning_remediation": str(cost_warning_remediation_path) if cost_warning_remediation_path else None,
            "cost_warning_remediation_sha256": (
                _sha256_file(cost_warning_remediation_path) if cost_warning_remediation_path else None
            ),
            "cost_warning_attribution": str(cost_warning_attribution_path) if cost_warning_attribution_path else None,
            "cost_warning_attribution_sha256": (
                _sha256_file(cost_warning_attribution_path) if cost_warning_attribution_path else None
            ),
            "cost_warning_turnover_attribution": (
                str(cost_warning_turnover_attribution_path) if cost_warning_turnover_attribution_path else None
            ),
            "cost_warning_turnover_attribution_sha256": (
                _sha256_file(cost_warning_turnover_attribution_path)
                if cost_warning_turnover_attribution_path
                else None
            ),
            "regime_filtered_micro_tilt": str(regime_filtered_micro_tilt_path) if regime_filtered_micro_tilt_path else None,
            "regime_filtered_micro_tilt_sha256": (
                _sha256_file(regime_filtered_micro_tilt_path) if regime_filtered_micro_tilt_path else None
            ),
            "require_warning_cost_pass": require_warning_cost_pass,
        },
        "training_design_boundary": {
            "design_id": design.get("design_id"),
            "freeze_id": design.get("freeze_id"),
            "frozen_manifest_sha256": design.get("frozen_manifest_sha256"),
            "proposal_id": design.get("proposal_id"),
            "selected_label": design.get("selected_label"),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(design.get("excluded_tickers") or []),
            "state_columns": state_columns,
            "reward_columns": reward_columns,
            "allowed_shadow_model_family": design.get("allowed_shadow_model_family"),
            "allowed_training_label": design.get("allowed_training_label"),
            "validation_plan": design.get("validation_plan") or {},
            "hard_constraints": hard_constraints,
        },
        "summary": {
            "shadow_model_design_allowed": _decision(design_review).get("shadow_model_design_allowed"),
            "cost_warning_count": len(cost_warning_reasons),
            "cost_warning_remediation_status": cost_warning_remediation.get("status"),
            "cost_warning_resolved": cost_warning_remediation.get("summary", {}).get("cost_warning_resolved"),
            "cost_warning_remediation_evaluated_count": cost_warning_remediation.get("summary", {}).get("evaluated_count"),
            "cost_warning_failure_explained": cost_warning_attribution.get("decision", {}).get(
                "cost_warning_failure_explained"
            ),
            "cost_warning_dominant_failure_metric": cost_warning_attribution.get("summary", {}).get(
                "dominant_failure_metric_for_best"
            ),
            "cost_warning_best_high_score": cost_warning_attribution.get("summary", {}).get("best_high_score"),
            "cost_warning_turnover_failure_cause": cost_warning_turnover_attribution.get("summary", {}).get(
                "best_failure_cause"
            ),
            "cost_warning_turnover_cost_caused_failure_fold_count": cost_warning_turnover_attribution.get(
                "summary", {}
            ).get("best_cost_caused_failure_fold_count"),
            "cost_warning_raw_signal_failure_fold_count": cost_warning_turnover_attribution.get("summary", {}).get(
                "best_raw_signal_failure_fold_count"
            ),
            "regime_filter_resolves_5bps_warning": regime_filtered_micro_tilt.get("decision", {}).get(
                "regime_filter_resolves_5bps_warning"
            ),
            "regime_filter_recommended_candidate": regime_filtered_micro_tilt.get("summary", {}).get(
                "recommended_candidate"
            ),
            "training_readiness_blocked_by_cost_warning": bool(
                require_warning_cost_pass
                and cost_warning_reasons
                and cost_warning_remediation.get("summary", {}).get("cost_warning_resolved") is not True
                and regime_filtered_micro_tilt.get("decision", {}).get("regime_filter_resolves_5bps_warning") is not True
            ),
            "state_column_count": len(state_columns),
            "reward_column_count": len(reward_columns),
            "eligible_ticker_count": len(eligible_tickers),
            "shadow_training_ready": not blockers,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "This is a pre-training readiness artifact only; it does not permit training.",
            "The warning cost scenario must be resolved before any future shadow training request is considered ready.",
            "A separate explicit training approval artifact would still be required after readiness passes.",
        ],
        "decision": {
            "available_for_manual_offline_review": True,
            "shadow_training_ready": not blockers,
            "shadow_training_request_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_shadow_training_readiness_review_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--design-review", default=str(DEFAULT_DESIGN_REVIEW))
    parser.add_argument("--cost-warning-remediation", default=str(DEFAULT_COST_WARNING_REMEDIATION))
    parser.add_argument("--no-cost-warning-remediation", action="store_true")
    parser.add_argument("--cost-warning-attribution", default=str(DEFAULT_COST_WARNING_ATTRIBUTION))
    parser.add_argument("--no-cost-warning-attribution", action="store_true")
    parser.add_argument("--cost-warning-turnover-attribution", default=str(DEFAULT_COST_WARNING_TURNOVER_ATTRIBUTION))
    parser.add_argument("--no-cost-warning-turnover-attribution", action="store_true")
    parser.add_argument("--regime-filtered-micro-tilt", default=str(DEFAULT_REGIME_FILTERED_MICRO_TILT))
    parser.add_argument("--no-regime-filtered-micro-tilt", action="store_true")
    parser.add_argument("--allow-warning-cost", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        design_review_path=_resolve(args.design_review),
        cost_warning_remediation_path=(
            None if args.no_cost_warning_remediation else _resolve(args.cost_warning_remediation)
        ),
        cost_warning_attribution_path=(
            None if args.no_cost_warning_attribution else _resolve(args.cost_warning_attribution)
        ),
        cost_warning_turnover_attribution_path=(
            None
            if args.no_cost_warning_turnover_attribution
            else _resolve(args.cost_warning_turnover_attribution)
        ),
        regime_filtered_micro_tilt_path=(
            None if args.no_regime_filtered_micro_tilt else _resolve(args.regime_filtered_micro_tilt)
        ),
        require_warning_cost_pass=not args.allow_warning_cost,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward shadow training readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "shadow_training_ready": review["decision"]["shadow_training_ready"],
                "shadow_training_request_allowed": review["decision"]["shadow_training_request_allowed"],
                "model_training_allowed": review["decision"]["model_training_allowed"],
                "ppo_training_allowed": review["decision"]["ppo_training_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
