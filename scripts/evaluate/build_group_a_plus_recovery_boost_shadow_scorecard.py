#!/usr/bin/env python3
"""Build a GroupA+ recovery-boost shadow scorecard.

This consolidates the clean re-entry replay and five-crisis stress report into
one shadow-only decision artifact. It does not run trading logic and does not
modify production strategy manifests.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_CLEAN_REPORT = PROJECT_ROOT / "results" / "group_a_plus_reentry_accelerator_clean_20260710.json"
DEFAULT_CRISIS_REPORT = PROJECT_ROOT / "results" / "group_a_plus_recovery_boost_five_crises_20260710.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "shadow" / "recovery_boost_age_guard_scorecard_20260711.json"

CANDIDATES: dict[str, dict[str, Any]] = {
    "a2127_recovery_00631l_boost_shadow": {
        "label": "A21.27 recovery boost, no age guard",
        "clean_variant": "recovery_boost_010",
        "crisis_variant": "recovery_boost_010",
        "boost_fraction": 0.10,
        "max_age_days": None,
        "risk_profile": "unbounded_recovery",
    },
    "a2128_recovery_00631l_boost_age_guard_shadow": {
        "label": "A21.28 conservative recovery boost age guard",
        "clean_variant": "recovery_boost_100_age20",
        "crisis_variant": "recovery_boost_010_age20",
        "boost_fraction": 0.10,
        "max_age_days": 20,
        "risk_profile": "conservative_shadow",
    },
    "a2129_recovery_00631l_boost_age_guard_aggressive_shadow": {
        "label": "A21.29 aggressive recovery boost age guard",
        "clean_variant": "recovery_boost_150_age20",
        "crisis_variant": "recovery_boost_015_age20",
        "boost_fraction": 0.15,
        "max_age_days": 20,
        "risk_profile": "aggressive_shadow",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _round(value: Any, digits: int = 6) -> float:
    return round(float(value), digits)


def build_scorecard(clean_report: dict[str, Any], crisis_report: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    clean_summary = clean_report["summary"]
    crisis_summary = crisis_report["summary"]

    for strategy_id, spec in CANDIDATES.items():
        clean_variant = spec["clean_variant"]
        crisis_variant = spec["crisis_variant"]
        clean = clean_summary[clean_variant]
        crisis = crisis_summary[crisis_variant]
        clean_total_delta = float(clean["tuning_sum_delta_final_value"]) + float(clean["oos_sum_delta_final_value"])
        clean_total_sharpe_delta = float(clean["tuning_sum_delta_sharpe_ratio"]) + float(clean["oos_sum_delta_sharpe_ratio"])
        crisis_rebased_delta = float(crisis["rebased_sum_delta_final_value"])
        crisis_rebased_sharpe_delta = float(crisis["rebased_sum_delta_sharpe_ratio"])
        crisis_positive_folds = int(crisis["rebased_positive_final_value_folds"])
        crisis_total_folds = int(crisis["total_folds"])
        age_guarded = spec["max_age_days"] is not None

        crisis_pass = crisis_rebased_delta > 0.0 and crisis_positive_folds >= 3
        clean_pass = clean_total_delta > 0.0 and clean_total_sharpe_delta > 0.0
        production_blockers: list[str] = ["research_only_shadow_candidate"]
        if not age_guarded:
            production_blockers.append("no_recovery_age_guard")
        if not crisis_pass:
            production_blockers.append("five_crisis_rebased_gate_failed")
        if not clean_pass:
            production_blockers.append("clean_reentry_gate_failed")
        if int(clean.get("changed_days", 0)) < 20:
            production_blockers.append("sparse_clean_event_count")

        composite_score = (
            crisis_rebased_delta
            + clean_total_delta
            + 100_000.0 * crisis_rebased_sharpe_delta
            + 25_000.0 * clean_total_sharpe_delta
        )
        rows.append(
            {
                "strategy_id": strategy_id,
                "label": spec["label"],
                "risk_profile": spec["risk_profile"],
                "boost_fraction": spec["boost_fraction"],
                "max_age_days": spec["max_age_days"],
                "clean_variant": clean_variant,
                "crisis_variant": crisis_variant,
                "clean_tuning_delta_final_value": _round(clean["tuning_sum_delta_final_value"], 3),
                "clean_oos_delta_final_value": _round(clean["oos_sum_delta_final_value"], 3),
                "clean_total_delta_final_value": _round(clean_total_delta, 3),
                "clean_total_delta_sharpe_ratio": _round(clean_total_sharpe_delta, 6),
                "clean_changed_days": int(clean.get("changed_days", 0)),
                "crisis_rebased_sum_delta_final_value": _round(crisis_rebased_delta, 3),
                "crisis_rebased_sum_delta_sharpe_ratio": _round(crisis_rebased_sharpe_delta, 6),
                "crisis_rebased_positive_folds": crisis_positive_folds,
                "crisis_total_folds": crisis_total_folds,
                "crisis_total_boosted_recovery_days": int(crisis.get("total_boosted_recovery_days", 0)),
                "age_guarded": age_guarded,
                "clean_gate_pass": clean_pass,
                "five_crisis_gate_pass": crisis_pass,
                "preferred_shadow_eligible": age_guarded and clean_pass and crisis_pass,
                "production_upgrade_pass": False,
                "production_blockers": production_blockers,
                "composite_score": _round(composite_score, 3),
            }
        )

    ranked = sorted(
        rows,
        key=lambda row: (
            row["preferred_shadow_eligible"],
            row["composite_score"],
            row["five_crisis_gate_pass"],
            row["clean_gate_pass"],
            -float(row["boost_fraction"]),
        ),
        reverse=True,
    )
    preferred = ranked[0] if ranked and ranked[0]["preferred_shadow_eligible"] else None
    conservative = next(
        (row for row in ranked if row["strategy_id"] == "a2128_recovery_00631l_boost_age_guard_shadow"),
        None,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_recovery_boost_shadow_scorecard",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "clean_report": str(DEFAULT_CLEAN_REPORT.relative_to(PROJECT_ROOT)),
            "crisis_report": str(DEFAULT_CRISIS_REPORT.relative_to(PROJECT_ROOT)),
        },
        "decision": {
            "production": "do_not_promote",
            "preferred_shadow": preferred["strategy_id"] if preferred else None,
            "conservative_shadow": conservative["strategy_id"] if conservative else None,
            "reason": (
                "A21.29 has the strongest combined clean/crisis score, while A21.28 remains the conservative "
                "parallel shadow. Production stays unchanged because evidence is still research-only and event counts are limited."
            ),
        },
        "ranked_candidates": ranked,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-report", default=str(DEFAULT_CLEAN_REPORT))
    parser.add_argument("--crisis-report", default=str(DEFAULT_CRISIS_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    clean_path = Path(args.clean_report)
    crisis_path = Path(args.crisis_report)
    output = Path(args.output)
    payload = build_scorecard(_load_json(clean_path), _load_json(crisis_path))
    payload["inputs"] = {
        "clean_report": str(clean_path.resolve().relative_to(PROJECT_ROOT)),
        "crisis_report": str(crisis_path.resolve().relative_to(PROJECT_ROOT)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Preferred shadow: {payload['decision']['preferred_shadow']}")
    print(f"Conservative shadow: {payload['decision']['conservative_shadow']}")
    print(f"Production decision: {payload['decision']['production']}")
    print(f"Saved: {output.resolve()}")


if __name__ == "__main__":
    main()
