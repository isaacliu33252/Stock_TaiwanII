#!/usr/bin/env python3
"""Review reward-alignment remediation candidates for the GroupA+ GIFT interface.

This consumes the current diagnostic-refinement review and the downside/tail
parameter sweep. It does not train a model, run PPO, emit target weights, or
change the live GroupA+ strategy.
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

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_diagnostic_refinement import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_DIAGNOSTIC_REFINEMENT,
    _alignment_grade,
)
from scripts.evaluate.sweep_group_a_plus_llm_state_reward_downside_tail_decay_params import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_DOWNSIDE_TAIL_DECAY_SWEEP,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_alignment_remediation_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_alignment_remediation_review/history"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _sha256_file(path), "exists": path.exists()}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _candidate_return_grade(candidate: dict[str, Any]) -> dict[str, Any]:
    return _alignment_grade(
        candidate.get("mean_return_alignment"),
        unavailable_reason="candidate_return_alignment_unavailable",
    )


def _unexpected_permission_blockers(name: str, payload: dict[str, Any]) -> list[str]:
    decision = _decision(payload)
    blockers: list[str] = []
    for key in (
        "model_training_allowed",
        "ppo_training_allowed",
        "promote_to_live",
        "target_weight_change_allowed",
        "auto_rebalance_allowed",
        "allow_00631l_add",
        "allow_00632r_open",
    ):
        if decision.get(key) is True:
            blockers.append(f"{name}_unexpected_permission:{key}")
    return blockers


def build_review(
    *,
    diagnostic_refinement_path: Path = DEFAULT_DIAGNOSTIC_REFINEMENT,
    downside_tail_decay_sweep_path: Path = DEFAULT_DOWNSIDE_TAIL_DECAY_SWEEP,
    as_of: str = "2026-07-22",
) -> dict[str, Any]:
    diagnostic = _load_json(diagnostic_refinement_path)
    sweep = _load_json(downside_tail_decay_sweep_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not diagnostic:
        blockers.append("missing_diagnostic_refinement_review")
    if not sweep:
        blockers.append("missing_downside_tail_decay_param_sweep")
    elif sweep.get("status") != "available_for_manual_offline_review":
        blockers.append(f"downside_tail_decay_sweep_not_available:{sweep.get('status')}")

    blockers.extend(_unexpected_permission_blockers("diagnostic_refinement", diagnostic))
    blockers.extend(_unexpected_permission_blockers("downside_tail_decay_sweep", sweep))

    top_candidates = list(sweep.get("top_candidates") or [])
    scored_candidates = [
        {
            **candidate,
            "return_alignment_gate": _candidate_return_grade(candidate),
        }
        for candidate in top_candidates
        if isinstance(candidate, dict)
    ]
    scored_candidates.sort(
        key=lambda row: (
            row["return_alignment_gate"]["abs_alignment"] or 0.0,
            row.get("rank_score") or 0.0,
        ),
        reverse=True,
    )
    best_return_candidate = scored_candidates[0] if scored_candidates else None
    acceptable_candidates = [
        candidate
        for candidate in scored_candidates
        if candidate["return_alignment_gate"]["grade"] in {"yellow", "green"}
    ]
    best_acceptable = acceptable_candidates[0] if acceptable_candidates else None

    diagnostic_summary = _summary(diagnostic)
    current_return_alignment = diagnostic_summary.get("mean_reward_future_return_alignment")
    current_return_gate = _alignment_grade(
        current_return_alignment,
        unavailable_reason="current_return_alignment_unavailable",
    )
    current_queue_allowed = diagnostic_summary.get("ppo_training_queue_allowed_by_alignment") is True
    candidate_resolves = best_acceptable is not None
    candidate_queue_grade = (
        best_acceptable["return_alignment_gate"]["grade"] if best_acceptable else None
    )
    if not candidate_resolves:
        warnings.append("no_candidate_moves_return_alignment_out_of_red")
    elif candidate_queue_grade != "green":
        warnings.append("candidate_requires_manual_review_yellow_alignment")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_alignment_remediation_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "reward_alignment_remediation_review_only_no_training_no_live_action",
        "sources": {
            "diagnostic_refinement": _source(diagnostic_refinement_path),
            "downside_tail_decay_param_sweep": _source(downside_tail_decay_sweep_path),
        },
        "summary": {
            "current_return_alignment": current_return_alignment,
            "current_return_alignment_grade": current_return_gate["grade"],
            "current_ppo_training_queue_allowed_by_alignment": current_queue_allowed,
            "evaluated_candidate_count": len(top_candidates),
            "acceptable_candidate_count": len(acceptable_candidates),
            "best_return_alignment": (
                best_return_candidate.get("mean_return_alignment") if best_return_candidate else None
            ),
            "best_return_alignment_grade": (
                best_return_candidate["return_alignment_gate"]["grade"] if best_return_candidate else None
            ),
            "best_acceptable_params": best_acceptable.get("params") if best_acceptable else None,
            "best_acceptable_return_alignment": (
                best_acceptable.get("mean_return_alignment") if best_acceptable else None
            ),
            "best_acceptable_return_alignment_grade": candidate_queue_grade,
            "best_acceptable_downside_alignment": (
                best_acceptable.get("mean_downside_alignment") if best_acceptable else None
            ),
            "best_acceptable_downside_grade": best_acceptable.get("downside_grade") if best_acceptable else None,
            "candidate_resolves_return_alignment_red_for_manual_review": candidate_resolves,
            "candidate_allows_ppo_queue_by_alignment": bool(
                best_acceptable and best_acceptable["return_alignment_gate"]["grade"] == "green"
            ),
        },
        "best_return_candidate": best_return_candidate,
        "best_acceptable_candidate": best_acceptable,
        "top_candidates": scored_candidates[:10],
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "This review can only suggest a revised offline reward proxy for manual review.",
            "Yellow alignment does not permit PPO queueing without a separate human waiver.",
            "No live strategy, target weights, or broker actions are changed by this review.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "candidate_resolves_return_alignment_red_for_manual_review": candidate_resolves,
            "candidate_allows_ppo_queue_by_alignment": bool(
                best_acceptable and best_acceptable["return_alignment_gate"]["grade"] == "green"
            ),
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
    return history_dir / f"llm_state_reward_alignment_remediation_review_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-22")
    parser.add_argument("--diagnostic-refinement", default=str(DEFAULT_DIAGNOSTIC_REFINEMENT))
    parser.add_argument("--downside-tail-decay-sweep", default=str(DEFAULT_DOWNSIDE_TAIL_DECAY_SWEEP))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        diagnostic_refinement_path=_resolve(args.diagnostic_refinement),
        downside_tail_decay_sweep_path=_resolve(args.downside_tail_decay_sweep),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward alignment remediation review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "current_return_alignment_grade": review["summary"]["current_return_alignment_grade"],
                "acceptable_candidate_count": review["summary"]["acceptable_candidate_count"],
                "best_acceptable_return_alignment_grade": review["summary"][
                    "best_acceptable_return_alignment_grade"
                ],
                "candidate_resolves_return_alignment_red_for_manual_review": review["decision"][
                    "candidate_resolves_return_alignment_red_for_manual_review"
                ],
                "candidate_allows_ppo_queue_by_alignment": review["decision"][
                    "candidate_allows_ppo_queue_by_alignment"
                ],
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
