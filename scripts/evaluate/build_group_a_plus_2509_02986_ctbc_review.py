#!/usr/bin/env python3
"""Review arXiv 2509.02986 CTBC ideas for GroupA++.

Research-only. The paper is a robotics/control paper, so this script records
only transferable engineering patterns. It never changes live weights, golden
artifacts, strategy manifests, signals, or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAPER = Path("/mnt/c/Users/isaac/Downloads/2509.02986.pdf")
DEFAULT_STRATEGY = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_groupa_plusplus_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_groupa_plusplus_review.md"
DEFAULT_DEBOUNCE = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_debounce_shadow.json"
DEFAULT_00713_DEBOUNCE = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_00713_debounce_shadow.json"
DEFAULT_DOMAIN_RANDOMIZATION = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_00713_domain_randomization.json"
DEFAULT_PROMOTION_READINESS = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_promotion_readiness_gate.json"


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_report(
    paper_path: Path,
    strategy_path: Path,
    debounce_path: Path,
    debounce_00713_path: Path,
    domain_randomization_path: Path,
    promotion_readiness_path: Path,
) -> dict[str, Any]:
    strategy = _load_json(strategy_path)
    debounce = _load_json(debounce_path)
    debounce_00713 = _load_json(debounce_00713_path)
    domain_randomization = _load_json(domain_randomization_path)
    promotion_readiness = _load_json(promotion_readiness_path)
    active = strategy.get("active_strategy", {}) if isinstance(strategy.get("active_strategy"), dict) else {}
    params = active.get("runner_params", {}) if isinstance(active.get("runner_params"), dict) else {}
    debounce_decision = debounce.get("decision", {}) if isinstance(debounce.get("decision"), dict) else {}
    debounce_00713_decision = (
        debounce_00713.get("decision", {}) if isinstance(debounce_00713.get("decision"), dict) else {}
    )
    domain_randomization_decision = (
        domain_randomization.get("decision", {}) if isinstance(domain_randomization.get("decision"), dict) else {}
    )
    promotion_readiness_decision = (
        promotion_readiness.get("decision", {}) if isinstance(promotion_readiness.get("decision"), dict) else {}
    )

    transferable = [
        {
            "idea": "contact_triggered_event_controller",
            "paper_basis": "CTBC activates leg-lifting rewards and feedforward motion only after contact force crosses a threshold.",
            "group_a_plusplus_mapping": (
                "Use event-triggered shadow controllers for actual market contact events such as realized drawdown, "
                "gap-down, liquidity stress, stale-data contact, or broker-fill friction. Do not let the controller "
                "fire from a pure forecast without an observed contact condition."
            ),
            "recommended_status": "candidate_shadow",
            "latest_strategy_change": False,
            "why": "This matches groupA++ better than a continuous always-on overlay and reduces unnecessary churn.",
        },
        {
            "idea": "sliding_window_trigger_debounce",
            "paper_basis": "The paper uses a short sliding window to suppress contact flicker before confirming stable contact.",
            "group_a_plusplus_mapping": (
                "Test 2-of-3 or 3-of-3 confirmation for slow actions such as no-add, re-entry, and 00713 sleeve disablement. "
                "Do not apply it blindly to emergency de-risking because confirmation can delay protection."
            ),
            "recommended_status": (
                "tested_do_not_promote"
                if debounce_decision
                and debounce.get("source_paper", {}).get("transferred_idea") == "sliding_window_trigger_debounce"
                else "candidate_shadow"
            ),
            "latest_strategy_change": False,
            "why": (
                "Implemented as 00631L no-add debounce shadow; strict gate did not pass, so it remains research-only."
                if debounce_decision
                else "Useful as a noise filter, but only where delayed action is acceptable."
            ),
        },
        {
            "idea": "feedforward_instruction_warm_start",
            "paper_basis": "CTBC guides exploration with a hand-designed feedforward trajectory, then anneals it away.",
            "group_a_plusplus_mapping": (
                "For future RL or learned micro-tilt agents, initialize behavior near the current latest strategy "
                "or Golden1 policy and anneal the imitation weight during shadow training."
            ),
            "recommended_status": "training_governance_candidate",
            "latest_strategy_change": False,
            "why": "This can reduce exploration damage in training; it is not evidence for changing live allocation.",
        },
        {
            "idea": "asymmetric_actor_critic_privileged_training",
            "paper_basis": "The critic sees privileged information during training while the actor uses deployable observations.",
            "group_a_plusplus_mapping": (
                "Allow shadow critics to use ex-post labels, realized future drawdown diagnostics, and full-cost attribution "
                "for training diagnostics, while live actors/signals remain limited to point-in-time features."
            ),
            "recommended_status": "research_only_design_pattern",
            "latest_strategy_change": False,
            "why": "This is compatible with no-leakage governance only if the actor's production inputs are audited separately.",
        },
        {
            "idea": "domain_randomization_for_strategy_robustness",
            "paper_basis": "The robot policy is trained with randomized mass, friction, restitution, torque, sensor offset, and delay.",
            "group_a_plusplus_mapping": (
                "Add robustness sweeps for transaction costs, execution delay, price slippage, missing chip/news data, "
                "stale TDCC rows, NCF probability perturbation, and capital-size scaling before any new overlay is promoted."
            ),
            "recommended_status": "can_import_as_validation_requirement",
            "latest_strategy_change": False,
            "why": "This is the paper's strongest transferable point and fits existing multi-window promotion gates.",
        },
        {
            "idea": "component_ablation_and_seed_stability",
            "paper_basis": "The paper compares full CTBC against no-feedforward, no-contact-trigger, and no-both variants across seeds.",
            "group_a_plusplus_mapping": (
                "Any paper-inspired GroupA++ candidate should report full, no-trigger, no-guidance, and baseline variants "
                "with at least three seed or window slices before promotion review."
            ),
            "recommended_status": "can_import_as_research_checklist",
            "latest_strategy_change": False,
            "why": "Prevents attributing gains to the wrong component.",
        },
    ]

    blocked = [
        {
            "idea": "direct_rl_policy_import",
            "reason": "The paper controls robot joints in a physics simulator; it does not model market returns, ETF flows, portfolio PnL, or transaction costs.",
        },
        {
            "idea": "contact_force_threshold_as_market_signal",
            "reason": "Robot contact force has no direct market analogue. Trading triggers must be rebuilt from observed market/account states.",
        },
        {
            "idea": "blind_policy_as_no_news_rule",
            "reason": "Blind locomotion means no vision sensor; it does not imply financial news/chip/external features should be removed.",
        },
        {
            "idea": "zero_shot_transfer_to_live_strategy",
            "reason": "The paper validates sim-to-real hardware transfer; groupA++ requires purged walk-forward, cost, capital, and multi-window portfolio validation.",
        },
    ]

    checks = {
        "paper_is_finance_or_trading": False,
        "direct_alpha_claim_available": False,
        "portfolio_pnl_evidence_available": False,
        "transferable_control_patterns_available": True,
        "latest_strategy_change_allowed": False,
        "golden_change_allowed": False,
        "shadow_only_review_complete": True,
    }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2509_02986_ctbc_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "path": str(paper_path),
            "arxiv_id": "2509.02986",
            "title": "CTBC: Contact-Triggered Blind Climbing for Wheeled Bipedal Robots with Instruction Learning and Reinforcement Learning",
            "domain": "robotics_control_reinforcement_learning",
            "main_claims_used": [
                "Contact-triggered task decomposition activates special behavior only after obstacle contact.",
                "Feedforward instruction learning guides exploration and is annealed away.",
                "An asymmetric actor-critic separates deployable observations from privileged training information.",
                "Domain randomization improves zero-shot transfer robustness.",
                "Ablations remove feedforward and contact-trigger components to isolate contribution.",
            ],
        },
        "current_group_a_plusplus_context": {
            "strategy_path": _rel(strategy_path),
            "active_strategy_id": active.get("id"),
            "ncf_00631l_panel": params.get("ncf_panel_631l_path"),
            "ncf_00713_path": params.get("ncf_00713_path"),
            "cash_sleeve_00713_weight_param": params.get("group_a_plusplus_00713_cash_sleeve_weight"),
            "ncf_00713_enabled": params.get("group_a_plusplus_00713_ncf_enabled"),
        },
        "implemented_shadow_artifacts": {
            "ctbc_debounce_shadow": _rel(debounce_path) if debounce_path.exists() else None,
            "ctbc_debounce_decision": debounce_decision.get("decision"),
            "ctbc_debounce_best_candidate": debounce_decision.get("best_candidate"),
            "ctbc_debounce_strict_passed": debounce_decision.get("strict_debounce_gate_passed"),
            "ctbc_00713_debounce_shadow": _rel(debounce_00713_path) if debounce_00713_path.exists() else None,
            "ctbc_00713_debounce_decision": debounce_00713_decision.get("decision"),
            "ctbc_00713_debounce_best_variant": debounce_00713_decision.get("best_variant"),
            "ctbc_00713_debounce_strict_passed": debounce_00713_decision.get("strict_debounce_gate_passed"),
            "ctbc_00713_domain_randomization": _rel(domain_randomization_path)
            if domain_randomization_path.exists()
            else None,
            "ctbc_00713_domain_randomization_decision": domain_randomization_decision.get("decision"),
            "ctbc_00713_domain_randomization_best_variant": domain_randomization_decision.get("best_variant"),
            "ctbc_00713_domain_randomization_strict_passed": domain_randomization_decision.get(
                "strict_robustness_passed"
            ),
            "ctbc_promotion_readiness_gate": _rel(promotion_readiness_path)
            if promotion_readiness_path.exists()
            else None,
            "ctbc_promotion_readiness_decision": promotion_readiness_decision.get("decision"),
            "ctbc_promotion_readiness_allowed": promotion_readiness_decision.get("promotion_allowed"),
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "changes_ncf_live_gate": False,
        "checks": checks,
        "transfer_candidates": transferable,
        "blocked_or_deferred_items": blocked,
        "decision": {
            "promotion_allowed_now": False,
            "latest_strategy_weight_change_allowed": False,
            "recommended_import_now": [
                "domain_randomization_for_strategy_robustness_as_validation_requirement",
                "component_ablation_and_seed_stability_as_research_checklist",
            ],
            "recommended_shadow_experiments": [
                "feedforward_warm_start_for_future_rl_micro_tilt_shadow",
            ],
            "reason": (
                "The paper is useful as a control/governance analogy, but it provides no direct financial alpha, "
                "no ETF allocation result, and no evidence that live groupA++ weights should change."
            ),
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    decision = report["decision"]
    lines = [
        "# 2509.02986 CTBC GroupA++ Review",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `research_only_no_weight_change`",
        f"- Promotion allowed now: `{decision['promotion_allowed_now']}`",
        f"- Latest strategy weight change allowed: `{decision['latest_strategy_weight_change_allowed']}`",
        f"- Golden1 unchanged: `{not report['changes_golden1_0531']}`",
        f"- Golden2 unchanged: `{not report['changes_golden2_0830']}`",
        "",
        "## Paper Identity",
        "",
        f"- Title: {report['source_paper']['title']}",
        f"- Domain: `{report['source_paper']['domain']}`",
        f"- Path: `{report['source_paper']['path']}`",
        "",
        "## Current Context",
        "",
        f"- Active strategy: `{report['current_group_a_plusplus_context']['active_strategy_id']}`",
        f"- NCF00631L panel: `{report['current_group_a_plusplus_context']['ncf_00631l_panel']}`",
        f"- NCF00713 path: `{report['current_group_a_plusplus_context']['ncf_00713_path']}`",
        "",
        "## Implemented Shadow",
        "",
        f"- CTBC debounce shadow: `{report['implemented_shadow_artifacts']['ctbc_debounce_shadow']}`",
        f"- Debounce decision: `{report['implemented_shadow_artifacts']['ctbc_debounce_decision']}`",
        f"- Debounce best candidate: `{report['implemented_shadow_artifacts']['ctbc_debounce_best_candidate']}`",
        f"- Debounce strict passed: `{report['implemented_shadow_artifacts']['ctbc_debounce_strict_passed']}`",
        f"- 00713 debounce shadow: `{report['implemented_shadow_artifacts']['ctbc_00713_debounce_shadow']}`",
        f"- 00713 debounce decision: `{report['implemented_shadow_artifacts']['ctbc_00713_debounce_decision']}`",
        f"- 00713 debounce best variant: `{report['implemented_shadow_artifacts']['ctbc_00713_debounce_best_variant']}`",
        f"- 00713 debounce strict passed: `{report['implemented_shadow_artifacts']['ctbc_00713_debounce_strict_passed']}`",
        f"- 00713 domain randomization: `{report['implemented_shadow_artifacts']['ctbc_00713_domain_randomization']}`",
        f"- 00713 domain randomization decision: `{report['implemented_shadow_artifacts']['ctbc_00713_domain_randomization_decision']}`",
        f"- 00713 domain randomization strict passed: `{report['implemented_shadow_artifacts']['ctbc_00713_domain_randomization_strict_passed']}`",
        f"- Promotion readiness gate: `{report['implemented_shadow_artifacts']['ctbc_promotion_readiness_gate']}`",
        f"- Promotion readiness decision: `{report['implemented_shadow_artifacts']['ctbc_promotion_readiness_decision']}`",
        f"- Promotion readiness allowed: `{report['implemented_shadow_artifacts']['ctbc_promotion_readiness_allowed']}`",
        "",
        "## Transfer Candidates",
        "",
        "| idea | status | latest strategy change | use |",
        "|---|---|---:|---|",
    ]
    for item in report["transfer_candidates"]:
        lines.append(
            f"| `{item['idea']}` | `{item['recommended_status']}` | `{item['latest_strategy_change']}` | {item['group_a_plusplus_mapping']} |"
        )

    lines.extend(
        [
            "",
            "## Blocked Or Deferred",
            "",
            "| idea | reason |",
            "|---|---|",
        ]
    )
    for item in report["blocked_or_deferred_items"]:
        lines.append(f"| `{item['idea']}` | {item['reason']} |")

    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | pass |",
            "|---|---:|",
        ]
    )
    for name, passed in report["checks"].items():
        lines.append(f"| `{name}` | `{passed}` |")

    lines.extend(
        [
            "",
            "## Final Decision",
            "",
            f"- Recommended import now: `{', '.join(decision['recommended_import_now'])}`",
            f"- Recommended shadow experiments: `{', '.join(decision['recommended_shadow_experiments'])}`",
            f"- Reason: {decision['reason']}",
            "",
            "This report is research-only. It does not emit trades, target weights, NCF gates, or order-generation changes.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(report: dict[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", default=str(DEFAULT_PAPER))
    parser.add_argument("--strategy", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--debounce", default=str(DEFAULT_DEBOUNCE))
    parser.add_argument("--debounce-00713", default=str(DEFAULT_00713_DEBOUNCE))
    parser.add_argument("--domain-randomization", default=str(DEFAULT_DOMAIN_RANDOMIZATION))
    parser.add_argument("--promotion-readiness", default=str(DEFAULT_PROMOTION_READINESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(
        Path(args.paper),
        Path(args.strategy),
        Path(args.debounce),
        Path(args.debounce_00713),
        Path(args.domain_randomization),
        Path(args.promotion_readiness),
    )
    write_outputs(report, Path(args.output), Path(args.markdown))
    print(
        "decision=research_only_no_weight_change "
        f"promotion_allowed={report['decision']['promotion_allowed_now']} "
        f"candidates={len(report['transfer_candidates'])}"
    )


if __name__ == "__main__":
    main()
