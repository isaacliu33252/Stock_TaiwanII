#!/usr/bin/env python3
"""Build a promotion gate for the 00631L/0050 relative re-entry shadow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_ADVISORY = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.json"
DEFAULT_REVIEW = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_candidate_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_promotion_gate.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_promotion_gate.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _check(name: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details or {}}


def _selected_predicted_edge(advisory: dict[str, Any]) -> float:
    selected = _nested(advisory, "model_snapshot", "selected_decision")
    if not isinstance(selected, dict):
        return 0.0
    action = str(selected.get("action") or "KEEP")
    if action == "KEEP":
        return 0.0
    return float(selected.get("predicted_regret") or selected.get("candidate_predicted_regret_before_reliability") or 0.0)


def build_gate(
    *,
    advisory_path: Path,
    review_path: Path,
    min_positive_rate_20d: float = 0.65,
    min_p10_edge_20d: float = 0.0,
    min_predicted_edge: float = 0.0005,
    warning_min_path_p10: float = -0.003,
    warning_min_path_worst: float = -0.006,
    warning_max_cluster_length: int = 10,
) -> dict[str, Any]:
    if not advisory_path.exists() or not review_path.exists():
        return {
            "schema_version": 1,
            "report_type": "00631l_0050_relative_reentry_promotion_gate",
            "status": "unavailable",
            "policy": "shadow_only_no_auto_weight_change",
            "reason": "required_input_missing",
            "inputs": {"advisory": str(advisory_path), "review": str(review_path)},
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
    advisory = _load_json(advisory_path)
    review = _load_json(review_path)
    checks = _nested(advisory, "gates", "checks") or {}
    selected = _nested(advisory, "model_snapshot", "selected_decision") or {}
    trust = _nested(advisory, "gates", "latest_strategy_trust") or {}
    edge20 = _nested(review, "summary", "edge_20d") or {}
    min_path = _nested(review, "summary", "min_path_edge_20d") or {}
    max_cluster_length = int(_nested(review, "summary", "max_cluster_length") or 0)
    action = str(selected.get("action") or "KEEP")
    predicted_edge = _selected_predicted_edge(advisory)

    hard_checks = [
        _check(
            "strategy_trust_not_abstain",
            str(trust.get("trust_level") or "MISSING") != "ABSTAIN",
            {"trust_level": trust.get("trust_level"), "reasons": trust.get("reasons")},
        ),
        _check("risk_mechanism_pass", bool(checks.get("risk_mechanism_pass")), {"value": checks.get("risk_mechanism_pass")}),
        _check(
            "exact_live_date_decision_available",
            bool(checks.get("exact_live_date_decision_available")),
            {"coverage": _nested(advisory, "gates", "coverage")},
        ),
        _check("model_action_shift_00631l_5", action == "SHIFT_00631L_5", {"action": action}),
        _check(
            "model_internal_gates_pass",
            bool(checks.get("model_internal_gates_pass")),
            {
                "action_allowed": selected.get("action_allowed"),
                "reliability_gate_pass": selected.get("reliability_gate_pass"),
                "block_reason": selected.get("block_reason"),
            },
        ),
        _check(
            "edge20_positive_rate_min",
            float(edge20.get("positive_rate") or 0.0) >= float(min_positive_rate_20d),
            {"actual": edge20.get("positive_rate"), "minimum": min_positive_rate_20d},
        ),
        _check(
            "edge20_p10_positive",
            edge20.get("p10") is not None and float(edge20.get("p10")) > float(min_p10_edge_20d),
            {"actual": edge20.get("p10"), "minimum_exclusive": min_p10_edge_20d},
        ),
        _check(
            "predicted_edge_min",
            predicted_edge > float(min_predicted_edge),
            {"actual": predicted_edge, "minimum_exclusive": min_predicted_edge},
        ),
    ]
    warnings = [
        _check(
            "strategy_trust_shadow_only_manual_review",
            str(trust.get("trust_level") or "") == "SHADOW_ONLY",
            {"trust_level": trust.get("trust_level")},
        ),
        _check(
            "min_path_edge_20d_p10_warning",
            min_path.get("p10") is not None and float(min_path.get("p10")) < float(warning_min_path_p10),
            {"actual": min_path.get("p10"), "warning_below": warning_min_path_p10},
        ),
        _check(
            "min_path_edge_20d_worst_warning",
            min_path.get("worst") is not None and float(min_path.get("worst")) < float(warning_min_path_worst),
            {"actual": min_path.get("worst"), "warning_below": warning_min_path_worst},
        ),
        _check(
            "candidate_cluster_length_warning",
            max_cluster_length > int(warning_max_cluster_length),
            {"actual": max_cluster_length, "warning_above": warning_max_cluster_length},
        ),
    ]
    failed = [row["name"] for row in hard_checks if not row["passed"]]
    active_warnings = [row["name"] for row in warnings if row["passed"]]
    trust_level = str(trust.get("trust_level") or "")
    promote_to_advisory = not failed and trust_level == "TRUST"
    manual_review_candidate = (
        not failed
        and trust_level == "SHADOW_ONLY"
        and bool(checks.get("risk_mechanism_pass"))
        and bool(checks.get("exact_live_date_decision_available"))
        and action == "SHIFT_00631L_5"
        and bool(checks.get("model_internal_gates_pass"))
    )
    return {
        "schema_version": 1,
        "report_type": "00631l_0050_relative_reentry_promotion_gate",
        "status": "available",
        "policy": "shadow_only_no_auto_weight_change",
        "active_allocation_impact": "none",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {"advisory": str(advisory_path), "review": str(review_path)},
        "promote_to_advisory": bool(promote_to_advisory),
        "manual_review_candidate": bool(manual_review_candidate),
        "blocked_by": failed,
        "warnings": active_warnings,
        "hard_checks": hard_checks,
        "warning_checks": warnings,
        "latest_decision": selected,
        "review_summary": _nested(review, "summary"),
        "recommendation": (
            "promote_to_advisory_candidate"
            if promote_to_advisory
            else "manual_review_candidate_only"
            if manual_review_candidate
            else "keep_shadow_only"
        ),
    }


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Relative Reentry Promotion Gate",
        "",
        f"- recommendation: `{payload.get('recommendation')}`",
        f"- promote_to_advisory: `{payload.get('promote_to_advisory')}`",
        f"- manual_review_candidate: `{payload.get('manual_review_candidate')}`",
        f"- blocked_by: `{payload.get('blocked_by')}`",
        f"- warnings: `{payload.get('warnings')}`",
        "",
        "This gate is shadow-only and has no live allocation impact.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory", default=str(DEFAULT_ADVISORY))
    parser.add_argument("--review", default=str(DEFAULT_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    payload = build_gate(advisory_path=_resolve(args.advisory), review_path=_resolve(args.review))
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(build_markdown(payload), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Markdown: {output_md}")
    print(f"Recommendation: {payload.get('recommendation')}")


if __name__ == "__main__":
    main()
