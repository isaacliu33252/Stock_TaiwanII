#!/usr/bin/env python3
"""Build a manual-review package for a future GIFT shadow training request.

This artifact packages the approved shadow design boundary and the
regime-filtered micro-tilt candidate. It does not train a model, queue PPO,
emit target weights, or authorize live action.
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
from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_training_readiness_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_TRAINING_READINESS,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_regime_filtered_micro_tilt_shadow import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_REGIME_FILTERED_MICRO_TILT,
)
from scripts.evaluate.build_group_a_plus_research_shadow_decision_snapshot import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_RESEARCH_SHADOW,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_shadow_training_request_package.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_shadow_training_request_package/history"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _sha256_file(path), "exists": path.exists()}


def build_package(
    *,
    design_review_path: Path = DEFAULT_DESIGN_REVIEW,
    training_readiness_path: Path = DEFAULT_TRAINING_READINESS,
    regime_filtered_micro_tilt_path: Path = DEFAULT_REGIME_FILTERED_MICRO_TILT,
    research_shadow_path: Path = DEFAULT_RESEARCH_SHADOW,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    design_review = _load_json(design_review_path)
    training_readiness = _load_json(training_readiness_path)
    regime_filtered = _load_json(regime_filtered_micro_tilt_path)
    research_shadow = _load_json(research_shadow_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not design_review:
        blockers.append("missing_shadow_model_design_review")
    elif _decision(design_review).get("shadow_model_design_allowed") is not True:
        blockers.append("shadow_model_design_not_allowed")

    if not training_readiness:
        blockers.append("missing_shadow_training_readiness_review")
    elif _decision(training_readiness).get("shadow_training_ready") is not True:
        blockers.append("shadow_training_not_ready")

    if not regime_filtered:
        blockers.append("missing_regime_filtered_micro_tilt_shadow_backtest")
    elif _decision(regime_filtered).get("regime_filter_resolves_5bps_warning") is not True:
        blockers.append("regime_filter_does_not_resolve_5bps_warning")

    if not research_shadow:
        warnings.append("missing_research_shadow_decision_snapshot")
    elif research_shadow.get("summary", {}).get("llm_state_reward_shadow_training_ready") is not True:
        warnings.append("research_shadow_snapshot_does_not_mark_gift_shadow_training_ready")

    for name, payload in {
        "design_review": design_review,
        "training_readiness": training_readiness,
        "regime_filtered_micro_tilt": regime_filtered,
        "research_shadow": research_shadow,
    }.items():
        decision = _decision(payload)
        if decision.get("model_training_allowed") is True or decision.get("ppo_training_allowed") is True:
            blockers.append(f"{name}_unexpected_training_permission")
        if (
            decision.get("promote_to_live") is True
            or decision.get("target_weight_change_allowed") is True
            or decision.get("auto_rebalance_allowed") is True
        ):
            blockers.append(f"{name}_unexpected_live_permission")
        if decision.get("allow_00631l_add") is True or decision.get("allow_00632r_open") is True:
            blockers.append(f"{name}_unexpected_blocked_ticker_permission")

    design = design_review.get("design") if isinstance(design_review.get("design"), dict) else {}
    boundary = training_readiness.get("training_design_boundary") or design
    candidate = (regime_filtered.get("summary") or {}).get("recommended_candidate")
    hard_constraints = boundary.get("hard_constraints") if isinstance(boundary.get("hard_constraints"), dict) else {}
    if not candidate:
        blockers.append("missing_regime_filter_recommended_candidate")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_shadow_training_request_package",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_review",
        "policy": "manual_shadow_training_request_package_no_training_no_live_action",
        "sources": {
            "design_review": _source(design_review_path),
            "training_readiness": _source(training_readiness_path),
            "regime_filtered_micro_tilt": _source(regime_filtered_micro_tilt_path),
            "research_shadow_decision_snapshot": _source(research_shadow_path),
        },
        "request_boundary": {
            "request_id": f"{boundary.get('freeze_id')}_manual_shadow_training_request",
            "design_id": boundary.get("design_id"),
            "freeze_id": boundary.get("freeze_id"),
            "frozen_manifest_sha256": boundary.get("frozen_manifest_sha256"),
            "proposal_id": boundary.get("proposal_id"),
            "selected_label": boundary.get("selected_label"),
            "eligible_tickers": list(boundary.get("eligible_tickers") or []),
            "excluded_tickers": list(boundary.get("excluded_tickers") or []),
            "state_columns": list(boundary.get("state_columns") or []),
            "reward_columns": list(boundary.get("reward_columns") or []),
            "allowed_shadow_model_family": boundary.get("allowed_shadow_model_family"),
            "allowed_training_label": boundary.get("allowed_training_label"),
            "recommended_regime_filter": candidate,
            "validation_plan": {
                "walk_forward_required": True,
                "purge_required": True,
                "regime_filter_required": True,
                "required_cost_bps": [0.0, 2.0, 5.0],
                "minimum_positive_final_folds": 4,
                "minimum_positive_sharpe_folds": 4,
                "minimum_non_worse_drawdown_folds": 3,
                "must_compare_to_equal_weight": True,
                "must_report_turnover_and_cost_drag": True,
                "must_exclude_live_blocked_tickers": ["00631L.TW", "00632R.TW"],
            },
            "hard_constraints": {
                **hard_constraints,
                "no_training_in_this_package": True,
                "separate_training_approval_required": True,
                "no_live_signal_output": True,
                "no_target_weight_output": True,
                "no_auto_rebalance": True,
                "no_00631l_add": True,
                "no_00632r_open": True,
            },
        },
        "summary": {
            "shadow_training_ready": _decision(training_readiness).get("shadow_training_ready"),
            "research_shadow_status": research_shadow.get("status"),
            "research_shadow_blocking_reasons_count": len(research_shadow.get("blocking_reasons") or []),
            "regime_filter_resolves_5bps_warning": _decision(regime_filtered).get(
                "regime_filter_resolves_5bps_warning"
            ),
            "recommended_regime_rule": candidate.get("regime_rule") if isinstance(candidate, dict) else None,
            "recommended_high_score": candidate.get("high_score") if isinstance(candidate, dict) else None,
            "recommended_cost_bps": candidate.get("cost_bps") if isinstance(candidate, dict) else None,
            "package_ready_for_manual_review": not blockers,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "This package is suitable only for manual review of a future shadow training request.",
            "It does not train a model, enqueue PPO, emit target weights, or change live strategy state.",
            "A separate explicit approval artifact is required before any training command may be run.",
        ],
        "decision": {
            "available_for_manual_review": not blockers,
            "shadow_training_request_package_ready": not blockers,
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
    return history_dir / f"llm_state_reward_shadow_training_request_package_{stamp}.json"


def write_package(package: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, package.get("as_of")).write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--design-review", default=str(DEFAULT_DESIGN_REVIEW))
    parser.add_argument("--training-readiness", default=str(DEFAULT_TRAINING_READINESS))
    parser.add_argument("--regime-filtered-micro-tilt", default=str(DEFAULT_REGIME_FILTERED_MICRO_TILT))
    parser.add_argument("--research-shadow", default=str(DEFAULT_RESEARCH_SHADOW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    package = build_package(
        design_review_path=_resolve(args.design_review),
        training_readiness_path=_resolve(args.training_readiness),
        regime_filtered_micro_tilt_path=_resolve(args.regime_filtered_micro_tilt),
        research_shadow_path=_resolve(args.research_shadow),
        as_of=args.as_of,
    )
    write_package(package, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward shadow training request package: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": package["status"],
                "package_ready_for_manual_review": package["summary"]["package_ready_for_manual_review"],
                "recommended_regime_rule": package["summary"]["recommended_regime_rule"],
                "shadow_training_request_allowed": package["decision"]["shadow_training_request_allowed"],
                "model_training_allowed": package["decision"]["model_training_allowed"],
                "ppo_training_allowed": package["decision"]["ppo_training_allowed"],
                "promote_to_live": package["decision"]["promote_to_live"],
                "blocking_reasons": package["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
