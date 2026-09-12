#!/usr/bin/env python3
"""Build a research-only current-policy re-evaluation gate for GroupA+.

This wraps the arXiv:2608.17808-inspired diagnostics already produced by the
Riccati/MV shadow and tail-bank review into one explicit promotion decision. It
never changes live strategy weights, golden weights, guards, signals, or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHADOW = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "riccati_mv_shadow.json"
DEFAULT_TAIL_BANK = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_17808_tail_bank_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path)


def _l1_delta(left: dict[str, Any], right: dict[str, Any]) -> float:
    tickers = set(left) | set(right)
    return sum(abs(_float(left.get(ticker)) - _float(right.get(ticker))) for ticker in tickers)


def _tail_bank_status(tail_bank: dict[str, Any] | None) -> dict[str, Any]:
    if tail_bank is None:
        return {
            "available": False,
            "promotion_allowed": False,
            "decision": "missing_tail_bank_review",
            "best_stability_candidate": None,
        }
    decision = tail_bank.get("decision", {}) if isinstance(tail_bank.get("decision"), dict) else {}
    return {
        "available": True,
        "promotion_allowed": bool(decision.get("promotion_allowed")),
        "decision": decision.get("decision"),
        "best_stability_candidate": decision.get("best_stability_candidate"),
        "no_further_auto_tuning_recommended": bool(decision.get("no_further_auto_tuning_recommended")),
    }


def build_report(
    shadow: dict[str, Any],
    *,
    shadow_path: Path,
    tail_bank: dict[str, Any] | None = None,
    tail_bank_path: Path | None = None,
) -> dict[str, Any]:
    re_eval = shadow.get("adjoint_policy_iteration_shadow", {})
    first_pass = re_eval.get("first_pass", {}) if isinstance(re_eval, dict) else {}
    second_pass = re_eval.get("second_pass", {}) if isinstance(re_eval, dict) else {}
    first_cap = first_pass.get("cap_only_weights", {}) if isinstance(first_pass, dict) else {}
    second_cap = second_pass.get("cap_only_weights", {}) if isinstance(second_pass, dict) else {}
    active_set = shadow.get("active_set_stability", {}) if isinstance(shadow.get("active_set_stability"), dict) else {}
    matched_budget = (
        shadow.get("matched_budget_re_evaluation_comparator", {})
        if isinstance(shadow.get("matched_budget_re_evaluation_comparator"), dict)
        else {}
    )
    error_decomp = shadow.get("error_decomposition", {}) if isinstance(shadow.get("error_decomposition"), dict) else {}
    tuned_gate = (
        shadow.get("stability_tuned_re_evaluation_gate", {})
        if isinstance(shadow.get("stability_tuned_re_evaluation_gate"), dict)
        else {}
    )
    risk_state = shadow.get("risk_state", {}) if isinstance(shadow.get("risk_state"), dict) else {}
    tail_status = _tail_bank_status(tail_bank)

    checks = {
        "shadow_report_ok": shadow.get("status") == "ok",
        "research_only_policy": shadow.get("policy") == "research_only_no_weight_change"
        and re_eval.get("policy") == "research_only_no_weight_change",
        "two_pass_stable_within_grid_step": bool(re_eval.get("stable_within_grid_step")),
        "active_set_stable": active_set.get("verdict") == "stable_active_set",
        "matched_budget_supported": bool(matched_budget.get("agrees_with_frozen_budget")),
        "error_certificate_not_blocked": error_decomp.get("verdict") != "diagnostic_blocked",
        "stability_tuned_gate_active": bool(tuned_gate.get("gate_active")),
        "cap_only_reduces_volatility": _float(risk_state.get("cap_only_annualized_volatility_reduction")) > 0.0,
        "tail_bank_available": tail_status["available"],
        "tail_bank_promotion_allowed": tail_status["promotion_allowed"],
    }
    blockers = [name for name, passed in checks.items() if not passed]
    promotion_allowed = not blockers
    decision = "eligible_for_manual_review_not_auto_promote" if promotion_allowed else "keep_shadow_do_not_promote"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_current_policy_re_evaluation_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": shadow.get("as_of"),
        "source_paper": {
            "id": "2608.17808",
            "title": "Self-Consistent Adjoint Policy Iteration for Constrained Dynamic Portfolio Choice",
            "transferable_use": "current_policy_re_evaluation_gate_only",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "inputs": {
            "riccati_mv_shadow": _rel(shadow_path),
            "tail_bank_review": _rel(tail_bank_path) if tail_bank_path else None,
        },
        "decision": {
            "promotion_allowed": promotion_allowed,
            "decision": decision,
            "reason": (
                "All current-policy re-evaluation checks passed; manual review is still required before any change."
                if promotion_allowed
                else "One or more required checks failed, so the 2608.17808 transfer stays shadow-only."
            ),
            "blockers": blockers,
        },
        "checks": checks,
        "evidence": {
            "two_pass_l1_delta_second_minus_first": _l1_delta(first_cap, second_cap),
            "cap_delta_second_minus_first": re_eval.get("cap_delta_second_minus_first"),
            "active_set_verdict": active_set.get("verdict"),
            "active_set_stability_ratio": active_set.get("stability_ratio"),
            "matched_budget_verdict": matched_budget.get("verdict"),
            "frozen_policy_vote_fraction": matched_budget.get("frozen_policy_vote_fraction"),
            "error_decomposition_verdict": error_decomp.get("verdict"),
            "error_decomposition_blockers": error_decomp.get("blockers", []),
            "stability_tuned_gate_active": tuned_gate.get("gate_active"),
            "cap_only_annualized_volatility_reduction": risk_state.get("cap_only_annualized_volatility_reduction"),
            "tail_bank": tail_status,
        },
        "non_goals": [
            "no_live_weight_change",
            "no_golden1_0531_change",
            "no_golden2_0830_change",
            "no_execution_permission_change",
            "no_order_generation",
        ],
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Current-Policy Re-Evaluation Gate",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Promotion allowed: `{report['decision']['promotion_allowed']}`",
        f"- No target-weight change: `{not report['changes_latest_strategy']}`",
        f"- Golden1 unchanged: `{not report['changes_golden1_0531']}`",
        f"- Golden2 unchanged: `{not report['changes_golden2_0830']}`",
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
            f"- Two-pass L1 drift: `{_float(evidence['two_pass_l1_delta_second_minus_first']):.6f}`",
            f"- Active-set verdict: `{evidence['active_set_verdict']}`",
            f"- Matched-budget verdict: `{evidence['matched_budget_verdict']}`",
            f"- Error decomposition verdict: `{evidence['error_decomposition_verdict']}`",
            f"- Tail-bank decision: `{evidence['tail_bank']['decision']}`",
            "",
            "This gate is research-only and does not emit trades or target weights.",
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
    parser.add_argument("--shadow", default=str(DEFAULT_SHADOW))
    parser.add_argument("--tail-bank", default=str(DEFAULT_TAIL_BANK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    shadow_path = Path(args.shadow)
    tail_bank_path = Path(args.tail_bank)
    tail_bank = _load_json(tail_bank_path) if tail_bank_path.exists() else None
    report = build_report(
        _load_json(shadow_path),
        shadow_path=shadow_path,
        tail_bank=tail_bank,
        tail_bank_path=tail_bank_path if tail_bank_path.exists() else None,
    )
    write_outputs(report, Path(args.output), Path(args.markdown))
    print(f"decision={report['decision']['decision']} promotion_allowed={report['decision']['promotion_allowed']}")
    if report["decision"]["blockers"]:
        print("blockers=" + ",".join(report["decision"]["blockers"]))
    print(f"Output: {Path(args.output).resolve()}")
    print(f"Markdown: {Path(args.markdown).resolve()}")


if __name__ == "__main__":
    main()
