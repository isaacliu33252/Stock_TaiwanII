#!/usr/bin/env python3
"""Compare GIFT-style state/reward proposal diagnostics for GroupA+.

This report ranks offline diagnostic candidates only. It never trains PPO,
outputs actions, target weights, or live rebalance decisions.
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

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_V1_DGR = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_diagnostic_refinement_review.json"
DEFAULT_V2_DGR = (
    PROJECT_ROOT
    / "report/group_a_plus/latest/llm_state_reward_interface_diagnostic_refinement_downside_tail_decay_review.json"
)
DEFAULT_V2_TUNED_DGR = (
    PROJECT_ROOT
    / "report/group_a_plus/latest/llm_state_reward_interface_diagnostic_refinement_downside_tail_decay_tuned_review.json"
)
DEFAULT_SWEEP = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_downside_tail_decay_param_sweep.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_proposal_comparison_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_proposal_comparison/history"


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _grade_rank(grade: str | None) -> int:
    return {"green": 3, "yellow": 2, "red": 1, "unavailable": 0}.get(str(grade), 0)


def _candidate_from_dgr(label: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    objective = summary.get("reward_alignment_objective")
    if objective == "future_downside_alignment":
        objective_alignment = summary.get("mean_reward_future_downside_alignment")
        objective_abs = summary.get("downside_alignment_abs")
    else:
        objective_alignment = summary.get("mean_reward_future_return_alignment")
        objective_abs = summary.get("return_alignment_abs")
    return {
        "label": label,
        "source": str(path),
        "status": payload.get("status", "missing"),
        "proposal_id": inputs.get("accepted_proposal_id"),
        "params": inputs.get("downside_tail_decay_params"),
        "reward_alignment_objective": objective,
        "objective_alignment": _finite_float(objective_alignment),
        "objective_abs_alignment": _finite_float(objective_abs),
        "mean_reward_future_return_alignment": _finite_float(summary.get("mean_reward_future_return_alignment")),
        "mean_reward_future_downside_alignment": _finite_float(summary.get("mean_reward_future_downside_alignment")),
        "mean_reward_snr": _finite_float(summary.get("mean_reward_snr")),
        "finite_reward_min_ratio": _finite_float(summary.get("finite_reward_min_ratio")),
        "reward_alignment_grade": summary.get("reward_alignment_grade"),
        "return_alignment_grade": summary.get("return_alignment_grade"),
        "downside_alignment_grade": summary.get("downside_alignment_grade"),
        "downside_alignment_direction": summary.get("downside_alignment_direction"),
        "downside_alignment_risk_sensitive_useful": summary.get("downside_alignment_risk_sensitive_useful"),
        "warning_count": len(payload.get("warning_reasons") or []),
        "blocking_count": len(payload.get("blocking_reasons") or []),
        "ppo_training_queue_candidate": bool(decision.get("ppo_training_queue_allowed_by_dgr")),
    }


def _rank_score(candidate: dict[str, Any]) -> float:
    alignment = candidate.get("objective_abs_alignment") or 0.0
    snr = candidate.get("mean_reward_snr") or 0.0
    status_bonus = 0.25 if candidate.get("status") == "available_for_manual_offline_review" else -0.50
    queue_bonus = 0.25 if candidate.get("ppo_training_queue_candidate") else 0.0
    return status_bonus + queue_bonus + _grade_rank(candidate.get("reward_alignment_grade")) + alignment + 0.01 * snr


def build_review(
    *,
    v1_dgr_path: Path = DEFAULT_V1_DGR,
    v2_dgr_path: Path = DEFAULT_V2_DGR,
    v2_tuned_dgr_path: Path = DEFAULT_V2_TUNED_DGR,
    sweep_path: Path = DEFAULT_SWEEP,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    inputs = {
        "v1_default": v1_dgr_path,
        "v2_default_downside_tail_decay": v2_dgr_path,
        "v2_tuned_downside_tail_decay": v2_tuned_dgr_path,
    }
    blockers: list[str] = []
    candidates: list[dict[str, Any]] = []
    for label, path in inputs.items():
        payload = _load_json(path)
        if not payload:
            blockers.append(f"missing_dgr:{label}")
            continue
        candidates.append(_candidate_from_dgr(label, path, payload))

    sweep = _load_json(sweep_path)
    if not sweep:
        blockers.append("missing_param_sweep")
    elif sweep.get("status") != "available_for_manual_offline_review":
        blockers.append(f"param_sweep_not_available:{sweep.get('status')}")

    ranked = sorted(candidates, key=_rank_score, reverse=True)
    best = ranked[0] if ranked else None
    sweep_summary = sweep.get("summary") if isinstance(sweep.get("summary"), dict) else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_proposal_comparison_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "proposal_comparison_only_no_model_training_no_live_action",
        "inputs": {
            "v1_diagnostic_refinement": str(v1_dgr_path),
            "v2_diagnostic_refinement": str(v2_dgr_path),
            "v2_tuned_diagnostic_refinement": str(v2_tuned_dgr_path),
            "param_sweep": str(sweep_path),
        },
        "summary": {
            "candidate_count": len(candidates),
            "best_label": best.get("label") if best else None,
            "best_proposal_id": best.get("proposal_id") if best else None,
            "best_reward_alignment_grade": best.get("reward_alignment_grade") if best else None,
            "best_objective": best.get("reward_alignment_objective") if best else None,
            "best_objective_alignment": best.get("objective_alignment") if best else None,
            "best_objective_abs_alignment": best.get("objective_abs_alignment") if best else None,
            "best_reward_snr": best.get("mean_reward_snr") if best else None,
            "best_ppo_training_queue_candidate": best.get("ppo_training_queue_candidate") if best else False,
            "sweep_best_params": sweep_summary.get("best_params"),
            "sweep_green_candidate_count": sweep_summary.get("green_candidate_count"),
        },
        "ranked_candidates": ranked,
        "blocking_reasons": sorted(set(blockers)),
        "interpretation": [
            "The tuned downside/tail-decay proposal is favored only as the next offline research candidate.",
            "A green diagnostic grade is not live strategy approval and does not permit PPO training by itself.",
            "Any future experiment must freeze the state/reward interface before out-of-sample evaluation.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "best_candidate_for_next_offline_experiment": bool(
                best and best.get("ppo_training_queue_candidate") and not blockers
            ),
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
    return history_dir / f"llm_state_reward_interface_proposal_comparison_{stamp}.json"


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
    parser.add_argument("--v1-dgr", default=str(DEFAULT_V1_DGR))
    parser.add_argument("--v2-dgr", default=str(DEFAULT_V2_DGR))
    parser.add_argument("--v2-tuned-dgr", default=str(DEFAULT_V2_TUNED_DGR))
    parser.add_argument("--sweep", default=str(DEFAULT_SWEEP))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        v1_dgr_path=_resolve(args.v1_dgr),
        v2_dgr_path=_resolve(args.v2_dgr),
        v2_tuned_dgr_path=_resolve(args.v2_tuned_dgr),
        sweep_path=_resolve(args.sweep),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward proposal comparison review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "best_label": review["summary"]["best_label"],
                "best_reward_alignment_grade": review["summary"]["best_reward_alignment_grade"],
                "best_objective_alignment": review["summary"]["best_objective_alignment"],
                "best_reward_snr": review["summary"]["best_reward_snr"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
