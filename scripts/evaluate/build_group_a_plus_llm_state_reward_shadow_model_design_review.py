#!/usr/bin/env python3
"""Build the GroupA+ GIFT shadow model design review.

This artifact records the allowed next shadow-model design boundary after the
research promotion gate passes. It does not train a model, run PPO, output
target weights, or authorize live rebalance decisions.
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

from scripts.evaluate.build_group_a_plus_llm_state_reward_promotion_gate_snapshot import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_PROMOTION_GATE,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_cost_aware_micro_tilt_guard_shadow import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_MICRO_TILT_GUARD,
)
from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_frozen_manifest import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_FROZEN_MANIFEST,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_shadow_model_design_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_shadow_model_design_review/history"
DEFAULT_EXCLUDED_TICKERS = ["00631L.TW", "00632R.TW"]


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _sha256_file(path), "exists": path.exists()}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def build_review(
    *,
    promotion_gate_path: Path = DEFAULT_PROMOTION_GATE,
    frozen_manifest_path: Path = DEFAULT_FROZEN_MANIFEST,
    micro_tilt_guard_path: Path = DEFAULT_MICRO_TILT_GUARD,
    excluded_tickers: list[str] | None = None,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    promotion_gate = _load_json(promotion_gate_path)
    frozen_manifest = _load_json(frozen_manifest_path)
    micro_tilt_guard = _load_json(micro_tilt_guard_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not promotion_gate:
        blockers.append("missing_promotion_gate_snapshot")
    elif promotion_gate.get("status") != "available_for_manual_offline_review":
        blockers.append(f"promotion_gate_not_available:{promotion_gate.get('status')}")
    elif _decision(promotion_gate).get("promotion_gate_passed") is not True:
        blockers.append("promotion_gate_not_passed")
    elif _decision(promotion_gate).get("next_shadow_model_design_allowed") is not True:
        blockers.append("next_shadow_model_design_not_allowed_by_gate")

    if not frozen_manifest:
        blockers.append("missing_frozen_manifest")
    elif frozen_manifest.get("status") != "frozen_for_manual_offline_review":
        blockers.append(f"frozen_manifest_not_available:{frozen_manifest.get('status')}")

    if not micro_tilt_guard:
        blockers.append("missing_cost_aware_micro_tilt_guard")
    elif micro_tilt_guard.get("status") != "available_for_manual_offline_review":
        blockers.append(f"cost_aware_micro_tilt_guard_not_available:{micro_tilt_guard.get('status')}")
    elif _decision(micro_tilt_guard).get("cost_aware_micro_tilt_guard_passed_shadow_gate") is not True:
        blockers.append("cost_aware_micro_tilt_guard_not_passed")

    for name, payload in {
        "promotion_gate": promotion_gate,
        "frozen_manifest": frozen_manifest,
        "cost_aware_micro_tilt_guard": micro_tilt_guard,
    }.items():
        decision = _decision(payload)
        if decision.get("model_training_allowed") is True or decision.get("ppo_training_allowed") is True:
            warnings.append(f"{name}_reports_training_allowed_unexpected")
        if decision.get("promote_to_live") is True or decision.get("target_weight_change_allowed") is True:
            warnings.append(f"{name}_reports_live_action_allowed_unexpected")
        if decision.get("allow_00631l_add") is True or decision.get("allow_00632r_open") is True:
            warnings.append(f"{name}_reports_leveraged_or_inverse_action_allowed_unexpected")

    freeze = frozen_manifest.get("freeze") if isinstance(frozen_manifest.get("freeze"), dict) else {}
    micro_inputs = micro_tilt_guard.get("inputs") if isinstance(micro_tilt_guard.get("inputs"), dict) else {}
    excluded = sorted(set(excluded_tickers or DEFAULT_EXCLUDED_TICKERS))
    eligible_tickers = list(micro_inputs.get("eligible_tickers") or [])
    blocked_live_tickers_present = sorted(set(eligible_tickers) & set(excluded))
    if blocked_live_tickers_present:
        blockers.append("excluded_ticker_present_in_shadow_design_universe")

    required_results = micro_tilt_guard.get("summary", {}).get("required_results")
    required_results = required_results if isinstance(required_results, list) else []
    warning_results = micro_tilt_guard.get("summary", {}).get("warning_results")
    warning_results = warning_results if isinstance(warning_results, list) else []

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_shadow_model_design_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "shadow_model_design_review_only_no_training_no_live_action",
        "sources": {
            "promotion_gate": _source(promotion_gate_path),
            "frozen_manifest": _source(frozen_manifest_path),
            "cost_aware_micro_tilt_guard": _source(micro_tilt_guard_path),
        },
        "design": {
            "design_id": f"{freeze.get('freeze_id') or 'unfrozen'}_shadow_model_design",
            "freeze_id": freeze.get("freeze_id"),
            "frozen_manifest_sha256": freeze.get("frozen_manifest_sha256"),
            "proposal_id": freeze.get("proposal_id"),
            "selected_label": freeze.get("selected_label"),
            "state_columns": freeze.get("state_columns") or [],
            "reward_columns": freeze.get("reward_columns") or [],
            "reward_params": freeze.get("reward_params"),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": excluded,
            "blocked_live_tickers_present": blocked_live_tickers_present,
            "allowed_shadow_model_family": "tabular_or_sequence_shadow_model_design_only",
            "allowed_training_label": "future_return_or_downside_proxy_for_offline_design",
            "validation_plan": {
                "walk_forward_required": True,
                "purge_required": True,
                "cost_scenarios_required_bps": micro_inputs.get("required_cost_bps") or [],
                "cost_scenarios_warning_bps": micro_inputs.get("warning_cost_bps") or [],
                "required_cost_results": required_results,
                "warning_cost_results": warning_results,
            },
            "hard_constraints": {
                "no_model_training_in_this_step": True,
                "no_ppo_training": True,
                "no_live_signal_output": True,
                "no_target_weight_output": True,
                "no_auto_rebalance": True,
                "no_00631l_add": True,
                "no_00632r_open": True,
            },
        },
        "summary": {
            "promotion_gate_passed": _decision(promotion_gate).get("promotion_gate_passed"),
            "micro_tilt_guard_passed": micro_tilt_guard.get("summary", {}).get("micro_tilt_guard_passed"),
            "required_cost_scenarios_passed": micro_tilt_guard.get("summary", {}).get(
                "required_cost_scenarios_passed"
            ),
            "warning_cost_scenarios_passed": micro_tilt_guard.get("summary", {}).get(
                "warning_cost_scenarios_passed"
            ),
            "shadow_model_design_allowed": not blockers,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings + list(micro_tilt_guard.get("warning_reasons") or []))),
        "interpretation": [
            "This artifact permits only designing a future shadow experiment around the frozen state/reward interface.",
            "The 5 bps cost scenario is a warning-level failure and must be considered before any later training proposal.",
            "A separate approval artifact is required before any model training or PPO training can occur.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "shadow_model_design_allowed": not blockers,
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
    return history_dir / f"llm_state_reward_shadow_model_design_review_{stamp}.json"


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
    parser.add_argument("--promotion-gate", default=str(DEFAULT_PROMOTION_GATE))
    parser.add_argument("--frozen-manifest", default=str(DEFAULT_FROZEN_MANIFEST))
    parser.add_argument("--micro-tilt-guard", default=str(DEFAULT_MICRO_TILT_GUARD))
    parser.add_argument("--exclude-ticker", action="append", default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        promotion_gate_path=_resolve(args.promotion_gate),
        frozen_manifest_path=_resolve(args.frozen_manifest),
        micro_tilt_guard_path=_resolve(args.micro_tilt_guard),
        excluded_tickers=args.exclude_ticker or None,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward shadow model design review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "shadow_model_design_allowed": review["decision"]["shadow_model_design_allowed"],
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
