#!/usr/bin/env python3
"""Validate research-only LLM state/reward interface proposals against catalog."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_catalog.json"
DEFAULT_PROPOSALS = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_sample_proposals.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_proposal_validation_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_proposal_validation/history"


SAMPLE_PROPOSALS: list[dict[str, Any]] = [
    {
        "proposal_id": "gift_research_momentum_vol_drawdown_turnover_v1",
        "description": "Research-only feature/reward interface using momentum and volatility features.",
        "feature_families": ["momentum", "volatility"],
        "feature_primitives": ["relative_momentum", "realized_volatility"],
        "reward_terms": ["drawdown_penalty", "turnover_penalty"],
        "validation_flags": {
            "preserves_raw_market_input": True,
            "appends_features_only": True,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "references_future_data": False,
            "returns_finite_numeric_values": True,
            "parameters_clipped_to_allowed_ranges": True,
            "includes_human_review_note": True,
            "includes_walk_forward_plan": True,
            "freezes_interface_before_oos": True,
            "uses_test_time_llm_queries": False,
            "executes_generated_code_live": False,
            "uses_high_frequency_order_book": False,
            "uses_synthetic_alpha_without_validation": False,
            "ignores_market_impact_for_turnover": False,
        },
        "requested_live_effects": {
            "promote_to_live": False,
            "target_weight_change": False,
            "auto_rebalance": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
    },
    {
        "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
        "description": (
            "Research-only downside/tail interface using downside risk, volatility, "
            "and LETF tail-decay reward terms for offline diagnostics."
        ),
        "feature_families": ["downside_risk", "volatility", "trend_strength"],
        "feature_primitives": ["downside_deviation", "realized_volatility", "drawdown_depth", "ema_cross_strength"],
        "reward_terms": ["drawdown_penalty", "volatility_scaling", "letf_tail_decay_cost"],
        "validation_flags": {
            "preserves_raw_market_input": True,
            "appends_features_only": True,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "references_future_data": False,
            "returns_finite_numeric_values": True,
            "parameters_clipped_to_allowed_ranges": True,
            "includes_human_review_note": True,
            "includes_walk_forward_plan": True,
            "freezes_interface_before_oos": True,
            "uses_test_time_llm_queries": False,
            "executes_generated_code_live": False,
            "uses_high_frequency_order_book": False,
            "uses_synthetic_alpha_without_validation": False,
            "ignores_market_impact_for_turnover": False,
        },
        "requested_live_effects": {
            "promote_to_live": False,
            "target_weight_change": False,
            "auto_rebalance": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
    },
    {
        "proposal_id": "gift_research_high_dividend_active_pain_v1",
        "description": (
            "Research-only redesign proposal from drawdown event audit. It adds "
            "lagged high-dividend bucket active-pain features versus equal weight "
            "so reward shaping can penalize concentrated high-dividend overweights "
            "during drawdown failure regimes."
        ),
        "feature_families": ["bucket_active_pain", "downside_risk", "volatility"],
        "feature_primitives": [
            "active_bucket_weight",
            "active_bucket_return_contribution",
            "active_bucket_drawdown_depth",
            "reward_signal_concentration_hhi",
            "high_dividend_active_pain",
            "drawdown_depth",
            "realized_volatility",
        ],
        "reward_terms": ["active_bucket_drawdown_penalty", "drawdown_penalty", "concentration_penalty"],
        "validation_flags": {
            "preserves_raw_market_input": True,
            "appends_features_only": True,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "references_future_data": False,
            "returns_finite_numeric_values": True,
            "parameters_clipped_to_allowed_ranges": True,
            "includes_human_review_note": True,
            "includes_walk_forward_plan": True,
            "freezes_interface_before_oos": True,
            "uses_test_time_llm_queries": False,
            "executes_generated_code_live": False,
            "uses_high_frequency_order_book": False,
            "uses_synthetic_alpha_without_validation": False,
            "ignores_market_impact_for_turnover": False,
        },
        "requested_live_effects": {
            "promote_to_live": False,
            "target_weight_change": False,
            "auto_rebalance": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
    },
    {
        "proposal_id": "gift_reject_live_00631l_target_weight_v1",
        "description": "Invalid proposal that tries to output live 00631L target weight.",
        "feature_families": ["momentum", "volatility"],
        "feature_primitives": ["relative_momentum", "realized_volatility"],
        "reward_terms": ["drawdown_penalty", "turnover_penalty"],
        "validation_flags": {
            "preserves_raw_market_input": True,
            "appends_features_only": False,
            "outputs_actions": True,
            "outputs_target_weights": True,
            "references_future_data": False,
            "returns_finite_numeric_values": True,
            "parameters_clipped_to_allowed_ranges": True,
            "includes_human_review_note": False,
            "includes_walk_forward_plan": False,
            "freezes_interface_before_oos": False,
            "uses_test_time_llm_queries": True,
            "executes_generated_code_live": True,
            "uses_high_frequency_order_book": False,
            "uses_synthetic_alpha_without_validation": False,
            "ignores_market_impact_for_turnover": True,
        },
        "requested_live_effects": {
            "promote_to_live": True,
            "target_weight_change": True,
            "auto_rebalance": True,
            "allow_00631l_add": True,
            "allow_00632r_open": False,
        },
    },
]


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_proposals(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return SAMPLE_PROPOSALS
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    proposals = payload.get("proposals") if isinstance(payload, dict) else None
    if isinstance(proposals, list):
        return [item for item in proposals if isinstance(item, dict)]
    return []


def write_sample_proposals(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_type": "group_a_plus_llm_state_reward_interface_sample_proposals",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "proposals": SAMPLE_PROPOSALS,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _flag(flags: dict[str, Any], key: str) -> bool:
    return flags.get(key) is True


def validate_proposal(proposal: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    feature_allowlist = catalog.get("feature_allowlist") if isinstance(catalog.get("feature_allowlist"), dict) else {}
    reward_allowlist = catalog.get("reward_allowlist") if isinstance(catalog.get("reward_allowlist"), dict) else {}
    proposal_id = str(proposal.get("proposal_id") or "unnamed_proposal")
    families = _as_list(proposal.get("feature_families"))
    primitives = _as_list(proposal.get("feature_primitives"))
    reward_terms = _as_list(proposal.get("reward_terms"))
    flags = proposal.get("validation_flags") if isinstance(proposal.get("validation_flags"), dict) else {}
    live = proposal.get("requested_live_effects") if isinstance(proposal.get("requested_live_effects"), dict) else {}

    rejection_reasons: list[str] = []
    warning_reasons: list[str] = []

    unknown_families = sorted(set(families) - set(feature_allowlist))
    if unknown_families:
        rejection_reasons.append(f"unknown_feature_families:{','.join(unknown_families)}")

    allowed_primitives = {
        primitive
        for family in families
        for primitive in (feature_allowlist.get(family, {}).get("allowed_primitives") or [])
    }
    unknown_primitives = sorted(set(primitives) - allowed_primitives)
    if unknown_primitives:
        rejection_reasons.append(f"unknown_feature_primitives:{','.join(unknown_primitives)}")

    unknown_rewards = sorted(set(reward_terms) - set(reward_allowlist))
    if unknown_rewards:
        rejection_reasons.append(f"unknown_reward_terms:{','.join(unknown_rewards)}")

    required_true_flags = {
        "preserves_raw_market_input": "does_not_preserve_raw_market_input",
        "appends_features_only": "does_not_append_features_only",
        "returns_finite_numeric_values": "nonfinite_or_unverified_numeric_values",
        "parameters_clipped_to_allowed_ranges": "parameters_not_clipped_to_allowed_ranges",
        "includes_human_review_note": "missing_human_review_note",
        "includes_walk_forward_plan": "missing_walk_forward_plan",
        "freezes_interface_before_oos": "interface_not_frozen_before_oos",
    }
    for key, reason in required_true_flags.items():
        if not _flag(flags, key):
            rejection_reasons.append(reason)

    forbidden_true_flags = {
        "outputs_actions": "outputs_actions",
        "outputs_target_weights": "outputs_target_weights",
        "references_future_data": "references_future_data",
        "uses_test_time_llm_queries": "uses_test_time_llm_queries",
        "executes_generated_code_live": "executes_generated_code_live",
        "uses_high_frequency_order_book": "uses_high_frequency_order_book",
        "uses_synthetic_alpha_without_validation": "uses_synthetic_alpha_without_validation",
        "ignores_market_impact_for_turnover": "ignores_market_impact_for_turnover",
    }
    for key, reason in forbidden_true_flags.items():
        if _flag(flags, key):
            rejection_reasons.append(reason)

    for key in ["promote_to_live", "target_weight_change", "auto_rebalance", "allow_00631l_add", "allow_00632r_open"]:
        if live.get(key) is True:
            rejection_reasons.append(f"requested_live_effect:{key}")

    if not families:
        rejection_reasons.append("missing_feature_families")
    if not primitives:
        rejection_reasons.append("missing_feature_primitives")
    if not reward_terms:
        warning_reasons.append("missing_reward_terms")

    accepted = not rejection_reasons
    return {
        "proposal_id": proposal_id,
        "status": "accepted_for_offline_review" if accepted else "rejected",
        "accepted_for_offline_review": accepted,
        "rejection_reasons": sorted(set(rejection_reasons)),
        "warning_reasons": sorted(set(warning_reasons)),
        "feature_families": families,
        "feature_primitives": primitives,
        "reward_terms": reward_terms,
        "decision": {
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
    }


def build_review(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    proposals_path: Path = DEFAULT_PROPOSALS,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    catalog = _load(catalog_path)
    proposals = _load_proposals(proposals_path)
    results = [validate_proposal(proposal, catalog) for proposal in proposals]
    accepted = [result for result in results if result["accepted_for_offline_review"]]
    rejected = [result for result in results if not result["accepted_for_offline_review"]]
    missing_catalog = not catalog

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_proposal_validation_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if missing_catalog else "available_for_manual_offline_review",
        "policy": "research_only_proposal_validation_no_live_action",
        "inputs": {
            "catalog": str(catalog_path),
            "proposals": str(proposals_path),
            "catalog_exists": bool(catalog),
            "proposal_count": len(proposals),
        },
        "summary": {
            "accepted_for_offline_review_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted_proposal_ids": [result["proposal_id"] for result in accepted],
            "rejected_proposal_ids": [result["proposal_id"] for result in rejected],
        },
        "proposal_results": results,
        "decision": {
            "proposal_validation_available": bool(catalog),
            "offline_review_allowed_for_accepted_proposals": bool(accepted) and bool(catalog),
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
    return history_dir / f"llm_state_reward_interface_proposal_validation_{stamp}.json"


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
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--proposals", default=str(DEFAULT_PROPOSALS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--write-sample-proposals", action="store_true")
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    proposals_path = _resolve(args.proposals)
    if args.write_sample_proposals or not proposals_path.exists():
        write_sample_proposals(proposals_path)
    review = build_review(catalog_path=_resolve(args.catalog), proposals_path=proposals_path, as_of=args.as_of)
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward proposal validation review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "accepted": review["summary"]["accepted_for_offline_review_count"],
                "rejected": review["summary"]["rejected_count"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
