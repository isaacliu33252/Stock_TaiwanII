#!/usr/bin/env python3
"""Build a research-only RL/ML governance readiness review for GroupA+.

Inspired by arXiv 2512.10913. This consolidates existing governance artifacts
before any RL/ML component can be promoted. It never changes target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEPLOYMENT = PROJECT_ROOT / "report/group_a_plus/latest/deployment_consistency_review.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_SYNTHETIC = PROJECT_ROOT / "report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json"
DEFAULT_DYNAMIC_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_INTERVENTION = PROJECT_ROOT / "report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json"
DEFAULT_RESEARCH = PROJECT_ROOT / "report/group_a_plus/latest/research_shadow_decision_snapshot.json"
DEFAULT_ADVERSARIAL = PROJECT_ROOT / "report/group_a_plus/latest/adversarial_market_integrity_review.json"
DEFAULT_FINSTRESSTS = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_decision_snapshot.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/rl_governance_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/rl_governance_readiness/history"


CORE_INPUTS = {
    "deployment_consistency": DEFAULT_DEPLOYMENT,
    "market_impact_readiness": DEFAULT_MARKET_IMPACT,
    "synthetic_augmentation_validation": DEFAULT_SYNTHETIC,
    "dynamic_cvar_tail_cost": DEFAULT_DYNAMIC_CVAR,
    "intervention_fatigue_risk_budget": DEFAULT_INTERVENTION,
    "research_shadow_decision_snapshot": DEFAULT_RESEARCH,
    "adversarial_market_integrity": DEFAULT_ADVERSARIAL,
    "finstressts_decision_snapshot": DEFAULT_FINSTRESSTS,
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
        "policy": payload.get("policy"),
        "blocking_reasons": payload.get("blocking_reasons") or [],
        "warning_reasons": payload.get("warning_reasons") or [],
        "decision": {
            "promote_to_live": decision.get("promote_to_live"),
            "promotion_allowed": decision.get("promotion_allowed"),
            "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
            "auto_rebalance_allowed": decision.get("auto_rebalance_allowed"),
            "allow_00631l_add": decision.get("allow_00631l_add"),
            "allow_00632r_open": decision.get("allow_00632r_open"),
            "broker_actionable": decision.get("broker_actionable"),
        },
        "key_metrics": _key_metrics(name, payload),
    }


def _key_metrics(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "deployment_consistency":
        return {
            "broker_actionable": _nested(payload, "decision", "broker_actionable"),
            "manual_review_required": _nested(payload, "decision", "manual_review_required"),
        }
    if name == "market_impact_readiness":
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
    if name == "intervention_fatigue_risk_budget":
        return {
            "intervention_fatigue_ready": _nested(payload, "decision", "intervention_fatigue_ready"),
            "risk_budget_pacing_ready": _nested(payload, "decision", "risk_budget_pacing_ready"),
        }
    if name == "research_shadow_decision_snapshot":
        return {
            "status": payload.get("status"),
            "allow_00631l_add": _nested(payload, "decision", "allow_00631l_add"),
        }
    if name == "adversarial_market_integrity":
        return {
            "market_integrity_ready": _nested(payload, "decision", "market_integrity_ready"),
            "single_model_auto_execution_allowed": _nested(
                payload, "decision", "single_model_auto_execution_allowed"
            ),
        }
    if name == "finstressts_decision_snapshot":
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
        if payload.get("status") in {"manual_review_required", "warning", "warn"}:
            warnings.append(f"{name}_manual_review_or_warning")
        decision = _decision(payload)
        if decision.get("promote_to_live") is True or decision.get("promotion_allowed") is True:
            warnings.append(f"{name}_reports_promotion_allowed_unexpected")
        if decision.get("target_weight_change_allowed") is True:
            warnings.append(f"{name}_reports_target_weight_change_allowed_unexpected")
        if decision.get("auto_rebalance_allowed") is True:
            warnings.append(f"{name}_reports_auto_rebalance_allowed_unexpected")

    deployment = payloads.get("deployment_consistency") or {}
    if _nested(deployment, "decision", "broker_actionable") is not True:
        blockers.append("deployment_not_broker_actionable")
    if _nested(payloads.get("market_impact_readiness") or {}, "decision", "market_impact_ready") is not True:
        blockers.append("market_impact_not_ready_for_rl_promotion")
    if _nested(payloads.get("synthetic_augmentation_validation") or {}, "decision", "synthetic_validation_ready") is not True:
        blockers.append("synthetic_validation_not_ready_for_rl_promotion")
    if _nested(payloads.get("dynamic_cvar_tail_cost") or {}, "decision", "tail_cost_readiness_ready") is not True:
        blockers.append("tail_cost_readiness_not_ready_for_rl_promotion")
    if _nested(payloads.get("intervention_fatigue_risk_budget") or {}, "decision", "risk_budget_pacing_ready") is not True:
        blockers.append("risk_budget_pacing_not_ready_for_rl_promotion")
    if (payloads.get("research_shadow_decision_snapshot") or {}).get("status") == "blocked":
        blockers.append("research_shadow_snapshot_blocked")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_rl_governance_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "research_ready",
        "policy": "research_only_rl_ml_governance_no_live_policy_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.10913.pdf",
            "title": (
                "Reinforcement Learning in Financial Decision Making: A Systematic Review of "
                "Performance, Challenges, and Implementation Strategies"
            ),
            "arxiv": "2512.10913v1",
            "imported_concepts": [
                "implementation_quality_over_algorithm_complexity",
                "domain_knowledge_and_data_quality_priority",
                "explainability_and_auditability_requirement",
                "robustness_to_nonstationary_market_regimes",
                "standardized_benchmarking_before_promotion",
                "deployment_feasibility_and_risk_management_first",
            ],
            "not_imported": [
                "live_rl_allocator",
                "market_making_rl_policy",
                "cryptocurrency_rl_results",
                "high_frequency_order_book_assumptions",
                "automatic_target_weight_change",
                "automatic_rebalance",
            ],
        },
        "governance_checklist": {
            "explainability_required": True,
            "audit_trail_required": True,
            "crash_window_validation_required": True,
            "false_positive_audit_required": True,
            "transaction_cost_and_turnover_required": True,
            "market_impact_required": True,
            "risk_budget_pacing_required": True,
            "deployment_consistency_required": True,
            "data_freshness_and_model_drift_required": True,
            "live_exploration_forbidden": True,
        },
        "component_readiness": components,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "rl_governance_ready": False,
            "rl_component_promotable": False,
            "live_rl_allocator_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
            "summary": (
                "2512.10913 supports RL/ML governance discipline only. Current GroupA+ artifacts "
                "do not clear the promotion gates for any live RL allocator or automatic policy."
            ),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"rl_governance_readiness_{stamp}.json"


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
    for name, path in CORE_INPUTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", default=str(path))
    args = parser.parse_args()

    input_paths = {name: _resolve(getattr(args, name)) for name in CORE_INPUTS}
    review = build_review(input_paths, as_of=args.as_of)
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"RL governance readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "rl_component_promotable": review["decision"]["rl_component_promotable"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
