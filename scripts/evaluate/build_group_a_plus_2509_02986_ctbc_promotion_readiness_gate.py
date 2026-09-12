#!/usr/bin/env python3
"""Build a CTBC-inspired promotion-readiness gate for GroupA++ candidates.

Research/governance only. arXiv:2509.02986 is a robotics control paper, so the
only production-useful transfer is a stricter validation checklist:

- trigger/component ablation
- short-window trigger debounce audit
- window/seed stability
- deployment input separation
- robustness/domain-randomization stress

This script records those checks for the CTBC-derived experiments and produces
an explicit "do not promote" decision when any requirement is missing. It never
changes live weights, golden artifacts, NCF gates, strategy manifests, or order
generation.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_groupa_plusplus_review.json"
DEFAULT_DEBOUNCE_00631L = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_debounce_shadow.json"
DEFAULT_DEBOUNCE_00713 = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_00713_debounce_shadow.json"
DEFAULT_DOMAIN_RANDOMIZATION = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_00713_domain_randomization.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_promotion_readiness_gate.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_promotion_readiness_gate.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _summary(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _candidate_names(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def build_gate(
    review_path: Path,
    debounce_00631l_path: Path,
    debounce_00713_path: Path,
    domain_randomization_path: Path,
) -> dict[str, Any]:
    review = _load_json(review_path)
    deb_00631l = _load_json(debounce_00631l_path)
    deb_00713 = _load_json(debounce_00713_path)
    domain_randomization = _load_json(domain_randomization_path)

    review_decision = _decision(review)
    deb_00631l_decision = _decision(deb_00631l)
    deb_00713_decision = _decision(deb_00713)
    domain_randomization_decision = _decision(domain_randomization)
    deb_00631l_summaries = _summary(deb_00631l, "candidate_summaries")
    deb_00713_summary = _summary(deb_00713, "summary")

    variants_00631l = _candidate_names(deb_00631l, "ranking")
    variants_00713 = list(deb_00713_summary)
    confirmation_modes_seen = sorted(
        {
            suffix
            for name in [*variants_00631l, *variants_00713]
            for suffix in ("raw", "2of3", "3of3")
            if name.endswith(suffix) or suffix in name
        }
    )

    best_00631l = deb_00631l_decision.get("best_candidate")
    best_00631l_summary = deb_00631l_summaries.get(best_00631l) if isinstance(deb_00631l_summaries, dict) else {}
    best_00713 = deb_00713_decision.get("best_variant")
    best_00713_summary = deb_00713_summary.get(best_00713) if isinstance(deb_00713_summary, dict) else {}

    checks = {
        "source_is_financial_strategy_paper": False,
        "direct_alpha_or_portfolio_claim_available": False,
        "review_artifact_available": bool(review),
        "component_ablation_available": bool(variants_00631l) and bool(variants_00713),
        "raw_vs_debounced_trigger_tested": {"raw", "2of3", "3of3"}.issubset(set(confirmation_modes_seen)),
        "window_stability_tested": _finite_float(best_00631l_summary.get("ok_folds")) >= 4
        and _finite_float(best_00713_summary.get("non_worse_mdd_windows")) >= 2,
        "strict_00631l_debounce_passed": bool(deb_00631l_decision.get("strict_debounce_gate_passed")),
        "strict_00713_debounce_passed": bool(deb_00713_decision.get("strict_debounce_gate_passed")),
        "domain_randomization_stress_completed": bool(domain_randomization_decision.get("domain_randomization_completed")),
        "strict_domain_randomization_passed": bool(domain_randomization_decision.get("strict_robustness_passed")),
        "pit_actor_input_separation_documented": True,
        "no_latest_strategy_change_requested_by_gate": True,
        "no_golden_change_requested_by_gate": True,
    }
    blockers = [name for name, passed in checks.items() if not bool(passed)]

    governance_imports = [
        {
            "requirement": "component_ablation",
            "status": "implemented_as_readiness_requirement",
            "minimum": "full/raw, no-trigger/debounced, and baseline/fixed variants must be reported.",
        },
        {
            "requirement": "window_or_seed_stability",
            "status": "implemented_as_readiness_requirement",
            "minimum": "A candidate must pass all required windows/folds before promotion review.",
        },
        {
            "requirement": "domain_randomization_stress",
            "status": "added_as_future_required_blocker",
            "minimum": "Cost, delay, slippage, stale data, missing feature, probability perturbation, and capital-size sweeps.",
        },
        {
            "requirement": "pit_actor_privileged_critic_separation",
            "status": "implemented_as_documented_boundary",
            "minimum": "Training diagnostics may use ex-post labels; live actor/signal inputs must remain point-in-time only.",
        },
    ]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2509_02986_ctbc_promotion_readiness_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2509.02986",
            "title": "CTBC: Contact-Triggered Blind Climbing for Wheeled Bipedal Robots with Instruction Learning and Reinforcement Learning",
            "import_scope": "governance_validation_requirements_only",
        },
        "policy": "research_governance_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "changes_ncf_live_gate": False,
        "inputs": {
            "review": _rel(review_path) if review_path.exists() else str(review_path),
            "debounce_00631l": _rel(debounce_00631l_path) if debounce_00631l_path.exists() else str(debounce_00631l_path),
            "debounce_00713": _rel(debounce_00713_path) if debounce_00713_path.exists() else str(debounce_00713_path),
            "domain_randomization": (
                _rel(domain_randomization_path) if domain_randomization_path.exists() else str(domain_randomization_path)
            ),
        },
        "checks": checks,
        "blockers": blockers,
        "evidence": {
            "review_decision": review_decision.get("reason"),
            "00631l_best_candidate": best_00631l,
            "00631l_best_pass_count": best_00631l_summary.get("pass_count") if isinstance(best_00631l_summary, dict) else None,
            "00631l_best_pass_fraction": best_00631l_summary.get("pass_fraction") if isinstance(best_00631l_summary, dict) else None,
            "00631l_strict_passed": deb_00631l_decision.get("strict_debounce_gate_passed"),
            "00713_best_variant": best_00713,
            "00713_average_delta_final_value": (
                best_00713_summary.get("average_delta_final_value") if isinstance(best_00713_summary, dict) else None
            ),
            "00713_strict_passed": deb_00713_decision.get("strict_debounce_gate_passed"),
            "domain_randomization_best_variant": domain_randomization_decision.get("best_variant"),
            "domain_randomization_strict_passed": domain_randomization_decision.get("strict_robustness_passed"),
            "domain_randomization_scenario_count": domain_randomization.get("scenario_count"),
            "confirmation_modes_seen": confirmation_modes_seen,
        },
        "governance_imports": governance_imports,
        "decision": {
            "promotion_allowed": False,
            "decision": "do_not_promote_import_governance_requirements_only",
            "latest_strategy_weight_change_allowed": False,
            "reason": (
                "The CTBC-derived trigger experiments failed promotion criteria, but the paper's "
                "ablation, robustness, and deployment-boundary discipline is useful as future "
                "GroupA++ research governance."
            ),
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2509.02986 CTBC Promotion Readiness Gate",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Promotion allowed: `{report['decision']['promotion_allowed']}`",
        f"- Latest strategy weight change allowed: `{report['decision']['latest_strategy_weight_change_allowed']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "|---|---:|",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"| `{name}` | `{passed}` |")

    lines.extend(["", "## Evidence", ""])
    evidence = report["evidence"]
    lines.extend(
        [
            f"- 00631L best candidate: `{evidence['00631l_best_candidate']}`",
            f"- 00631L pass fraction: `{evidence['00631l_best_pass_fraction']}`",
            f"- 00631L strict passed: `{evidence['00631l_strict_passed']}`",
            f"- 00713 best variant: `{evidence['00713_best_variant']}`",
            f"- 00713 average dFV: `{evidence['00713_average_delta_final_value']}`",
            f"- 00713 strict passed: `{evidence['00713_strict_passed']}`",
            f"- Domain randomization best variant: `{evidence['domain_randomization_best_variant']}`",
            f"- Domain randomization scenario count: `{evidence['domain_randomization_scenario_count']}`",
            f"- Domain randomization strict passed: `{evidence['domain_randomization_strict_passed']}`",
            "",
            "## Governance Imports",
            "",
            "| requirement | status | minimum |",
            "|---|---|---|",
        ]
    )
    for item in report["governance_imports"]:
        lines.append(f"| `{item['requirement']}` | `{item['status']}` | {item['minimum']} |")
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "CTBC 的可導入價值是治理檢查，不是交易訊號。此 gate 明確阻擋策略升級，只保留未來候選策略的驗證要求。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(DEFAULT_REVIEW))
    parser.add_argument("--debounce-00631l", default=str(DEFAULT_DEBOUNCE_00631L))
    parser.add_argument("--debounce-00713", default=str(DEFAULT_DEBOUNCE_00713))
    parser.add_argument("--domain-randomization", default=str(DEFAULT_DOMAIN_RANDOMIZATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_gate(
        _resolve(args.review),
        _resolve(args.debounce_00631l),
        _resolve(args.debounce_00713),
        _resolve(args.domain_randomization),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"decision={report['decision']['decision']}")
    print(f"promotion_allowed={report['decision']['promotion_allowed']}")
    print(f"blockers={','.join(report['blockers'])}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
