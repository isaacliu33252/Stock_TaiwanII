#!/usr/bin/env python3
"""Define the GroupA+ live hedge policy boundary for 00632R.

The policy can document what would be required for manual hedge discussion, but
it explicitly forbids automatic 00632R orders, target weights, and rebalance.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANUAL_HEDGE = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_manual_hedge_eligibility_review.json"
)
DEFAULT_TAIL_GATE = PROJECT_ROOT / "report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json"
DEFAULT_EFFECTIVE_FEE = PROJECT_ROOT / "report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/live_hedge_policy_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/live_hedge_policy/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    return decision if isinstance(decision, dict) else {}


def _check(name: str, passed: bool, *, value: Any = None, threshold: Any = None, blocker: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "value": value,
        "threshold": threshold,
        "blocking_reason_if_failed": blocker or name,
    }


def build_review(
    *,
    manual_hedge_path: Path = DEFAULT_MANUAL_HEDGE,
    tail_gate_path: Path = DEFAULT_TAIL_GATE,
    effective_fee_path: Path = DEFAULT_EFFECTIVE_FEE,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    manual_hedge = _load(manual_hedge_path)
    tail_gate = _load(tail_gate_path)
    effective_fee = _load(effective_fee_path)
    manual_decision = _decision(manual_hedge)
    tail_decision = _decision(tail_gate)
    fee_decision = _decision(effective_fee)

    policy_rules = {
        "scope": "manual_discussion_policy_only",
        "target_ticker": "00632R.TW",
        "benchmark_ticker": "0050.TW",
        "minimum_conditions_before_discussion": [
            "manual_hedge_eligibility_review_allows_discussion",
            "tail_gate_manual_discussion_tier_passes",
            "effective_fee_proxy_validated_for_manual_review",
            "market_impact_and_research_shadow_no_longer_block",
            "human_operator_confirms_risk_budget",
        ],
        "hard_prohibitions": [
            "no_llm_generated_order",
            "no_ppo_or_rl_allocator_order",
            "no_script_generated_target_weight",
            "no_auto_rebalance",
            "no_market_order_instruction",
            "no_position_open_without_manual_broker_action",
        ],
        "manual_discussion_bounds_if_all_future_gates_pass": {
            "max_initial_00632r_weight_note": "policy placeholder only; no target weight emitted",
            "max_holding_days_note": "policy placeholder only; no trade lifecycle emitted",
            "exit_conditions_note": "must be separately approved; no automated exit emitted",
        },
    }

    checks = [
        _check(
            "manual_hedge_policy_text_defined",
            True,
            value=True,
            threshold=True,
        ),
        _check(
            "policy_forbids_automatic_orders",
            True,
            value=policy_rules["hard_prohibitions"],
            threshold="contains no order/no target/no rebalance prohibitions",
        ),
        _check(
            "manual_hedge_eligibility_allows_discussion",
            manual_decision.get("manual_hedge_discussion_allowed") is True,
            value=manual_decision.get("manual_hedge_discussion_allowed"),
            threshold=True,
            blocker="manual_hedge_eligibility_blocks_discussion",
        ),
        _check(
            "tail_gate_manual_discussion_tier_passes",
            tail_decision.get("manual_discussion_tail_gate_passed") is True,
            value=tail_decision.get("manual_discussion_tail_gate_passed"),
            threshold=True,
            blocker="tail_gate_manual_discussion_tier_not_passed",
        ),
        _check(
            "effective_fee_proxy_validated_for_manual_review",
            fee_decision.get("effective_fee_proxy_validated_for_manual_review") is True,
            value=fee_decision.get("effective_fee_proxy_validated_for_manual_review"),
            threshold=True,
            blocker="effective_fee_proxy_not_validated_for_manual_review",
        ),
    ]

    blockers = [check["blocking_reason_if_failed"] for check in checks if not check["passed"]]
    policy_defined = True
    policy_validated_for_manual_discussion = not blockers

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_live_hedge_policy_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked",
        "policy": "define_manual_hedge_policy_boundary_no_live_permission",
        "inputs": {
            "manual_hedge_eligibility": str(manual_hedge_path),
            "tail_tracking_error_gate": str(tail_gate_path),
            "effective_fee_proxy_validation": str(effective_fee_path),
        },
        "policy_rules": policy_rules,
        "checks": checks,
        "summary": {
            "policy_defined": policy_defined,
            "policy_validated_for_manual_discussion": policy_validated_for_manual_discussion,
            "failed_check_count": len(blockers),
            "manual_hedge_discussion_allowed": False,
            "live_hedge_policy_validated": False,
        },
        "blocking_reasons": sorted(set(blockers + ["live_hedge_policy_not_validated_for_live_action"])),
        "warning_reasons": [
            "policy_definition_does_not_unlock_live_hedge",
            "future_manual_discussion_still_requires_all_external_gates",
        ],
        "interpretation": [
            "The policy boundary is now explicit: even perfect evidence cannot create an automatic 00632R order.",
            "Current evidence gates still fail, especially effective-fee proxy validation.",
            "This artifact reduces ambiguity but intentionally leaves live hedge validation false.",
        ],
        "decision": {
            "policy_defined": policy_defined,
            "live_hedge_policy_validated": False,
            "manual_hedge_discussion_allowed": False,
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
    return history_dir / f"live_hedge_policy_{stamp}.json"


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
    parser.add_argument("--manual-hedge", default=str(DEFAULT_MANUAL_HEDGE))
    parser.add_argument("--tail-gate", default=str(DEFAULT_TAIL_GATE))
    parser.add_argument("--effective-fee", default=str(DEFAULT_EFFECTIVE_FEE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        manual_hedge_path=_resolve(args.manual_hedge),
        tail_gate_path=_resolve(args.tail_gate),
        effective_fee_path=_resolve(args.effective_fee),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"Live hedge policy review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "policy_defined": review["summary"]["policy_defined"],
                "live_hedge_policy_validated": review["summary"]["live_hedge_policy_validated"],
                "manual_hedge_discussion_allowed": review["summary"]["manual_hedge_discussion_allowed"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
