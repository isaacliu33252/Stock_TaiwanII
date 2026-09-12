#!/usr/bin/env python3
"""Research-only blueprint for a 2608.15841-style candidate auxiliary bank."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _readiness_blockers(readiness: dict[str, Any] | None) -> list[str]:
    if not readiness:
        return ["readiness_report_missing"]
    decision = readiness.get("decision") if isinstance(readiness.get("decision"), dict) else {}
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    return [str(item) for item in blockers]


def build_report(readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    blockers = _readiness_blockers(readiness)
    training_allowed = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2608.15841",
            "transferable_use": "small_controlled_gvf_auxiliary_bank_research_spec",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "training_allowed": training_allowed,
        "promotion_allowed": False,
        "decision": {
            "decision": "blocked_until_readiness_gates_pass" if not training_allowed else "research_spec_ready_for_offline_experiment",
            "blockers": blockers,
            "reason": "A learned auxiliary bank must not be trained or promoted while live freshness, policy-lift, churn/cost, or regime-stability gates fail.",
        },
        "candidate_grid": [
            {
                "bank_id": "gvf_bank_16_k10",
                "gvf_question_count": 16,
                "meta_unroll_length": 10,
                "role": "minimum_viable_candidate",
            },
            {
                "bank_id": "gvf_bank_32_k10",
                "gvf_question_count": 32,
                "meta_unroll_length": 10,
                "role": "balanced_default_candidate",
            },
            {
                "bank_id": "gvf_bank_32_k20",
                "gvf_question_count": 32,
                "meta_unroll_length": 20,
                "role": "delayed_credit_candidate",
            },
            {
                "bank_id": "gvf_bank_64_k20",
                "gvf_question_count": 64,
                "meta_unroll_length": 20,
                "role": "upper_complexity_candidate",
            },
        ],
        "admission_tests": [
            "point_in_time_feature_build_no_forward_label_leakage",
            "purged_walk_forward_policy_impact_passed",
            "full_window_delta_final_value_nonnegative_after_costs",
            "delta_sharpe_ratio_nonnegative",
            "delta_max_drawdown_nonnegative",
            "turnover_to_initial_below_cap",
            "temporal_regime_stability_passed",
            "live_feature_freshness_ok",
            "seed_sensitivity_small_enough",
        ],
        "hard_rejections": [
            "standalone_auc_only_without_portfolio_lift",
            "high_turnover_score_churn",
            "recent_or_regime_slice_auc_below_floor",
            "unbounded_auxiliary_question_count",
            "zero_slippage_or_negligible_impact_assumption_for_live_decisions",
        ],
        "implementation_notes": [
            "Reuse existing NCF panel schema for fixed-head comparisons before adding learned GVF tasks.",
            "Start with 16 and 32 questions; 64 is an upper research bound, not a default.",
            "Do not test 128-question banks unless smaller banks pass policy impact after costs.",
            "Keep all outputs under report/group_a_plus/latest until promotion gates pass.",
        ],
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Candidate Auxiliary Bank Blueprint",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Training allowed: `{report['training_allowed']}`",
        f"- Promotion allowed: `{report['promotion_allowed']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Blockers: `{', '.join(report['decision']['blockers']) or 'none'}`",
        "",
        "## Candidate Grid",
        "",
        "| bank | questions | K | role |",
        "|---|---:|---:|---|",
    ]
    for item in report["candidate_grid"]:
        lines.append(
            f"| `{item['bank_id']}` | {item['gvf_question_count']} | {item['meta_unroll_length']} | `{item['role']}` |"
        )
    lines.extend(["", "## Admission Tests", ""])
    lines.extend(f"- `{item}`" for item in report["admission_tests"])
    lines.extend(["", "This blueprint is research-only and does not train a model or change weights."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", default=str(DEFAULT_READINESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(_load_optional_json(_resolve(args.readiness) if args.readiness else None))
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"decision={report['decision']['decision']} training_allowed={report['training_allowed']}")
    print("blockers=" + ",".join(report["decision"]["blockers"]))
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
