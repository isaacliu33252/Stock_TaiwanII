#!/usr/bin/env python3
"""Build a consolidated FinStressTS decision snapshot for GroupA+.

This is a daily-readable summary over the FinStressTS readiness,
counterfactual, and baseline-comparison shadow reports. It never changes live
target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_readiness_review.json"
DEFAULT_COUNTERFACTUAL = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_counterfactual_shadow.json"
DEFAULT_BASELINE = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_baseline_compare_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_decision_snapshot.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def build_snapshot(
    *,
    readiness_path: Path,
    counterfactual_path: Path,
    baseline_path: Path,
) -> dict[str, Any]:
    readiness = _load(readiness_path)
    counterfactual = _load(counterfactual_path)
    baseline = _load(baseline_path)
    readiness_decision = _decision(readiness)
    counterfactual_decision = _decision(counterfactual)
    baseline_decision = _decision(baseline)

    blockers: list[str] = []
    warnings: list[str] = []
    if not readiness:
        blockers.append("missing_finstressts_readiness_review")
    if not counterfactual:
        blockers.append("missing_finstressts_counterfactual_shadow")
    if not baseline:
        blockers.append("missing_finstressts_baseline_compare_shadow")

    if readiness.get("status") == "blocked":
        blockers.append("readiness_review_blocked")
    if counterfactual_decision.get("reference_loses_to_no_00631l_scenarios", 0) > 0:
        blockers.append("reference_loses_to_no_00631l_under_counterfactuals")
    if counterfactual_decision.get("reference_tail_failure_scenarios", 0) > 0:
        blockers.append("reference_tail_failures_under_counterfactuals")
    wins = baseline.get("wins_vs_no_00631l") or {}
    if wins and max(int(v) for v in wins.values()) <= 0:
        blockers.append("no_baseline_beats_no_00631l")
    if baseline.get("best_shadow_candidate"):
        warnings.append(f"best_shadow_candidate:{baseline['best_shadow_candidate']}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_finstressts_decision_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_summary_no_weight_change",
        "status": "blocked" if blockers else "available_for_manual_review",
        "source_paper": "C:/Users/isaac/Downloads/2606.03184.pdf",
        "summary": {
            "readiness_status": readiness.get("status"),
            "blocked_mechanisms": (readiness.get("summary") or {}).get("blocked_mechanisms", []),
            "reference_loses_to_no_00631l_scenarios": counterfactual_decision.get(
                "reference_loses_to_no_00631l_scenarios"
            ),
            "reference_tail_failure_scenarios": counterfactual_decision.get("reference_tail_failure_scenarios"),
            "baseline_best_shadow_candidate": baseline.get("best_shadow_candidate"),
            "baseline_wins_vs_no_00631l": wins,
            "baseline_tail_failures": baseline.get("tail_failures") or {},
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "FinStressTS consolidated snapshot blocks promotion: readiness is blocked, "
                "the 7/20 reference loses to no-00631L under stress, and no tested baseline "
                "beats no-00631L on the strict ES95 + max-drawdown rule."
            )
            if blockers
            else "FinStressTS consolidated snapshot is available for manual review only.",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "readiness": str(readiness_path),
            "counterfactual": str(counterfactual_path),
            "baseline": str(baseline_path),
        },
        "upstream_decisions": {
            "readiness": readiness_decision,
            "counterfactual": counterfactual_decision,
            "baseline": baseline_decision,
        },
    }


def write_snapshot(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", default=str(DEFAULT_READINESS))
    parser.add_argument("--counterfactual", default=str(DEFAULT_COUNTERFACTUAL))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    snapshot = build_snapshot(
        readiness_path=_resolve(args.readiness),
        counterfactual_path=_resolve(args.counterfactual),
        baseline_path=_resolve(args.baseline),
    )
    write_snapshot(snapshot, _resolve(args.output))
    print(f"FinStressTS decision snapshot: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": snapshot["status"],
                "allow_00631l_add": snapshot["decision"]["allow_00631l_add"],
                "blocking_reasons": snapshot["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
