#!/usr/bin/env python3
"""Freeze the selected GroupA+ GIFT state/reward interface for offline review.

The manifest makes the selected proposal reproducible before any future
walk-forward or PPO-shadow experiment. It never permits model training, live
actions, target weights, or rebalance changes.
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

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_proposal_comparison_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_COMPARISON,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _proposal_columns,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_frozen_manifest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_frozen_manifest/history"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_candidate(comparison: dict[str, Any], label: str | None) -> dict[str, Any] | None:
    ranked = comparison.get("ranked_candidates") if isinstance(comparison.get("ranked_candidates"), list) else []
    if label is None:
        return ranked[0] if ranked else None
    for candidate in ranked:
        if isinstance(candidate, dict) and candidate.get("label") == label:
            return candidate
    return None


def _source_record(path: str | None) -> dict[str, Any]:
    if not path:
        return {"path": None, "sha256": None, "exists": False}
    source = _resolve(path)
    return {
        "path": str(source),
        "sha256": _sha256_file(source),
        "exists": source.exists(),
    }


def build_manifest(
    *,
    comparison_path: Path = DEFAULT_COMPARISON,
    selected_label: str | None = None,
    freeze_id: str = "group_a_plus_gift_downside_tail_decay_v2_tuned_20260720",
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    comparison = _load_json(comparison_path)
    blockers: list[str] = []
    if not comparison:
        blockers.append("missing_proposal_comparison_review")
    elif comparison.get("status") != "available_for_manual_offline_review":
        blockers.append(f"proposal_comparison_not_available:{comparison.get('status')}")

    candidate = _find_candidate(comparison, selected_label) if comparison else None
    if not candidate:
        blockers.append("selected_candidate_missing")

    if candidate and candidate.get("reward_alignment_grade") != "green":
        blockers.append(f"selected_candidate_not_green:{candidate.get('reward_alignment_grade')}")
    if candidate and candidate.get("ppo_training_queue_candidate") is not True:
        blockers.append("selected_candidate_not_queued_by_dgr")

    source_dgr = _source_record(candidate.get("source") if candidate else None)
    if source_dgr["exists"] is not True:
        blockers.append("selected_candidate_dgr_source_missing")
    comparison_source = {
        "path": str(comparison_path),
        "sha256": _sha256_file(comparison_path),
        "exists": comparison_path.exists(),
    }
    if comparison_source["exists"] is not True:
        blockers.append("comparison_source_missing")

    proposal_id = candidate.get("proposal_id") if candidate else None
    columns = _proposal_columns(str(proposal_id)) if proposal_id else {"feature_columns": [], "reward_columns": []}
    params = candidate.get("params") if candidate else None
    freeze_payload = {
        "freeze_id": freeze_id,
        "proposal_id": proposal_id,
        "selected_label": candidate.get("label") if candidate else selected_label,
        "state_columns": columns.get("feature_columns", []),
        "reward_columns": columns.get("reward_columns", []),
        "reward_params": params,
        "reward_alignment_objective": candidate.get("reward_alignment_objective") if candidate else None,
        "objective_alignment": candidate.get("objective_alignment") if candidate else None,
        "objective_abs_alignment": candidate.get("objective_abs_alignment") if candidate else None,
        "mean_reward_snr": candidate.get("mean_reward_snr") if candidate else None,
        "finite_reward_min_ratio": candidate.get("finite_reward_min_ratio") if candidate else None,
        "source_hashes": {
            "comparison_review": comparison_source,
            "selected_dgr_review": source_dgr,
        },
    }
    frozen_hash = hashlib.sha256(
        json.dumps(freeze_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_manifest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "frozen_for_manual_offline_review",
        "policy": "frozen_interface_manifest_only_no_model_training_no_live_action",
        "freeze": freeze_payload | {"frozen_manifest_sha256": frozen_hash},
        "blocking_reasons": sorted(set(blockers)),
        "interpretation": [
            "This manifest freezes the selected state/reward interface before out-of-sample work.",
            "Future offline experiments should reference this freeze_id and frozen_manifest_sha256.",
            "Changing reward parameters requires a new comparison review and a new freeze manifest.",
        ],
        "decision": {
            "frozen_for_manual_offline_review": not blockers,
            "offline_feature_reward_export_allowed": not blockers,
            "offline_walk_forward_design_allowed": not blockers,
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
    return history_dir / f"llm_state_reward_interface_frozen_manifest_{stamp}.json"


def write_manifest(manifest: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, manifest.get("as_of")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--selected-label", default=None)
    parser.add_argument("--freeze-id", default="group_a_plus_gift_downside_tail_decay_v2_tuned_20260720")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    manifest = build_manifest(
        comparison_path=_resolve(args.comparison),
        selected_label=args.selected_label,
        freeze_id=args.freeze_id,
        as_of=args.as_of,
    )
    write_manifest(manifest, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward frozen manifest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "freeze_id": manifest["freeze"]["freeze_id"],
                "selected_label": manifest["freeze"]["selected_label"],
                "frozen_manifest_sha256": manifest["freeze"]["frozen_manifest_sha256"],
                "promote_to_live": manifest["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
