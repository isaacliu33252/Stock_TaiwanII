#!/usr/bin/env python3
"""Build a research-only LLM state-reward interface readiness review.

Inspired by arXiv 2606.08450 GIFT. This review permits constrained LLM
feature/reward proposal governance only. It never permits LLM trading actions,
PPO live allocation, target-weight changes, or automatic rebalance.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RL_GOVERNANCE = PROJECT_ROOT / "report/group_a_plus/latest/rl_governance_readiness_review.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_SYNTHETIC = PROJECT_ROOT / "report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json"
DEFAULT_DYNAMIC_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_DEPLOYMENT = PROJECT_ROOT / "report/group_a_plus/latest/deployment_consistency_review.json"
DEFAULT_RESEARCH = PROJECT_ROOT / "report/group_a_plus/latest/research_shadow_decision_snapshot.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface/history"


CORE_INPUTS = {
    "rl_governance": DEFAULT_RL_GOVERNANCE,
    "market_impact": DEFAULT_MARKET_IMPACT,
    "synthetic_augmentation_validation": DEFAULT_SYNTHETIC,
    "dynamic_cvar_tail_cost": DEFAULT_DYNAMIC_CVAR,
    "deployment_consistency": DEFAULT_DEPLOYMENT,
    "research_shadow_decision_snapshot": DEFAULT_RESEARCH,
}


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


def _component(name: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    decision = _decision(payload)
    return {
        "path": str(path),
        "exists": bool(payload),
        "status": payload.get("status"),
        "blocking_reasons": payload.get("blocking_reasons") or [],
        "decision": {
            "promote_to_live": decision.get("promote_to_live"),
            "promotion_allowed": decision.get("promotion_allowed"),
            "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
            "auto_rebalance_allowed": decision.get("auto_rebalance_allowed"),
            "allow_00631l_add": decision.get("allow_00631l_add"),
            "allow_00632r_open": decision.get("allow_00632r_open"),
        },
        "key_metrics": _key_metrics(name, payload),
    }


def _key_metrics(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "rl_governance":
        return {
            "rl_governance_ready": _nested(payload, "decision", "rl_governance_ready"),
            "rl_component_promotable": _nested(payload, "decision", "rl_component_promotable"),
            "live_rl_allocator_allowed": _nested(payload, "decision", "live_rl_allocator_allowed"),
        }
    if name == "market_impact":
        return {
            "market_impact_ready": _nested(payload, "decision", "market_impact_ready"),
            "turnover_guard_ready": _nested(payload, "decision", "turnover_guard_ready"),
        }
    if name == "synthetic_augmentation_validation":
        return {
            "synthetic_validation_ready": _nested(payload, "decision", "synthetic_validation_ready"),
            "directional_synthetic_alpha_allowed": _nested(
                payload, "decision", "directional_synthetic_alpha_allowed"
            ),
        }
    if name == "dynamic_cvar_tail_cost":
        return {
            "tail_cost_readiness_ready": _nested(payload, "decision", "tail_cost_readiness_ready"),
            "dynamic_optimizer_ready": _nested(payload, "decision", "dynamic_optimizer_ready"),
        }
    if name == "deployment_consistency":
        return {
            "broker_actionable": _nested(payload, "decision", "broker_actionable"),
            "manual_review_required": _nested(payload, "decision", "manual_review_required"),
        }
    if name == "research_shadow_decision_snapshot":
        return {
            "status": payload.get("status"),
            "allow_00631l_add": _nested(payload, "decision", "allow_00631l_add"),
        }
    return {}


def build_review(input_paths: dict[str, Path] | None = None, *, as_of: str = "2026-07-20") -> dict[str, Any]:
    paths = input_paths or CORE_INPUTS
    payloads = {name: _load(path) for name, path in paths.items()}
    components = {name: _component(name, paths[name], payload) for name, payload in payloads.items()}

    blockers: list[str] = []
    warnings: list[str] = []
    for name, payload in payloads.items():
        if not payload:
            blockers.append(f"missing_{name}")
            continue
        if payload.get("status") == "blocked":
            blockers.append(f"{name}_blocked")
        decision = _decision(payload)
        if decision.get("promote_to_live") is True or decision.get("promotion_allowed") is True:
            warnings.append(f"{name}_reports_promotion_allowed_unexpected")
        if decision.get("target_weight_change_allowed") is True:
            warnings.append(f"{name}_reports_target_weight_change_allowed_unexpected")
        if decision.get("auto_rebalance_allowed") is True:
            warnings.append(f"{name}_reports_auto_rebalance_allowed_unexpected")

    if _nested(payloads.get("rl_governance") or {}, "decision", "rl_component_promotable") is not True:
        blockers.append("rl_component_not_promotable_for_llm_interface")
    if _nested(payloads.get("market_impact") or {}, "decision", "market_impact_ready") is not True:
        blockers.append("market_impact_not_ready_for_reward_shaping")
    if _nested(payloads.get("synthetic_augmentation_validation") or {}, "decision", "synthetic_validation_ready") is not True:
        blockers.append("synthetic_validation_not_ready_for_interface_search")
    if _nested(payloads.get("dynamic_cvar_tail_cost") or {}, "decision", "tail_cost_readiness_ready") is not True:
        blockers.append("tail_cost_not_ready_for_reward_shaping")
    if _nested(payloads.get("deployment_consistency") or {}, "decision", "broker_actionable") is not True:
        blockers.append("deployment_not_broker_actionable")
    if (payloads.get("research_shadow_decision_snapshot") or {}).get("status") == "blocked":
        blockers.append("research_shadow_snapshot_blocked")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_research_interface_design",
        "policy": "research_only_constrained_llm_feature_reward_proposals_no_live_policy",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.08450.pdf",
            "title": "GIFT: LLM-Guided State-Reward Interface for Financial Reinforcement Learning",
            "arxiv": "2606.08450v1",
            "date_in_pdf": "2026-06-07",
            "imported_concepts": [
                "constrained_llm_state_feature_proposal_from_approved_financial_primitives",
                "risk_rule_guided_reward_shaping_as_training_objective_audit",
                "diagnostic_guided_refinement_using_rollout_metrics",
                "freeze_interface_before_out_of_sample_evaluation",
                "no_llm_query_or_prompt_update_at_test_time",
            ],
            "not_imported": [
                "llm_trading_agent",
                "ppo_live_allocator",
                "generated_code_without_review",
                "test_time_llm_updates",
                "automatic_rebalance",
                "automatic_target_weight_change",
            ],
        },
        "allowed_shadow_scope": {
            "llm_may_propose_features": True,
            "feature_primitives_must_be_allowlisted": True,
            "reward_terms_must_map_to_existing_risk_objectives": True,
            "human_code_review_required": True,
            "walk_forward_validation_required": True,
            "interface_must_be_frozen_before_oos": True,
            "llm_queries_allowed_at_test_time": False,
            "llm_actions_allowed": False,
        },
        "component_readiness": components,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "llm_state_reward_interface_ready": False,
            "feature_proposal_governance_imported": True,
            "reward_shaping_governance_imported": True,
            "diagnostic_refinement_governance_imported": True,
            "live_llm_trading_allowed": False,
            "live_ppo_allocator_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
            "summary": (
                "2606.08450 is useful for constrained research-interface governance only. "
                "Current GroupA+ gates block any live PPO/LLM allocator or weight change."
            ),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_readiness_{stamp}.json"


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
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(as_of=args.as_of)
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward interface readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "llm_state_reward_interface_ready": review["decision"]["llm_state_reward_interface_ready"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
