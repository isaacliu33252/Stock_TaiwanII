#!/usr/bin/env python3
"""Build a research-only DRL sample-efficiency readiness review for GroupA+.

Based on arXiv:2307.07694, which evaluates common DRL algorithms for
portfolio optimisation under noisy rewards, market impact, and regime changes.
This builder does not train or import an RL allocator. It records whether the
paper's prerequisites are satisfied before any live RL/fractional-Kelly-style
allocator could be considered.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_RL_GOVERNANCE = PROJECT_ROOT / "report/group_a_plus/latest/rl_governance_readiness_review.json"
DEFAULT_EXECUTION_PLAN_PY = PROJECT_ROOT / "group_a_plus/operations/execution_plan.py"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/drl_sample_efficiency_readiness_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/drl_sample_efficiency_readiness_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/drl_sample_efficiency_readiness/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _source_contains(path: Path, needle: str) -> bool:
    if not path.exists():
        return False
    return needle in path.read_text(encoding="utf-8")


def build_review(
    *,
    as_of: str,
    market_impact_path: Path,
    rl_governance_path: Path,
    execution_plan_py: Path,
) -> dict[str, Any]:
    market_impact = _load_json(market_impact_path)
    rl_governance = _load_json(rl_governance_path)

    staged_buys_present = _source_contains(execution_plan_py, "_apply_buy_staging")
    buy_fraction_present = _source_contains(execution_plan_py, "max_initial_buy_fraction")
    transaction_cost_present = _source_contains(execution_plan_py, "total_execution_cost")

    blockers: list[str] = []
    warnings: list[str] = []

    if not market_impact:
        blockers.append("missing_market_impact_readiness_review")
    elif market_impact.get("status") == "blocked":
        blockers.append("market_impact_readiness_blocked")

    if not rl_governance:
        blockers.append("missing_rl_governance_readiness_review")
    elif rl_governance.get("status") == "blocked":
        blockers.append("rl_governance_readiness_blocked")

    if _nested(rl_governance, "decision", "live_rl_allocator_allowed") is not False:
        warnings.append("rl_governance_does_not_explicitly_forbid_live_rl_allocator")
    if _nested(rl_governance, "governance_checklist", "live_exploration_forbidden") is not True:
        blockers.append("live_exploration_forbidden_gate_missing")

    if not staged_buys_present:
        blockers.append("staged_adjustment_mechanism_missing")
    if not buy_fraction_present:
        blockers.append("fractional_initial_buy_control_missing")
    if not transaction_cost_present:
        blockers.append("execution_transaction_cost_logging_missing")

    # The paper reports roughly 2m simulator steps for PPO in its simplest
    # low-impact setting, which it translates to nearly 8,000 years of daily
    # observations. GroupA+ cannot meet that with real Taiwan ETF history.
    blockers.append("paper_sample_efficiency_requirement_not_satisfied_by_real_market_history")
    blockers.append("no_local_resettable_market_simulator_validated_for_training_live_rl")
    blockers.append("no_noisy_reward_q_function_diagnostic_for_off_policy_rl")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_drl_sample_efficiency_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "research_ready",
        "policy": "research_only_drl_sample_efficiency_no_live_policy_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2307.07694.pdf",
            "title": "Evaluation of Deep Reinforcement Learning Algorithms for Portfolio Optimisation",
            "arxiv": "2307.07694v3",
            "paper_date": "2025-08-07",
            "imported_concepts": [
                "do_not_promote_sample_inefficient_drl_on_real_market_history",
                "prefer_on_policy_stability_diagnostics_if_rl_is_researched",
                "explicit_noisy_reward_and_q_function_failure_check",
                "market_impact_and_transaction_cost_must_be_part_of_any_rl_gate",
                "fractional_kelly_and_staged_adjustment_as_execution_primitives",
                "regime_context_required_before_any_regime_switching_allocator",
            ],
            "not_imported": [
                "PPO_allocator",
                "A2C_allocator",
                "DDPG_TD3_SAC_allocator",
                "GBM_Bertsimas_Lo_training_simulator",
                "HMM_context_network_for_live_weights",
                "shorting_or_levered_Kelly_weights",
                "automatic_target_weight_change",
                "automatic_rebalance",
            ],
        },
        "paper_findings_relevant_to_group_a_plus": {
            "off_policy_noisy_reward_failure": True,
            "ppo_clip_and_gae_help_stability": True,
            "sample_complexity_too_high_for_real_data": True,
            "market_impact_pushes_policy_toward_fractional_kelly": True,
            "regime_context_can_help_but_needs_validation": True,
        },
        "local_capability_check": {
            "market_impact_review": {
                "path": str(market_impact_path),
                "exists": bool(market_impact),
                "status": market_impact.get("status"),
                "turnover": _nested(market_impact, "computed", "turnover"),
                "max_participation_of_volume": _nested(market_impact, "computed", "max_participation_of_volume"),
                "auto_rebalance_allowed": _nested(market_impact, "decision", "auto_rebalance_allowed"),
            },
            "rl_governance_review": {
                "path": str(rl_governance_path),
                "exists": bool(rl_governance),
                "status": rl_governance.get("status"),
                "live_rl_allocator_allowed": _nested(rl_governance, "decision", "live_rl_allocator_allowed"),
                "live_exploration_forbidden": _nested(
                    rl_governance, "governance_checklist", "live_exploration_forbidden"
                ),
            },
            "execution_plan_primitives": {
                "path": str(execution_plan_py),
                "staged_buys_present": staged_buys_present,
                "buy_fraction_control_present": buy_fraction_present,
                "transaction_cost_logging_present": transaction_cost_present,
            },
        },
        "decision": {
            "drl_allocator_promotable": False,
            "ppo_or_a2c_research_allowed": False,
            "off_policy_drl_research_priority": "low",
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
            "recommended_use": "governance_blocker_and_shadow_design_reference",
            "summary": (
                "The paper argues against live DRL promotion under current data limits. "
                "GroupA+ should borrow staged/fractional execution and noisy-reward governance ideas only."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {
            "market_impact_readiness": str(market_impact_path),
            "rl_governance_readiness": str(rl_governance_path),
            "execution_plan_py": str(execution_plan_py),
        },
    }


def _write_md(review: dict[str, Any], path: Path) -> None:
    local = review["local_capability_check"]
    lines = [
        "# 2307.07694 DRL Sample-Efficiency Readiness Review",
        "",
        f"- Generated: `{review['generated_at']}`",
        f"- Status: `{review['status']}`",
        f"- Policy: `{review['policy']}`",
        f"- Recommended use: `{review['decision']['recommended_use']}`",
        "",
        "## Decision",
        "",
        f"- DRL allocator promotable: `{review['decision']['drl_allocator_promotable']}`",
        f"- Target weight change allowed: `{review['decision']['target_weight_change_allowed']}`",
        f"- Auto rebalance allowed: `{review['decision']['auto_rebalance_allowed']}`",
        f"- Keep golden1_0531 unchanged: `{review['decision']['keep_golden1_0531_unchanged']}`",
        "",
        "## Local Checks",
        "",
        f"- Market impact status: `{local['market_impact_review']['status']}`",
        f"- RL governance status: `{local['rl_governance_review']['status']}`",
        f"- Staged buys present: `{local['execution_plan_primitives']['staged_buys_present']}`",
        f"- Buy fraction control present: `{local['execution_plan_primitives']['buy_fraction_control_present']}`",
        f"- Transaction cost logging present: `{local['execution_plan_primitives']['transaction_cost_logging_present']}`",
        "",
        "## Blocking Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in review["blocking_reasons"])
    lines.extend(
        [
            "",
            "## Import Decision",
            "",
            "- Do not import PPO/A2C/DDPG/TD3/SAC into GroupA+ latest.",
            "- Do not replace golden1_0531 or a2118 target weights.",
            "- Keep market-impact, staged execution, and RL governance ideas as blockers/advisory checks only.",
            "- No live strategy, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_review(review: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(review, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(review["as_of"]).replace("-", "")
        (history_dir / f"drl_sample_efficiency_readiness_{stamp}.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--market-impact-readiness", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--rl-governance-readiness", default=str(DEFAULT_RL_GOVERNANCE))
    parser.add_argument("--execution-plan-py", default=str(DEFAULT_EXECUTION_PLAN_PY))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    review = build_review(
        as_of=str(args.as_of),
        market_impact_path=_resolve(args.market_impact_readiness),
        rl_governance_path=_resolve(args.rl_governance_readiness),
        execution_plan_py=_resolve(args.execution_plan_py),
    )
    write_review(
        review,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "status": review["status"],
                "drl_allocator_promotable": review["decision"]["drl_allocator_promotable"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
